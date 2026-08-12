"""Policy-shaped synthetic ops scenarios (Moscow social-taxi rules + world paratransit).

Not real Moscow trips. Zones are labels. claim_level remains synthetic_benchmark.
Clock: minute 0 = 06:00, minute 780 = 19:00 (operator service hours, mgovos.ru 2026-08).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from mobiroute.adapters.synthetic_data import ZONES, _stable_uuid, _travel_matrix
from mobiroute.domain.models import (
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

# 06:00-19:00 service day used by Moscow social taxi (mgovos.ru, retrieved 2026-08-12).
SERVICE_START = 0
SERVICE_END = 13 * 60
PICKUP_WINDOW = 15  # ADA-style ±15 min pickup window used as synthetic latest-earliest span.
DEST_WAIT_CAP = 60  # Moscow: суммарное ожидание в пункте назначения ≤ 60 мин.
MAX_COMPANIONS = 2


OpsScenarioId = Literal[
    "ops_clinic_peak",
    "ops_wait_return",
    "ops_airport",
    "ops_palliative",
    "ops_group",
    "ops_wav_shortage",
    "ops_companions",
    "ops_subscription_vs_nextday",
    "ops_fairness_districts",
    "ops_shift_close",
    "ops_stretcher",
    "ops_scooter",
    "ops_medical_vs_dacha",
    "ops_service_area",
    "ops_untrained_driver",
    "ops_agency_missed",
    "ops_via",
    "ops_quota",
]

OPS_MODES: tuple[str, ...] = (
    "ops_clinic_peak",
    "ops_wait_return",
    "ops_airport",
    "ops_palliative",
    "ops_group",
    "ops_wav_shortage",
    "ops_companions",
    "ops_subscription_vs_nextday",
    "ops_fairness_districts",
    "ops_shift_close",
    "ops_stretcher",
    "ops_scooter",
    "ops_medical_vs_dacha",
    "ops_service_area",
    "ops_untrained_driver",
    "ops_agency_missed",
    "ops_via",
    "ops_quota",
)


@dataclass(frozen=True, slots=True)
class OpsEvent:
    kind: str
    trip_id: str | None = None
    vehicle_id: str | None = None
    driver_id: str | None = None
    delay_minutes: int = 0
    note: str = ""


@dataclass(frozen=True, slots=True)
class OpsScript:
    scenario_id: str
    title: str
    moscow_rule: str
    world_practice: str
    kernel_owns: str
    not_kernel: str
    events: tuple[OpsEvent, ...]


def _uid(seed: int, kind: str, i: int) -> str:
    return _stable_uuid(seed, kind, i)


def _passenger(
    pid: str,
    *,
    elig: EligibilityClass,
    wheelchair: WheelchairType = WheelchairType.NONE,
    companions: int = 0,
    medical: bool = False,
    quota_minutes_remaining: int | None = None,
) -> PassengerProfile:
    return PassengerProfile(
        pseudonymous_id=pid,
        eligibility_class=elig,
        accessibility_requirements=AccessibilityRequirements(
            wheelchair_type=wheelchair,
            companion_count=companions,
            needs_lift=wheelchair in {WheelchairType.MANUAL, WheelchairType.POWER},
            needs_boarding_assistance=wheelchair != WheelchairType.NONE,
        ),
        wheelchair_type=wheelchair,
        companion_count=companions,
        medical_priority=medical,
        privacy_class=PrivacyClass.PUBLIC_SYNTHETIC,
        data_provenance=DataProvenance.SYNTHETIC,
        quota_minutes_remaining=quota_minutes_remaining,
    )


def _trip(
    tid: str,
    pid: str,
    pu: str,
    do: str,
    *,
    earliest: int,
    latest: int | None = None,
    appt_start: int | None = None,
    appt_end: int | None = None,
    wheelchair: WheelchairType = WheelchairType.NONE,
    companions: int = 0,
    purpose: str = "OTHER",
    channel: str = "STANDARD",
    medical: bool = False,
    lift: bool = False,
    ramp: bool = False,
    assist: bool = False,
    same_vehicle_as: str | None = None,
    insert_immediately_after: str | None = None,
    board: int | None = None,
    alight: int | None = None,
    max_ride: int = 70,
    frozen: bool = False,
    elig: EligibilityClass = EligibilityClass.STANDARD,
    priority: ServicePriority = ServicePriority.STANDARD,
    via_zone: str | None = None,
    quota_minutes_remaining: int | None = None,
) -> TripRequest:
    wc = wheelchair != WheelchairType.NONE
    return TripRequest(
        id=tid,
        pseudonymous_passenger_id=pid,
        pickup_zone=pu,
        dropoff_zone=do,
        requested_at=0,
        earliest_pickup=earliest,
        latest_pickup=latest if latest is not None else earliest + PICKUP_WINDOW * 2,
        appointment_start=appt_start,
        appointment_end=appt_end,
        max_ride_time=max_ride,
        max_wait_time=60,
        wheelchair_requirement=wheelchair,
        companion_count=companions,
        service_priority=priority,
        eligibility_class=elig,
        boarding_duration=board if board is not None else (8 if wc else 3),
        alighting_duration=alight if alight is not None else (5 if wc else 2),
        needs_lift=lift or (wc and wheelchair != WheelchairType.SCOOTER),
        needs_ramp=ramp,
        needs_boarding_assistance=assist or wc,
        medical_priority=medical,
        frozen=frozen,
        trip_purpose=purpose,
        channel=channel,
        same_vehicle_as=same_vehicle_as,
        insert_immediately_after=insert_immediately_after,
        via_zone=via_zone,
        quota_minutes_remaining=quota_minutes_remaining,
        data_provenance=DataProvenance.SYNTHETIC,
    )


def _fleet(
    seed: int, *, sedans: int, wavs: int, group_bus: bool
) -> tuple[list[Vehicle], list[Driver]]:
    vehicles: list[Vehicle] = []
    drivers: list[Driver] = []
    depots = ["Z_DEPOT_1", "Z_DEPOT_2", "Z_DEPOT_3"]
    for i in range(sedans):
        vid, did = _uid(seed, "ops_sedan", i), _uid(seed, "ops_sedan_d", i)
        depot = depots[i % 3]
        vehicles.append(
            Vehicle(
                id=vid,
                vehicle_type="sedan",
                passenger_capacity=3,
                wheelchair_capacity=0,
                lift_available=False,
                ramp_available=False,
                compatible_wheelchair_types=[],
                depot_id=depot,
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                service_area=list(ZONES),
            )
        )
        drivers.append(
            Driver(
                id=did,
                qualifications=["passenger"],
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                depot_id=depot,
                accessibility_training=False,
                qualified_vehicle_types=["sedan"],
            )
        )
    for i in range(wavs):
        vid, did = _uid(seed, "ops_wav", i), _uid(seed, "ops_wav_d", i)
        depot = depots[i % 3]
        vehicles.append(
            Vehicle(
                id=vid,
                vehicle_type="minibus",
                passenger_capacity=8,
                wheelchair_capacity=1,
                lift_available=i % 2 == 0,
                ramp_available=i % 2 == 1,
                compatible_wheelchair_types=[WheelchairType.MANUAL, WheelchairType.POWER],
                depot_id=depot,
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                service_area=list(ZONES),
            )
        )
        drivers.append(
            Driver(
                id=did,
                qualifications=["passenger", "accessibility"],
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                depot_id=depot,
                accessibility_training=True,
                qualified_vehicle_types=["minibus"],
            )
        )
    if group_bus:
        vid, did = _uid(seed, "ops_bus", 0), _uid(seed, "ops_bus_d", 0)
        vehicles.append(
            Vehicle(
                id=vid,
                vehicle_type="bus",
                passenger_capacity=18,
                wheelchair_capacity=2,
                lift_available=True,
                ramp_available=True,
                compatible_wheelchair_types=[
                    WheelchairType.MANUAL,
                    WheelchairType.POWER,
                    WheelchairType.SCOOTER,
                ],
                depot_id="Z_DEPOT_1",
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                service_area=list(ZONES),
            )
        )
        drivers.append(
            Driver(
                id=did,
                qualifications=["passenger", "accessibility", "group"],
                shift_start=SERVICE_START,
                shift_end=SERVICE_END,
                depot_id="Z_DEPOT_1",
                accessibility_training=True,
                qualified_vehicle_types=["bus", "minibus"],
            )
        )
    return vehicles, drivers


def _pack(
    seed: int,
    scenario: str,
    vehicles: list[Vehicle],
    drivers: list[Driver],
    passengers: list[PassengerProfile],
    requests: list[TripRequest],
) -> DayProblem:
    travel = _travel_matrix()
    requests = sorted(requests, key=lambda t: (t.earliest_pickup, t.id))
    # Simulator leaves depot at shift_start; pull-out is delayed to the first window.
    first_pu = min(t.earliest_pickup for t in requests) if requests else SERVICE_START
    pull = max(SERVICE_START, first_pu - 45)
    vehicles = [v.model_copy(update={"shift_start": pull}) for v in vehicles]
    drivers = [d.model_copy(update={"shift_start": pull}) for d in drivers]
    return DayProblem(
        problem_id=f"moscow_ops_{scenario}_{seed}",
        seed=seed,
        passengers=passengers,
        vehicles=vehicles,
        drivers=drivers,
        requests=requests,
        travel=travel,
        data_provenance=DataProvenance.SYNTHETIC,
        claim_level="synthetic_benchmark",
    )


def scenario_clinic_peak(seed: int = 42) -> DayProblem:
    """Morning clinic cluster: medical appointments 09:00-11:00, mixed WAV/sedan."""
    vehicles, drivers = _fleet(seed, sedans=2, wavs=2, group_bus=False)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(10):
        pid, tid = _uid(seed, "ops_clinic_p", i), _uid(seed, "ops_clinic_t", i)
        wc = WheelchairType.MANUAL if i % 3 == 0 else WheelchairType.NONE
        medical = True
        earliest = 180 + (i * 12)  # from 09:00
        appt = earliest + 35
        passengers.append(
            _passenger(
                pid,
                elig=EligibilityClass.MEDICAL,
                wheelchair=wc,
                companions=1 if i % 4 == 0 else 0,
                medical=True,
            )
        )
        requests.append(
            _trip(
                tid,
                pid,
                ZONES[i % 5],
                "Z_HOSP_A",
                earliest=earliest,
                appt_start=appt,
                appt_end=appt + 40,
                wheelchair=wc,
                companions=1 if i % 4 == 0 else 0,
                purpose="MEDICAL",
                medical=medical,
                lift=wc != WheelchairType.NONE,
                assist=wc != WheelchairType.NONE,
                elig=EligibilityClass.MEDICAL,
                priority=ServicePriority.MEDICAL_URGENT,
            )
        )
    return _pack(seed, "ops_clinic_peak", vehicles, drivers, passengers, requests)


def scenario_wait_return(seed: int = 42) -> DayProblem:
    """Outbound to clinic + same-vehicle wait-and-return (Moscow ≤60 min wait)."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=1, group_bus=False)
    pid = _uid(seed, "ops_wr_p", 0)
    out_id = _uid(seed, "ops_wr_out", 0)
    ret_id = _uid(seed, "ops_wr_ret", 0)
    passengers = [
        _passenger(
            pid,
            elig=EligibilityClass.MEDICAL,
            wheelchair=WheelchairType.MANUAL,
            companions=1,
            medical=True,
        )
    ]
    outbound = _trip(
        out_id,
        pid,
        "Z_NORTH",
        "Z_HOSP_A",
        earliest=200,
        appt_start=240,
        appt_end=280,
        wheelchair=WheelchairType.MANUAL,
        companions=1,
        purpose="MEDICAL",
        medical=True,
        lift=True,
        assist=True,
        elig=EligibilityClass.MEDICAL,
        priority=ServicePriority.APPOINTMENT_PROTECTED,
    )
    ret = _trip(
        ret_id,
        pid,
        "Z_HOSP_A",
        "Z_NORTH",
        earliest=240,
        latest=240 + DEST_WAIT_CAP,
        wheelchair=WheelchairType.MANUAL,
        companions=1,
        purpose="MEDICAL",
        medical=True,
        lift=True,
        assist=True,
        same_vehicle_as=out_id,
        insert_immediately_after=out_id,
        elig=EligibilityClass.MEDICAL,
        priority=ServicePriority.APPOINTMENT_PROTECTED,
    )
    filler = _trip(
        _uid(seed, "ops_wr_fill", 0),
        _uid(seed, "ops_wr_fill_p", 0),
        "Z_EAST",
        "Z_WEST",
        earliest=220,
        purpose="OTHER",
    )
    passengers.append(_passenger(_uid(seed, "ops_wr_fill_p", 0), elig=EligibilityClass.STANDARD))
    return _pack(seed, "ops_wait_return", vehicles, drivers, passengers, [outbound, ret, filler])


