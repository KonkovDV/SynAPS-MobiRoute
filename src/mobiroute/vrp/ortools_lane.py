"""OR-Tools Routing baseline on the same model, judged by the same verifier.

The configuration is the common industrial one for pickup and delivery:
``PARALLEL_CHEAPEST_INSERTION`` for the first solution and
``GUIDED_LOCAL_SEARCH`` with a wall-clock limit. Vehicle types become
individual vehicles with their own arc-cost evaluator, fixed cost, capacity
dimensions, travel-time transit and span cap; skills restrict
``VehicleVar``; ride limits are cumul constraints; every order sits in a
disjunction with a large penalty so the solver always returns a plan.

Routing works in integers, so times are scaled by ``scale`` and rounded *up*
(any plan it returns is on time in real numbers too), costs are rounded to
the nearest unit. The plan is then re-timed and re-priced by
:func:`mobiroute.vrp.verify.verify`; the solver's own objective is reported
but never trusted.

``soft_windows=True`` mirrors a common production setup: late arrivals are
allowed and priced per minute instead of forbidden. Such plans usually fail
the verifier; :mod:`mobiroute.vrp.lateness` then says by how much.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import Verdict, verify

#: Penalty (in unscaled cost units) for dropping an order in the disjunction.
DROP_PENALTY = 1e7


@dataclass(frozen=True, slots=True)
class OrtoolsRun:
    solution: Solution
    verdict: Verdict
    status: str
    solver_objective: float | None
    seconds: float
    first_solution: str
    metaheuristic: str
    time_limit: float
    soft_windows: bool
    ortools_version: str


def _version() -> str:
    import ortools

    return str(getattr(ortools, "__version__", "unknown"))


def solve_ortools(
    inst: Instance,
    *,
    time_limit: float = 10.0,
    scale: int = 100,
    soft_windows: bool = False,
    late_penalty_per_min: float = 100.0,
    first_solution: str = "PARALLEL_CHEAPEST_INSERTION",
    metaheuristic: str = "GUIDED_LOCAL_SEARCH",
    max_units_per_type: int | None = None,
) -> OrtoolsRun:
    """Solve ``inst`` with OR-Tools Routing and verify the plan independently."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    pickups_only = any(r.pickup is not None and r.delivery is None for r in inst.requests)
    deliveries_only = any(r.pickup is None and r.delivery is not None for r in inst.requests)
    if pickups_only and deliveries_only:
        raise ValueError("ORTOOLS_LANE_MIXED_DEPOT_LOADS_UNSUPPORTED")
    n = inst.n_nodes
    unit_type: list[int] = []
    for t, vt in enumerate(inst.vehicle_types):
        units = vt.count if max_units_per_type is None else min(vt.count, max_units_per_type)
        units = min(units, max(1, inst.n_requests))
        unit_type += [t] * units
    if not unit_type:
        raise ValueError("ORTOOLS_LANE_NO_VEHICLES")
    starts = [inst.vehicle_types[t].start_depot for t in unit_type]
    ends = [inst.vehicle_types[t].end_depot for t in unit_type]
    manager: Any = pywrapcp.RoutingIndexManager(n, len(unit_type), starts, ends)
    routing: Any = pywrapcp.RoutingModel(manager)
    solver: Any = routing.solver()

    service = [nd.service for nd in inst.nodes]

    def node(index: int) -> int:
        return int(manager.IndexToNode(index))

    # One cost and one time evaluator per vehicle type (callbacks must stay alive).
    keep: list[Any] = []
    time_cb: dict[int, int] = {}
    cost_cb: dict[int, int] = {}
    for t, vt in enumerate(inst.vehicle_types):
        profile = inst.profiles[vt.profile]
        tm = [
            [math.ceil((service[a] + profile.time[a][b]) * scale - 1e-9) for b in range(n)]
            for a in range(n)
        ]
        cm = [
            [
                round(
                    (
                        vt.cost_per_distance * profile.distance[a][b]
                        + vt.cost_per_time * (profile.time[a][b] + service[b])
                    )
                    * scale
                )
                for b in range(n)
            ]
            for a in range(n)
        ]

        def time_fn(i: int, j: int, tm: list[list[int]] = tm) -> int:
            return tm[node(i)][node(j)]

        def cost_fn(i: int, j: int, cm: list[list[int]] = cm) -> int:
            return cm[node(i)][node(j)]

        keep += [time_fn, cost_fn]
        time_cb[t] = routing.RegisterTransitCallback(time_fn)
        cost_cb[t] = routing.RegisterTransitCallback(cost_fn)
    for v, t in enumerate(unit_type):
        vt = inst.vehicle_types[t]
        routing.SetArcCostEvaluatorOfVehicle(cost_cb[t], v)
        routing.SetFixedCostOfVehicle(round((vt.fixed_cost + inst.vehicle_penalty) * scale), v)

    finite = [nd.latest for nd in inst.nodes if math.isfinite(nd.latest)]
    finite += [vt.shift_end for vt in inst.vehicle_types if math.isfinite(vt.shift_end)]
    horizon = math.ceil((max(finite) if finite else 1e5) * scale) + 1
    routing.AddDimensionWithVehicleTransits(
        [time_cb[t] for t in unit_type], horizon, horizon, False, "time"
    )
    time_dim: Any = routing.GetDimensionOrDie("time")

    for d, _name in enumerate(inst.dimensions):
        deltas = [0] * n
        for req in inst.requests:
            q = round(req.demand[d] * scale)
            if req.pickup is not None:
                deltas[req.pickup] = q
            if req.delivery is not None:
                deltas[req.delivery] = -q

        def demand_fn(i: int, deltas: list[int] = deltas) -> int:
            return deltas[node(i)]

        keep.append(demand_fn)
        cb = routing.RegisterUnaryTransitCallback(demand_fn)
        caps = [math.floor(inst.vehicle_types[t].capacity[d] * scale + 1e-9) for t in unit_type]
        routing.AddDimensionWithVehicleCapacity(cb, 0, caps, False, f"load{d}")
        dim: Any = routing.GetDimensionOrDie(f"load{d}")
        for v in range(len(unit_type)):
            if deliveries_only:
                # Deliveries are loaded at the depot: the route ends empty, so the
                # start load equals the route's deliveries exactly.
                dim.CumulVar(routing.End(v)).SetValue(0)
            else:
                dim.CumulVar(routing.Start(v)).SetValue(0)

    for k, nd in enumerate(inst.nodes):
        if inst.request_of(k) < 0:
            continue
        index = manager.NodeToIndex(k)
        lo = math.ceil(nd.earliest * scale - 1e-9)
        if math.isfinite(nd.latest):
            hi = math.floor(nd.latest * scale + 1e-9)
            if soft_windows:
                time_dim.CumulVar(index).SetRange(lo, horizon)
                time_dim.SetCumulVarSoftUpperBound(index, hi, round(late_penalty_per_min))
            else:
                time_dim.CumulVar(index).SetRange(lo, hi)
        else:
            time_dim.CumulVar(index).SetMin(lo)
    for v, t in enumerate(unit_type):
        vt = inst.vehicle_types[t]
        s_node, e_node = inst.nodes[vt.start_depot], inst.nodes[vt.end_depot]
        start_lo = math.ceil(max(s_node.earliest, vt.shift_start) * scale - 1e-9)
        start_hi = math.floor(min(s_node.latest, vt.shift_end) * scale + 1e-9)
        end_hi = math.floor(min(e_node.latest, vt.shift_end) * scale + 1e-9)
        time_dim.CumulVar(routing.Start(v)).SetRange(start_lo, min(start_hi, horizon))
        time_dim.CumulVar(routing.End(v)).SetRange(
            math.ceil(e_node.earliest * scale - 1e-9), min(end_hi, horizon)
        )
        if vt.max_duration is not None:
            time_dim.SetSpanUpperBoundForVehicle(math.floor(vt.max_duration * scale + 1e-9), v)
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(v)))
        routing.AddVariableMaximizedByFinalizer(time_dim.CumulVar(routing.Start(v)))

    penalty = round(DROP_PENALTY * scale)
    for req in inst.requests:
        allowed = [
            v
            for v, t in enumerate(unit_type)
            if req.skills <= inst.vehicle_types[t].skills
            and all(
                q <= c + 1e-9
                for q, c in zip(req.demand, inst.vehicle_types[t].capacity, strict=True)
            )
        ]
        indices = [manager.NodeToIndex(k) for k in req.nodes]
        for index in indices:
            if len(allowed) < len(unit_type):
                # -1 keeps the "unperformed" value for the disjunction.
                routing.VehicleVar(index).SetValues([-1, *allowed])
            routing.AddDisjunction([index], penalty)
        if req.is_pair:
            p_idx, d_idx = indices
            routing.AddPickupAndDelivery(p_idx, d_idx)
            solver.Add(routing.VehicleVar(p_idx) == routing.VehicleVar(d_idx))
            solver.Add(routing.ActiveVar(p_idx) == routing.ActiveVar(d_idx))
            solver.Add(time_dim.CumulVar(p_idx) <= time_dim.CumulVar(d_idx))
            if req.max_ride is not None:
                assert req.pickup is not None
                limit = math.floor((req.max_ride + service[req.pickup]) * scale + 1e-9)
                solver.Add(time_dim.CumulVar(d_idx) - time_dim.CumulVar(p_idx) <= limit)

    params: Any = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = getattr(
        routing_enums_pb2.FirstSolutionStrategy, first_solution
    )
    params.local_search_metaheuristic = getattr(
        routing_enums_pb2.LocalSearchMetaheuristic, metaheuristic
    )
    params.time_limit.FromMilliseconds(int(time_limit * 1000))
    began = time.perf_counter()
    assignment: Any = routing.SolveWithParameters(params)
    elapsed = time.perf_counter() - began
    status_names = {0: "NOT_SOLVED", 1: "SUCCESS", 2: "FAIL", 3: "FAIL_TIMEOUT", 4: "INVALID"}
    status = status_names.get(int(routing.status()), str(routing.status()))
    routes: list[Route] = []
    objective: float | None = None
    served: set[int] = set()
    if assignment is not None:
        objective = assignment.ObjectiveValue() / scale
        for v, t in enumerate(unit_type):
            index = routing.Start(v)
            nodes: list[int] = []
            while not routing.IsEnd(index):
                k = node(index)
                if inst.request_of(k) >= 0:
                    nodes.append(k)
                    served.add(inst.request_of(k))
                index = assignment.Value(routing.NextVar(index))
            if nodes:
                routes.append(Route(t, nodes))
    sol = Solution(routes, set(range(inst.n_requests)) - served)
    return OrtoolsRun(
        solution=sol,
        verdict=verify(inst, sol),
        status=status,
        solver_objective=objective,
        seconds=round(elapsed, 3),
        first_solution=first_solution,
        metaheuristic=metaheuristic,
        time_limit=time_limit,
        soft_windows=soft_windows,
        ortools_version=_version(),
    )
