"""Driver assignment adversarial tests."""

from __future__ import annotations

from mobiroute.domain.driver_assignment import select_driver
from mobiroute.domain.models import WheelchairType
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def test_driver_not_chosen_only_by_depot_id():
    untrained = driver("untrained", trained=False, depot="Z_DEPOT_1")
    trained = driver("trained", trained=True, depot="Z_DEPOT_1")
    p = problem(
        [vehicle("v1", depot="Z_DEPOT_1")],
        [untrained, trained],
        [
            trip(
                "need",
                "Z_NORTH",
                "Z_HOSP_A",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
            )
        ],
    )
    # untrained sorts first by construction of select_driver (id sort: trained < untrained? )
    # 'trained' < 'untrained' lexicographically, but needs_accessibility filters untrained out.
    chosen = select_driver(p, p.vehicles[0], needs_accessibility=True, occupied_driver_ids=set())
    assert chosen == "trained"
    res = solve_greedy(p)
    assert res.route_plans
    assert res.route_plans[0].driver_id == "trained"


def test_no_fallback_to_foreign_depot_driver():
    p = problem(
        [vehicle("v1", depot="Z_DEPOT_1")],
        [driver("other", depot="Z_DEPOT_2", trained=True)],
        [trip("a", "Z_NORTH", "Z_SOUTH")],
    )
    res = solve_greedy(p)
    assert "a" not in res.served_requests
    assert res.rejected_requests
    assert res.rejected_requests[0].reason_code in {"NO_DRIVER", "DRIVER_SHIFT_CONFLICT"}


def test_one_driver_not_double_booked():
    p = problem(
        [
            vehicle("v1", depot="Z_DEPOT_1"),
            vehicle("v2", depot="Z_DEPOT_1"),
        ],
        [driver("only", depot="Z_DEPOT_1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=120),
            trip("b", "Z_EAST", "Z_WEST", earliest=60, latest=120),
        ],
    )
    res = solve_greedy(p)
    drivers = [rp.driver_id for rp in res.route_plans if rp.driver_id]
    assert len(drivers) == len(set(drivers))
    report = check_plan(p, res)
    assert not any("DRIVER_DOUBLE_BOOK" in v for v in report.violations)


def test_driver_shift_blocks_assignment():
    p = problem(
        [vehicle("v1")],
        [driver("late", shift_start=500, shift_end=720)],
        [trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=90)],
    )
    res = solve_greedy(p)
    assert "a" not in res.served_requests


def test_driver_vehicle_type_qualification():
    p = problem(
        [vehicle("v1", vtype="car")],
        [driver("bus-only", types=["minibus"])],
        [trip("a", "Z_NORTH", "Z_SOUTH")],
    )
    res = solve_greedy(p)
    assert "a" not in res.served_requests


def test_driver_unavailable_mode_does_not_assign_absent_driver():
    from mobiroute.adapters.synthetic_data import generate_day

    p = generate_day("driver_unavailable", seed=3)
    absent = next(d.id for d in p.drivers if not d.availability)
    res = solve_greedy(p)
    assert all(rp.driver_id != absent for rp in res.route_plans)
