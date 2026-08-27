"""Driver rest/unavail occupancy is policy data, not a labour-law certificate."""

from __future__ import annotations

import pytest

from mobiroute.adapters.fingerprint import fingerprint_problem
from mobiroute.domain.requests import PlanningResult
from mobiroute.solvers.greedy import _trip_stops, simulate_stop_sequence, solve_greedy
from mobiroute.solvers.insertion_kernel import DriverKernel, VehicleKernel, vehicle_payload
from mobiroute.solvers.native_accel import native_available
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _result(routes, served) -> PlanningResult:
    return PlanningResult(
        status="FEASIBLE",
        solution_type="ADVERSARIAL",
        verified_feasible=False,
        served_requests=served,
        rejected_requests=[],
        route_plans=routes,
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
    )


def test_python_soa_rejects_occupancy_through_driver_rest() -> None:
    t = trip("t", "Z_NORTH", "Z_SOUTH", earliest=100, latest=160, max_ride=90, max_wait=40)
    p = problem([vehicle("v1")], [driver("d1", unavail=[(90, 110)])], [t])
    plan = simulate_stop_sequence(p, p.vehicles[0], "d1", _trip_stops(t), {t.id: t})
    assert plan is None


def test_notary_flags_driver_rest_occupancy() -> None:
    t = trip("t", "Z_NORTH", "Z_SOUTH", earliest=100, latest=160, max_ride=90, max_wait=40)
    open_p = problem([vehicle("v1")], [driver("d1")], [t])
    plan = simulate_stop_sequence(open_p, open_p.vehicles[0], "d1", _trip_stops(t), {t.id: t})
    assert plan is not None
    blocked = problem([vehicle("v1")], [driver("d1", unavail=[(90, 110)])], [t])
    report = check_plan(blocked, _result([plan], ["t"]))
    assert not report.feasible
    assert any(v.startswith("DRIVER_REST:") for v in report.violations)


def test_fingerprint_includes_driver_rest_windows() -> None:
    t = trip("t", "Z_NORTH", "Z_SOUTH")
    open_p = problem([vehicle("v1")], [driver("d1")], [t])
    rest_p = problem([vehicle("v1")], [driver("d1", unavail=[(90, 110)])], [t])
    assert fingerprint_problem(open_p) != fingerprint_problem(rest_p)


def test_native_payload_flattens_driver_rest_after_vehicle_shop() -> None:
    vk = VehicleKernel(
        depot=0,
        shift_start=0,
        shift_end=720,
        cap_p=4,
        cap_w=2,
        flags=0,
        wmask=0,
        unavail=((10, 20),),
        area=(),
    )
    dk = DriverKernel(shift_start=0, shift_end=720, assist=True, unavail=((90, 110),))
    _veh, una = vehicle_payload(vk, dk)
    assert una == [10, 20, 90, 110]


def test_greedy_rejects_trip_inside_driver_rest() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    t = trip("t", "Z_NORTH", "Z_SOUTH", earliest=100, latest=160, max_ride=90, max_wait=40)
    p = problem([vehicle("v1")], [driver("d1", unavail=[(90, 110)])], [t])
    res = solve_greedy(p)
    assert "t" not in res.served_requests
