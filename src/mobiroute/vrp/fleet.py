"""Best vehicle type for every route: a transportation problem.

Insertion builds routes one order at a time, so a vehicle whose fixed fee is
charged up front is never attractive for a single order, even when the whole
route would be cheaper on it. After each repair the engine therefore re-picks
the vehicle type of every finished route:

* a route may move to any type whose capacity, skills, profile, shift and cap
  keep it feasible (checked exactly, schedule included);
* type ``k`` offers at most ``count_k`` units;
* minimise the sum of route costs.

That is a transportation problem; it is solved exactly as a min-cost flow
(source → route → type → sink) by successive shortest paths with
Bellman-Ford on the residual graph. Options per route are cached by its
stop sequence, because ALNS leaves most routes untouched between
iterations, and the flow runs only when some route has a cheaper type.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from itertools import pairwise

from mobiroute.vrp.insertion import EPS, Compiled
from mobiroute.vrp.solution import Route, Solution

RouteCheck = Callable[[int, list[int]], bool]


def route_money(c: Compiled, t: int, nodes: Sequence[int]) -> float:
    """What the search pays for this route on type ``t`` (fee, arcs, service)."""
    cost = c.cost[t]
    seq = [c.start[t], *nodes, c.end[t]]
    total = c.open_cost[t]
    for a, b in pairwise(seq):
        total += cost[a][b]
    return total + c.svc_rate[t] * sum(c.s[n] for n in nodes)


def _peak(c: Compiled, nodes: Sequence[int]) -> list[float]:
    present = set(nodes)
    load = [0.0] * c.dims
    for n in nodes:
        r = c.node_req[n]
        if n == c.deliv[r] and c.pick[r] not in present:
            for d in range(c.dims):
                load[d] += c.demand[r][d]
    peak = list(load)
    for n in nodes:
        r = c.node_req[n]
        sign = 1.0 if n == c.pick[r] else -1.0
        for d in range(c.dims):
            load[d] += sign * c.demand[r][d]
            peak[d] = max(peak[d], load[d])
    return peak


def min_cost_assignment(
    options: Sequence[dict[int, float]], capacity: Sequence[int]
) -> list[int] | None:
    """Assign every row one column, column ``k`` at most ``capacity[k]`` times.

    Successive shortest paths: push one unit at a time along the cheapest
    source-to-sink path of the residual graph (Bellman-Ford, since reverse
    arcs carry negative costs). Returns the column per row, or ``None`` if no
    complete assignment exists.
    """
    rows = len(options)
    cols = len(capacity)
    source, sink = rows + cols, rows + cols + 1
    n = rows + cols + 2
    # Arc lists: to, residual capacity, cost, index of the reverse arc.
    graph: list[list[list[float]]] = [[] for _ in range(n)]

    def add(u: int, v: int, cap: int, cost: float) -> None:
        graph[u].append([v, cap, cost, len(graph[v])])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1])

    for r in range(rows):
        add(source, r, 1, 0.0)
        for k, cost in sorted(options[r].items()):
            add(r, rows + k, 1, cost)
    for k in range(cols):
        if capacity[k] > 0:
            add(rows + k, sink, capacity[k], 0.0)
    for _ in range(rows):
        dist = [math.inf] * n
        prev: list[tuple[int, int] | None] = [None] * n
        dist[source] = 0.0
        for _ in range(n - 1):
            changed = False
            for u in range(n):
                if dist[u] == math.inf:
                    continue
                for idx, (v, cap, cost, _rev) in enumerate(graph[u]):
                    if cap > 0 and dist[u] + cost < dist[int(v)] - 1e-12:
                        dist[int(v)] = dist[u] + cost
                        prev[int(v)] = (u, idx)
                        changed = True
            if not changed:
                break
        if dist[sink] == math.inf:
            return None
        v = sink
        while v != source:
            step = prev[v]
            assert step is not None
            u, idx = step
            arc = graph[u][idx]
            arc[1] -= 1
            graph[v][int(arc[3])][1] += 1
            v = u
    out = [-1] * rows
    for r in range(rows):
        for v, cap, _cost, _rev in graph[r]:
            if rows <= v < rows + cols and cap == 0:
                out[r] = int(v) - rows
    return out


class TypeAssigner:
    """Re-picks vehicle types of a solution's routes (see module docstring)."""

    def __init__(self, c: Compiled, route_ok: RouteCheck) -> None:
        self.c = c
        self.route_ok = route_ok
        self.cache: dict[tuple[int, ...], dict[int, float]] = {}

    def options(self, route: Route) -> dict[int, float]:
        key = tuple(route.nodes)
        cached = self.cache.get(key)
        if cached is not None and route.vehicle_type in cached:
            return cached
        c = self.c
        requests = {c.node_req[n] for n in route.nodes}
        allowed = set(range(c.n_types))
        for r in requests:
            allowed &= set(c.allowed[r])
        peak = _peak(c, route.nodes)
        found: dict[int, float] = {}
        for t in sorted(allowed | {route.vehicle_type}):
            if t != route.vehicle_type:
                if any(peak[d] > c.cap[t][d] + EPS for d in range(c.dims)):
                    continue
                if not self.route_ok(t, route.nodes):
                    continue
            found[t] = route_money(c, t, route.nodes)
        if len(self.cache) > 200_000:
            self.cache.clear()
        self.cache[key] = found
        return found

    def improve(self, sol: Solution) -> Solution:
        c = self.c
        if c.n_types == 1:
            return sol
        routes = [r for r in sol.routes if r.nodes]
        if not routes:
            return sol
        opts = [self.options(r) for r in routes]
        cheaper = (
            min(o.values()) < o[r.vehicle_type] - 1e-9 for o, r in zip(opts, routes, strict=True)
        )
        if not any(cheaper):
            return sol
        choice = min_cost_assignment(opts, c.count)
        if choice is None:
            return sol
        before = sum(o[r.vehicle_type] for o, r in zip(opts, routes, strict=True))
        after = sum(o[k] for o, k in zip(opts, choice, strict=True))
        if after >= before - 1e-9:
            return sol
        moved = [Route(k, list(r.nodes)) for r, k in zip(routes, choice, strict=True)]
        return Solution(moved, set(sol.unassigned))
