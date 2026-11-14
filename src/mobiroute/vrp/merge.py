"""Merge two routes onto one vehicle, possibly of another type.

Insertion keeps the vehicle type of a route, and :class:`~mobiroute.vrp.fleet.TypeAssigner`
re-types finished routes one by one. Neither can replace two small routes
by one route on a larger vehicle: every single step on the way is worse
(the first order moved leaves two half-empty routes, both paying their fee).
This operator makes the whole step at once:

* for a pair of routes ``(A, B)`` and a vehicle type ``k`` that may carry
  every order of both (skills, capacity of each order, a spare unit once
  ``A`` and ``B`` are gone), start from ``A`` re-timed on ``k`` and insert
  the orders of ``B`` one by one, cheapest first, with the same exact
  feasibility tests as the repair step;
* the merge is worth it when the merged route costs less than ``A`` and
  ``B`` together; the best merge over all pairs and types is applied, and
  the scan repeats until no merge saves money;
* the types of the result are then re-picked by the transportation model.

On instances with multi-trip vehicles the same scan also *chains* trips:
``A + reload + B`` on A's type keeps every trip's loads, so only the day's
timing is checked, and B may be a hired vehicle's route moved onto an own
vehicle's second trip (:meth:`RouteMerger._chains`). Routes that already
reload keep their type and are only chained.

Pairs are pruned before any insertion: the combined peak load must fit the
largest admissible type, and only the ``neighbours`` routes nearest to a
route (by the distance between their stop centroids) are tried with it.
The operator is deterministic and uses the repair kernel's insertion when
it is available, so both backends produce identical plans.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from mobiroute.vrp.fleet import TypeAssigner, _peak, route_money
from mobiroute.vrp.insertion import EPS, Compiled, apply_insertion
from mobiroute.vrp.solution import Route, Solution

#: ``(vehicle type, current nodes, request) -> (delta cost, i, j)`` or ``None``.
InsertFn = Callable[[int, list[int], int], "tuple[float, int, int] | None"]
#: ``(vehicle type, nodes) -> feasible``, timing checked exactly.
RouteCheck = Callable[[int, list[int]], bool]


class RouteMerger:
    """Best-improvement merging of route pairs (see module docstring)."""

    def __init__(
        self,
        c: Compiled,
        insert: InsertFn,
        route_ok: RouteCheck,
        assigner: TypeAssigner,
        *,
        neighbours: int = 4,
    ) -> None:
        self.c = c
        self.insert = insert
        self.route_ok = route_ok
        self.assigner = assigner
        self.neighbours = neighbours
        inst = c.inst
        self.x = [nd.x for nd in inst.nodes]
        self.y = [nd.y for nd in inst.nodes]
        #: Merges already found infeasible or useless, by (type, A, B).
        self._dead: set[tuple[int, tuple[int, ...], tuple[int, ...]]] = set()

    # -- pruning ---------------------------------------------------------
    def _centroid(self, nodes: Sequence[int]) -> tuple[float, float]:
        n = len(nodes)
        return (sum(self.x[v] for v in nodes) / n, sum(self.y[v] for v in nodes) / n)

    def _candidate_pairs(self, routes: list[Route]) -> list[tuple[int, int]]:
        # Routes with reload stops keep their type and are only chained.
        plain = [k for k, r in enumerate(routes) if not self._reloads(r.nodes)]
        cents = {k: self._centroid(routes[k].nodes) for k in plain}
        pairs: set[tuple[int, int]] = set()
        for a in plain:
            ax, ay = cents[a]
            near = sorted(
                (math.hypot(ax - cents[b][0], ay - cents[b][1]), b) for b in plain if b != a
            )
            for _, b in near[: self.neighbours]:
                pairs.add((min(a, b), max(a, b)))
        return sorted(pairs)

    def _reloads(self, nodes: Sequence[int]) -> int:
        c = self.c
        return sum(1 for n in nodes if c.reload_of[n] >= 0) if c.has_reload else 0

    # -- chaining trips ----------------------------------------------------
    def _chains(
        self, routes: list[Route], money: list[float]
    ) -> tuple[float, int, int, int, list[int]] | None:
        """Best day ``A + reload + B`` (or ``B + reload + A``) on A's multi-trip type.

        B may come from another type if its orders are allowed on A's type
        and its peak load fits: each trip keeps its own loads, so capacity
        holds per trip, and the exact check covers windows, the shift cap and
        the rest rule over the whole day. The day saves B's vehicle (its fee
        and penalty) and pays the reload stop.
        """
        c = self.c
        used_stops = {n for r in routes for n in r.nodes if c.reload_of[n] >= 0}
        best: tuple[float, int, int, int, list[int]] | None = None
        for a_idx, a in enumerate(routes):
            t = a.vehicle_type
            if c.max_reloads[t] == 0:
                continue
            free = [n for n in c.reload_nodes[t] if n not in used_stops]
            if not free:
                continue
            stop = free[0]
            for b_idx, b in enumerate(routes):
                if b_idx == a_idx:
                    continue
                if b.vehicle_type != t:
                    if self._reloads(b.nodes):
                        continue  # B's reload stops belong to its own type
                    if any(t not in c.allowed[r] for r in c.requests_of(b.nodes)):
                        continue
                    peak = _peak(c, b.nodes)
                    if any(peak[d] > c.cap[t][d] + EPS for d in range(c.dims)):
                        continue
                if self._reloads(a.nodes) + self._reloads(b.nodes) + 1 > c.max_reloads[t]:
                    continue
                for first, second in ((a, b), (b, a)):
                    key = (t, (*first.nodes, -1), tuple(second.nodes))
                    if key in self._dead:
                        continue
                    nodes = [*first.nodes, stop, *second.nodes]
                    if not self.route_ok(t, nodes):
                        self._dead.add(key)
                        continue
                    saving = money[a_idx] + money[b_idx] - route_money(c, t, nodes)
                    if saving <= 1e-9:
                        self._dead.add(key)
                        continue
                    cand = (-saving, min(a_idx, b_idx), max(a_idx, b_idx), t, nodes)
                    if best is None or cand[:4] < best[:4]:
                        best = cand
        return best

    def _types_for(self, a: Route, b: Route, used: list[int]) -> list[int]:
        c = self.c
        requests = c.requests_of(a.nodes) | c.requests_of(b.nodes)
        allowed = set(range(c.n_types))
        for r in requests:
            allowed &= set(c.allowed[r])
        peak_a = _peak(c, a.nodes)
        peak_b = _peak(c, b.nodes)
        out = []
        for t in sorted(allowed):
            free = c.count[t] - used[t] + (a.vehicle_type == t) + (b.vehicle_type == t)
            if free < 1:
                continue
            # The merged peak is at least each route's own peak.
            if any(max(peak_a[d], peak_b[d]) > c.cap[t][d] + EPS for d in range(c.dims)):
                continue
            out.append(t)
        return out

    # -- one merge -------------------------------------------------------
    def _merge(self, t: int, base: Route, other: Route) -> list[int] | None:
        """Orders of ``other`` inserted into ``base`` re-timed on type ``t``."""
        c = self.c
        nodes = list(base.nodes)
        if t != base.vehicle_type and not self.route_ok(t, nodes):
            return None
        todo = sorted(c.requests_of(other.nodes))
        while todo:
            best: tuple[float, int, int, int] | None = None
            for r in todo:
                found = self.insert(t, nodes, r)
                if found is not None and (best is None or (found[0], r) < (best[0], best[1])):
                    best = (found[0], r, found[1], found[2])
            if best is None:
                return None
            _, r, i, j = best
            nodes = apply_insertion(c, nodes, r, i, j)
            todo.remove(r)
        return nodes

    def improve(self, sol: Solution) -> Solution:
        c = self.c
        routes = [r.copy() for r in sol.routes if r.nodes]
        if len(routes) < 2:
            return sol
        changed = False
        while len(routes) >= 2:
            used = [0] * c.n_types
            for r in routes:
                used[r.vehicle_type] += 1
            money = [route_money(c, r.vehicle_type, r.nodes) for r in routes]
            best: tuple[float, int, int, int, list[int]] | None = None
            if c.has_reload:
                best = self._chains(routes, money)
            for a_idx, b_idx in self._candidate_pairs(routes):
                a, b = routes[a_idx], routes[b_idx]
                # Insert the shorter route into the longer one.
                big, small = (a, b) if len(a.nodes) >= len(b.nodes) else (b, a)
                for t in self._types_for(a, b, used):
                    key = (t, tuple(big.nodes), tuple(small.nodes))
                    if key in self._dead:
                        continue
                    merged = self._merge(t, big, small)
                    if merged is None:
                        self._dead.add(key)
                        continue
                    saving = money[a_idx] + money[b_idx] - route_money(c, t, merged)
                    if saving <= 1e-9:
                        self._dead.add(key)
                        continue
                    cand = (-saving, a_idx, b_idx, t, merged)
                    if best is None or cand[:4] < best[:4]:
                        best = cand
            if best is None:
                break
            _, a_idx, b_idx, t, merged = best
            routes = [r for k, r in enumerate(routes) if k not in (a_idx, b_idx)]
            routes.append(Route(t, merged))
            changed = True
        if len(self._dead) > 100_000:
            self._dead.clear()
        if not changed:
            return sol
        return self.assigner.improve(Solution(routes, set(sol.unassigned)))
