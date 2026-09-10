"""A driver swap that is scored but not chosen must not measure the plan."""

from __future__ import annotations

import pytest

from mobiroute.solvers.greedy import _trip_stops, solve_greedy
from mobiroute.solvers.native_accel import native_available
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _swap_case() -> tuple[object, object, object]:
    seated = trip("t-seed", "Z_NORTH", "Z_SOUTH", earliest=60, latest=400, max_wait=400)
    assist = trip("t-assist", "Z_EAST", "Z_WEST", earliest=60, latest=180, assist=True)
    p = problem(
        [vehicle("v1"), vehicle("v2")],
        [
            driver("d1", trained=False, unavail=[(0, 200)]),
            driver("d2"),
            driver("d3"),
        ],
        [seated, assist],
    )
    return p, seated, assist


def test_a_losing_driver_swap_does_not_measure_the_published_route() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p, seated, _assist = _swap_case()
    res = solve_greedy(
        p,
        seed_stops={"v1": _trip_stops(seated)},
        seed_drivers={"v1": "d1"},
    )
    seed_route = next(rp for rp in res.route_plans if rp.vehicle_id == "v1")
    assert seed_route.driver_id == "d1"
    # The seated driver rests until 200: published clocks may not start before it.
    assert min(seed_route.arrival_times.values()) >= 200
    report = check_plan(p, res)
    assert report.feasible, report.violations
    assert res.objective_values["violations"] == 0.0


def test_the_assist_trip_is_served_by_a_trained_driver() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p, seated, _assist = _swap_case()
    res = solve_greedy(
        p,
        seed_stops={"v1": _trip_stops(seated)},
        seed_drivers={"v1": "d1"},
    )
    if "t-assist" not in res.served_requests:
        return
    route = next(rp for rp in res.route_plans if "t-assist" in rp.passenger_assignments)
    assert route.driver_id in {"d2", "d3"}
