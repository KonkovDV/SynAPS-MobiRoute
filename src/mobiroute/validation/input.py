"""Canonical input snapshots and the signed-i32 native arithmetic envelope."""

from __future__ import annotations

from collections.abc import Iterable

from mobiroute.domain.constraints import (
    EARLY_DROPOFF_SLACK,
    MAX_NATIVE_MINUTES,
    detour_limit,
    pickup_service_minutes,
)
from mobiroute.domain.requests import DayProblem, Driver, TripRequest, Vehicle


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _unique(values: Iterable[str], label: str) -> None:
    ids = list(values)
    _require(all(value.strip() for value in ids), f"EMPTY_{label}_ID")
    _require(len(ids) == len(set(ids)), f"DUPLICATE_{label}_ID")


def _native_nonnegative(value: int, label: str) -> None:
    _require(0 <= value <= MAX_NATIVE_MINUTES, f"NATIVE_RANGE:{label}")


def _trip_contract(trip: TripRequest) -> None:
    for name in (
        "earliest_pickup",
        "latest_pickup",
        "max_ride_time",
        "max_wait_time",
        "boarding_duration",
        "alighting_duration",
        "via_service_duration",
    ):
        _native_nonnegative(getattr(trip, name), name)
    for name in ("appointment_start", "appointment_end"):
        value = getattr(trip, name)
        if value is not None:
            _native_nonnegative(value, name)
    _require(trip.earliest_pickup <= trip.latest_pickup, "REVERSED_PICKUP_WINDOW")
    _native_nonnegative(1 + trip.companion_count, "trip_seats")
    _require(bool(trip.id.strip()), "EMPTY_TRIP_ID")
    _require(bool(trip.pseudonymous_passenger_id.strip()), "EMPTY_PASSENGER_ID")
    # Also rejects finite values whose multiplication by 1000 becomes infinity.
    detour_limit(0, trip.max_detour_ratio)
    # appointment_start is lobby metadata, not a mandatory lower bound on appointment_end.
    for point in (trip.pickup_coordinates, trip.dropoff_coordinates):
        if point is not None:
            lat, lon = point
            _require(-90 <= lat <= 90 and -180 <= lon <= 180, "INVALID_COORDINATES")


def validate_trip(trip: TripRequest) -> TripRequest:
    """Return the canonical record; callers must use the returned value."""
    _require(isinstance(trip, TripRequest), "TRIP_REQUEST_REQUIRED")
    try:
        snapshot = TripRequest.model_validate(trip.model_dump(warnings=False))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("INVALID_TRIP_SCHEMA") from None
    _trip_contract(snapshot)
    return snapshot


def validate_problem(problem: DayProblem) -> DayProblem:
    """Return a validated snapshot, including unchecked copies and list mutations.

    Never validate a reconstructed model and then execute the original object.
    This function deliberately returns a new canonical object with fresh matrix caches.
    Missing passenger profiles are supported; profiles are optional quota metadata.
    """
    _require(isinstance(problem, DayProblem), "DAY_PROBLEM_REQUIRED")
    try:
        snapshot = DayProblem.model_validate(problem.model_dump(warnings=False))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("INVALID_PROBLEM_SCHEMA") from None
    _require(bool(snapshot.problem_id.strip()), "EMPTY_PROBLEM_ID")
    _require(snapshot.schema_version == "mobiroute.problem.v1", "UNSUPPORTED_PROBLEM_SCHEMA")
    _unique((t.id for t in snapshot.requests), "TRIP")
    _unique((v.id for v in snapshot.vehicles), "VEHICLE")
    _unique((d.id for d in snapshot.drivers), "DRIVER")
    _unique((p.pseudonymous_id for p in snapshot.passengers), "PASSENGER")
    zones = set(snapshot.travel.zones)
    anchors: list[int] = []
    resources: list[Vehicle | Driver] = [*snapshot.vehicles, *snapshot.drivers]
    for resource in resources:
        _require(resource.depot_id in zones, "UNKNOWN_DEPOT_ZONE")
        _native_nonnegative(resource.shift_start, "shift_start")
        _native_nonnegative(resource.shift_end, "shift_end")
        _require(resource.shift_start <= resource.shift_end, "REVERSED_SHIFT")
        anchors.append(resource.shift_end)
        for begin, end in resource.unavailable_intervals:
            _native_nonnegative(begin, "unavailable_start")
            _native_nonnegative(end, "unavailable_end")
            _require(begin <= end, "REVERSED_UNAVAILABLE_INTERVAL")
            anchors.append(end)
    for vehicle in snapshot.vehicles:
        _native_nonnegative(vehicle.passenger_capacity, "passenger_capacity")
        _native_nonnegative(vehicle.wheelchair_capacity, "wheelchair_capacity")
        _require(set(vehicle.service_area) <= zones, "UNKNOWN_SERVICE_AREA_ZONE")
    services: list[int] = []
    for trip in snapshot.requests:
        _trip_contract(trip)
        _require(trip.pickup_zone in zones and trip.dropoff_zone in zones, "UNKNOWN_TRIP_ZONE")
        _require(trip.via_zone is None or trip.via_zone in zones, "UNKNOWN_VIA_ZONE")
        anchors.append(trip.earliest_pickup)
        if trip.appointment_start is not None:
            anchors.append(max(0, trip.appointment_start - EARLY_DROPOFF_SLACK))
        services.extend(
            (
                pickup_service_minutes(trip.boarding_duration),
                trip.alighting_duration,
                trip.via_service_duration,
            )
        )
        if trip.via_zone is not None:
            direct = (
                snapshot.travel.travel(trip.pickup_zone, trip.via_zone)
                + trip.via_service_duration
                + snapshot.travel.travel(trip.via_zone, trip.dropoff_zone)
            )
            _native_nonnegative(direct, "via_direct_minutes")
    # Guard intermediate additions, not just individual serialized integers.
    edge = max((max(row, default=0) for row in snapshot.travel.minutes), default=0)
    horizon = max(anchors, default=0)
    _native_nonnegative(horizon + edge + max(services, default=0), "arrival_plus_service")
    _native_nonnegative(sum(1 + t.companion_count for t in snapshot.requests), "total_trip_seats")
    wait_bound = sum(
        min(t.max_wait_time, max(0, horizon + edge - t.earliest_pickup)) for t in snapshot.requests
    )
    _native_nonnegative(wait_bound, "total_wait_score")
    return snapshot
