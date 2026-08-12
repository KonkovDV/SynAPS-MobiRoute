"""Nearest feasible vehicle baseline (heuristic — never OPTIMAL)."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.models import ReasonCode, SolutionStatus
from mobiroute.domain.priorities import trip_sort_key
from mobiroute.domain.requests import DayProblem, PlanningResult, RejectedTrip, TripRequest
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import _assign_driver, _simulate_route
from mobiroute.validation.feasibility import accessibility_compatible
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


def solve_nearest(problem: DayProblem) -> PlanningResult:
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

    for trip in ordered:
        candidates = []
        occupied = {d for d in vehicle_driver.values() if d}
        for v in problem.vehicles:
            if accessibility_compatible(v, trip) is not None:
                continue
            occ = occupied - ({vehicle_driver[v.id]} if vehicle_driver[v.id] else set())
            driver_id = vehicle_driver[v.id] or _assign_driver(
                problem,
                v.id,
                needs_accessibility=trip.needs_boarding_assistance,
                occupied_driver_ids=occ,
                preferred_id=vehicle_driver[v.id],
            )
            if driver_id is None:
                continue
            dist = problem.travel.travel(v.depot_id, trip.pickup_zone)
            trial = routes[v.id] + [trip]
            plan = _simulate_route(problem, v, driver_id, trial)
            if plan is not None:
                candidates.append((dist, plan.route_duration, v.id, driver_id))
        if not candidates:
            code = non_empty_reason(diagnose_rejection(problem, trip))
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            continue
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        _dist, _dur, vid, did = candidates[0]
        routes[vid].append(trip)
        vehicle_driver[vid] = did
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value

    route_plans: list[RoutePlan] = []
    for v in problem.vehicles:
        if not routes[v.id]:
            continue
        occ = {d for vid, d in vehicle_driver.items() if d and vid != v.id}
        plan = _simulate_route(
            problem,
            v,
            _assign_driver(
                problem,
                v.id,
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
                rejected.append(
                    RejectedTrip(trip_id=tid, reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)
                )
                reasons[tid] = ReasonCode.TIME_WINDOW_CONFLICT.value

    result = PlanningResult(
        status=SolutionStatus.HEURISTIC_FEASIBLE.value,
        solution_type="NEAREST_FEASIBLE",
        verified_feasible=False,
        served_requests=sorted(served),
        rejected_requests=rejected,
        route_plans=route_plans,
        objective_values={"served": float(len(served)), "rejected": float(len(rejected))},
        reason_codes=reasons,
        input_hash=fingerprint(problem.model_dump(mode="json")),
        config_hash=fingerprint({"solver": "NEAREST_FEASIBLE", "version": __version__}),
        solver_config={"name": "NEAREST_FEASIBLE", "pooling": False},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
        event_type="DAY_AHEAD",
    )
    return finalize_result(problem, result)
