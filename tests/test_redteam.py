"""Red-team: notary holes, sort-order traps, pipeline completeness, rare combos."""

from __future__ import annotations

from mobiroute.adapters.ops_scenarios import generate_ops_day
from mobiroute.dispatch.online_insertion import (
    active_trip_ids,
    apply_cancellation,
    apply_no_show,
    online_insert,
    recover_disruption,
)
from mobiroute.domain.models import ReasonCode, StopType, WheelchairType
from mobiroute.domain.requests import PlanningResult, RoutePlan, Stop
from mobiroute.solvers.greedy import simulate_stop_sequence, solve_fifo, solve_greedy
from mobiroute.validation.feasibility import check_plan, passenger_rides
from tests.factories import driver, problem, trip, vehicle


def _result(problem, routes: list[RoutePlan], served: list[str]) -> PlanningResult:
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


def test_notary_rejects_stretcher_sharing_cabin() -> None:
    p = problem(
        [
            vehicle(
                "v1",
                capacity=4,
                wheelchairs=2,
                types=[WheelchairType.STRETCHER, WheelchairType.MANUAL],
            )
        ],
        [driver("d1")],
        [
            trip(
                "s",
                "Z_NORTH",
                "Z_NORTH",
                wheelchair=WheelchairType.STRETCHER,
                lift=True,
                assist=True,
                earliest=60,
                latest=400,
                max_ride=400,
                max_wait=400,
                detour=20.0,
            ),
            trip(
                "a",
                "Z_NORTH",
                "Z_NORTH",
                earliest=60,
                latest=400,
                max_ride=400,
                max_wait=400,
                detour=20.0,
            ),
        ],
    )
    stops = [
        Stop(
            id="s:PU",
            trip_id="s",
            stop_type=StopType.PICKUP,
            location="Z_NORTH",
            load_delta=1,
            wheelchair_load_delta=1,
        ),
        Stop(
            id="a:PU",
            trip_id="a",
            stop_type=StopType.PICKUP,
            location="Z_NORTH",
            load_delta=1,
        ),
        Stop(
            id="s:DO",
            trip_id="s",
            stop_type=StopType.DROPOFF,
            location="Z_NORTH",
            load_delta=-1,
            wheelchair_load_delta=-1,
        ),
        Stop(
            id="a:DO",
            trip_id="a",
            stop_type=StopType.DROPOFF,
            location="Z_NORTH",
            load_delta=-1,
        ),
    ]
    arr = {"s:PU": 60, "a:PU": 70, "s:DO": 80, "a:DO": 90}
    dep = {"s:PU": 68, "a:PU": 73, "s:DO": 85, "a:DO": 92}
    route = RoutePlan(
        vehicle_id="v1",
        driver_id="d1",
        ordered_stops=stops,
        passenger_assignments=["s", "a"],
        arrival_times=arr,
        departure_times=dep,
        passenger_load_after_stop={"s:PU": 1, "a:PU": 2, "s:DO": 1, "a:DO": 0},
        wheelchair_load_after_stop={"s:PU": 1, "a:PU": 1, "s:DO": 0, "a:DO": 0},
    )
    report = check_plan(p, _result(p, [route], ["s", "a"]))
    assert not report.feasible
    assert any("STRETCHER_EXCLUSIVE" in v for v in report.violations)
    sim = simulate_stop_sequence(p, p.vehicles[0], "d1", stops, {t.id: t for t in p.requests})
    assert sim is None


