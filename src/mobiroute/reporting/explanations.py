"""Per-trip explanations for accepted and rejected requests."""

from __future__ import annotations

from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import DayProblem, PlanningResult, TripExplanation


def default_explanations(problem: DayProblem, result: PlanningResult) -> list[TripExplanation]:
    trips = {t.id: t for t in problem.requests}
    by_trip: dict[str, TripExplanation] = {}
    for rp in result.route_plans:
        for it in rp.passenger_itineraries:
            trip = trips.get(it.trip_id)
            constraints: list[str] = ["PAIRING_SAME_VEHICLE", "PICKUP_BEFORE_DROPOFF"]
            if trip is not None:
                if trip.appointment_end is not None:
                    constraints.append("APPOINTMENT_WINDOW")
                if trip.wheelchair_requirement.value != "NONE":
                    constraints.append("WHEELCHAIR_CAPACITY")
                if trip.needs_lift:
                    constraints.append("LIFT")
                if trip.needs_ramp:
                    constraints.append("RAMP")
                if trip.needs_boarding_assistance:
                    constraints.append("BOARDING_ASSISTANCE")
            by_trip[it.trip_id] = TripExplanation(
                trip_id=it.trip_id,
                accepted=True,
                vehicle_id=it.vehicle_id,
                driver_id=it.driver_id,
                pickup_stop_id=it.pickup_stop_id,
                dropoff_stop_id=it.dropoff_stop_id,
                pickup_time=it.pickup_time,
                dropoff_time=it.dropoff_time,
                waiting_time=it.waiting_time,
                ride_time=it.ride_time,
                appointment_slack=it.appointment_slack,
                active_constraints=constraints,
                why_this_route=(
                    f"Assigned to vehicle {it.vehicle_id} with driver {it.driver_id} "
                    f"under hard accessibility and window constraints."
                ),
                reason_code=ReasonCode.ACCEPTED.value,
            )
    for r in result.rejected_requests:
        if r.trip_id in by_trip:
            continue
        by_trip[r.trip_id] = TripExplanation(
            trip_id=r.trip_id,
            accepted=False,
            why_this_route="Not inserted; see reason_code.",
            alternatives_rejected=[r.reason_code],
            reason_code=r.reason_code or ReasonCode.MANUAL_REVIEW_REQUIRED.value,
        )
    return [by_trip[k] for k in sorted(by_trip)]
