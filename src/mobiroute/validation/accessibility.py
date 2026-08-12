"""Accessibility-focused validation helpers."""

from __future__ import annotations

from mobiroute.domain.models import ReasonCode
from mobiroute.domain.requests import DayProblem, TripRequest, Vehicle
from mobiroute.validation.feasibility import accessibility_compatible


def find_compatible_vehicles(problem: DayProblem, trip: TripRequest) -> list[Vehicle]:
    out: list[Vehicle] = []
    for v in problem.vehicles:
        if accessibility_compatible(v, trip) is None and (
            not v.service_area or trip.pickup_zone in v.service_area
        ):
            out.append(v)
    return out


def explain_incompatibility(problem: DayProblem, trip: TripRequest) -> ReasonCode:
    reasons = []
    for v in problem.vehicles:
        r = accessibility_compatible(v, trip)
        if r is None:
            return ReasonCode.ACCEPTED  # at least one exists
        reasons.append(r)
    if all(x == ReasonCode.NO_WHEELCHAIR_CAPACITY for x in reasons):
        return ReasonCode.NO_WHEELCHAIR_CAPACITY
    if all(x == ReasonCode.NO_CAPACITY for x in reasons):
        return ReasonCode.NO_CAPACITY
    return ReasonCode.NO_COMPATIBLE_VEHICLE
