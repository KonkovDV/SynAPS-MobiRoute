"""Cordeau (2006) DARP instance loader.

Academic type-a/b files: header ``K n T Q L`` then ``2n+2`` nodes
(depot, n pickups, n dropoffs, return depot). Pickup ``i`` pairs with
dropoff ``i+n``. Travel is rounded Euclidean minutes on the integer
kernel grain. That is **not** the real-valued BKS algebra.

Literature BKS for ``a2-16`` is 294.25 (Ho et al. 2018 table of Cordeau
2006 / Ropke et al. 2007). MobiRoute does not claim that number: curb
wait is 5 min, travel is integer, Floyd-Warshall may shortcut rounded
edges.
"""

from __future__ import annotations

import math
from pathlib import Path

from mobiroute.domain.models import (
    ClaimLevel,
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

# Ho, S.C. et al. (2018) survey table; Cordeau (2006) instance a2-16.
CORDEAU_A2_16_BKS = 294.25

_REPO_A2_16 = (
    Path(__file__).resolve().parents[3] / "benchmark" / "instances" / "cordeau" / "a2-16.txt"
)


def parse_cordeau_darp(text: str, *, instance_id: str) -> DayProblem:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header = [int(tok) for tok in lines[0].split()]
    if len(header) != 5:
        raise ValueError(f"{instance_id}: header must be K n T Q L")
    n_vehicles, _n_field, max_duration, capacity, max_ride = header
    nodes: list[tuple[int, float, float, int, int, int, int]] = []
    for raw in lines[1:]:
        parts = raw.split()
        if len(parts) != 7:
            raise ValueError(f"{instance_id}: node line must have 7 fields")
        nid = int(parts[0])
        x, y = float(parts[1]), float(parts[2])
        service, load, earliest, latest = (
            int(parts[3]),
            int(parts[4]),
            int(parts[5]),
            int(parts[6]),
        )
        nodes.append((nid, x, y, service, load, earliest, latest))
    if len(nodes) < 4 or (len(nodes) - 2) % 2 != 0:
        raise ValueError(f"{instance_id}: expected 2n+2 nodes")
    n_requests = (len(nodes) - 2) // 2
    by_id = {row[0]: row for row in nodes}
    depot = by_id[0]
    zones = ["depot"] + [f"n{i}" for i in range(1, 2 * n_requests + 1)]
    coords: dict[str, tuple[float, float]] = {"depot": (depot[1], depot[2])}
    for i in range(1, 2 * n_requests + 1):
        coords[f"n{i}"] = (by_id[i][1], by_id[i][2])
    minutes: list[list[int]] = []
    for a in zones:
        row: list[int] = []
        ax, ay = coords[a]
        for b in zones:
            if a == b:
                row.append(0)
            else:
                bx, by = coords[b]
                row.append(round(math.hypot(ax - bx, ay - by)))
        minutes.append(row)
    travel = TravelMatrix(zones=zones, minutes=minutes)
    passengers: list[PassengerProfile] = []
    requests: list[TripRequest] = []
    for i in range(1, n_requests + 1):
        pu = by_id[i]
        do = by_id[i + n_requests]
        pid = f"p{i:02d}"
        tid = f"t{i:02d}"
        passengers.append(
            PassengerProfile(
                pseudonymous_id=pid,
                eligibility_class=EligibilityClass.STANDARD,
                accessibility_requirements=AccessibilityRequirements(),
                privacy_class=PrivacyClass.OPEN_SYNTHETIC,
                data_provenance=DataProvenance.UNKNOWN,
            )
        )
        requests.append(
            TripRequest(
                id=tid,
                pseudonymous_passenger_id=pid,
                pickup_zone=f"n{i}",
                dropoff_zone=f"n{i + n_requests}",
                requested_at=0,
                earliest_pickup=pu[5],
                latest_pickup=pu[6],
                appointment_start=do[5],
                appointment_end=do[6],
                max_ride_time=max_ride,
                max_wait_time=max_duration,
                boarding_duration=pu[3],
                alighting_duration=do[3],
                max_detour_ratio=50.0,
                data_provenance=DataProvenance.UNKNOWN,
                service_priority=ServicePriority.STANDARD,
                wheelchair_requirement=WheelchairType.NONE,
            )
        )
    vehicles = [
        Vehicle(
            id=f"v{k}",
            vehicle_type="cordeau",
            passenger_capacity=capacity,
            wheelchair_capacity=0,
            depot_id="depot",
            shift_start=0,
            shift_end=max_duration,
            service_area=list(zones),
        )
        for k in range(n_vehicles)
    ]
    drivers = [
        Driver(
            id=f"d{k}",
            qualifications=[],
            shift_start=0,
            shift_end=max_duration,
            depot_id="depot",
            accessibility_training=True,
            qualified_vehicle_types=["cordeau"],
        )
        for k in range(n_vehicles)
    ]
    return DayProblem(
        problem_id=instance_id,
        seed=0,
        passengers=passengers,
        vehicles=vehicles,
        drivers=drivers,
        requests=requests,
        travel=travel,
        data_provenance=DataProvenance.UNKNOWN,
        claim_level=ClaimLevel.OPEN_DATA.value,
    )


def load_cordeau_a2_16(path: Path | None = None) -> DayProblem:
    target = path or _REPO_A2_16
    return parse_cordeau_darp(target.read_text(encoding="utf-8"), instance_id="cordeau-a2-16")
