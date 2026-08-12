"""Human-in-the-loop manual override audit trail."""

from __future__ import annotations

from pydantic import Field

from mobiroute.domain.models import ReasonCode, StrictModel
from mobiroute.domain.requests import PlanningResult


class ManualOverride(StrictModel):
    operator_id: str  # pseudonymous staff id — never FIO in open logs
    trip_id: str
    action: str  # ACCEPT | REJECT | REASSIGN | FREEZE_OVERRIDE
    reason_code: str = ReasonCode.MANUAL_REVIEW_REQUIRED.value
    free_text_reason: str
    previous_vehicle_id: str | None = None
    new_vehicle_id: str | None = None


class OverrideJournal(StrictModel):
    entries: list[ManualOverride] = Field(default_factory=list)

    def record(self, entry: ManualOverride) -> None:
        if not entry.free_text_reason.strip():
            raise ValueError("Manual override requires a non-empty reason")
        self.entries.append(entry)

    def apply_reject(
        self, result: PlanningResult, trip_id: str, entry: ManualOverride
    ) -> PlanningResult:
        self.record(entry)
        served = [t for t in result.served_requests if t != trip_id]
        from mobiroute.domain.requests import RejectedTrip

        rejected = [
            *list(result.rejected_requests),
            RejectedTrip(
                trip_id=trip_id, reason_code=entry.reason_code, detail=entry.free_text_reason
            ),
        ]
        reasons = dict(result.reason_codes)
        reasons[trip_id] = entry.reason_code
        plans = []
        for rp in result.route_plans:
            if trip_id not in rp.passenger_assignments:
                plans.append(rp)
                continue
            # drop route for simplicity — operator must re-solve; mark review
            plans.append(rp)
        out = result.model_copy(
            update={
                "served_requests": served,
                "rejected_requests": rejected,
                "reason_codes": reasons,
                "status": "MANUAL_REVIEW_REQUIRED",
                "route_plans": plans,
                "verified_feasible": False,
            }
        )
        return out
