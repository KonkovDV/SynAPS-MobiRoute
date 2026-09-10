"""A frozen trip keeps the vehicle, the driver and the clocks it was published with."""

from __future__ import annotations

import pytest

from mobiroute.dispatch.online_insertion import (
    _frozen_break_ids,
    compute_diff,
    online_insert,
)
from mobiroute.domain.models import ReasonCode
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import native_available
from tests.factories import driver, problem, trip, vehicle


def _corridor() -> tuple[object, object]:
    """Same corridor, wide windows: insertion feasibility is not the obstacle."""
    seated = trip(
        "t-seed",
        "Z_NORTH",
        "Z_SOUTH",
        earliest=60,
        latest=400,
        max_wait=400,
        max_ride=200,
    )
    extra = trip(
        "t-new",
        "Z_NORTH",
        "Z_SOUTH",
        earliest=60,
        latest=400,
        max_wait=400,
        max_ride=200,
    )
    return seated, extra


def test_a_frozen_trip_is_not_reseated_behind_the_operator() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    seated, extra = _corridor()
    p = problem([vehicle("v1")], [driver("d1"), driver("d2")], [seated])
    base = solve_greedy(p)
    assert "t-seed" in base.served_requests
    # A committed route that reached dispatch without a driver record.
    driverless = [rp.model_copy(update={"driver_id": ""}) for rp in base.route_plans]
    base = base.model_copy(update={"route_plans": driverless})
    _updated, res, diff = online_insert(p, base, extra)
    assert "t-new" not in res.served_requests
    assert res.reason_codes["t-new"] == ReasonCode.MANUAL_REVIEW_REQUIRED.value
    assert diff.broken_frozen_trips == []
    assert [rp.driver_id for rp in res.route_plans] == [""]


def test_the_guard_matches_the_diff_it_publishes() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    seated, _extra = _corridor()
    p = problem([vehicle("v1")], [driver("d1"), driver("d2")], [seated])
    base = solve_greedy(p)
    frozen = set(base.served_requests)
    swapped_routes = [rp.model_copy(update={"driver_id": "d2"}) for rp in base.route_plans]
    swapped = base.model_copy(update={"route_plans": swapped_routes})
    retimed_routes = [
        rp.model_copy(update={"arrival_times": {k: v + 7 for k, v in rp.arrival_times.items()}})
        for rp in base.route_plans
    ]
    retimed = base.model_copy(update={"route_plans": retimed_routes})
    for other in (swapped, retimed):
        assert _frozen_break_ids(base, other, frozen) == sorted(frozen)
        assert compute_diff(base, other, frozen).broken_frozen_trips == sorted(frozen)
    assert _frozen_break_ids(base, base, frozen) == []
    assert compute_diff(base, base, frozen).unchanged_frozen_trips == sorted(frozen)
