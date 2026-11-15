"""Serve a left-out order by re-sequencing a short route exactly.

Destroy and repair puts one order at a time into routes whose other stops
keep their order. Some better plans need two changes at once: the new pickup
and delivery go in and a stop already on the route moves. On a 14-order day
of the warm-start study ALNS stayed 16% above the optimum for exactly this
reason (seed 2004: a collection had to move ahead of a new pair).

For every order left out of a plan and every route short enough, this module
searches all orders of the route's stops plus the new ones that put each
pickup before its delivery, depth first. Windows (with the earliest
departure, a lower bound on every arrival), capacity per dimension and the
cost already spent prune the tree; a complete order is kept only if
:func:`mobiroute.vrp.insertion.route_exact` accepts it, so ride limits, the
shift cap and drivers' breaks hold as everywhere else. The order joins the
route that gains most against its price of refusal (the must-serve price for
a mandatory order).

The search is exact up to ``MAX_EXPANSIONS`` tree nodes per route and order;
past that it keeps the best order found. Days with reload stops are left as
they are: their trips have structure this search does not model.
"""

from __future__ import annotations

from collections.abc import Sequence

from mobiroute.vrp.fleet import route_money
from mobiroute.vrp.insertion import EPS, Compiled, route_exact
from mobiroute.vrp.solution import Route, Solution

#: Stops on a route after the insertion; the tree grows with their factorial.
MAX_STOPS = 9
#: Tree nodes searched per route and order before the best so far is kept.
MAX_EXPANSIONS = 20_000


class Reseater:
    """Puts left-out orders into short routes, re-sequencing them exactly."""

    def __init__(self, c: Compiled) -> None:
        self.c = c
        self.enabled = not c.has_reload

    def improve(self, sol: Solution) -> Solution:
        """``sol`` with every left-out order that a short route can take cheaper than refusing.

        Routes that take no order keep their order of stops: re-sequencing
        them all was measured too, and it moved the search elsewhere as often
        as it helped.
        """
        if not self.enabled or not sol.unassigned:
            return sol
        c = self.c
        cur = sol
        for r in sorted(cur.unassigned):
            new = [n for n in (c.pick[r], c.deliv[r]) if n >= 0]
            best: tuple[float, int, list[int]] | None = None
            for ri, route in enumerate(cur.routes):
                t = route.vehicle_type
                if not route.nodes or t not in c.allowed[r]:
                    continue
                if len(route.nodes) + len(new) > MAX_STOPS:
                    continue
                found = self.best_order(t, [*route.nodes, *new])
                if found is None:
                    continue
                gain = c.penalty[r] - (found[0] - route_money(c, t, route.nodes))
                if gain > 1e-9 and (best is None or gain > best[0]):
                    best = (gain, ri, found[1])
            if best is not None:
                _, ri, nodes = best
                routes = [rt.copy() for rt in cur.routes]
                routes[ri] = Route(routes[ri].vehicle_type, nodes)
                cur = Solution(routes, set(cur.unassigned) - {r})
        return cur

    def best_order(self, t: int, stops: Sequence[int]) -> tuple[float, list[int]] | None:
        """Cheapest feasible order of ``stops`` on type ``t``: ``(money, nodes)``."""
        c = self.c
        time, cost = c.time[t], c.cost[t]
        e, lat, s = c.e, c.l, c.s
        cap, dims = c.cap[t], c.dims
        end, end_lim = c.end[t], c.end_lim[t]
        todo = sorted(stops)
        # Deliveries from the depot ride from the start; pickups add their load.
        load0 = [0.0] * dims
        for n in todo:
            r = c.node_req[n]
            if c.pick[r] < 0:
                load0 = [a + b for a, b in zip(load0, c.demand[r], strict=True)]
        if any(load0[d] > cap[d] + EPS for d in range(dims)):
            return None
        best_money = float("inf")
        best_nodes: list[int] | None = None
        expansions = 0
        order: list[int] = []
        placed: set[int] = set()

        def dfs(at: int, clock: float, load: list[float], spent: float) -> None:
            nonlocal best_money, best_nodes, expansions
            if len(order) == len(todo):
                if clock + s[at] + time[at][end] > end_lim + EPS:
                    return
                money = route_money(c, t, order)
                if money < best_money - 1e-9 and route_exact(c, t, order):
                    best_money, best_nodes = money, list(order)
                return
            for v in todo:
                if v in placed or expansions >= MAX_EXPANSIONS:
                    continue
                r = c.node_req[v]
                if v == c.deliv[r] and c.pick[r] >= 0 and c.pick[r] not in placed:
                    continue  # a pair's delivery waits for its pickup
                arrive = clock + s[at] + time[at][v]
                if arrive < e[v]:
                    arrive = e[v]
                if arrive > lat[v] + EPS:
                    continue
                q = c.demand[r]
                if v == c.pick[r]:
                    step = [a + b for a, b in zip(load, q, strict=True)]
                else:
                    step = [a - b for a, b in zip(load, q, strict=True)]
                if any(step[d] > cap[d] + EPS for d in range(dims)):
                    continue
                if spent + cost[at][v] >= best_money - 1e-9:
                    continue  # every route money includes its arcs
                expansions += 1
                order.append(v)
                placed.add(v)
                dfs(v, arrive, step, spent + cost[at][v])
                placed.discard(v)
                order.pop()

        dfs(c.start[t], c.t_min[t], load0, c.open_cost[t])
        return None if best_nodes is None else (best_money, best_nodes)
