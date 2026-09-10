"""A driver swap that is scored but not chosen must not measure the plan."""

from __future__ import annotations

import pytest

from mobiroute.solvers.greedy import _trip_stops, solve_greedy
from mobiroute.solvers.native_accel import native_available
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _swap_case() -> tuple[object, object]:
    """The assist trip is out of reach for every payload, so the swap always loses."""
    seated = trip("t-seed", "Z_NORTH", "Z_SOUTH", earliest=60, latest=400, max_wait=400)
    assist = trip("t-assist", "Z_EAST", "Z_WEST", earliest=0, latest=2, assist=True)
    p = problem(
        [vehicle("v1")],
        [driver("d1", trained=False, unavail=[(0, 200)]), driver("d2")],
        [seated, assist],
    )
    return p, seated


def _solve(p, seated):
    return solve_greedy(p, seed_stops={"v1": _trip_stops(seated)}, seed_drivers={"v1": "d1"})


def test_a_losing_driver_swap_does_not_measure_the_published_route() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p, seated = _swap_case()
    res = _solve(p, seated)
    route = next(rp for rp in res.route_plans if rp.vehicle_id == "v1")
    assert route.driver_id == "d1"
    # d1 rests until 200, so the published pickup cannot be measured without it.
    pickup = next(i.pickup_time for i in route.passenger_itineraries if i.trip_id == "t-seed")
    assert pickup >= 200
    report = check_plan(p, res)
    assert report.feasible, report.violations
    assert res.objective_values["violations"] == 0.0


def test_the_scored_assist_trip_is_refused_with_evidence() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p, seated = _swap_case()
    res = _solve(p, seated)
    assert "t-assist" not in res.served_requests
    assert "t-assist" in {r.trip_id for r in res.rejected_requests}
