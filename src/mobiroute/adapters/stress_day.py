"""Harsh synthetic social-taxi day: 200 vehicles, mixed failures. Not real MAST."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import ZONES, _stable_uuid, _travel_matrix
from mobiroute.domain.models import (
    BookingStatus,
    DataProvenance,
    EligibilityClass,
    PrivacyClass,
    ServicePriority,
    WheelchairType,
)
from mobiroute.domain.requests import (
    AccessibilityRequirements,
    DayProblem,
    Driver,
    PassengerProfile,
    TripRequest,
    Vehicle,
)

N_VEHICLES = 200
N_REQUESTS = 3200
SERVICE_START = 0
SERVICE_END = 13 * 60
N_DEPOTS = 4

# Pickup zones skewed north (fairness stress), not uniform city demand.
_PICK_ZONES = (
    ["Z_NORTH"] * 5
    + ["Z_CENTER"] * 2
    + ["Z_EAST"]
    + ["Z_WEST"]
    + ["Z_SOUTH"]
    + ["Z_SOCIAL"]
    + ["Z_REHAB"]
)


def _uid(seed: int, kind: str, i: int) -> str:
    return _stable_uuid(seed, f"stress_{kind}", i)


def _fleet(seed: int) -> tuple[list[Vehicle], list[Driver]]:
    depots = [f"Z_DEPOT_{i + 1}" for i in range(N_DEPOTS)]
    vehicles: list[Vehicle] = []
    drivers: list[Driver] = []
    for i in range(N_VEHICLES):
        vid, did = _uid(seed, "vehicle", i), _uid(seed, "driver", i)
        depot = depots[i % N_DEPOTS]
        slot = i % 20
        if slot < 8:
            vtype, cap_p, cap_w, lift, ramp = "sedan", 3, 0, False, False
            wtypes: list[WheelchairType] = []
        elif slot < 15:
            vtype, cap_p, cap_w, lift, ramp = "wav", 3, 1, True, False
            wtypes = [WheelchairType.MANUAL, WheelchairType.POWER]
        elif slot < 18:
            vtype, cap_p, cap_w, lift, ramp = "wav", 3, 1, False, True
            wtypes = [WheelchairType.MANUAL, WheelchairType.POWER, WheelchairType.SCOOTER]
        elif slot == 18:
            vtype, cap_p, cap_w, lift, ramp = "minibus", 12, 2, True, True
            wtypes = [WheelchairType.MANUAL, WheelchairType.POWER, WheelchairType.SCOOTER]
        else:
            vtype, cap_p, cap_w, lift, ramp = "stretcher", 2, 1, True, False
            wtypes = [WheelchairType.MANUAL, WheelchairType.STRETCHER]

        area = list(ZONES)
        if i % 23 == 0:
            area = [depot, "Z_CENTER", "Z_NORTH", "Z_HOSP_A"]
        unavail: list[tuple[int, int]] = []
        if i % 17 == 0:
            unavail = [(240, 300)]  # midday shop / fuel
        shift_end = SERVICE_END
        if i % 71 == 0:
            shift_end = SERVICE_START  # dead on arrival
            unavail = [(SERVICE_START, SERVICE_END)]

        vehicles.append(
            Vehicle(
                id=vid,
                vehicle_type=vtype,
                passenger_capacity=cap_p,
                wheelchair_capacity=cap_w,
                lift_available=lift,
                ramp_available=ramp,
                accessible_features=["lift"] if lift else (["ramp"] if ramp else []),
                compatible_wheelchair_types=wtypes,
                depot_id=depot,
                shift_start=SERVICE_START,
                shift_end=shift_end,
                service_area=area,
                unavailable_intervals=unavail,
            )
        )
        trained = not (slot < 8 and i % 19 == 0)
        available = i % 61 != 0
        drivers.append(
            Driver(
                id=did,
                qualifications=["passenger"] + (["accessibility"] if trained else []),
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                depot_id=depot,
                language_capabilities=["ru"],
                accessibility_training=trained,
                availability=available,
                qualified_vehicle_types=[vtype, "sedan", "wav", "minibus", "stretcher"],
            )
        )
    return vehicles, drivers


def _trip_mix(
    seed: int,
    i: int,
    *,
    outbound: TripRequest | None = None,
) -> tuple[PassengerProfile, TripRequest]:
    pid, tid = _uid(seed, "passenger", i), _uid(seed, "trip", i)
    pick = _PICK_ZONES[i % len(_PICK_ZONES)]
    medical = i % 7 == 0 or outbound is not None
    via = i % 22 == 3 and outbound is None
    stretcher = i % 211 == 7 and outbound is None
    scooter = i % 53 == 11 and not stretcher
    power = i % 29 == 5 and not stretcher and not scooter
    manual = (i % 5 == 0 or outbound is not None) and not stretcher and not scooter and not power
    if stretcher:
        wc = WheelchairType.STRETCHER
    elif scooter:
        wc = WheelchairType.SCOOTER
    elif power:
        wc = WheelchairType.POWER
    elif manual:
        wc = WheelchairType.MANUAL
    else:
        wc = WheelchairType.NONE
    if medical:
        drop = "Z_HOSP_A" if i % 2 == 0 else "Z_HOSP_B"
    elif i % 31 == 0:
        drop = "Z_SOCIAL"
    else:
        drop = ZONES[(i + 4) % 5]
    if outbound is not None:
        pick, drop = outbound.dropoff_zone, outbound.pickup_zone
        pid = outbound.pseudonymous_passenger_id
    peak = i % 5 < 2
    earliest = (180 + (i * 3) % 130) if peak else (50 + (i * 11) % 680)
    latest = earliest + (20 if medical else 40)
    appt_s = earliest + 35 if medical else None
    appt_e = earliest + 85 if medical else None
    if outbound is not None:
        earliest = outbound.appointment_end or (outbound.earliest_pickup + 40)
        latest = earliest + 60
        appt_s, appt_e = None, None
    elig = EligibilityClass.STANDARD
    if medical:
        elig = EligibilityClass.PALLIATIVE if i % 17 == 0 else EligibilityClass.MEDICAL
    elif i % 11 == 0:
        elig = EligibilityClass.CHILD
    companions = 2 if i % 47 == 0 else (1 if i % 9 == 0 else 0)
    quota = 22 if i % 13 == 0 else None
    status = BookingStatus.REQUESTED
    if outbound is None:
        if i % 37 == 0:
            status = BookingStatus.CANCELLED
        elif i % 43 == 0:
            status = BookingStatus.NO_SHOW
    lift = (
        wc in {WheelchairType.MANUAL, WheelchairType.POWER, WheelchairType.STRETCHER} and i % 2 == 0
    )
    ramp = wc != WheelchairType.NONE and not lift
    passenger = PassengerProfile(
        pseudonymous_id=pid,
        eligibility_class=elig,
        accessibility_requirements=AccessibilityRequirements(
            needs_lift=lift,
            needs_ramp=ramp,
            needs_boarding_assistance=wc != WheelchairType.NONE,
            wheelchair_type=wc,
            companion_count=companions,
        ),
        wheelchair_type=wc,
        companion_count=companions,
        medical_priority=medical,
        privacy_class=PrivacyClass.PUBLIC_SYNTHETIC,
        data_provenance=DataProvenance.SYNTHETIC,
        quota_minutes_remaining=quota,
    )
    trip = TripRequest(
        id=tid,
        pseudonymous_passenger_id=pid,
        pickup_zone=pick,
        dropoff_zone=drop,
        requested_at=0,
        earliest_pickup=earliest,
        latest_pickup=latest,
        appointment_start=appt_s,
        appointment_end=appt_e,
        max_ride_time=90 if via else 55,
        max_wait_time=30,
        wheelchair_requirement=wc,
        companion_count=companions,
        service_priority=(ServicePriority.MEDICAL_URGENT if medical else ServicePriority.STANDARD),
        eligibility_class=elig,
        booking_status=status,
        boarding_duration=8 if stretcher else (5 if wc != WheelchairType.NONE else 3),
        alighting_duration=6 if stretcher else 2,
        needs_lift=lift,
        needs_ramp=ramp,
        needs_boarding_assistance=wc != WheelchairType.NONE,
        medical_priority=medical,
        max_detour_ratio=2.2 if via else 3.0,
        data_provenance=DataProvenance.SYNTHETIC,
        trip_purpose="MEDICAL" if medical else ("VIA_PHARMACY" if via else "OTHER"),
        same_vehicle_as=None if outbound is None else outbound.id,
        insert_immediately_after=None if outbound is None else outbound.id,
        via_zone="Z_SOCIAL" if via else None,
        via_service_duration=8 if via else 2,
        quota_minutes_remaining=quota,
    )
    return passenger, trip


def generate_stress_day(seed: int = 42) -> DayProblem:
    """200 vehicles / 3200 requests, mixed WAV/VIA/quota/unavail/wait-return.

    claim_level remains synthetic_benchmark. Not live Moscow trips.
    """
    vehicles, drivers = _fleet(seed)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    skip = False
    for i in range(N_REQUESTS):
        if skip:
            skip = False
            continue
        if i % 41 == 0 and i + 1 < N_REQUESTS:
            p0, outbound = _trip_mix(seed, i)
            _, ret = _trip_mix(seed, i + 1, outbound=outbound)
            passengers.append(p0)
            requests.extend((outbound, ret))
            skip = True
            continue
        p, t = _trip_mix(seed, i)
        passengers.append(p)
        requests.append(t)

    requests.sort(key=lambda t: (t.earliest_pickup, t.id))
    vehicles.sort(key=lambda v: v.id)
    drivers.sort(key=lambda d: d.id)
    passengers.sort(key=lambda p: p.pseudonymous_id)
    missing = sorted({v.depot_id for v in vehicles if v.depot_id not in ZONES})
    if missing:
        raise ValueError(f"stress_200 depot(s) missing from travel matrix: {missing}")
    return DayProblem(
        problem_id=f"moscow_synth_stress_200_{seed}",
        seed=seed,
        passengers=passengers,
        vehicles=vehicles,
        drivers=drivers,
        requests=requests,
        travel=_travel_matrix(),
        data_provenance=DataProvenance.SYNTHETIC,
        claim_level="synthetic_benchmark",
    )


def inventory(problem: DayProblem) -> dict[str, int]:
    reqs = problem.requests
    vehs = problem.vehicles
    drvs = problem.drivers
    return {
        "vehicles": len(vehs),
        "drivers": len(drvs),
        "requests": len(reqs),
        "wav_vehicles": sum(1 for v in vehs if v.wheelchair_capacity > 0),
        "dead_vehicles": sum(1 for v in vehs if v.shift_end <= v.shift_start),
        "shop_unavail": sum(1 for v in vehs if v.unavailable_intervals),
        "restricted_area": sum(1 for v in vehs if 0 < len(v.service_area) < len(ZONES)),
        "untrained_drivers": sum(1 for d in drvs if not d.accessibility_training),
        "unavailable_drivers": sum(1 for d in drvs if not d.availability),
        "via_trips": sum(1 for t in reqs if t.via_zone),
        "wait_return": sum(1 for t in reqs if t.same_vehicle_as),
        "medical": sum(1 for t in reqs if t.medical_priority),
        "wheelchair": sum(1 for t in reqs if t.wheelchair_requirement.value != "NONE"),
        "stretcher": sum(1 for t in reqs if t.wheelchair_requirement.value == "STRETCHER"),
        "scooter": sum(1 for t in reqs if t.wheelchair_requirement.value == "SCOOTER"),
        "quota": sum(1 for t in reqs if t.quota_minutes_remaining is not None),
        "cancelled": sum(1 for t in reqs if t.booking_status.value == "CANCELLED"),
        "no_show": sum(1 for t in reqs if t.booking_status.value == "NO_SHOW"),
        "companions": sum(1 for t in reqs if t.companion_count > 0),
    }
