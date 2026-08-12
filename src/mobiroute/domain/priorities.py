"""Configurable, transparent priority hierarchy (not hidden weights)."""

from __future__ import annotations

from mobiroute.domain.models import ServicePriority, StrictModel
from mobiroute.domain.requests import TripRequest


class PriorityLevel(StrictModel):
    name: str
    rank: int  # 1 = highest
    description: str


DEFAULT_HIERARCHY: list[PriorityLevel] = [
    PriorityLevel(name="passenger_safety", rank=1, description="Safety never traded for cost"),
    PriorityLevel(name="medical_urgency", rank=2, description="Medical / palliative urgency"),
    PriorityLevel(name="protected_time_window", rank=3, description="Appointment windows"),
    PriorityLevel(name="vehicle_compatibility", rank=4, description="Lift/ramp/wheelchair fit"),
    PriorityLevel(name="companion_availability", rank=5, description="Companion seats"),
    PriorityLevel(name="lateness_minimization", rank=6, description="Reduce late arrivals"),
    PriorityLevel(name="fairness", rank=7, description="Group equity of service"),
    PriorityLevel(name="distance_and_cost", rank=8, description="Deadhead and cost last"),
]


def trip_sort_key(trip: TripRequest) -> tuple[object, ...]:
    """Lexicographic sort for greedy/FIFO hybrids — transparent ranks.

    Frozen confirmed trips and unpaired outbounds are placed before
    ``same_vehicle_as`` returns so pairing cannot fail by sort order.
    """
    frozen = 0 if trip.frozen else 1
    paired = 1 if trip.same_vehicle_as else 0
    medical = (
        0 if trip.medical_priority or trip.service_priority == ServicePriority.MEDICAL_URGENT else 1
    )
    protected = 0 if trip.appointment_end is not None else 1
    accessibility = 0 if trip.wheelchair_requirement.value != "NONE" else 1
    return (frozen, paired, medical, protected, accessibility, trip.earliest_pickup, trip.id)


def fifo_sort_key(trip: TripRequest) -> tuple[object, ...]:
    """Request-time order with frozen-first and outbound-before-return."""
    return (
        0 if trip.frozen else 1,
        1 if trip.same_vehicle_as else 0,
        trip.requested_at,
        trip.id,
    )
