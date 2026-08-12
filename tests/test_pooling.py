"""Pooling and dynamic load tests."""

from __future__ import annotations

from mobiroute.domain.models import StopType, WheelchairType
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _max_load(result) -> int:
    m = 0
    for rp in result.route_plans:
        if rp.passenger_load_after_stop:
            m = max(m, max(rp.passenger_load_after_stop.values()))
    return m


def test_two_standard_passengers_can_share():
    p = problem(
        [vehicle(capacity=3, wheelchairs=0, types=[])],
        [driver()],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=200),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=70, latest=210),
        ],
    )
    greedy = solve_greedy(p)
    fifo = solve_fifo(p)
    assert greedy.verified_feasible
    assert fifo.verified_feasible
    assert greedy.status != "OPTIMAL"
    assert _max_load(greedy) >= 2
    assert _max_load(fifo) <= 1


def test_one_wheelchair_plus_ambulatory():
    p = problem(
        [vehicle(capacity=3, wheelchairs=1)],
        [driver(trained=True)],
        [
            trip(
                "w",
                "Z_NORTH",
                "Z_SOUTH",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
                earliest=60,
                latest=200,
            ),
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=70, latest=210),
        ],
    )
    res = solve_greedy(p)
    assert res.verified_feasible
    assert "w" in res.served_requests
    assert "a" in res.served_requests
    wmax = 0
    for rp in res.route_plans:
        if rp.wheelchair_load_after_stop:
            wmax = max(wmax, max(rp.wheelchair_load_after_stop.values()))
    assert wmax == 1


def test_two_wheelchairs_capacity_one_rejected_or_unpooled():
    p = problem(
        [vehicle(capacity=4, wheelchairs=1)],
        [driver(trained=True)],
        [
            trip(
                "w1",
                "Z_NORTH",
                "Z_SOUTH",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
                earliest=60,
                latest=180,
            ),
            trip(
                "w2",
                "Z_NORTH",
                "Z_SOUTH",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
                earliest=65,
                latest=185,
            ),
        ],
    )
    res = solve_greedy(p)
    if len(res.served_requests) == 2:
        for rp in res.route_plans:
            if rp.wheelchair_load_after_stop:
                assert max(rp.wheelchair_load_after_stop.values()) <= 1
    else:
        assert res.rejected_requests
        assert all(r.reason_code for r in res.rejected_requests)


def test_passenger_plus_companion_uses_two_seats():
    p = problem(
        [vehicle(capacity=2, wheelchairs=0, types=[])],
        [driver()],
        [trip("c", "Z_NORTH", "Z_SOUTH", companions=1, earliest=60, latest=200)],
    )
    res = solve_greedy(p)
    assert "c" in res.served_requests
    assert res.verified_feasible
    assert _max_load(res) == 2


def test_incompatible_wheelchair_type_rejected():
    p = problem(
        [
            vehicle(
                capacity=3,
                wheelchairs=1,
                types=[WheelchairType.MANUAL],
            )
        ],
        [driver(trained=True)],
        [
            trip(
                "sc",
                "Z_NORTH",
                "Z_SOUTH",
                wheelchair=WheelchairType.SCOOTER,
                lift=True,
                assist=True,
            )
        ],
    )
    res = solve_greedy(p)
    assert "sc" not in res.served_requests
    assert res.rejected_requests[0].reason_code == "NO_COMPATIBLE_VEHICLE"


def test_sequential_dropoff_before_next_pickup_load_zero():
    p = problem(
        [vehicle(capacity=2, wheelchairs=0, types=[])],
        [driver()],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=90, max_ride=40, max_wait=200),
            trip("b", "Z_EAST", "Z_WEST", earliest=200, latest=260, max_ride=40, max_wait=200),
        ],
    )
    res = solve_fifo(p)
    assert res.verified_feasible
    assert set(res.served_requests) == {"a", "b"}
    assert _max_load(res) == 1


def test_max_load_third_passenger_rejected():
    p = problem(
        [vehicle(capacity=2, wheelchairs=0, types=[])],
        [driver()],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=85),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=62, latest=85),
            trip("c", "Z_NORTH", "Z_SOUTH", earliest=64, latest=85),
        ],
    )
    res = solve_greedy(p)
    assert len(res.served_requests) <= 2
    assert res.rejected_requests
    assert all(r.reason_code for r in res.rejected_requests)
    report = check_plan(p, res)
    assert report.feasible == res.verified_feasible


def test_detour_ratio_blocks_long_ride():
    p = problem(
        [vehicle(capacity=3, wheelchairs=0, types=[])],
        [driver()],
        [
            trip("short", "Z_NORTH", "Z_SOUTH", earliest=60, latest=200, detour=1.01, max_ride=8),
        ],
    )
    res = solve_greedy(p)
    # either served with short ride or rejected with ride/time reason
    if "short" in res.served_requests:
        it = res.route_plans[0].passenger_itineraries[0]
        assert it.ride_time <= 8
    else:
        assert res.rejected_requests[0].reason_code


def test_max_ride_time_violation_rejected():
    p = problem(
        [vehicle(capacity=3, wheelchairs=0, types=[])],
        [driver()],
        [trip("r", "Z_NORTH", "Z_SOUTH", earliest=60, latest=200, max_ride=1)],
    )
    res = solve_greedy(p)
    assert "r" not in res.served_requests
    assert res.rejected_requests[0].reason_code


def test_route_has_depot_start_and_end():
    p = problem(
        [vehicle()],
        [driver()],
        [trip("a", "Z_NORTH", "Z_SOUTH")],
    )
    res = solve_greedy(p)
    assert res.served_requests
    stops = res.route_plans[0].ordered_stops
    assert stops[0].stop_type == StopType.DEPOT_START
    assert stops[-1].stop_type == StopType.DEPOT_END
    assert res.route_plans[0].passenger_itineraries


def test_stretcher_not_pooled_with_ambulatory() -> None:
    p = problem(
        [
            vehicle(
                capacity=4,
                wheelchairs=1,
                types=[WheelchairType.MANUAL, WheelchairType.POWER, WheelchairType.STRETCHER],
            )
        ],
        [driver(trained=True)],
        [
            trip(
                "st",
                "Z_NORTH",
                "Z_HOSP_A",
                wheelchair=WheelchairType.STRETCHER,
                lift=True,
                assist=True,
                earliest=60,
                latest=200,
            ),
            trip("amb", "Z_NORTH", "Z_HOSP_A", earliest=65, latest=200),
        ],
    )
    res = solve_greedy(p)
    assert res.status != "OPTIMAL"
    if "st" in res.served_requests and "amb" in res.served_requests:
        for rp in res.route_plans:
            wloads = rp.wheelchair_load_after_stop or {}
            ploads = rp.passenger_load_after_stop or {}
            for sid, w in wloads.items():
                if w >= 1:
                    assert ploads.get(sid, 0) <= 1
    else:
        assert "st" in res.served_requests or res.rejected_requests


def test_service_area_rejects_outside_zone() -> None:
    v = vehicle(capacity=3, wheelchairs=0, types=[])
    v = v.model_copy(update={"service_area": ["Z_NORTH", "Z_CENTER", v.depot_id]})
    p = problem([v], [driver()], [trip("out", "Z_SOUTH", "Z_WEST")])
    res = solve_greedy(p)
    assert "out" not in res.served_requests
    assert res.rejected_requests[0].reason_code == "NO_COMPATIBLE_VEHICLE"
