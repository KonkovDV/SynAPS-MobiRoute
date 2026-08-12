"""Shared post-solve notary: enrich routes, completeness, status honesty."""

from __future__ import annotations

import uuid

from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.models import ReasonCode, SolutionStatus
from mobiroute.domain.requests import DayProblem, PlanningResult, RejectedTrip, TripExplanation
from mobiroute.domain.route_graph import enrich_planning_result
from mobiroute.reporting.explanations import default_explanations
from mobiroute.validation.feasibility import check_plan
from mobiroute.validation.reasons import non_empty_reason


def _plan_id(result: PlanningResult) -> str:
    key = f"mobiroute:plan:{result.input_hash}:{result.config_hash}:{result.solution_type}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _account_inactive(problem: DayProblem, result: PlanningResult) -> PlanningResult:
    known = set(result.served_requests) | {r.trip_id for r in result.rejected_requests}
    extra: list[RejectedTrip] = list(result.rejected_requests)
    reasons = dict(result.reason_codes)
    for t in problem.requests:
        if t.id in known:
            continue
        if t.booking_status.value == "CANCELLED":
            extra.append(RejectedTrip(trip_id=t.id, reason_code=ReasonCode.CANCELLED.value))
            reasons[t.id] = ReasonCode.CANCELLED.value
        elif t.booking_status.value == "NO_SHOW":
            extra.append(RejectedTrip(trip_id=t.id, reason_code=ReasonCode.NO_SHOW.value))
            reasons[t.id] = ReasonCode.NO_SHOW.value
    cleaned: list[RejectedTrip] = []
    for r in extra:
        code = non_empty_reason(r.reason_code)
        cleaned.append(r.model_copy(update={"reason_code": code}))
        reasons[r.trip_id] = code
    return result.model_copy(update={"rejected_requests": cleaned, "reason_codes": reasons})


def finalize_result(
    problem: DayProblem,
    result: PlanningResult,
    *,
    proven_optimal: bool = False,
    exact: bool = False,
    explanations: list[TripExplanation] | None = None,
    changed_vehicle_ids: set[str] | None = None,
) -> PlanningResult:
    result = enrich_planning_result(problem, result, only_vehicles=changed_vehicle_ids)
    result = _account_inactive(problem, result)
    if explanations:
        result = result.model_copy(update={"explanations": explanations})
    elif not result.explanations:
        result = result.model_copy(update={"explanations": default_explanations(problem, result)})

    report = check_plan(problem, result, only_vehicles=changed_vehicle_ids)
    result.verified_feasible = report.feasible
    result.objective_values = {
        **result.objective_values,
        "served": float(len(result.served_requests)),
        "rejected": float(len(result.rejected_requests)),
        "violations": float(len(report.violations)),
    }

    active_reject = [
        r
        for r in result.rejected_requests
        if r.reason_code not in {ReasonCode.CANCELLED.value, ReasonCode.NO_SHOW.value}
    ]
    if not report.feasible:
        status = SolutionStatus.NOT_VERIFIED.value
    elif proven_optimal and exact and not active_reject:
        status = SolutionStatus.OPTIMAL.value
    elif proven_optimal and exact and active_reject:
        status = SolutionStatus.PARTIAL.value
    elif exact and not active_reject:
        status = SolutionStatus.FEASIBLE.value
    elif active_reject:
        status = SolutionStatus.PARTIAL.value
    else:
        status = SolutionStatus.HEURISTIC_FEASIBLE.value
    result.status = status
    if not result.plan_id:
        result.plan_id = _plan_id(result)
    result.fairness_metrics = compute_fairness(problem, result)
    result.solver_config = {
        **result.solver_config,
        "verified_feasible": report.feasible,
        "proven_optimal": proven_optimal,
    }
    return result
