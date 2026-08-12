"""Rejection diagnostics — never return an empty reason."""

from __future__ import annotations

from mobiroute.domain.driver_assignment import select_driver
from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import DayProblem, TripRequest
from mobiroute.validation.feasibility import accessibility_compatible, trip_quota_remaining


def diagnose_rejection(problem: DayProblem, trip: TripRequest) -> ReasonCode:
    vehicles = problem.vehicles
    if not vehicles:
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    quota = trip_quota_remaining(problem, trip)
    if quota is not None:
        if quota <= 0:
            return ReasonCode.QUOTA_EXCEEDED
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
            direct = 0
        if direct > quota:
            return ReasonCode.QUOTA_EXCEEDED
    if all(v.shift_end <= v.shift_start for v in vehicles):
        return ReasonCode.VEHICLE_UNAVAILABLE
    acc = [accessibility_compatible(v, trip) for v in vehicles]
    if all(c is not None for c in acc):
        for code in acc:
            if code is not None:
                return code
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
        if need:
            return ReasonCode.NO_DRIVER
        return ReasonCode.DRIVER_SHIFT_CONFLICT
    from mobiroute.solvers.greedy import _trip_stops, simulate_stop_sequence

    for v in vehicles:
        if accessibility_compatible(v, trip) is not None:
            continue
        did = select_driver(problem, v, needs_accessibility=need, occupied_driver_ids=set())
        if did is None:
            continue
        plan = simulate_stop_sequence(problem, v, did, _trip_stops(trip), {trip.id: trip})
        if plan is not None:
            ride = plan.ride_times.get(trip.id, 0)
            if quota is not None and ride > quota:
                return ReasonCode.QUOTA_EXCEEDED
            return ReasonCode.TIME_WINDOW_CONFLICT
    if trip.appointment_start is not None or trip.appointment_end is not None:
        return ReasonCode.APPOINTMENT_CONFLICT
    return ReasonCode.TIME_WINDOW_CONFLICT


def non_empty_reason(code: str | ReasonCode | None) -> str:
    if code is None:
        return ReasonCode.MANUAL_REVIEW_REQUIRED.value
    text = code.value if isinstance(code, ReasonCode) else str(code).strip()
    return text or ReasonCode.MANUAL_REVIEW_REQUIRED.value
