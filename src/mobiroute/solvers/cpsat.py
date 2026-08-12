"""Tiny sequential CP-SAT DARP. OPTIMAL only if OR-Tools OPTIMAL and notary pass."""

from __future__ import annotations

from typing import Any

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.constraints import detour_limit, earliest_alight_time, pickup_service_minutes
from mobiroute.domain.driver_assignment import driver_compatible
from mobiroute.domain.models import ReasonCode, SolutionStatus, StopType
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TimeWindow,
    TripRequest,
)
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import accessibility_compatible, trip_quota_remaining
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


def solve_cpsat(problem: DayProblem, time_limit_s: float = 10.0) -> PlanningResult:
    """
    Sequential (non-pooling) assignment for tiny fleets.

    Each assigned trip is a PU→DO pair; two trips on one vehicle cannot overlap.
    This is **not** an optimum of the pooling DARP. Label OPTIMAL only when
    OR-Tools status is OPTIMAL **and** the independent notary accepts the plan.
    """
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    if len(active) > 40 or len(problem.vehicles) > 12:
        res = solve_greedy(problem)
        status = res.status
        if status in {SolutionStatus.OPTIMAL.value, SolutionStatus.FEASIBLE.value}:
            status = SolutionStatus.HEURISTIC_FEASIBLE.value
        return res.model_copy(
            update={
                "solution_type": "CPSAT_FALLBACK_GREEDY",
                "status": status,
                "solver_config": {
                    **res.solver_config,
                    "name": "CPSAT_FALLBACK_GREEDY",
                    "reason": "instance_too_large_for_tiny_cpsat",
                    "proven_optimal": False,
                },
            }
        )

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        res = solve_greedy(problem)
        return res.model_copy(
            update={
                "status": SolutionStatus.ERROR.value,
                "solver_config": {**res.solver_config, "error": "ortools_missing"},
            }
        )

    model = cp_model.CpModel()
    trips = list(active)
    vehicles = problem.vehicles
    drivers = list(problem.drivers)
    horizon = max((v.shift_end for v in vehicles), default=0) + 120
    travel = problem.travel

    assign: dict[tuple[str, str], Any] = {}
    for t in trips:
        for v in vehicles:
            assign[(t.id, v.id)] = model.NewBoolVar(f"a_{t.id[:8]}_{v.id[:8]}")
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) <= 1)
        if t.frozen:
            model.Add(sum(assign[(t.id, v.id)] for v in vehicles) == 1)

    pickup_arr: dict[tuple[str, str], Any] = {}
    drop_arr: dict[tuple[str, str], Any] = {}
    via_arr: dict[tuple[str, str], Any] = {}
    for t in trips:
        for v in vehicles:
            pickup_arr[(t.id, v.id)] = model.NewIntVar(0, horizon, f"pu_{t.id[:8]}_{v.id[:8]}")
            drop_arr[(t.id, v.id)] = model.NewIntVar(0, horizon, f"do_{t.id[:8]}_{v.id[:8]}")

    for t in trips:
        for v in vehicles:
            a = assign[(t.id, v.id)]
            pu = pickup_arr[(t.id, v.id)]
            do = drop_arr[(t.id, v.id)]
            acc = accessibility_compatible(v, t)
            if acc is not None:
                model.Add(a == 0)
                continue
            model.Add(pu >= t.earliest_pickup).OnlyEnforceIf(a)
            model.Add(pu <= t.latest_pickup).OnlyEnforceIf(a)
            model.Add(pu - t.earliest_pickup <= t.max_wait_time).OnlyEnforceIf(a)
            board_eff = pickup_service_minutes(t.boarding_duration)
            if t.via_zone:
                via_arr[(t.id, v.id)] = model.NewIntVar(0, horizon, f"via_{t.id[:8]}_{v.id[:8]}")
                via_t = via_arr[(t.id, v.id)]
                tt_pv = travel.travel(t.pickup_zone, t.via_zone)
                tt_vd = travel.travel(t.via_zone, t.dropoff_zone)
                model.Add(via_t >= pu + board_eff + tt_pv).OnlyEnforceIf(a)
                model.Add(do >= via_t + t.via_service_duration + tt_vd).OnlyEnforceIf(a)
                direct = tt_pv + t.via_service_duration + tt_vd
            else:
                direct = travel.travel(t.pickup_zone, t.dropoff_zone)
                model.Add(do >= pu + board_eff + direct).OnlyEnforceIf(a)
            model.Add(do - (pu + board_eff) <= t.max_ride_time).OnlyEnforceIf(a)
            cap = detour_limit(direct, t.max_detour_ratio)
            model.Add(do - (pu + board_eff) <= cap).OnlyEnforceIf(a)
            early_do = earliest_alight_time(t.appointment_start)
            if early_do is not None:
                model.Add(do >= early_do).OnlyEnforceIf(a)
            if t.appointment_end is not None:
                model.Add(do <= t.appointment_end).OnlyEnforceIf(a)
            qleft = trip_quota_remaining(problem, t)
            if qleft is not None:
                if qleft <= 0:
                    model.Add(a == 0)
                else:
                    model.Add(do - (pu + board_eff) <= qleft).OnlyEnforceIf(a)
            tt0 = travel.travel(v.depot_id, t.pickup_zone)
            model.Add(pu >= v.shift_start + tt0).OnlyEnforceIf(a)
            model.Add(
                do + t.alighting_duration + travel.travel(t.dropoff_zone, v.depot_id) <= v.shift_end
            ).OnlyEnforceIf(a)
            for u0, u1 in v.unavailable_intervals:
                # trip service cannot overlap [u0, u1]
                before = model.NewBoolVar(f"u_b_{t.id[:6]}_{v.id[:6]}_{u0}")
                model.Add(do + t.alighting_duration <= u0).OnlyEnforceIf([a, before])
                model.Add(pu >= u1).OnlyEnforceIf([a, before.Not()])

    for v in vehicles:
        for i, t1 in enumerate(trips):
            for t2 in trips[i + 1 :]:
                a1 = assign[(t1.id, v.id)]
                a2 = assign[(t2.id, v.id)]
                both = model.NewBoolVar(f"both_{t1.id[:6]}_{t2.id[:6]}_{v.id[:6]}")
                model.AddBoolAnd([a1, a2]).OnlyEnforceIf(both)
                model.AddBoolOr([a1.Not(), a2.Not(), both])
                b = model.NewBoolVar(f"ord_{t1.id[:6]}_{t2.id[:6]}_{v.id[:6]}")
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

    dv: dict[tuple[str, str], Any] = {}
    for d in drivers:
        for v in vehicles:
            dv[(d.id, v.id)] = model.NewBoolVar(f"dv_{d.id[:8]}_{v.id[:8]}")
            if not driver_compatible(d, v, needs_accessibility=False):
                model.Add(dv[(d.id, v.id)] == 0)
    for d in drivers:
        model.Add(sum(dv[(d.id, v.id)] for v in vehicles) <= 1)
    for v in vehicles:
        used = model.NewBoolVar(f"used_{v.id[:8]}")
        trip_sum = sum(assign[(t.id, v.id)] for t in trips)
        model.Add(trip_sum >= 1).OnlyEnforceIf(used)
        model.Add(trip_sum == 0).OnlyEnforceIf(used.Not())
        model.Add(sum(dv[(d.id, v.id)] for d in drivers) == 1).OnlyEnforceIf(used)
        model.Add(sum(dv[(d.id, v.id)] for d in drivers) == 0).OnlyEnforceIf(used.Not())

    for t in trips:
        if not t.needs_boarding_assistance:
            continue
        for v in vehicles:
            for d in drivers:
                if not d.accessibility_training:
                    model.Add(assign[(t.id, v.id)] + dv[(d.id, v.id)] <= 1)

    for t in trips:
        for v in vehicles:
            for d in drivers:
                both = model.NewBoolVar(f"tdv_{t.id[:6]}_{d.id[:6]}_{v.id[:6]}")
                model.AddBoolAnd([assign[(t.id, v.id)], dv[(d.id, v.id)]]).OnlyEnforceIf(both)
                model.AddBoolOr([assign[(t.id, v.id)].Not(), dv[(d.id, v.id)].Not(), both])
                tt0 = travel.travel(v.depot_id, t.pickup_zone)
                model.Add(pickup_arr[(t.id, v.id)] >= d.shift_start + tt0).OnlyEnforceIf(both)
                model.Add(
                    drop_arr[(t.id, v.id)]
                    + t.alighting_duration
                    + travel.travel(t.dropoff_zone, v.depot_id)
                    <= d.shift_end
                ).OnlyEnforceIf(both)

    served_vars = []
    for t in trips:
        s = model.NewBoolVar(f"srv_{t.id[:8]}")
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) == 1).OnlyEnforceIf(s)
        model.Add(sum(assign[(t.id, v.id)] for v in vehicles) == 0).OnlyEnforceIf(s.Not())
        served_vars.append(s)
    model.Maximize(sum(served_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)

    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}
    by_vehicle: dict[str, list[tuple[int, TripRequest, int]]] = {v.id: [] for v in vehicles}
    vehicle_driver: dict[str, str | None] = {v.id: None for v in vehicles}

    ortools_optimal = status == cp_model.OPTIMAL
    ortools_ok = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    if ortools_ok:
        for v in vehicles:
            for d in drivers:
                if solver.Value(dv[(d.id, v.id)]) == 1:
                    vehicle_driver[v.id] = d.id
        for t in trips:
            assigned_v = None
            for v in vehicles:
                if solver.Value(assign[(t.id, v.id)]) == 1:
                    assigned_v = v
                    break
            if assigned_v is None:
                code = non_empty_reason(diagnose_rejection(problem, t))
                rejected.append(RejectedTrip(trip_id=t.id, reason_code=code))
                reasons[t.id] = code
            else:
                served.append(t.id)
                reasons[t.id] = ReasonCode.ACCEPTED.value
                pu_t = solver.Value(pickup_arr[(t.id, assigned_v.id)])
                do_t = solver.Value(drop_arr[(t.id, assigned_v.id)])
                by_vehicle[assigned_v.id].append((pu_t, t, do_t))
    else:
        for t in trips:
            code = non_empty_reason(diagnose_rejection(problem, t))
            rejected.append(RejectedTrip(trip_id=t.id, reason_code=code))
            reasons[t.id] = code

    route_plans: list[RoutePlan] = []
    for v in vehicles:
        items = sorted(by_vehicle[v.id], key=lambda x: x[0])
        if not items:
            continue
        stops: list[Stop] = []
        arr: dict[str, int] = {}
        dep: dict[str, int] = {}
        ride: dict[str, int] = {}
        wait: dict[str, int] = {}
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
            arr[pu.id] = pu_t
            dep[pu.id] = pu_t + pickup_service_minutes(t.boarding_duration)
            if t.via_zone and (t.id, v.id) in via_arr:
                via_stop = Stop(
                    id=f"{t.id}:VIA",
                    trip_id=t.id,
                    stop_type=StopType.VIA,
                    location=t.via_zone,
                    service_duration=t.via_service_duration,
                    load_delta=0,
                    wheelchair_load_delta=0,
                )
                via_t = solver.Value(via_arr[(t.id, v.id)])
                stops.extend([pu, via_stop, do])
                arr[via_stop.id] = via_t
                dep[via_stop.id] = via_t + t.via_service_duration
            else:
                stops.extend([pu, do])
            arr[do.id] = do_t
            dep[do.id] = do_t + t.alighting_duration
            ride[t.id] = do_t - (pu_t + pickup_service_minutes(t.boarding_duration))
            wait[t.id] = max(0, pu_t - t.earliest_pickup)
        route_plans.append(
            RoutePlan(
                vehicle_id=v.id,
                driver_id=vehicle_driver[v.id],
                ordered_stops=stops,
                passenger_assignments=[t.id for _, t, _ in items],
                arrival_times=arr,
                departure_times=dep,
                waiting_times=wait,
                ride_times=ride,
            )
        )

    result = PlanningResult(
        status=SolutionStatus.NOT_VERIFIED.value,
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
            "pooling": False,
            "model": "sequential_pair_assignment",
        },
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
        event_type="DAY_AHEAD",
    )
    return finalize_result(
        problem,
        result,
        proven_optimal=ortools_optimal,
        exact=ortools_ok,
    )
