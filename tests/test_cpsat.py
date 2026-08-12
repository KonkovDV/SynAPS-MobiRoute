"""Tiny CP-SAT correctness and honesty tests."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.domain.models import WheelchairType
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _too_large_for_tiny_cpsat():
    base = generate_day("tiny", seed=1)
    vehs = []
    drvs = []
    for i in range(13):
        src_v = base.vehicles[i % len(base.vehicles)]
        src_d = base.drivers[i % len(base.drivers)]
        v = src_v.model_copy(update={"id": f"v-extra-{i:02d}"})
        d = src_d.model_copy(update={"id": f"d-extra-{i:02d}", "depot_id": v.depot_id})
        vehs.append(v)
        drvs.append(d)
    return base.model_copy(update={"vehicles": vehs, "drivers": drvs})


def test_cpsat_optimal_implies_notary():
    p = problem(
        [vehicle("v1"), vehicle("v2", depot="Z_DEPOT_2")],
        [driver("d1"), driver("d2", depot="Z_DEPOT_2")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=180),
            trip("b", "Z_EAST", "Z_WEST", earliest=80, latest=200),
        ],
    )
    res = solve_cpsat(p, time_limit_s=8.0)
    assert res.solution_type == "CPSAT_TINY"
    report = check_plan(p, res)
    assert report.feasible == res.verified_feasible
    if res.status == "OPTIMAL":
        assert res.verified_feasible
        assert res.solver_config.get("ortools_status") == 4  # CpSolverStatus.OPTIMAL
        assert not report.violations
    if res.status != "NOT_VERIFIED":
        assert res.verified_feasible


def test_cpsat_never_optimal_when_notary_fails_is_enforced():
    p = generate_day("tiny", seed=7)
    p = p.model_copy(update={"requests": p.requests[:6]})
    res = solve_cpsat(p, time_limit_s=8.0)
    if not res.verified_feasible:
        assert res.status == "NOT_VERIFIED"
    if res.status == "OPTIMAL":
        assert res.verified_feasible


def test_cpsat_fallback_not_optimal():
    p = _too_large_for_tiny_cpsat()
    res = solve_cpsat(p, time_limit_s=2.0)
    assert res.solution_type == "CPSAT_FALLBACK_GREEDY"
    assert res.status != "OPTIMAL"
    assert res.status in {"HEURISTIC_FEASIBLE", "PARTIAL", "NOT_VERIFIED"}


def test_cpsat_large_heuristic_feasible_or_partial():
    p = _too_large_for_tiny_cpsat()
    res = solve_cpsat(p, time_limit_s=1.0)
    assert res.status != "OPTIMAL"
    assert res.solution_type == "CPSAT_FALLBACK_GREEDY"


def test_cpsat_assigns_explicit_driver():
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("a", "Z_NORTH", "Z_SOUTH")],
    )
    res = solve_cpsat(p, time_limit_s=5.0)
    if "a" in res.served_requests:
        assert res.route_plans[0].driver_id == "d1"
        assert res.driver_assignments
        assert res.driver_assignments[0].driver_id == "d1"


def test_cpsat_appointment_end_binds_not_cabin_hold():
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip(
                "med",
                "Z_NORTH",
                "Z_HOSP_A",
                earliest=60,
                latest=200,
                appt_start=150,
                appt_end=200,
                max_ride=80,
            )
        ],
    )
    res = solve_cpsat(p, time_limit_s=5.0)
    if "med" in res.served_requests:
        it = res.route_plans[0].passenger_itineraries[0]
        assert it.dropoff_time >= 120
        assert it.dropoff_time <= 200
    report = check_plan(p, res)
    assert not any("APPOINTMENT_START" in v for v in report.violations) or not res.verified_feasible


def test_cpsat_deterministic():
    p = problem(
        [vehicle("v1"), vehicle("v2", depot="Z_DEPOT_2")],
        [driver("d1"), driver("d2", depot="Z_DEPOT_2")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH"),
            trip("b", "Z_EAST", "Z_WEST", earliest=90, latest=200),
        ],
    )
    a = solve_cpsat(p, time_limit_s=5.0)
    b = solve_cpsat(p, time_limit_s=5.0)
    assert a.served_requests == b.served_requests
    assert a.status == b.status
    assert a.input_hash == b.input_hash


def test_cpsat_sequential_not_pooling_model():
    p = problem(
        [vehicle("v1", capacity=4)],
        [driver("d1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=220),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=70, latest=230),
        ],
    )
    cpsat = solve_cpsat(p, time_limit_s=5.0)
    greedy = solve_greedy(p)
    assert cpsat.solver_config.get("pooling") is False
    assert greedy.solver_config.get("pooling") is True
    if cpsat.verified_feasible and cpsat.served_requests:
        for rp in cpsat.route_plans:
            if rp.passenger_load_after_stop:
                assert max(rp.passenger_load_after_stop.values()) <= 1
    # honesty: do not call greedy OPTIMAL
    assert greedy.status != "OPTIMAL"


def test_cpsat_rejects_incompatible_wheelchair():
    p = problem(
        [vehicle("v1", wheelchairs=0, types=[])],
        [driver("d1")],
        [
            trip(
                "w",
                "Z_NORTH",
                "Z_SOUTH",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
            )
        ],
    )
    res = solve_cpsat(p, time_limit_s=3.0)
    assert "w" not in res.served_requests
    assert res.rejected_requests[0].reason_code
