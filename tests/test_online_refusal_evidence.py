"""Truncated refusal evidence must say how many refusals it does not show."""

from __future__ import annotations

import pytest

from mobiroute.dispatch.online_insertion import (
    EVIDENCE_VEHICLE_LIMIT,
    _refusal_evidence,
    online_insert,
)
from mobiroute.domain.models import WheelchairType
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import native_available
from tests.factories import driver, problem, trip, vehicle


def test_the_helper_counts_what_it_hides() -> None:
    many = [f"v{i:02d}:NO_COMPATIBLE_VEHICLE" for i in range(EVIDENCE_VEHICLE_LIMIT + 3)]
    out = _refusal_evidence(many)
    assert len(out) == EVIDENCE_VEHICLE_LIMIT + 1
    assert out[-1] == "+3 more vehicles"
    single = _refusal_evidence([*many[: EVIDENCE_VEHICLE_LIMIT + 1]])
    assert single[-1] == "+1 more vehicle"
    assert _refusal_evidence([]) == []
    # A vehicle that failed at several insertion points is still one refusal.
    assert _refusal_evidence(["v1:INSERT_INFEASIBLE"] * 4) == ["v1:INSERT_INFEASIBLE"]


def test_a_refused_online_trip_reports_the_vehicles_it_omitted() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    fleet = [vehicle(f"v{i:02d}", wheelchairs=0) for i in range(EVIDENCE_VEHICLE_LIMIT + 2)]
    drivers = [driver(f"d{i:02d}") for i in range(EVIDENCE_VEHICLE_LIMIT + 2)]
    seated = trip("t-seed", "Z_NORTH", "Z_SOUTH", earliest=60, latest=400, max_wait=400)
    p = problem(fleet, drivers, [seated])
    base = solve_greedy(p)
    wav = trip("t-wav", "Z_NORTH", "Z_SOUTH", wheelchair=WheelchairType.MANUAL)
    _updated, res, _diff = online_insert(p, base, wav)
    assert "t-wav" not in res.served_requests
    detail = next(r.detail for r in res.rejected_requests if r.trip_id == "t-wav")
    assert detail.count("NO_COMPATIBLE_VEHICLE") == EVIDENCE_VEHICLE_LIMIT
    assert detail.endswith("+2 more vehicles")