def test_notary_rejects_vehicle_shift_overrun() -> None:
    v = vehicle("v1")
    v = v.model_copy(update={"shift_end": 50})
    p = problem(
        [v],
        [driver("d1", shift_end=12 * 60)],
        [trip("t", "Z_NORTH", "Z_SOUTH", earliest=10, latest=40, max_ride=400, max_wait=400)],
    )
    t = p.requests[0]
    stops = [
        Stop(
            id="t:PU",
            trip_id="t",
            stop_type=StopType.PICKUP,
            location=t.pickup_zone,
            load_delta=1,
        ),
        Stop(
            id="t:DO",
            trip_id="t",
            stop_type=StopType.DROPOFF,
            location=t.dropoff_zone,
            load_delta=-1,
        ),
        Stop(id="v1:DEPOT_END", trip_id=None, stop_type=StopType.DEPOT_END, location=v.depot_id),
    ]
    route = RoutePlan(
        vehicle_id="v1",
        driver_id="d1",
        ordered_stops=stops,
        passenger_assignments=["t"],
        arrival_times={"t:PU": 38, "t:DO": 80, "v1:DEPOT_END": 200},
        departure_times={"t:PU": 41, "t:DO": 82, "v1:DEPOT_END": 200},
        passenger_load_after_stop={"t:PU": 1, "t:DO": 0, "v1:DEPOT_END": 0},
    )
    report = check_plan(p, _result(p, [route], ["t"]))
    assert not report.feasible
    assert any("VEHICLE_SHIFT_END" in x for x in report.violations)


def test_notary_unknown_trip_does_not_crash() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH")],
    )
    ghost = Stop(
        id="g:PU",
        trip_id="ghost",
        stop_type=StopType.PICKUP,
        location="Z_NORTH",
        load_delta=1,
    )
    route = RoutePlan(
        vehicle_id="v1",
        driver_id="d1",
        ordered_stops=[ghost],
        passenger_assignments=["ghost"],
        arrival_times={"g:PU": 40},
        departure_times={"g:PU": 43},
    )
    report = check_plan(p, _result(p, [route], ["ghost"]))
    assert not report.feasible
    assert any("UNKNOWN_TRIP:ghost" in x for x in report.violations)


def test_notary_duplicate_vehicle_route() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH", earliest=60, latest=200, max_wait=200)],
    )
    res = solve_greedy(p)
    if not res.route_plans:
        return
    doubled = res.model_copy(update={"route_plans": [res.route_plans[0], res.route_plans[0]]})
    report = check_plan(p, doubled)
    assert not report.feasible
    assert any("DUPLICATE_VEHICLE_ROUTE" in x for x in report.violations)


def test_notary_does_not_mutate_ride_times() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH", earliest=60, latest=200, max_wait=200)],
    )
    res = solve_greedy(p)
    if not res.route_plans:
        return
    before = dict(res.route_plans[0].ride_times)
    check_plan(p, res)
    assert dict(res.route_plans[0].ride_times) == before


def test_empty_vehicle_may_idle_until_earliest() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("late", "Z_NORTH", "Z_SOUTH", earliest=300, latest=360, max_wait=20, max_ride=90)],
    )
    res = solve_greedy(p)
    assert "late" in res.served_requests
    assert res.verified_feasible


def test_same_vehicle_return_not_starved_by_sort() -> None:
    ret = trip("ret", "Z_HOSP_A", "Z_NORTH", earliest=200, latest=280, max_wait=200, max_ride=90)
    ret = ret.model_copy(update={"same_vehicle_as": "out", "medical_priority": True})
    out = trip("out", "Z_NORTH", "Z_HOSP_A", earliest=60, latest=120, max_wait=200, max_ride=90)
    p = problem([vehicle("v1")], [driver("d1")], [ret, out])
    res = solve_greedy(p)
    assert "out" in res.served_requests
    assert "ret" in res.served_requests
    assert res.reason_codes.get("ret") != "SAME_VEHICLE_UNAVAILABLE"


def test_fifo_subscription_does_not_fail_notary_on_explained_frozen() -> None:
    p = generate_ops_day("ops_subscription_vs_nextday", seed=42)
    res = solve_fifo(p)
    report = check_plan(p, res)
    assert report.feasible == res.verified_feasible
    assert res.status != "NOT_VERIFIED"
    frozen = [t.id for t in p.requests if t.frozen]
    accounted = set(res.served_requests) | {r.trip_id for r in res.rejected_requests}
    assert set(frozen) <= accounted


