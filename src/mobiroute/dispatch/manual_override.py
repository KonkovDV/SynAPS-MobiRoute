"""Human-in-the-loop manual override audit trail."""

from __future__ import annotations

from pydantic import Field

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.models import ReasonCode, StrictModel
from mobiroute.domain.requests import PlanningResult, RejectedTrip
from mobiroute.solvers.finalize import _reconcile_explanations, plan_identity
from mobiroute.validation.reasons import non_empty_reason


def _clock_owner(key: str) -> str:
    """Stop clocks are keyed `<trip_id>:<stop_type>`; the owner is that prefix."""
    return key.split(":", 1)[0]


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
        # The entry is the audit record of this override. It cannot name a
        # different trip than the one that leaves the published plan.
        if entry.trip_id != trip_id:
            raise ValueError("Manual override entry does not match the overridden trip")
        self.record(entry)
        code = non_empty_reason(entry.reason_code)
        served = [t for t in result.served_requests if t != trip_id]
        rejected = [
            *list(result.rejected_requests),
            RejectedTrip(trip_id=trip_id, reason_code=code, detail=entry.free_text_reason),
        ]
        reasons = dict(result.reason_codes)
        reasons[trip_id] = code
        plans = []
        for rp in result.route_plans:
            if trip_id not in rp.passenger_assignments:
                plans.append(rp)
                continue
            kept = [s for s in rp.ordered_stops if s.trip_id != trip_id]
            assigns = [t for t in rp.passenger_assignments if t != trip_id]
            arr = {k: v for k, v in rp.arrival_times.items() if _clock_owner(k) != trip_id}
            dep = {k: v for k, v in rp.departure_times.items() if _clock_owner(k) != trip_id}
            plans.append(
                rp.model_copy(
                    update={
                        "ordered_stops": kept,
                        "passenger_assignments": assigns,
                        "arrival_times": arr,
                        "departure_times": dep,
                    }
                )
            )
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
        # An override changes what is published. The explanation of the removed
        # trip cannot keep claiming service, and the identity cannot keep
        # fingerprinting the plan the operator overrode.
        payload: dict[str, object] = {
            "solver": "MANUAL_OVERRIDE",
            "base": result.config_hash,
            "action": entry.action,
            "trip": trip_id,
            "reason": code,
            "operator": entry.operator_id,
            "version": __version__,
            "synaps": SYNAPS_COMMIT,
        }
        stamped = out.model_copy(
            update={
                "explanations": _reconcile_explanations(out),
                "config_hash": fingerprint(payload),
            }
        )
        return stamped.model_copy(update={"plan_id": plan_identity(stamped)})
