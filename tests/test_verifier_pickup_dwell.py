"""A passenger held on board at the curb must not vanish from the clocks.

The ride clock starts at pickup departure. A plan that keeps the vehicle at the
pickup after the curb wait, with the passenger already aboard, used to pass the
verifier while ride time and quota debit stayed unchanged.
"""

from __future__ import annotations

import pytest

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.domain.models import StopType
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import native_available
from mobiroute.validation.feasibility import check_plan


def test_extra_onboard_dwell_at_pickup_is_unexplained() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=42)
    res = solve_greedy(p)
    assert check_plan(p, res).feasible
    caught = 0
    for route in res.route_plans:
        stops = route.ordered_stops
        for k, stop in enumerate(stops):
            if stop.stop_type != StopType.PICKUP:
                continue
            arr = dict(route.arrival_times)
            dep = dict(route.departure_times)
            dep[stop.id] += 15
            for later in stops[k + 1 :]:
                arr[later.id] += 15
                dep[later.id] += 15
            forged = route.model_copy(
                update={"arrival_times": arr, "departure_times": dep, "ride_times": {}}
            )
            plans = [forged if r is route else r for r in res.route_plans]
            report = check_plan(p, res.model_copy(update={"route_plans": plans}))
            assert not report.feasible
            assert f"UNEXPLAINED_DWELL:{stop.trip_id}" in report.violations
            caught += 1
    assert caught > 0