def test_fifo_wait_return_processes_outbound_first() -> None:
    p = generate_ops_day("ops_wait_return", seed=42)
    res = solve_fifo(p)
    assert res.status != "NOT_VERIFIED"
    returns = [t for t in p.requests if t.same_vehicle_as]
    for ret in returns:
        out_id = ret.same_vehicle_as
        if ret.id in {r.trip_id for r in res.rejected_requests}:
            if out_id not in res.served_requests:
                code = res.reason_codes[ret.id]
                assert code == "SAME_VEHICLE_UNAVAILABLE"
            continue
        assert out_id in res.served_requests


def test_disruption_keeps_unrelated_vehicle_assignments() -> None:
    p = generate_ops_day("ops_clinic_peak", seed=42)
    base = solve_greedy(p)
    used = [rp for rp in base.route_plans if rp.passenger_assignments]
    assert len(used) >= 2
    broken = used[0].vehicle_id
    on_broken = set(used[0].passenger_assignments)
    other = next(tid for rp in used[1:] for tid in rp.passenger_assignments)
    other_vid = next(rp.vehicle_id for rp in used[1:] if other in rp.passenger_assignments)
    _upd, new, diff = recover_disruption(p, base, vehicle_unavailable_id=broken)
    assert other not in diff.moved_trips
    new_map = {tid: rp.vehicle_id for rp in new.route_plans for tid in rp.passenger_assignments}
    if other in new_map:
        assert new_map[other] == other_vid
    assert all(new_map.get(tid) != broken for tid in on_broken)


def test_via_pharmacy_dwell_is_not_geographic_detour() -> None:
    t = trip(
        "via",
        "Z_NORTH",
        "Z_CENTER",
        earliest=60,
        latest=240,
        max_ride=200,
        max_wait=80,
        via="Z_HOSP_A",
        detour=1.15,
    )
    t = t.model_copy(update={"via_service_duration": 25})
    p = problem([vehicle("v1")], [driver("d1")], [t])
    res = solve_greedy(p)
    assert "via" in res.served_requests
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
        assert not any(v.startswith("DETOUR:") for v in report.violations)


def test_unavail_blocks_wait_and_travel_not_only_boarding() -> None:
    v = vehicle("v1")
    v = v.model_copy(update={"unavailable_intervals": [(90, 110)]})
    p = problem(
        [v],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH", earliest=100, latest=160, max_ride=90, max_wait=40)],
    )
    res = solve_greedy(p)
    assert "t" not in res.served_requests


def test_online_insert_does_not_retime_frozen_pickup() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("a", "Z_NORTH", "Z_SOUTH", earliest=80, latest=200, max_ride=90, max_wait=40)],
    )
    base = solve_greedy(p)
    assert "a" in base.served_requests
    before = base.route_plans[0].passenger_itineraries[0].pickup_time
    extra = trip("b", "Z_NORTH", "Z_SOUTH", earliest=50, latest=200, max_ride=90, max_wait=40)
    _upd, res, _diff = online_insert(p, base, extra)
    after_map = {
        it.trip_id: it.pickup_time for rp in res.route_plans for it in rp.passenger_itineraries
    }
    if "a" in after_map:
        assert after_map["a"] == before


def test_online_insert_respects_remaining_quota() -> None:
    first = trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=180, quota=80, max_ride=90)
    p = problem([vehicle("v1")], [driver("d1")], [first])
    base = solve_greedy(p)
    assert "a" in base.served_requests
    ride_a = base.route_plans[0].ride_times["a"]
    second = trip("b", "Z_EAST", "Z_WEST", earliest=200, latest=400, quota=ride_a, max_ride=90)
    second = second.model_copy(
        update={"pseudonymous_passenger_id": first.pseudonymous_passenger_id}
    )
    _upd, res, _diff = online_insert(p, base, second)
    assert "b" not in res.served_requests
    assert res.reason_codes.get("b") == ReasonCode.QUOTA_EXCEEDED.value


