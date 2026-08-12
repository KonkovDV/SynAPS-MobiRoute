"""Completeness checks: no dropped trips without reject reason."""

from mobiroute.domain.requests import DayProblem, PlanningResult


def incomplete_plan_issues(problem: DayProblem, result: PlanningResult) -> list[str]:
    active = {
        t.id for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}
    }
    accounted = set(result.served_requests) | {r.trip_id for r in result.rejected_requests}
    missing = sorted(active - accounted)
    return [f"UNACCOUNTED:{tid}" for tid in missing]
