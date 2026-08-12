"""Deterministic synthetic Moscow-zone day generator."""

from __future__ import annotations

import uuid
from typing import Literal

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
    TravelMatrix,
    TripRequest,
    Vehicle,
)

Mode = Literal[
    "tiny",
    "small",
    "medium",
    "large",
    "wheelchair_heavy",
    "medical_priority",
    "pooled_rides",
    "disruption",
    "infeasible",
    "fairness_stress",
    "peak_demand",
    "driver_unavailable",
    "vehicle_breakdown",
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
    "stress_200",
]

MODES: tuple[str, ...] = (
    "tiny",
    "small",
    "medium",
    "large",
    "wheelchair_heavy",
    "medical_priority",
    "pooled_rides",
    "disruption",
    "infeasible",
    "fairness_stress",
    "peak_demand",
    "driver_unavailable",
    "vehicle_breakdown",
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
    "stress_200",
)

_MODE_SIZES = {
    "tiny": (5, 20, 2),
    "small": (20, 200, 3),
    "medium": (60, 1000, 4),
    "large": (180, 2000, 5),
    "wheelchair_heavy": (10, 40, 2),
    "medical_priority": (8, 30, 2),
    "pooled_rides": (6, 24, 2),
    "disruption": (5, 20, 2),
    "infeasible": (2, 30, 1),
    "fairness_stress": (8, 40, 4),
    "peak_demand": (15, 120, 3),
    "driver_unavailable": (5, 20, 2),
    "vehicle_breakdown": (5, 20, 2),
}

ZONES = [
    "Z_NORTH",
    "Z_SOUTH",
    "Z_EAST",
    "Z_WEST",
    "Z_CENTER",
    "Z_HOSP_A",
    "Z_HOSP_B",
    "Z_REHAB",
    "Z_SOCIAL",
    "Z_DEPOT_1",
    "Z_DEPOT_2",
    "Z_DEPOT_3",
    "Z_DEPOT_4",
]