def test_notary_flags_unexplained_via_idle() -> None:
    t = trip("via", "Z_NORTH", "Z_CENTER", earliest=60, latest=240, max_ride=200, via="Z_HOSP_A")
    p = problem([vehicle("v1")], [driver("d1")], [t])
    res = solve_greedy(p)
    assert res.route_plans
    rp = res.route_plans[0]
    via_stop = next(s for s in rp.ordered_stops if s.stop_type == StopType.VIA)
    arr = dict(rp.arrival_times)
    dep = dict(rp.departure_times)
    arr[via_stop.id] = arr[via_stop.id] + 40
    dep[via_stop.id] = dep[via_stop.id] + 40
    forged = rp.model_copy(update={"arrival_times": arr, "departure_times": dep})
    report = check_plan(p, _result(p, [forged], ["via"]))
    assert not report.feasible
    assert any("UNEXPLAINED_WAIT" in v for v in report.violations)


def test_later_pooling_cannot_exceed_existing_quota() -> None:
    """Inserting B must not lengthen A's ride past A's remaining hour quota."""
    p = problem(
        [vehicle("v1", capacity=4)],
        [driver("d1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=400, max_ride=400, quota=20),
            trip("b", "Z_EAST", "Z_WEST", earliest=70, latest=400, max_ride=400),
        ],
    )
    res = solve_greedy(p)
    report = check_plan(p, res)
    assert all(not v.startswith("QUOTA:") for v in report.violations)
    for rp in res.route_plans:
        if "a" in rp.ride_times:
            assert rp.ride_times["a"] <= 20


def test_cancel_outbound_cancels_wait_return() -> None:
    p = generate_ops_day("ops_wait_return", seed=42)
    ret = next(t for t in p.requests if t.same_vehicle_as)
    out_id = ret.same_vehicle_as
    assert out_id is not None

    cancelled = apply_cancellation(p, out_id)
    statuses = {t.id: t.booking_status.value for t in cancelled.requests}
    assert statuses[out_id] == "CANCELLED"
    assert statuses[ret.id] == "CANCELLED"
    active = active_trip_ids(cancelled)
    assert out_id not in active
    assert ret.id not in active

    noshow = apply_no_show(p, out_id)
    statuses = {t.id: t.booking_status.value for t in noshow.requests}
    assert statuses[out_id] == "NO_SHOW"
    assert statuses[ret.id] == "CANCELLED"


def test_seeded_replan_peels_over_quota_and_passes_notary() -> None:
    a = trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=400, max_ride=400)
    b = trip("b", "Z_EAST", "Z_WEST", earliest=70, latest=400, max_ride=400)
    b = b.model_copy(update={"pseudonymous_passenger_id": a.pseudonymous_passenger_id})
    p0 = problem([vehicle("v1", capacity=4)], [driver("d1")], [a, b])
    pooled = solve_greedy(p0)
    assert "a" in pooled.served_requests
    assert "b" in pooled.served_requests

    rp = pooled.route_plans[0]
    total = passenger_rides(rp, {t.id: t for t in p0.requests})[a.pseudonymous_passenger_id]
    tight = max(1, total - 1)
    a2 = a.model_copy(update={"quota_minutes_remaining": tight})
    b2 = b.model_copy(update={"quota_minutes_remaining": tight})
    p = problem([vehicle("v1", capacity=4)], [driver("d1")], [a2, b2])
    res = solve_greedy(
        p,
        seed_stops={rp.vehicle_id: list(rp.ordered_stops)},
        seed_drivers={rp.vehicle_id: rp.driver_id},
    )
    report = check_plan(p, res)
    assert all(not v.startswith("QUOTA:") for v in report.violations)
    assert res.status != "NOT_VERIFIED"


def test_online_insert_reports_native_backend() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("a", "Z_NORTH", "Z_SOUTH", earliest=80, latest=200, max_ride=90, max_wait=40)],
    )
    base = solve_greedy(p)
    assert "a" in base.served_requests
    extra = trip("b", "Z_EAST", "Z_WEST", earliest=300, latest=400, max_ride=90, max_wait=40)
    _upd, res, _diff = online_insert(p, base, extra)
    assert res.solver_config.get("insertion_backend") == "native"