def scenario_airport(seed: int = 42) -> DayProblem:
    """Airport/station trip: 24h-30d booking is intake policy; kernel sees a long-lead trip."""
    vehicles, drivers = _fleet(seed, sedans=2, wavs=1, group_bus=False)
    pid, tid = _uid(seed, "ops_air_p", 0), _uid(seed, "ops_air_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.STANDARD, companions=1)]
    requests = [
        _trip(
            tid,
            pid,
            "Z_WEST",
            "Z_SOCIAL",
            earliest=60,
            latest=60 + 40,
            companions=1,
            purpose="AIRPORT",
            max_ride=90,
        )
    ]
    for i in range(4):
        p2, t2 = _uid(seed, "ops_air_local_p", i), _uid(seed, "ops_air_local_t", i)
        passengers.append(_passenger(p2, elig=EligibilityClass.STANDARD))
        requests.append(
            _trip(t2, p2, ZONES[i % 5], ZONES[(i + 2) % 5], earliest=80 + i * 20, purpose="OTHER")
        )
    return _pack(seed, "ops_airport", vehicles, drivers, passengers, requests)


def scenario_palliative(seed: int = 42) -> DayProblem:
    """Separate palliative ID channel: higher priority, trained WAV, not a legal ID check."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=1, group_bus=False)
    pid, tid = _uid(seed, "ops_pal_p", 0), _uid(seed, "ops_pal_t", 0)
    passengers = [
        _passenger(
            pid,
            elig=EligibilityClass.PALLIATIVE,
            wheelchair=WheelchairType.MANUAL,
            medical=True,
        )
    ]
    requests = [
        _trip(
            tid,
            pid,
            "Z_SOUTH",
            "Z_HOSP_B",
            earliest=150,
            appt_start=190,
            appt_end=230,
            wheelchair=WheelchairType.MANUAL,
            purpose="MEDICAL",
            channel="PALLIATIVE_ID",
            medical=True,
            lift=True,
            assist=True,
            elig=EligibilityClass.PALLIATIVE,
            priority=ServicePriority.MEDICAL_URGENT,
        )
    ]
    for i in range(3):
        p2, t2 = _uid(seed, "ops_pal_std_p", i), _uid(seed, "ops_pal_std_t", i)
        passengers.append(_passenger(p2, elig=EligibilityClass.STANDARD))
        requests.append(
            _trip(t2, p2, "Z_NORTH", "Z_CENTER", earliest=140 + i * 10, purpose="OTHER")
        )
    return _pack(seed, "ops_palliative", vehicles, drivers, passengers, requests)


def scenario_group(seed: int = 42) -> DayProblem:
    """MGO VOI-style group booking: one bus, several organization passengers."""
    vehicles, drivers = _fleet(seed, sedans=0, wavs=0, group_bus=True)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(6):
        pid, tid = _uid(seed, "ops_grp_p", i), _uid(seed, "ops_grp_t", i)
        wc = WheelchairType.MANUAL if i < 2 else WheelchairType.NONE
        passengers.append(
            _passenger(pid, elig=EligibilityClass.ORGANIZATION, wheelchair=wc, companions=0)
        )
        requests.append(
            _trip(
                tid,
                pid,
                "Z_EAST",
                "Z_SOCIAL",
                earliest=300,
                latest=360,
                wheelchair=wc,
                purpose="EDUCATION",
                channel="ORG_GROUP",
                lift=wc != WheelchairType.NONE,
                assist=wc != WheelchairType.NONE,
                elig=EligibilityClass.ORGANIZATION,
                max_ride=90,
            )
        )
    return _pack(seed, "ops_group", vehicles, drivers, passengers, requests)


def scenario_wav_shortage(seed: int = 42) -> DayProblem:
    """More wheelchair trips than WAV seats — explainable rejects, not silent drops."""
    vehicles, drivers = _fleet(seed, sedans=2, wavs=1, group_bus=False)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(5):
        pid, tid = _uid(seed, "ops_wav_p", i), _uid(seed, "ops_wav_t", i)
        passengers.append(
            _passenger(
                pid,
                elig=EligibilityClass.MEDICAL,
                wheelchair=WheelchairType.MANUAL,
                medical=True,
            )
        )
        requests.append(
            _trip(
                tid,
                pid,
                ZONES[i % 5],
                "Z_HOSP_A",
                earliest=180 + i * 8,
                appt_start=220 + i * 8,
                appt_end=260 + i * 8,
                wheelchair=WheelchairType.MANUAL,
                purpose="MEDICAL",
                medical=True,
                lift=True,
                assist=True,
                elig=EligibilityClass.MEDICAL,
                priority=ServicePriority.MEDICAL_URGENT,
            )
        )
    return _pack(seed, "ops_wav_shortage", vehicles, drivers, passengers, requests)


def scenario_companions(seed: int = 42) -> DayProblem:
    """Passenger + two companions (Moscow max) vs sedan capacity 3."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    pid, tid = _uid(seed, "ops_cmp_p", 0), _uid(seed, "ops_cmp_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.CHILD, companions=MAX_COMPANIONS)]
    requests = [
        _trip(
            tid,
            pid,
            "Z_CENTER",
            "Z_REHAB",
            earliest=120,
            companions=MAX_COMPANIONS,
            purpose="EDUCATION",
            elig=EligibilityClass.CHILD,
        )
    ]
    return _pack(seed, "ops_companions", vehicles, drivers, passengers, requests)