def _stable_uuid(seed: int, kind: str, i: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mobiroute:{seed}:{kind}:{i}"))


def _travel_matrix() -> TravelMatrix:
    n = len(ZONES)
    minutes: list[list[int]] = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(0)
            else:
                # deterministic pseudo-distance from indices
                row.append(8 + abs(i - j) * 3 + ((i * 7 + j * 3) % 5))
        minutes.append(row)
    return TravelMatrix(zones=list(ZONES), minutes=minutes)


def generate_day(mode: str = "tiny", seed: int = 42) -> DayProblem:
    if mode == "stress_200":
        from mobiroute.adapters.stress_day import generate_stress_day

        return generate_stress_day(seed)
    if mode.startswith("ops_"):
        from mobiroute.adapters.ops_scenarios import generate_ops_day

        return generate_ops_day(mode, seed)
    if mode not in _MODE_SIZES:
        raise ValueError(f"unknown generator mode: {mode}")
    n_veh, n_req, n_depots = _MODE_SIZES[mode]
    travel = _travel_matrix()
    depots = [f"Z_DEPOT_{i + 1}" for i in range(n_depots)]

    vehicles: list[Vehicle] = []
    drivers: list[Driver] = []
    for i in range(n_veh):
        vid = _stable_uuid(seed, "vehicle", i)
        did = _stable_uuid(seed, "driver", i)
        depot = depots[i % n_depots]
        accessible = (i % 3) != 2 or mode in {"wheelchair_heavy", "tiny"}
        if mode == "infeasible":
            accessible = False
        vehicles.append(
            Vehicle(
                id=vid,
                vehicle_type="car" if i % 4 else "minibus",
                passenger_capacity=3 if i % 4 else 8,
                wheelchair_capacity=1 if accessible else 0,
                lift_available=accessible and (i % 2 == 0),
                ramp_available=accessible and (i % 2 == 1),
                accessible_features=["lift"] if accessible else [],
                compatible_wheelchair_types=(
                    [WheelchairType.MANUAL, WheelchairType.POWER] if accessible else []
                ),
                depot_id=depot,
                shift_start=0,
                shift_end=12 * 60,
                service_area=list(ZONES),
            )
        )
        drivers.append(
            Driver(
                id=did,
                qualifications=["passenger"] + (["accessibility"] if accessible else []),
                shift_start=0,
                shift_end=12 * 60,
                depot_id=depot,
                language_capabilities=["ru"],
                accessibility_training=accessible,
                availability=True,
                qualified_vehicle_types=["car", "minibus"],
            )
        )

    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(n_req):
        pid = _stable_uuid(seed, "passenger", i)
        tid = _stable_uuid(seed, "trip", i)
        medical = mode == "medical_priority" or (i % 7 == 0)
        wheelchair = mode == "wheelchair_heavy" or (i % 5 == 0)
        zone_p = ZONES[i % 5]
        zone_d = "Z_HOSP_A" if medical else ZONES[(i + 3) % 5]
        if mode == "fairness_stress":
            zone_p = ZONES[i % 4]  # skew demand
        elig = EligibilityClass.MEDICAL if medical else EligibilityClass.STANDARD
        if i % 11 == 0:
            elig = EligibilityClass.CHILD
        earliest = 60 + (i * 7) % 400
        passengers.append(
            PassengerProfile(
                pseudonymous_id=pid,
                eligibility_class=elig,
                accessibility_requirements=AccessibilityRequirements(
                    needs_lift=wheelchair and (i % 2 == 0),
                    needs_ramp=wheelchair and (i % 2 == 1),
                    wheelchair_type=WheelchairType.MANUAL if wheelchair else WheelchairType.NONE,
                    companion_count=1 if i % 9 == 0 else 0,
                ),
                wheelchair_type=WheelchairType.MANUAL if wheelchair else WheelchairType.NONE,
                companion_count=1 if i % 9 == 0 else 0,
                medical_priority=medical,
                privacy_class=PrivacyClass.PUBLIC_SYNTHETIC,
                data_provenance=DataProvenance.SYNTHETIC,
            )
        )
        requests.append(
            TripRequest(
                id=tid,
                pseudonymous_passenger_id=pid,
                pickup_zone=zone_p,
                dropoff_zone=zone_d,
                requested_at=0,
                earliest_pickup=earliest,
                latest_pickup=earliest + 45,
                appointment_start=earliest + 40 if medical else None,
                appointment_end=earliest + 90 if medical else None,
                max_ride_time=60,
                max_wait_time=30,
                wheelchair_requirement=(
                    WheelchairType.MANUAL if wheelchair else WheelchairType.NONE
                ),
                companion_count=1 if i % 9 == 0 else 0,
                service_priority=(
                    ServicePriority.MEDICAL_URGENT if medical else ServicePriority.STANDARD
                ),
                eligibility_class=elig,
                needs_lift=wheelchair and (i % 2 == 0),
                needs_ramp=wheelchair and (i % 2 == 1),
                needs_boarding_assistance=wheelchair,
                medical_priority=medical,
                data_provenance=DataProvenance.SYNTHETIC,
            )
        )

    # stable sort
    requests.sort(key=lambda t: (t.earliest_pickup, t.id))
    vehicles.sort(key=lambda v: v.id)
    drivers.sort(key=lambda d: d.id)
    passengers.sort(key=lambda p: p.pseudonymous_id)

    if mode == "driver_unavailable" and drivers:
        drivers[0] = drivers[0].model_copy(update={"availability": False})
    if mode == "vehicle_breakdown" and vehicles:
        v0 = vehicles[0]
        vehicles[0] = v0.model_copy(
            update={
                "shift_end": v0.shift_start,
                "unavailable_intervals": [(v0.shift_start, 12 * 60)],
            }
        )

    return DayProblem(
        problem_id=f"moscow_synth_{mode}_{seed}",
        seed=seed,
        passengers=passengers,
        vehicles=vehicles,
        drivers=drivers,
        requests=requests,
        travel=travel,
        data_provenance=DataProvenance.SYNTHETIC,
        claim_level="synthetic_benchmark",
    )
