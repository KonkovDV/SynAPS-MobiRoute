"""Hand-built tiny problems for pooling / driver / CP-SAT regression tests."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.domain.models import WheelchairType
from mobiroute.domain.requests import DayProblem, Driver, TripRequest, Vehicle


def catalog_travel() -> object:
    return generate_day("tiny", seed=1).travel


def vehicle(
    vid: str = "veh-1",
    *,
    capacity: int = 4,
    wheelchairs: int = 2,
    depot: str = "Z_DEPOT_1",
    vtype: str = "minibus",
    lift: bool = True,
    types: list[WheelchairType] | None = None,
) -> Vehicle:
    return Vehicle(
        id=vid,
        vehicle_type=vtype,
        passenger_capacity=capacity,
        wheelchair_capacity=wheelchairs,
        lift_available=lift,
        ramp_available=True,
        compatible_wheelchair_types=types or [WheelchairType.MANUAL, WheelchairType.POWER],
        depot_id=depot,
        shift_start=0,
        shift_end=12 * 60,
        service_area=[],
    )


def driver(
    did: str = "drv-1",
    *,
    depot: str = "Z_DEPOT_1",
    trained: bool = True,
    available: bool = True,
    types: list[str] | None = None,
    shift_start: int = 0,
    shift_end: int = 12 * 60,
) -> Driver:
    return Driver(
        id=did,
        qualifications=["passenger"],
        shift_start=shift_start,
        shift_end=shift_end,
        depot_id=depot,
        accessibility_training=trained,
        availability=available,
        qualified_vehicle_types=types or ["car", "minibus"],
    )


def trip(
    tid: str,
    pickup: str,
    dropoff: str,
    *,
    earliest: int = 60,
    latest: int = 180,
    max_ride: int = 90,
    max_wait: int = 40,
    wheelchair: WheelchairType = WheelchairType.NONE,
    companions: int = 0,
    lift: bool = False,
    ramp: bool = False,
    assist: bool = False,
    appt_start: int | None = None,
    appt_end: int | None = None,
    detour: float = 3.0,
    frozen: bool = False,
    via: str | None = None,
    quota: int | None = None,
) -> TripRequest:
    return TripRequest(
        id=tid,
        pseudonymous_passenger_id=f"p-{tid}",
        pickup_zone=pickup,
        dropoff_zone=dropoff,
        requested_at=0,
        earliest_pickup=earliest,
        latest_pickup=latest,
        appointment_start=appt_start,
        appointment_end=appt_end,
        max_ride_time=max_ride,
        max_wait_time=max_wait,
        wheelchair_requirement=wheelchair,
        companion_count=companions,
        needs_lift=lift,
        needs_ramp=ramp,
        needs_boarding_assistance=assist,
        frozen=frozen,
        max_detour_ratio=detour,
        via_zone=via,
        quota_minutes_remaining=quota,
    )


def problem(
    vehicles: list[Vehicle],
    drivers: list[Driver],
    requests: list[TripRequest],
    *,
    pid: str = "hand-built",
) -> DayProblem:
    return DayProblem(
        problem_id=pid,
        seed=1,
        passengers=[],
        vehicles=vehicles,
        drivers=drivers,
        requests=requests,
        travel=generate_day("tiny", seed=1).travel,
    )
