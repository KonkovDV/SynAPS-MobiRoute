"""How late a fixed stop sequence must run when its windows cannot all be met.

Soft time windows are the usual production answer to delays: allow lateness,
charge for it. The risk is that nobody sees how late the plan really is.
This module keeps windows hard in the plan and prices a delay explicitly:

* :func:`min_max_lateness` - the smallest ``delta`` such that opening every
  latest-start bound by ``delta`` makes the sequence schedulable. A uniform
  relaxation keeps the system a set of difference constraints, so each probe
  is one Bellman-Ford run and ``delta`` is found by bisection.
* :func:`min_total_lateness` - the schedule minimising the sum (optionally
  weighted) of minutes late over all stops, as a linear programme solved by
  GLOP. Ride limits and the shift cap stay hard. The constraint matrix is the
  incidence matrix of the constraint graph, so the dual is a min-cost flow
  and the LP optimum is exact, not an approximation.

Both return ``None`` when no amount of lateness helps (a ride limit or the
shift cap is already violated by pure driving time).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from mobiroute.vrp.model import Instance
from mobiroute.vrp.schedule import route_arcs, shortest_paths


@dataclass(frozen=True, slots=True)
class LatePlan:
    """A schedule that may start stops after their windows close."""

    start_times: tuple[float, ...]
    lateness: tuple[float, ...]
    total: float
    worst: float
    late_stops: tuple[int, ...]


def _feasible_with(inst: Instance, t: int, nodes: Sequence[int], delta: float) -> bool:
    z, arcs = route_arcs(inst, t, nodes, slack=delta)
    dist, _ = shortest_paths(z + 1, arcs, z, to_root=True)
    return dist is not None


def min_max_lateness(
    inst: Instance, t: int, nodes: Sequence[int], *, tol: float = 1e-4
) -> float | None:
    """Smallest uniform window extension that makes the sequence schedulable."""
    if _feasible_with(inst, t, nodes, 0.0):
        return 0.0
    # Start from the lateness of the as-early-as-possible schedule; ride or
    # shift limits may need more, so double until feasible or give up.
    vt = inst.vehicle_types[t]
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *nodes, vt.end_depot]
    clock = max(inst.nodes[seq[0]].earliest, vt.shift_start)
    worst = 0.0
    for a, b in pairwise(seq):
        clock = max(clock + inst.nodes[a].service + time[a][b], inst.nodes[b].earliest)
        limit = min(inst.nodes[b].latest, vt.shift_end) if b == seq[-1] else inst.nodes[b].latest
        worst = max(worst, clock - limit)
    hi = max(1.0, worst + 1.0)
    while not _feasible_with(inst, t, nodes, hi):
        hi *= 2.0
        if hi > 1e7:
            return None
    lo = 0.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if _feasible_with(inst, t, nodes, mid):
            hi = mid
        else:
            lo = mid
    return round(hi, 4)


def min_total_lateness(
    inst: Instance,
    t: int,
    nodes: Sequence[int],
    *,
    weights: Mapping[int, float] | None = None,
) -> LatePlan | None:
    """Schedule with the least (weighted) total lateness; windows' opening stays hard."""
    from ortools.linear_solver import pywraplp

    vt = inst.vehicle_types[t]
    profile = inst.profiles[vt.profile]
    seq = [vt.start_depot, *nodes, vt.end_depot]
    m = len(seq)
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:  # pragma: no cover - GLOP ships with OR-Tools
        raise RuntimeError("GLOP_UNAVAILABLE")
    inf = solver.infinity()
    start = []
    late = []
    for k, node in enumerate(seq):
        info = inst.nodes[node]
        lo = info.earliest
        hi = info.latest
        if k == 0:
            lo, hi = max(lo, vt.shift_start), min(hi, vt.shift_end)
        elif k == m - 1:
            hi = min(hi, vt.shift_end)
        b = solver.NumVar(lo, inf, f"b{k}")
        lam = solver.NumVar(0.0, inf, f"late{k}")
        if math.isfinite(hi):
            solver.Add(b <= hi + lam)
        start.append(b)
        late.append(lam)
    for k in range(m - 1):
        a, b_node = seq[k], seq[k + 1]
        solver.Add(start[k + 1] >= start[k] + inst.nodes[a].service + profile.time[a][b_node])
    where = {node: k for k, node in enumerate(seq) if 0 < k < m - 1}
    for k in range(1, m - 1):
        req = inst.requests[inst.request_of(seq[k])]
        if req.max_ride is not None and req.pickup == seq[k] and req.delivery in where:
            kd = where[req.delivery]
            solver.Add(start[kd] - start[k] <= req.max_ride + inst.nodes[seq[k]].service)
    if vt.max_duration is not None:
        solver.Add(start[m - 1] - start[0] <= vt.max_duration)
    w = weights or {}
    solver.Minimize(sum(w.get(seq[k], 1.0) * late[k] for k in range(m)))
    if solver.Solve() != solver.OPTIMAL:
        return None
    values = tuple(round(lam.solution_value(), 6) for lam in late)
    return LatePlan(
        start_times=tuple(round(b.solution_value(), 6) for b in start),
        lateness=values,
        total=round(sum(values), 6),
        worst=max(values) if values else 0.0,
        late_stops=tuple(seq[k] for k, v in enumerate(values) if v > 1e-6),
    )
