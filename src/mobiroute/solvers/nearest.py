"""Nearest feasible vehicle baseline (heuristic — never OPTIMAL)."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.driver_assignment import DriverIndex
from mobiroute.domain.models import ReasonCode, SolutionStatus
from mobiroute.domain.priorities import trip_sort_key
from mobiroute.domain.requests import DayProblem, PlanningResult, RejectedTrip, Stop, TripRequest
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import _assign_driver, _quota_lower_bound_exceeds, _simulate_route
from mobiroute.validation.feasibility import (
    accessibility_compatible,
    passenger_quota_debits,
    quota_caps,
    trial_exceeds_quota,
)
from mobiroute.validation.input import validate_problem
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


def solve_nearest(problem: DayProblem) -> PlanningResult:
    problem = validate_problem(problem)
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    return _nearest_core(problem, active)


def _nearest_core(problem: DayProblem, ordered: list[TripRequest]) -> PlanningResult:
    from mobiroute.domain.requests import RoutePlan

    routes: dict[str, list[TripRequest]] = {v.id: [] for v in problem.vehicles}
    vehicle_driver: dict[str, str | None] = {v.id: None for v in problem.vehicles}
    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}
    # Passenger-day entitlement is a cross-route resource: track it like greedy.
    caps = quota_caps(problem)
    drivers_index = DriverIndex(problem)
    stops_cache: dict[str, list[Stop]] = {}
    used_now: dict[str, int] = {}
    veh_used: dict[str, dict[str, int]] = {v.id: {} for v in problem.vehicles}

    for trip in ordered:
        pid = trip.pseudonymous_passenger_id
        left = caps[pid] - used_now.get(pid, 0) if pid in caps else None
        if _quota_lower_bound_exceeds(problem, trip, left):
            code = ReasonCode.QUOTA_EXCEEDED.value
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            continue
        candidates = []
        quota_blocked = False
        occupied = {d for d in vehicle_driver.values() if d}
        for v in problem.vehicles:
            if accessibility_compatible(v, trip) is not None:
                continue
            occ = occupied - ({vehicle_driver[v.id]} if vehicle_driver[v.id] else set())
            # A seated driver is not a licence: re-check the need of every trip.
            driver_id = _assign_driver(
                problem,
                v.id,
                vehicle=v,
                needs_accessibility=trip.needs_boarding_assistance,
                occupied_driver_ids=occ,
                preferred_id=vehicle_driver[v.id],
                index=drivers_index,
            )
            if driver_id is None:
                continue
            # "Nearest" is the deadhead from where the vehicle already stands.
            anchor = routes[v.id][-1].dropoff_zone if routes[v.id] else v.depot_id
            dist = problem.travel.travel(anchor, trip.pickup_zone)
            trial = routes[v.id] + [trip]
            plan = _simulate_route(problem, v, driver_id, trial, stops_cache)
            if plan is None:
                continue
            if trial_exceeds_quota(
                plan,
                quota_cap=caps,
                used_now=used_now,
                previous_on_vehicle=veh_used[v.id],
                problem=problem,
            ):
                quota_blocked = True
                continue
            candidates.append((dist, plan.route_duration, v.id, driver_id, plan))
        if not candidates:
            code = (
                ReasonCode.QUOTA_EXCEEDED.value
                if quota_blocked
                else non_empty_reason(diagnose_rejection(problem, trip))
            )
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            continue
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        _dist, _dur, vid, did, chosen = candidates[0]
        routes[vid].append(trip)
        vehicle_driver[vid] = did
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value
        for owner, mins in veh_used[vid].items():
            used_now[owner] = used_now.get(owner, 0) - mins
        veh_used[vid] = passenger_quota_debits(problem, chosen)
        for owner, mins in veh_used[vid].items():
            used_now[owner] = used_now.get(owner, 0) + mins

    route_plans: list[RoutePlan] = []
    for v in problem.vehicles:
        if not routes[v.id]:
            continue
        occ = {d for vid, d in vehicle_driver.items() if d and vid != v.id}
        need = any(t.needs_boarding_assistance for t in routes[v.id])
        plan = _simulate_route(
            problem,
            v,
            _assign_driver(
                problem,
                v.id,
                needs_accessibility=need,
                occupied_driver_ids=occ,
                preferred_id=vehicle_driver[v.id],
            ),
            routes[v.id],
        )
        if plan is not None:
            route_plans.append(plan)
        else:
            for trip_obj in routes[v.id]:
                tid = trip_obj.id
                if tid in served:
                    served.remove(tid)
                code = non_empty_reason(diagnose_rejection(problem, trip_obj))
                rejected.append(RejectedTrip(trip_id=tid, reason_code=code))
                reasons[tid] = code

    result = PlanningResult(
        status=SolutionStatus.HEURISTIC_FEASIBLE.value,
        solution_type="NEAREST_FEASIBLE",
        verified_feasible=False,
        served_requests=sorted(served),
        rejected_requests=rejected,
        route_plans=route_plans,
        objective_values={"served": float(len(served)), "rejected": float(len(rejected))},
        reason_codes=reasons,
        input_hash="",
        config_hash=fingerprint({"solver": "NEAREST_FEASIBLE", "version": __version__}),
        solver_config={"name": "NEAREST_FEASIBLE", "pooling": False},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level=problem.claim_level,
        event_type="DAY_AHEAD",
    )
    return finalize_result(problem, result)
