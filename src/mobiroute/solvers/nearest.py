"""Nearest feasible vehicle baseline (heuristic — never OPTIMAL)."""

from __future__ import annotations

from mobiroute.domain.priorities import trip_sort_key
from mobiroute.domain.requests import DayProblem, PlanningResult, TripRequest
from mobiroute.solvers.greedy import _assign_driver, _simulate_route
from mobiroute.validation.feasibility import accessibility_compatible


def solve_nearest(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    return _nearest_core(problem, active)


def _nearest_core(problem: DayProblem, ordered: list[TripRequest]) -> PlanningResult:
    """Assign each trip to the compatible vehicle with minimal depot→pickup travel."""
    from mobiroute import SYNAPS_COMMIT, __version__
    from mobiroute.adapters.fingerprint import fingerprint
    from mobiroute.domain.fairness import compute_fairness
    from mobiroute.domain.models import ReasonCode, SolutionStatus
    from mobiroute.domain.requests import PlanningResult, RejectedTrip, RoutePlan
    from mobiroute.validation.feasibility import check_plan

    routes: dict[str, list[TripRequest]] = {v.id: [] for v in problem.vehicles}
    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}

    for trip in ordered:
        candidates = []
        for v in problem.vehicles:
            if accessibility_compatible(v, trip) is not None:
                continue
            dist = problem.travel.travel(v.depot_id, trip.pickup_zone)
            trial = routes[v.id] + [trip]
            plan = _simulate_route(problem, v, _assign_driver(problem, v.id), trial)
            if plan is not None:
                candidates.append((dist, plan.route_duration, v.id))
        if not candidates:
            code = ReasonCode.TIME_WINDOW_CONFLICT.value
            if all(accessibility_compatible(v, trip) is not None for v in problem.vehicles):
                r0 = accessibility_compatible(problem.vehicles[0], trip)
                code = r0.value if r0 else ReasonCode.NO_COMPATIBLE_VEHICLE.value
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            continue
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        vid = candidates[0][2]
        routes[vid].append(trip)
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value

    route_plans: list[RoutePlan] = []
    for v in problem.vehicles:
        if not routes[v.id]:
            continue
        plan = _simulate_route(problem, v, _assign_driver(problem, v.id), routes[v.id])
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
        solver_config={"name": "NEAREST_FEASIBLE"},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
    )
    report = check_plan(problem, result)
    result.verified_feasible = report.feasible
    if not report.feasible:
        result.status = SolutionStatus.NOT_VERIFIED.value
    elif rejected:
        result.status = SolutionStatus.PARTIAL.value
    else:
        result.status = SolutionStatus.HEURISTIC_FEASIBLE.value
    result.fairness_metrics = compute_fairness(problem, result)
    return result
