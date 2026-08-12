"""Tiny CP-SAT DARP: one vehicle sequence with pairing — for small instances."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.models import ReasonCode, SolutionStatus, StopType
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TimeWindow,
)
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan


def solve_cpsat(problem: DayProblem, time_limit_s: float = 10.0) -> PlanningResult:
    """
    Exact-ish assignment for tiny fleets: assign each trip to at most one vehicle,
    order = earliest_pickup, prove infeasibility per vehicle via OR-Tools CP-SAT
    on start times with pairing and capacity.

    For larger instances, falls back to greedy and labels HEURISTIC (never OPTIMAL).
    """
    if len(problem.requests) > 40 or len(problem.vehicles) > 12:
        res = solve_greedy(problem)
        res.solver_config = {
            "name": "CPSAT_FALLBACK_GREEDY",
            "reason": "instance_too_large_for_tiny_cpsat",
        }
        res.solution_type = "CPSAT_FALLBACK_GREEDY"
        # Must not claim OPTIMAL
        if res.status == SolutionStatus.FEASIBLE.value:
            res.status = SolutionStatus.HEURISTIC_FEASIBLE.value
        return res

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        res = solve_greedy(problem)
        res.status = SolutionStatus.ERROR.value
        res.solver_config = {"error": "ortools_missing"}
        return res

    # Multi-vehicle: binary assign trip->vehicle + sequential timing per vehicle
    model = cp_model.CpModel()
    trips = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    vehicles = problem.vehicles
    horizon = max(v.shift_end for v in vehicles) + 120

    assign = {}
    for t in trips:
        for v in vehicles:
            assign[(t.id, v.id)] = model.NewBoolVar(f"a_{t.id[:8]}_{v.id[:8]}")
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) <= 1)

    # Precompute travel
    travel = problem.travel
    pickup_arr = {}
    drop_arr = {}
    for t in trips:
        for v in vehicles:
            pickup_arr[(t.id, v.id)] = model.NewIntVar(0, horizon, f"pu_{t.id[:8]}")
            drop_arr[(t.id, v.id)] = model.NewIntVar(0, horizon, f"do_{t.id[:8]}")

    for t in trips:
        for v in vehicles:
            a = assign[(t.id, v.id)]
            pu = pickup_arr[(t.id, v.id)]
            do = drop_arr[(t.id, v.id)]
            # if not assigned, times free but we force loose
            model.Add(pu >= t.earliest_pickup).OnlyEnforceIf(a)
            model.Add(pu <= t.latest_pickup).OnlyEnforceIf(a)
            tt = travel.travel(t.pickup_zone, t.dropoff_zone)
            model.Add(do >= pu + t.boarding_duration + tt).OnlyEnforceIf(a)
            model.Add(do - (pu + t.boarding_duration) <= t.max_ride_time).OnlyEnforceIf(a)
            if t.appointment_end is not None:
                model.Add(do <= t.appointment_end).OnlyEnforceIf(a)
            # accessibility hard filter: forbid assign
            seats = 1 + t.companion_count
            if seats > v.passenger_capacity:
                model.Add(a == 0)
            if t.wheelchair_requirement.value != "NONE" and v.wheelchair_capacity < 1:
                model.Add(a == 0)
            if t.needs_lift and not v.lift_available:
                model.Add(a == 0)
            if t.needs_ramp and not (v.ramp_available or v.lift_available):
                model.Add(a == 0)
            # depot reachability to pickup
            tt0 = travel.travel(v.depot_id, t.pickup_zone)
            model.Add(pu >= v.shift_start + tt0).OnlyEnforceIf(a)
            model.Add(
                do + t.alighting_duration + travel.travel(t.dropoff_zone, v.depot_id) <= v.shift_end
            ).OnlyEnforceIf(a)

    # Disjunctive sequencing per vehicle (pairwise)
    for v in vehicles:
        for i, t1 in enumerate(trips):
            for t2 in trips[i + 1 :]:
                a1 = assign[(t1.id, v.id)]
                a2 = assign[(t2.id, v.id)]
                both = model.NewBoolVar(f"both_{t1.id[:6]}_{t2.id[:6]}_{v.id[:6]}")
                model.AddBoolAnd([a1, a2]).OnlyEnforceIf(both)
                model.AddBoolOr([a1.Not(), a2.Not(), both])
                # order: t1 before t2 or reverse — finish drop before next pickup
                b = model.NewBoolVar(f"ord_{t1.id[:6]}_{t2.id[:6]}")
                tt12 = travel.travel(t1.dropoff_zone, t2.pickup_zone)
                tt21 = travel.travel(t2.dropoff_zone, t1.pickup_zone)
                model.Add(
                    pickup_arr[(t2.id, v.id)]
                    >= drop_arr[(t1.id, v.id)] + t1.alighting_duration + tt12
                ).OnlyEnforceIf([both, b])
                model.Add(
                    pickup_arr[(t1.id, v.id)]
                    >= drop_arr[(t2.id, v.id)] + t2.alighting_duration + tt21
                ).OnlyEnforceIf([both, b.Not()])

    # Maximize served
    served_vars = []
    for t in trips:
        s = model.NewBoolVar(f"srv_{t.id[:8]}")
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) == 1).OnlyEnforceIf(s)
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) == 0).OnlyEnforceIf(s.Not())
        served_vars.append(s)
    model.Maximize(sum(served_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1  # determinism
    status = solver.Solve(model)

    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}
    by_vehicle: dict[str, list] = {v.id: [] for v in vehicles}

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for t in trips:
            assigned_v = None
            for v in vehicles:
                if solver.Value(assign[(t.id, v.id)]) == 1:
                    assigned_v = v
                    break
            if assigned_v is None:
                rejected.append(
                    RejectedTrip(
                        trip_id=t.id,
                        reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value,
                    )
                )
                reasons[t.id] = ReasonCode.TIME_WINDOW_CONFLICT.value
            else:
                served.append(t.id)
                reasons[t.id] = ReasonCode.ACCEPTED.value
                pu_t = solver.Value(pickup_arr[(t.id, assigned_v.id)])
                do_t = solver.Value(drop_arr[(t.id, assigned_v.id)])
                by_vehicle[assigned_v.id].append((pu_t, t, do_t))
    else:
        # infeasible or unknown — reject all with reason
        for t in trips:
            rejected.append(
                RejectedTrip(trip_id=t.id, reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)
            )
            reasons[t.id] = ReasonCode.TIME_WINDOW_CONFLICT.value

    route_plans: list[RoutePlan] = []
    dmap = {d.depot_id: d.id for d in problem.drivers}
    for v in vehicles:
        items = sorted(by_vehicle[v.id], key=lambda x: x[0])
        if not items:
            continue
        stops: list[Stop] = []
        arr: dict[str, int] = {}
        dep: dict[str, int] = {}
        ride: dict[str, int] = {}
        for pu_t, t, do_t in items:
            seats = 1 + t.companion_count
            w = 0 if t.wheelchair_requirement.value == "NONE" else 1
            pu = Stop(
                id=f"{t.id}:PU",
                trip_id=t.id,
                stop_type=StopType.PICKUP,
                location=t.pickup_zone,
                service_duration=t.boarding_duration,
                time_window=TimeWindow(earliest=t.earliest_pickup, latest=t.latest_pickup),
                load_delta=seats,
                wheelchair_load_delta=w,
            )
            do = Stop(
                id=f"{t.id}:DO",
                trip_id=t.id,
                stop_type=StopType.DROPOFF,
                location=t.dropoff_zone,
                service_duration=t.alighting_duration,
                load_delta=-seats,
                wheelchair_load_delta=-w,
            )
            stops.extend([pu, do])
            arr[pu.id] = pu_t
            dep[pu.id] = pu_t + t.boarding_duration
            arr[do.id] = do_t
            dep[do.id] = do_t + t.alighting_duration
            ride[t.id] = do_t - (pu_t + t.boarding_duration)
        route_plans.append(
            RoutePlan(
                vehicle_id=v.id,
                driver_id=dmap.get(v.depot_id, problem.drivers[0].id if problem.drivers else None),
                ordered_stops=stops,
                passenger_assignments=[t.id for _, t, _ in items],
                arrival_times=arr,
                departure_times=dep,
                ride_times=ride,
            )
        )

    sol_status = SolutionStatus.NOT_VERIFIED
    if status == cp_model.OPTIMAL:
        sol_status = SolutionStatus.OPTIMAL if not rejected else SolutionStatus.PARTIAL
    elif status == cp_model.FEASIBLE:
        sol_status = SolutionStatus.FEASIBLE if not rejected else SolutionStatus.PARTIAL

    result = PlanningResult(
        status=sol_status.value,
        solution_type="CPSAT_TINY",
        verified_feasible=False,
        served_requests=sorted(served),
        rejected_requests=rejected,
        route_plans=route_plans,
        objective_values={
            "served": float(len(served)),
            "rejected": float(len(rejected)),
            "cp_status": float(status),
        },
        reason_codes=reasons,
        input_hash=fingerprint(problem.model_dump(mode="json")),
        config_hash=fingerprint({"solver": "CPSAT_TINY", "tl": time_limit_s}),
        solver_config={
            "name": "CPSAT_TINY",
            "time_limit_s": time_limit_s,
            "workers": 1,
            "ortools_status": int(status),
        },
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
    )
    report = check_plan(problem, result)
    result.verified_feasible = report.feasible
    if not report.feasible and sol_status in (
        SolutionStatus.OPTIMAL,
        SolutionStatus.FEASIBLE,
        SolutionStatus.PARTIAL,
    ):
        result.status = SolutionStatus.NOT_VERIFIED.value
        result.objective_values["violations"] = float(len(report.violations))
    result.fairness_metrics = compute_fairness(problem, result)
    return result