def scenario_subscription_vs_nextday(seed: int = 42) -> DayProblem:
    """Recurring dialysis-like trips vs one-off next-day demand (FTA 50% analog as label only)."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=1, group_bus=False)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(3):
        pid, tid = _uid(seed, "ops_sub_p", i), _uid(seed, "ops_sub_t", i)
        passengers.append(_passenger(pid, elig=EligibilityClass.MEDICAL, medical=True))
        requests.append(
            _trip(
                tid,
                pid,
                "Z_NORTH",
                "Z_HOSP_B",
                earliest=120 + i * 5,
                appt_start=160 + i * 5,
                appt_end=200 + i * 5,
                purpose="MEDICAL",
                channel="SUBSCRIPTION",
                medical=True,
                elig=EligibilityClass.MEDICAL,
                priority=ServicePriority.APPOINTMENT_PROTECTED,
                frozen=True,
            )
        )
    for i in range(3):
        pid, tid = _uid(seed, "ops_nd_p", i), _uid(seed, "ops_nd_t", i)
        passengers.append(_passenger(pid, elig=EligibilityClass.STANDARD))
        requests.append(
            _trip(
                tid,
                pid,
                "Z_SOUTH",
                "Z_CENTER",
                earliest=125 + i * 8,
                purpose="OTHER",
                channel="NEXT_DAY",
            )
        )
    return _pack(seed, "ops_subscription_vs_nextday", vehicles, drivers, passengers, requests)


def scenario_fairness_districts(seed: int = 42) -> DayProblem:
    """Skewed demand from two zones; fairness is multi-metric, never one index."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=1, group_bus=False)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(8):
        pid, tid = _uid(seed, "ops_fair_p", i), _uid(seed, "ops_fair_t", i)
        zone = "Z_NORTH" if i < 6 else "Z_SOUTH"
        passengers.append(_passenger(pid, elig=EligibilityClass.STANDARD))
        requests.append(_trip(tid, pid, zone, "Z_CENTER", earliest=200 + i * 15, purpose="OTHER"))
    return _pack(seed, "ops_fairness_districts", vehicles, drivers, passengers, requests)


