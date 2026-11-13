"""Exact CP-SAT model of the rich VRP for small instances.

One ``AddCircuit`` per vehicle unit (Laborie & Rogerie's optional-node
circuit): a self-loop on a node means the unit skips it, a self-loop on the
depot means the unit stays home. Because every unit has its own circuit,
heterogeneous capacity, cost, skills, travel profile and shift are plain
per-unit data. Time and load propagate along chosen arcs; pickup before
delivery, ride limits and the shift cap are linear constraints guarded by
the visit literal. Identical units of one type are ordered (a unit is used
only if the previous one is) to break symmetry.

Times are scaled to integers and travel is rounded *up*, so every model
solution is feasible in real numbers; ``OPTIMAL`` means optimal for that
conservative integer model. The plan's real cost always comes from
:func:`mobiroute.vrp.verify.verify`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, Route, Solution
from mobiroute.vrp.verify import Verdict, verify


@dataclass(frozen=True, slots=True)
class ExactRun:
    solution: Solution
    verdict: Verdict
    status: str
    model_objective: float | None
    model_bound: float | None
    seconds: float
    units: int
    arcs: int


def solve_exact(
    inst: Instance,
    *,
    time_limit: float = 30.0,
    workers: int = 8,
    scale: int = 100,
    max_units_per_type: int | None = None,
) -> ExactRun:
    from ortools.sat.python import cp_model

    n_req = inst.n_requests
    dims = len(inst.dimensions)
    units: list[int] = []
    for t, vt in enumerate(inst.vehicle_types):
        cap_units = min(vt.count, max(1, n_req))
        if max_units_per_type is not None:
            cap_units = min(cap_units, max_units_per_type)
        units += [t] * cap_units
    service_nodes = [n for r in inst.requests for n in r.nodes]
    model: Any = cp_model.CpModel()
    visit: dict[tuple[int, int], Any] = {}
    used: list[Any] = []
    arcs_total = 0
    objective_terms: list[Any] = []
    starts: list[Any] = []

    def up(x: float) -> int:
        return math.ceil(x * scale - 1e-9)

    def down(x: float) -> int:
        return math.floor(x * scale + 1e-9)

    finite = [nd.latest for nd in inst.nodes if math.isfinite(nd.latest)]
    finite += [vt.shift_end for vt in inst.vehicle_types if math.isfinite(vt.shift_end)]
    horizon = down(max(finite)) if finite else 10**9
    succ: dict[int, dict[tuple[int, int], Any]] = {}
    for k, t in enumerate(units):
        vt = inst.vehicle_types[t]
        prof = inst.profiles[vt.profile]
        allowed = [
            n
            for n in service_nodes
            if inst.requests[inst.request_of(n)].skills <= vt.skills
            and all(
                q <= c + 1e-9
                for q, c in zip(inst.requests[inst.request_of(n)].demand, vt.capacity, strict=True)
            )
        ]
        # Local circuit: 0 is the depot (start for outgoing arcs, end for incoming).
        local = [-1, *allowed]
        arcs: list[tuple[int, int, Any]] = []
        lits: dict[tuple[int, int], Any] = {}
        u_used = model.new_bool_var(f"used{k}")
        used.append(u_used)
        arcs.append((0, 0, ~u_used))
        t_start = model.new_int_var(
            up(max(inst.nodes[vt.start_depot].earliest, vt.shift_start)),
            min(horizon, down(min(inst.nodes[vt.start_depot].latest, vt.shift_end))),
            f"ts{k}",
        )
        t_end = model.new_int_var(
            up(inst.nodes[vt.end_depot].earliest),
            min(horizon, down(min(inst.nodes[vt.end_depot].latest, vt.shift_end))),
            f"te{k}",
        )
        starts.append(t_start)
        times: dict[int, Any] = {}
        loads: dict[int, list[Any]] = {}
        for a, node in enumerate(local):
            if a == 0:
                continue
            nd = inst.nodes[node]
            v_lit = model.new_bool_var(f"v{k}_{node}")
            visit[(k, node)] = v_lit
            arcs.append((a, a, ~v_lit))
            model.add_implication(v_lit, u_used)
            hi = min(horizon, down(nd.latest)) if math.isfinite(nd.latest) else horizon
            times[node] = model.new_int_var(
                up(nd.earliest), max(up(nd.earliest), hi), f"t{k}_{node}"
            )
            loads[node] = [
                model.new_int_var(0, down(vt.capacity[d]), f"q{k}_{node}_{d}") for d in range(dims)
            ]
        start_load = [
            sum(
                up(inst.requests[inst.request_of(n)].demand[d]) * visit[(k, n)]
                for n in allowed
                if inst.requests[inst.request_of(n)].pickup is None
            )
            for d in range(dims)
        ]

        def delta(node: int, d: int) -> int:
            req = inst.requests[inst.request_of(node)]
            q = up(req.demand[d])
            return q if node == req.pickup else -q

        for a, na in enumerate(local):
            for b, nb in enumerate(local):
                if a == b:
                    continue
                src = vt.start_depot if a == 0 else na
                dst = vt.end_depot if b == 0 else nb
                if a == 0 and b == 0:
                    continue
                lit = model.new_bool_var(f"x{k}_{a}_{b}")
                arcs.append((a, b, lit))
                lits[(a, b)] = lit
                gap = up(inst.nodes[src].service + prof.time[src][dst])
                tail_time = t_start if a == 0 else times[na]
                head_time = t_end if b == 0 else times[nb]
                model.add(head_time >= tail_time + gap).only_enforce_if(lit)
                if b != 0:
                    for d in range(dims):
                        base = start_load[d] if a == 0 else loads[na][d]
                        model.add(loads[nb][d] == base + delta(nb, d)).only_enforce_if(lit)
                arc_cost = vt.cost_per_distance * prof.distance[src][dst] + vt.cost_per_time * (
                    prof.time[src][dst] + (inst.nodes[dst].service if b != 0 else 0.0)
                )
                objective_terms.append(round(arc_cost * scale) * lit)
        model.add_circuit(arcs)
        arcs_total += len(arcs)
        succ[k] = lits
        for d in range(dims):
            model.add(start_load[d] <= down(vt.capacity[d]))
        if vt.max_duration is not None:
            model.add(t_end - t_start <= down(vt.max_duration))
        for req in inst.requests:
            if not req.is_pair:
                continue
            assert req.pickup is not None and req.delivery is not None
            if (k, req.pickup) not in visit:
                continue
            vp, vd = visit[(k, req.pickup)], visit[(k, req.delivery)]
            model.add(vp == vd)
            gap = up(inst.nodes[req.pickup].service + prof.time[req.pickup][req.delivery])
            model.add(times[req.delivery] >= times[req.pickup] + gap).only_enforce_if(vp)
            if req.max_ride is not None:
                # B[d] - (B[p] + s_p) <= L, i.e. B[d] - B[p] <= L + s_p.
                limit = down(req.max_ride + inst.nodes[req.pickup].service)
                model.add(times[req.delivery] - times[req.pickup] <= limit).only_enforce_if(vp)
        objective_terms.append(round((vt.fixed_cost + inst.vehicle_penalty) * scale) * u_used)
    # Symmetry: identical units of one type are used in order.
    for k in range(1, len(units)):
        if units[k] == units[k - 1]:
            model.add_implication(used[k], used[k - 1])
    for r, req in enumerate(inst.requests):
        first = req.nodes[0]
        lits_r = [visit[(k, first)] for k in range(len(units)) if (k, first) in visit]
        served = sum(lits_r) if lits_r else 0
        if req.penalty is None:
            model.add(served == 1)
        else:
            model.add(served <= 1)
            miss = model.new_bool_var(f"miss{r}")
            model.add(served + miss == 1)
            objective_terms.append(round(min(req.penalty, MUST_SERVE_PENALTY) * scale) * miss)
    model.minimize(sum(objective_terms))
    solver: Any = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = int(workers)
    solver.parameters.random_seed = 0
    began = time.perf_counter()
    status = solver.solve(model)
    elapsed = time.perf_counter() - began
    routes: list[Route] = []
    objective = bound = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        objective = solver.objective_value / scale
        bound = solver.best_objective_bound / scale
        for k, t in enumerate(units):
            if not solver.value(used[k]):
                continue
            nxt = {a: b for (a, b), lit in succ[k].items() if solver.value(lit)}
            vt = inst.vehicle_types[t]
            allowed_local = [-1] + [n for n in service_nodes if (k, n) in visit]
            nodes: list[int] = []
            cur = nxt.get(0)
            while cur is not None and cur != 0 and len(nodes) <= len(service_nodes):
                nodes.append(allowed_local[cur])
                cur = nxt.get(cur)
            if nodes:
                routes.append(Route(t, nodes))
            del vt
    served = {inst.request_of(n) for r in routes for n in r.nodes}
    sol = Solution(routes, set(range(n_req)) - served)
    return ExactRun(
        solution=sol,
        verdict=verify(inst, sol),
        status=str(solver.status_name(status)),
        model_objective=objective,
        model_bound=bound,
        seconds=round(elapsed, 3),
        units=len(units),
        arcs=arcs_total,
    )
