"""Result accounting: unique, known and disjoint service/rejection records."""

from collections import Counter

from mobiroute.domain.requests import DayProblem, PlanningResult


def incomplete_plan_issues(problem: DayProblem, result: PlanningResult) -> list[str]:
    trips = {t.id: t for t in problem.requests}
    known = set(trips)
    active = {
        t.id for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}
    }
    served_counts = Counter(result.served_requests)
    rejected_counts = Counter(r.trip_id for r in result.rejected_requests)
    served, rejected = set(served_counts), set(rejected_counts)
    checks = (
        ("UNACCOUNTED", active - served - rejected),
        ("UNKNOWN_SERVED", served - known),
        ("UNKNOWN_REJECTED", rejected - known),
        ("DUPLICATE_SERVED", {tid for tid, n in served_counts.items() if n > 1}),
        ("DUPLICATE_REJECTED", {tid for tid, n in rejected_counts.items() if n > 1}),
        ("SERVED_AND_REJECTED", served & rejected),
        ("INACTIVE_SERVED", served & (known - active)),
    )
    issues = [f"{code}:{tid}" for code, ids in checks for tid in ids]
    for record in result.rejected_requests:
        trip = trips.get(record.trip_id)
        if (
            trip is not None
            and record.reason_code in {"CANCELLED", "NO_SHOW"}
            and record.reason_code != trip.booking_status.value
        ):
            issues.append(f"REJECTION_STATUS_MISMATCH:{record.trip_id}")
    return sorted(set(issues))
