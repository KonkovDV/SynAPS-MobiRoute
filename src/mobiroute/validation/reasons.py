"""Conservative diagnostics: necessary-condition evidence, not an infeasibility proof."""

from __future__ import annotations

from mobiroute.domain.driver_assignment import select_driver
from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import DayProblem, TripRequest
from mobiroute.validation.feasibility import accessibility_compatible, trip_quota_remaining


def diagnose_rejection(problem: DayProblem, trip: TripRequest) -> ReasonCode:
    """Use validated inputs; unresolved scheduling failures require human review."""
    vehicles = problem.vehicles
    if not vehicles:
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    quota = trip_quota_remaining(problem, trip)
    if quota is not None:
        try:
            if trip.via_zone:
                direct = (
                    problem.travel.travel(trip.pickup_zone, trip.via_zone)
                    + trip.via_service_duration
                    + problem.travel.travel(trip.via_zone, trip.dropoff_zone)
                )
            else:
                direct = problem.travel.travel(trip.pickup_zone, trip.dropoff_zone)
        except KeyError:
            return ReasonCode.MANUAL_REVIEW_REQUIRED
        if direct > quota:
            return ReasonCode.QUOTA_EXCEEDED
    if all(v.shift_end <= v.shift_start for v in vehicles):
        return ReasonCode.VEHICLE_UNAVAILABLE
    acc = [accessibility_compatible(v, trip) for v in vehicles]
    if all(c is not None for c in acc):
        causes = {c for c in acc if c is not None}
        if len(causes) == 1:
            return next(iter(causes))
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    need = trip.needs_boarding_assistance
    any_driver = False
    any_shift = False
    for v in vehicles:
        if accessibility_compatible(v, trip) is not None:
            continue
        if v.shift_end <= v.shift_start:
            continue
        any_shift = True
        did = select_driver(problem, v, needs_accessibility=need, occupied_driver_ids=set())
        if did is not None:
            any_driver = True
            break
    if not any_shift:
        return ReasonCode.VEHICLE_UNAVAILABLE
    if not any_driver:
        return ReasonCode.NO_DRIVER
    # One greedy singleton simulation cannot rule out other drivers, departure
    # times or global rearrangements. Appointment metadata is not conflict evidence.
    return ReasonCode.MANUAL_REVIEW_REQUIRED


def non_empty_reason(code: str | ReasonCode | None) -> str:
    if code is None:
        return ReasonCode.MANUAL_REVIEW_REQUIRED.value
    text = code.value if isinstance(code, ReasonCode) else str(code).strip()
    return text or ReasonCode.MANUAL_REVIEW_REQUIRED.value
