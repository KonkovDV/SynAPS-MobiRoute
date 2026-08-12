"""Residuals: unified max_wait, lobby dropoff, VIA, quota, travel graph."""

from __future__ import annotations

from mobiroute.adapters.ops_scenarios import generate_ops_day
from mobiroute.domain.models import ReasonCode, StopType
from mobiroute.domain.requests import TravelMatrix
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.insertion_kernel import ProblemKernel, best_insert_python, simulate_score
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def test_passenger_late_pickup_capped_by_max_wait() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("late", "Z_NORTH", "Z_SOUTH", earliest=0, latest=200, max_wait=1, max_ride=90)],
    )
    res = solve_greedy(p)
    assert "late" not in res.served_requests
    assert any(r.reason_code for r in res.rejected_requests)


def test_empty_vehicle_idle_still_free() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("late", "Z_NORTH", "Z_SOUTH", earliest=300, latest=360, max_wait=20, max_ride=90)],
    )
    res = solve_greedy(p)
    assert "late" in res.served_requests
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible


def test_appointment_start_does_not_hold_in_cabin() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip(
                "med",
                "Z_NORTH",
                "Z_HOSP_A",
                earliest=50,
                latest=200,
                appt_start=140,
                appt_end=190,
                max_ride=80,
            )
        ],
    )
    res = solve_greedy(p)
    assert "med" in res.served_requests
    it = res.route_plans[0].passenger_itineraries[0]
    assert it.dropoff_time >= 110
    assert it.dropoff_time < 140
    assert it.dropoff_time <= 190
    report = check_plan(p, res)
    assert not any("APPOINTMENT_START" in v for v in report.violations)


def test_via_stop_between_pickup_and_dropoff() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip(
                "via",
                "Z_NORTH",
                "Z_CENTER",
                earliest=60,
                latest=240,
                max_ride=90,
                via="Z_HOSP_A",
            )
        ],
    )
    res = solve_greedy(p)
    assert "via" in res.served_requests
    core = [
        s
        for s in res.route_plans[0].ordered_stops
        if s.stop_type in {StopType.PICKUP, StopType.VIA, StopType.DROPOFF}
    ]
    types = [s.stop_type for s in core if s.trip_id == "via"]
    assert types == [StopType.PICKUP, StopType.VIA, StopType.DROPOFF]
    via_stop = next(s for s in core if s.stop_type == StopType.VIA)
    assert via_stop.location == "Z_HOSP_A"
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible


def test_via_kernel_matches_pydantic() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("via", "Z_NORTH", "Z_CENTER", earliest=60, latest=240, max_ride=90, via="Z_HOSP_A")],
    )
    k = ProblemKernel.from_problem(p)
    vk = k.vehicles[p.vehicles[0].id]
    dk = k.drivers[p.drivers[0].id]
    found = best_insert_python(k, vk, dk, [], [], k.id_to_idx["via"])
    assert found is not None
    i, mid, j, _dur, _wait, _mx = found
    assert i == 0 and mid == 0 and j == 0


def test_quota_rejects_long_ride() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip("ok", "Z_NORTH", "Z_SOUTH", earliest=60, latest=180, quota=80),
            trip("no", "Z_EAST", "Z_WEST", earliest=90, latest=200, quota=1),
        ],
    )
    res = solve_greedy(p)
    assert "ok" in res.served_requests
    assert "no" not in res.served_requests
    codes = {r.trip_id: r.reason_code for r in res.rejected_requests}
    assert codes.get("no") == ReasonCode.QUOTA_EXCEEDED.value
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
        assert not any(v.startswith("QUOTA:") for v in report.violations)


def test_travel_shortest_path_not_raw_cell() -> None:
    m = TravelMatrix(
        zones=["A", "B", "C"],
        minutes=[[0, 5, 100], [5, 0, 5], [100, 5, 0]],
    )
    assert m.travel("A", "C") == 10
    assert m.shortest_path("A", "C") == ["A", "B", "C"]
    dump = m.model_dump(mode="json")
    assert dump["minutes"][0][2] == 100


def test_curb_wait_and_travel_path() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH", earliest=80, latest=200, max_ride=90)],
    )
    res = solve_greedy(p)
    assert "t" in res.served_requests
    it = res.route_plans[0].passenger_itineraries[0]
    assert it.travel_path[0] == "Z_NORTH"
    assert it.travel_path[-1] == "Z_SOUTH"
    pu = next(s for s in res.route_plans[0].ordered_stops if s.stop_type == StopType.PICKUP)
    dwell = res.route_plans[0].departure_times[pu.id] - res.route_plans[0].arrival_times[pu.id]
    assert dwell >= 5


def test_dropoff_snap_does_not_hold_other_passengers() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=300, max_ride=200, max_wait=90),
            trip(
                "b",
                "Z_NORTH",
                "Z_HOSP_A",
                earliest=60,
                latest=300,
                appt_start=150,
                appt_end=200,
                max_ride=90,
                max_wait=90,
            ),
        ],
    )
    k = ProblemKernel.from_problem(p)
    vk = k.vehicles[p.vehicles[0].id]
    dk = k.drivers[p.drivers[0].id]
    ia, ib = k.id_to_idx["a"], k.id_to_idx["b"]
    pooled = simulate_score(k, vk, dk, [ia, ib, ib, ia], [0, 0, 1, 1])
    assert pooled is None
    solo = simulate_score(k, vk, dk, [ib, ib], [0, 1])
    assert solo is not None


def test_ops_via_and_quota_modes() -> None:
    via = generate_ops_day("ops_via", seed=42)
    assert via.requests[0].via_zone == "Z_HOSP_A"
    res_via = solve_greedy(via)
    assert via.requests[0].id in res_via.served_requests
    quota = generate_ops_day("ops_quota", seed=42)
    res_q = solve_greedy(quota)
    tight = next(t for t in quota.requests if t.quota_minutes_remaining == 1)
    assert tight.id not in res_q.served_requests
    assert any(r.reason_code == ReasonCode.QUOTA_EXCEEDED.value for r in res_q.rejected_requests)