def scenario_shift_close(seed: int = 42) -> DayProblem:
    """Late trip that cannot return to depot by 19:00."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    pid, tid = _uid(seed, "ops_late_p", 0), _uid(seed, "ops_late_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.STANDARD)]
    requests = [
        _trip(
            tid,
            pid,
            "Z_NORTH",
            "Z_SOUTH",
            earliest=SERVICE_END - 25,
            latest=SERVICE_END - 5,
            purpose="OTHER",
            max_ride=80,
        )
    ]
    return _pack(seed, "ops_shift_close", vehicles, drivers, passengers, requests)


def scenario_stretcher(seed: int = 42) -> DayProblem:
    """Stretcher is exclusive: cannot share the cabin with another passenger."""
    vehicles, drivers = _fleet(seed, sedans=0, wavs=1, group_bus=False)
    vehicles[0] = vehicles[0].model_copy(
        update={
            "compatible_wheelchair_types": [
                WheelchairType.MANUAL,
                WheelchairType.POWER,
                WheelchairType.STRETCHER,
            ]
        }
    )
    pid_s, tid_s = _uid(seed, "ops_str_p", 0), _uid(seed, "ops_str_t", 0)
    pid_a, tid_a = _uid(seed, "ops_str_amb_p", 0), _uid(seed, "ops_str_amb_t", 0)
    passengers = [
        _passenger(
            pid_s, elig=EligibilityClass.MEDICAL, wheelchair=WheelchairType.STRETCHER, medical=True
        ),
        _passenger(pid_a, elig=EligibilityClass.STANDARD),
    ]
    requests = [
        _trip(
            tid_s,
            pid_s,
            "Z_NORTH",
            "Z_HOSP_A",
            earliest=200,
            latest=240,
            wheelchair=WheelchairType.STRETCHER,
            purpose="MEDICAL",
            medical=True,
            lift=True,
            assist=True,
            elig=EligibilityClass.MEDICAL,
            priority=ServicePriority.MEDICAL_URGENT,
        ),
        _trip(
            tid_a,
            pid_a,
            "Z_NORTH",
            "Z_HOSP_A",
            earliest=205,
            latest=245,
            purpose="OTHER",
        ),
    ]
    return _pack(seed, "ops_stretcher", vehicles, drivers, passengers, requests)


def scenario_scooter(seed: int = 42) -> DayProblem:
    """Scooter is not in the default WAV type mask (MANUAL/POWER only)."""
    vehicles, drivers = _fleet(seed, sedans=0, wavs=1, group_bus=False)
    pid, tid = _uid(seed, "ops_sco_p", 0), _uid(seed, "ops_sco_t", 0)
    passengers = [
        _passenger(pid, elig=EligibilityClass.STANDARD, wheelchair=WheelchairType.SCOOTER)
    ]
    requests = [
        _trip(
            tid,
            pid,
            "Z_WEST",
            "Z_CENTER",
            earliest=180,
            wheelchair=WheelchairType.SCOOTER,
            purpose="OTHER",
            lift=True,
            assist=True,
        )
    ]
    return _pack(seed, "ops_scooter", vehicles, drivers, passengers, requests)


def scenario_medical_vs_dacha(seed: int = 42) -> DayProblem:
    """RUSSPASS: medical destinations outrank dacha when capacity is tight."""
    vehicles, drivers = _fleet(seed, sedans=0, wavs=1, group_bus=False)
    pid_m, tid_m = _uid(seed, "ops_med_p", 0), _uid(seed, "ops_med_t", 0)
    pid_d, tid_d = _uid(seed, "ops_dacha_p", 0), _uid(seed, "ops_dacha_t", 0)
    passengers = [
        _passenger(
            pid_m, elig=EligibilityClass.MEDICAL, wheelchair=WheelchairType.MANUAL, medical=True
        ),
        _passenger(pid_d, elig=EligibilityClass.STANDARD, wheelchair=WheelchairType.MANUAL),
    ]
    requests = [
        _trip(
            tid_m,
            pid_m,
            "Z_SOUTH",
            "Z_HOSP_A",
            earliest=200,
            latest=230,
            appt_start=240,
            appt_end=270,
            wheelchair=WheelchairType.MANUAL,
            purpose="MEDICAL",
            medical=True,
            lift=True,
            assist=True,
            elig=EligibilityClass.MEDICAL,
            priority=ServicePriority.MEDICAL_URGENT,
        ),
        _trip(
            tid_d,
            pid_d,
            "Z_SOUTH",
            "Z_WEST",
            earliest=200,
            latest=230,
            wheelchair=WheelchairType.MANUAL,
            purpose="DACHA",
            lift=True,
            assist=True,
            priority=ServicePriority.FLEXIBLE,
        ),
    ]
    return _pack(seed, "ops_medical_vs_dacha", vehicles, drivers, passengers, requests)


def scenario_service_area(seed: int = 42) -> DayProblem:
    """Vehicle bound to a district cannot take a trip outside that set."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    vehicles[0] = vehicles[0].model_copy(
        update={"service_area": ["Z_NORTH", "Z_CENTER", vehicles[0].depot_id]}
    )
    pid, tid = _uid(seed, "ops_area_p", 0), _uid(seed, "ops_area_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.STANDARD)]
    requests = [
        _trip(tid, pid, "Z_SOUTH", "Z_WEST", earliest=180, purpose="OTHER"),
    ]
    return _pack(seed, "ops_service_area", vehicles, drivers, passengers, requests)


def scenario_untrained_driver(seed: int = 42) -> DayProblem:
    """Wheelchair boarding assistance requires a trained driver."""
    vehicles, drivers = _fleet(seed, sedans=0, wavs=1, group_bus=False)
    drivers[0] = drivers[0].model_copy(update={"accessibility_training": False})
    pid, tid = _uid(seed, "ops_untr_p", 0), _uid(seed, "ops_untr_t", 0)
    passengers = [
        _passenger(
            pid, elig=EligibilityClass.MEDICAL, wheelchair=WheelchairType.MANUAL, medical=True
        )
    ]
    requests = [
        _trip(
            tid,
            pid,
            "Z_EAST",
            "Z_HOSP_B",
            earliest=160,
            wheelchair=WheelchairType.MANUAL,
            purpose="MEDICAL",
            medical=True,
            lift=True,
            assist=True,
            elig=EligibilityClass.MEDICAL,
        )
    ]
    return _pack(seed, "ops_untrained_driver", vehicles, drivers, passengers, requests)


def scenario_agency_missed(seed: int = 42) -> DayProblem:
    """Agency missed trip (vehicle never arrives) — Zvenigorod-style complaint, synthetic."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    pid, tid = _uid(seed, "ops_miss_p", 0), _uid(seed, "ops_miss_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.STANDARD)]
    requests = [
        _trip(
            tid,
            pid,
            "Z_WEST",
            "Z_CENTER",
            earliest=180,
            purpose="MEDICAL",
            medical=True,
            elig=EligibilityClass.MEDICAL,
        )
    ]
    return _pack(seed, "ops_agency_missed", vehicles, drivers, passengers, requests)


def scenario_via(seed: int = 42) -> DayProblem:
    """Clinic then pharmacy: passenger stays onboard at the VIA stop."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    pid, tid = _uid(seed, "ops_via_p", 0), _uid(seed, "ops_via_t", 0)
    passengers = [_passenger(pid, elig=EligibilityClass.MEDICAL, medical=True)]
    requests = [
        _trip(
            tid,
            pid,
            "Z_NORTH",
            "Z_CENTER",
            earliest=60,
            latest=240,
            appt_end=240,
            purpose="MEDICAL",
            medical=True,
            elig=EligibilityClass.MEDICAL,
            via_zone="Z_HOSP_A",
            max_ride=90,
        )
    ]
    return _pack(seed, "ops_via", vehicles, drivers, passengers, requests)


def scenario_quota(seed: int = 42) -> DayProblem:
    """Remaining entitlement minutes vs a long ride (not annual 80h CRM)."""
    vehicles, drivers = _fleet(seed, sedans=1, wavs=0, group_bus=False)
    pid_ok, tid_ok = _uid(seed, "ops_q_ok_p", 0), _uid(seed, "ops_q_ok_t", 0)
    pid_no, tid_no = _uid(seed, "ops_q_no_p", 0), _uid(seed, "ops_q_no_t", 0)
    passengers = [
        _passenger(pid_ok, elig=EligibilityClass.STANDARD, quota_minutes_remaining=80),
        _passenger(pid_no, elig=EligibilityClass.STANDARD, quota_minutes_remaining=1),
    ]
    requests = [
        _trip(
            tid_ok,
            pid_ok,
            "Z_NORTH",
            "Z_SOUTH",
            earliest=60,
            quota_minutes_remaining=80,
        ),
        _trip(
            tid_no,
            pid_no,
            "Z_EAST",
            "Z_WEST",
            earliest=90,
            quota_minutes_remaining=1,
            max_ride=70,
        ),
    ]
    return _pack(seed, "ops_quota", vehicles, drivers, passengers, requests)


BUILDERS: dict[str, Callable[[int], DayProblem]] = {
    "ops_clinic_peak": scenario_clinic_peak,
    "ops_wait_return": scenario_wait_return,
    "ops_airport": scenario_airport,
    "ops_palliative": scenario_palliative,
    "ops_group": scenario_group,
    "ops_wav_shortage": scenario_wav_shortage,
    "ops_companions": scenario_companions,
    "ops_subscription_vs_nextday": scenario_subscription_vs_nextday,
    "ops_fairness_districts": scenario_fairness_districts,
    "ops_shift_close": scenario_shift_close,
    "ops_stretcher": scenario_stretcher,
    "ops_scooter": scenario_scooter,
    "ops_medical_vs_dacha": scenario_medical_vs_dacha,
    "ops_service_area": scenario_service_area,
    "ops_untrained_driver": scenario_untrained_driver,
    "ops_agency_missed": scenario_agency_missed,
    "ops_via": scenario_via,
    "ops_quota": scenario_quota,
}


SCRIPTS: dict[str, OpsScript] = {
    "ops_clinic_peak": OpsScript(
        scenario_id="ops_clinic_peak",
        title="Morning clinic peak",
        moscow_rule="Medical destinations; booking 24h-3d; service 06:00-19:00; companion allowed.",
        world_practice="Appointment drop-off window typically -30/0; longer wheelchair dwell.",
        kernel_owns="Assignment, windows, WAV match, appointment, pooling load.",
        not_kernel="Phone queue, mos.ru registry, fare 210 ₽/h.",
        events=(
            OpsEvent(kind="day_ahead", note="greedy day plan"),
            OpsEvent(kind="no_show", note="first served trip no-show if any"),
        ),
    ),
    "ops_wait_return": OpsScript(
        scenario_id="ops_wait_return",
        title="Wait-and-return at clinic",
        moscow_rule="Need wait at destination and/or return; total wait ≤ 60 min; same vehicle.",
        world_practice="Will-call / open return is premium in ADA; not required next-day service.",
        kernel_owns="same_vehicle_as + insert_immediately_after; notary.",
        not_kernel="How long the doctor actually takes.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_airport": OpsScript(
        scenario_id="ops_airport",
        title="Airport / station transfer",
        moscow_rule="Book 24h-30d ahead for stations/airports; still >=24h notice.",
        world_practice="Airport pickups often will-call; long deadhead.",
        kernel_owns="Long ride, companion seat, depot return by shift end.",
        not_kernel="30-day intake calendar (CRM).",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_palliative": OpsScript(
        scenario_id="ops_palliative",
        title="Palliative ID channel",
        moscow_rule="Separate phone +7 (495) 357-10-01; coordination +7 (499) 444-04-57.",
        world_practice="NEMT / hospice trips often protected in lexicographic objectives.",
        kernel_owns="Priority sort + trained WAV; eligibility is a label.",
        not_kernel="Issuing palliative ID.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_group": OpsScript(
        scenario_id="ops_group",
        title="Organization / group trip",
        moscow_rule="MGO VOI group bookings via mgo_voi@mail.ru / Bakhrushina office.",
        world_practice="Subscription/group loads on high-capacity accessible buses.",
        kernel_owns="Capacity 18 / 2 WC, pooling on one bus.",
        not_kernel="Paper originals at Bakhrushina 21-23.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_wav_shortage": OpsScript(
        scenario_id="ops_wav_shortage",
        title="WAV shortage",
        moscow_rule="Refusal if no free compatible vehicle for date/time (operator policy pages).",
        world_practice="ADA treats a pattern of capacity denials as a constraint; we only explain.",
        kernel_owns="Reason codes NO_COMPATIBLE_VEHICLE / INSERT_INFEASIBLE; never silent drop.",
        not_kernel="Buying more vehicles.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_companions": OpsScript(
        scenario_id="ops_companions",
        title="Two companions",
        moscow_rule="Up to two accompanying persons.",
        world_practice="PCA/attendant often unpaid in ADA; the person still occupies a seat.",
        kernel_owns="seats = 1 + companions vs sedan capacity 3.",
        not_kernel="Who legally counts as attendant.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_subscription_vs_nextday": OpsScript(
        scenario_id="ops_subscription_vs_nextday",
        title="Subscription vs next-day",
        moscow_rule="Work/study hour caps exist (80h) — billing, not this kernel.",
        world_practice="FTA 49 CFR 37.133: subscription ≤50% of capacity unless excess exists.",
        kernel_owns="Frozen subscription trips; remaining capacity for next-day.",
        not_kernel="Enforcing 50% as Moscow law (it is not).",
        events=(
            OpsEvent(kind="day_ahead"),
            OpsEvent(kind="cancel", note="cancel one subscription if served"),
        ),
    ),
    "ops_fairness_districts": OpsScript(
        scenario_id="ops_fairness_districts",
        title="District skew",
        moscow_rule="Citywide service; complaints about opaque refusals are org/UX signals.",
        world_practice="Equity-aware DARP: group acceptance and P95 wait, not Jain alone.",
        kernel_owns="Multi-metric fairness report; fair_by_single_metric=false.",
        not_kernel="Declaring the city fair.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_shift_close": OpsScript(
        scenario_id="ops_shift_close",
        title="Shift close 19:00",
        moscow_rule="Service daily 06:00-19:00; depot return required in the kernel model.",
        world_practice="Hours of service follow the comparable network; overtime is ops policy.",
        kernel_owns="Reject if leave+deadhead > shift_end.",
        not_kernel="Driver overtime pay.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_stretcher": OpsScript(
        scenario_id="ops_stretcher",
        title="Stretcher exclusive",
        moscow_rule="Lying patients need a dedicated cabin; not a shared sedan ride.",
        world_practice="Many ADA agencies exclude stretchers from complementary paratransit.",
        kernel_owns="STRETCHER cannot share load with another passenger.",
        not_kernel="Whether MAST legally carries stretchers.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_scooter": OpsScript(
        scenario_id="ops_scooter",
        title="Scooter vs WAV type mask",
        moscow_rule="Ask sedan vs ramp; unaided transfer. Scooter/power fit is a fleet fact.",
        world_practice="Default compatible types are MANUAL/POWER unless listed.",
        kernel_owns="NO_COMPATIBLE_VEHICLE when type mask excludes SCOOTER.",
        not_kernel="Buying a scooter-securement kit.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_medical_vs_dacha": OpsScript(
        scenario_id="ops_medical_vs_dacha",
        title="Medical vs dacha priority",
        moscow_rule="RUSSPASS (2025-07-31): hospital trips outrank dacha when cars are scarce.",
        world_practice="Lexicographic medical/appointment before flexible demand.",
        kernel_owns="trip_sort_key medical before FLEXIBLE/DACHA.",
        not_kernel="Seasonal dacha calendar May-Sep (CRM).",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_service_area": OpsScript(
        scenario_id="ops_service_area",
        title="District-bound vehicle",
        moscow_rule="Oblast vs city is fare; some vehicles still have a geographic beat.",
        world_practice="ADA complementary service is corridor-comparable, not citywide by default.",
        kernel_owns="service_area on pickup and dropoff.",
        not_kernel="420 RUB/h oblast tariff.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_untrained_driver": OpsScript(
        scenario_id="ops_untrained_driver",
        title="Untrained driver vs lift trip",
        moscow_rule="Ramp vehicle: can the passenger transfer unaided? Boarding help is a skill.",
        world_practice="Passenger assistance is a trained-operator constraint.",
        kernel_owns="needs_boarding_assistance requires accessibility_training.",
        not_kernel="Driver courtesy scores.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_agency_missed": OpsScript(
        scenario_id="ops_agency_missed",
        title="Agency missed trip",
        moscow_rule="Review: promised 11:30 oblast pickup, waited to 14:30, no vehicle.",
        world_practice="Agency lateness is not a passenger no-show (49 CFR 37.125).",
        kernel_owns="vehicle_unavailable recovery; reason codes.",
        not_kernel="Callback / order-number CRM; 3h wait is an org failure.",
        events=(
            OpsEvent(kind="day_ahead"),
            OpsEvent(kind="breakdown", note="assigned vehicle never arrives"),
        ),
    ),
    "ops_via": OpsScript(
        scenario_id="ops_via",
        title="Clinic then pharmacy",
        moscow_rule="Third stop (pharmacy after clinic) without leaving the cabin.",
        world_practice="ADA complementary is typically origin-destination; via is an add-on.",
        kernel_owns="VIA between pickup and dropoff; onboard; detour vs PU-VIA-DO.",
        not_kernel="Pharmacy opening hours / e-prescription CRM.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
    "ops_quota": OpsScript(
        scenario_id="ops_quota",
        title="Remaining hour quota",
        moscow_rule="Work/study hour caps (80h) are billing CRM; kernel sees remaining minutes.",
        world_practice="Subscription caps are policy; do not over-consume remaining minutes.",
        kernel_owns="quota_minutes_remaining vs door-to-door ride; QUOTA_EXCEEDED.",
        not_kernel="Annual 80h ledger, fare 210 ₽/h.",
        events=(OpsEvent(kind="day_ahead"),),
    ),
}


def generate_ops_day(mode: str, seed: int = 42) -> DayProblem:
    if mode not in BUILDERS:
        raise ValueError(f"unknown ops mode: {mode}")
    return BUILDERS[mode](seed)
