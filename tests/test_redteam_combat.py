"""Harsh Red Team: stacked disruptions, kernel-fork isolation, native/Pydantic lockstep."""

from __future__ import annotations

import pytest

from mobiroute.adapters.ops_scenarios import generate_ops_day
from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.dispatch.online_insertion import (
    apply_cancellation,
    apply_traffic_delay,
    online_insert,
    recover_disruption,
)
from mobiroute.domain.models import WheelchairType
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import (
    _pair_stops,
    route_plan_from_eval,
    simulate_stop_sequence,
    solve_greedy,
)
from mobiroute.solvers.insertion_kernel import ProblemKernel, best_insert_python, vehicle_payload
from mobiroute.solvers.native_accel import (
    append_trip,
    attach_native,
    best_insert,
    eval_route,
    fork_kernel,
    kernel_for,
    native_available,
    score_stored,
    set_fleet,
)
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _assert_notary(problem, result) -> None:
    report = check_plan(problem, result)
    if result.verified_feasible:
        assert report.feasible, report.violations[:12]
    assert result.status != "OPTIMAL"


def _assert_native_lockstep(problem, result) -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    kernel = attach_native(ProblemKernel.from_problem(problem))
    trips = {t.id: t for t in problem.requests}
    vmap = {v.id: v for v in problem.vehicles}
    for rp in result.route_plans:
        core = service_stops(list(rp.ordered_stops))
        if not core:
            continue
        veh = vmap[rp.vehicle_id]
        st, sk = kernel.stops_to_arrays(core)
        dk = kernel.drivers.get(rp.driver_id) if rp.driver_id else None
        payload, una = vehicle_payload(kernel.vehicles[veh.id], dk)
        set_fleet(kernel, [st], [sk], [payload], [una])
        native_plan = route_plan_from_eval(veh, rp.driver_id, core, kernel, eval_route(kernel, 0))
        py_plan = simulate_stop_sequence(problem, veh, rp.driver_id, core, trips)
        assert native_plan is not None, rp.vehicle_id
        assert py_plan is not None, rp.vehicle_id
        assert native_plan.route_duration == py_plan.route_duration
        assert native_plan.ride_times == py_plan.ride_times
        assert native_plan.waiting_times == py_plan.waiting_times


def test_native_eval_lockstep_via_unavail_appointment() -> None:
    v = vehicle("v1")
    v = v.model_copy(update={"unavailable_intervals": [(500, 520)]})
    p = problem(
        [v],
        [driver("d1")],
        [
            trip(
                "via",
                "Z_NORTH",
                "Z_SOUTH",
                earliest=60,
                latest=240,
                max_ride=200,
                max_wait=80,
                via="Z_HOSP_A",
                appt_start=200,
                appt_end=280,
            )
        ],
    )
    res = solve_greedy(p)
    _assert_notary(p, res)
    if res.route_plans:
        _assert_native_lockstep(p, res)


def test_online_does_not_mutate_baseline_routes() -> None:
    p = generate_day("tiny", seed=5)
    base = solve_greedy(p)
    before_assign = [list(rp.passenger_assignments) for rp in base.route_plans]
    before_times = [
        (rp.vehicle_id, dict(rp.arrival_times), dict(rp.ride_times)) for rp in base.route_plans
    ]
    extra = trip("e1", "Z_EAST", "Z_WEST", earliest=400, latest=520, max_ride=90, max_wait=40)
    _upd, res, _diff = online_insert(p, base, extra)
    assert [list(rp.passenger_assignments) for rp in base.route_plans] == before_assign
    assert [
        (rp.vehicle_id, dict(rp.arrival_times), dict(rp.ride_times)) for rp in base.route_plans
    ] == before_times
    _assert_notary(_upd, res)
    assert extra.id not in base.served_requests


def test_online_from_same_baseline_does_not_poison_kernel() -> None:
    p = generate_day("tiny", seed=8)
    base = solve_greedy(p)
    a = trip("e-a", "Z_EAST", "Z_WEST", earliest=400, latest=520, max_ride=90, max_wait=40)
    b = trip("e-b", "Z_WEST", "Z_EAST", earliest=410, latest=530, max_ride=90, max_wait=40)
    _u1, r1, _d1 = online_insert(p, base, a)
    _u2, r2, _d2 = online_insert(p, base, b)
    assigned_r2 = {tid for rp in r2.route_plans for tid in rp.passenger_assignments}
    if a.id in r1.served_requests:
        assert a.id not in assigned_r2
    _assert_notary(_u2, r2)
    assert kernel_for(base) is not kernel_for(r1) or kernel_for(r1) is None
    if r1.event_id and base.plan_id:
        assert r1.event_id != (base.event_id or "")
        assert r1.plan_id != base.plan_id


def test_online_verified_feasible_matches_full_notary() -> None:
    p = generate_day("tiny", seed=9)
    base = solve_greedy(p)
    extra = trip(
        "wav",
        "Z_NORTH",
        "Z_HOSP_A",
        earliest=90,
        latest=150,
        max_ride=55,
        max_wait=25,
        wheelchair=WheelchairType.MANUAL,
        lift=True,
        assist=True,
    )
    upd, res, _diff = online_insert(p, base, extra)
    report = check_plan(upd, res)
    assert res.verified_feasible == report.feasible
    _assert_notary(upd, res)


def test_cancel_then_emergency_replans_before_insert() -> None:
    p = generate_day("tiny", seed=11)
    base = solve_greedy(p)
    assert base.served_requests
    drop = base.served_requests[0]
    em = trip("er", "Z_CENTER", "Z_HOSP_A", earliest=80, latest=140, max_ride=60, max_wait=30)
    upd, res, _diff = recover_disruption(p, base, cancel_trip_id=drop, emergency_trip=em)
    assert drop not in res.served_requests
    report = check_plan(upd, res)
    if res.verified_feasible:
        assert report.feasible, report.violations[:12]
    assert res.status != "OPTIMAL"


def test_wait_return_cancel_then_traffic_notary() -> None:
    p = generate_ops_day("ops_wait_return", seed=42)
    base = solve_greedy(p)
    ret = next(t for t in p.requests if t.same_vehicle_as)
    out_id = ret.same_vehicle_as
    assert out_id is not None
    cancelled = apply_cancellation(p, out_id)
    upd, res, _diff = recover_disruption(cancelled, base, traffic_delay_minutes=8)
    _assert_notary(upd, res)
    assert out_id not in res.served_requests
    assert ret.id not in res.served_requests
    if res.route_plans:
        _assert_native_lockstep(upd, res)


def test_combat_stacked_disruptions_on_wheelchair_heavy() -> None:
    p = generate_day("wheelchair_heavy", seed=13)
    day = solve_greedy(p)
    _assert_notary(p, day)
    _assert_native_lockstep(p, day)
    assert day.route_plans
    served = list(day.served_requests)
    vid = day.route_plans[0].vehicle_id
    did = day.route_plans[0].driver_id
    appt = next((t for t in p.requests if t.id in set(served) and t.appointment_end), None)

    p2, r2, _ = recover_disruption(p, day, cancel_trip_id=served[0])
    _assert_notary(p2, r2)

    noshow_id = served[1] if len(served) > 1 else served[0]
    p3, r3, _ = recover_disruption(p2, r2, no_show_trip_id=noshow_id)
    _assert_notary(p3, r3)

    p4, r4, _ = recover_disruption(p3, r3, vehicle_unavailable_id=vid)
    _assert_notary(p4, r4)
    assert all(rp.vehicle_id != vid for rp in r4.route_plans)

    if did:
        p5, r5, _ = recover_disruption(p4, r4, driver_unavailable_id=did)
        _assert_notary(p5, r5)
    else:
        p5, r5 = p4, r4

    p6, r6, _ = recover_disruption(p5, r5, traffic_delay_minutes=8)
    _assert_notary(p6, r6)
    if r6.route_plans:
        _assert_native_lockstep(p6, r6)

    if appt is not None and appt.id in set(r6.served_requests) and appt.appointment_end is not None:
        p7, r7, _ = recover_disruption(
            p6,
            r6,
            appointment_trip_id=appt.id,
            appointment_end=max(0, appt.appointment_end - 15),
        )
        _assert_notary(p7, r7)
    else:
        p7, r7 = p6, r6

    em = trip(
        "combat-er",
        "Z_NORTH",
        "Z_HOSP_A",
        earliest=100,
        latest=160,
        max_ride=55,
        max_wait=25,
        wheelchair=WheelchairType.MANUAL,
        lift=True,
        assist=True,
    )
    p8, r8, diff = recover_disruption(p7, r7, emergency_trip=em)
    _assert_notary(p8, r8)
    assert diff.plan_churn
    assert r8.status != "OPTIMAL"


def test_combat_small_day_traffic_then_two_online() -> None:
    p = generate_day("small", seed=17)
    day = solve_greedy(p)
    _assert_notary(p, day)
    traffic = apply_traffic_delay(p, 6)
    p2, r2, _ = recover_disruption(traffic, day, traffic_delay_minutes=6)
    _assert_notary(p2, r2)
    cur_p, cur_r = p2, r2
    for i in range(3):
        em = trip(
            f"small-er-{i}",
            "Z_EAST",
            "Z_HOSP_B",
            earliest=120 + i * 8,
            latest=180 + i * 8,
            max_ride=60,
            max_wait=30,
        )
        cur_p, cur_r, _diff = online_insert(cur_p, cur_r, em)
        _assert_notary(cur_p, cur_r)
    if cur_r.route_plans:
        _assert_native_lockstep(cur_p, cur_r)


def test_native_prefix_insert_matches_python_on_loaded_route() -> None:
    """Incremental (i, j) must match the Python SoA oracle on a non-empty route."""
    if not native_available():
        pytest.skip("mobiroute_native not built")
    v = vehicle("v1", capacity=8, wheelchairs=2)
    d = driver("d1")
    trips = [
        trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=240, max_ride=180, max_wait=80),
        trip("b", "Z_EAST", "Z_WEST", earliest=70, latest=250, max_ride=180, max_wait=80),
        trip("c", "Z_CENTER", "Z_HOSP_A", earliest=80, latest=260, max_ride=180, max_wait=80),
        trip(
            "d",
            "Z_WEST",
            "Z_HOSP_B",
            earliest=90,
            latest=270,
            max_ride=180,
            max_wait=80,
            appt_start=200,
            appt_end=280,
        ),
    ]
    p = problem([v], [d], trips)
    k = attach_native(ProblemKernel.from_problem(p))
    vk = k.vehicles[v.id]
    dk = k.drivers[d.id]
    current: list = []
    for new in trips:
        st, sk = k.stops_to_arrays(current)
        py_best = best_insert_python(k, vk, dk, st, sk, k.id_to_idx[new.id])
        nat_best = best_insert(k, vk, dk, st, sk, k.id_to_idx[new.id])
        assert nat_best == py_best, (new.id, nat_best, py_best)
        if py_best is None:
            break
        i, _mid, j, _dur, _wait, _mx = py_best
        pu, do = _pair_stops(new)
        core = service_stops(current)
        current = [*core[:i], pu, *core[i:j], do, *core[j:]]


def test_native_via_insert_matches_python_on_loaded_route() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    v = vehicle("v1", capacity=6, wheelchairs=2)
    d = driver("d1")
    first = trip("a", "Z_NORTH", "Z_SOUTH", earliest=50, latest=300, max_ride=200, max_wait=90)
    via_trip = trip(
        "via",
        "Z_EAST",
        "Z_WEST",
        earliest=80,
        latest=320,
        max_ride=220,
        max_wait=90,
        via="Z_HOSP_A",
        appt_start=210,
        appt_end=300,
    )
    p = problem([v], [d], [first, via_trip])
    k = attach_native(ProblemKernel.from_problem(p))
    vk = k.vehicles[v.id]
    dk = k.drivers[d.id]
    st, sk = k.stops_to_arrays([])
    first_best = best_insert_python(k, vk, dk, st, sk, k.id_to_idx[first.id])
    assert first_best is not None
    pu, do = _pair_stops(first)
    current = [pu, do]
    st, sk = k.stops_to_arrays(current)
    py_best = best_insert_python(k, vk, dk, st, sk, k.id_to_idx[via_trip.id])
    nat_best = best_insert(k, vk, dk, st, sk, k.id_to_idx[via_trip.id])
    assert nat_best == py_best


def test_fork_copy_on_write_does_not_mutate_parent_table() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=21)
    k = attach_native(ProblemKernel.from_problem(p))
    vk = k.vehicles[p.vehicles[0].id]
    dk = k.drivers[p.drivers[0].id]
    veh, una = vehicle_payload(vk, dk)
    set_fleet(k, [[]], [[]], [veh], [una])
    new_idx = 0
    parent = score_stored(k, new_idx)
    child = fork_kernel(k)
    extra = trip("cow", "Z_SOUTH", "Z_NORTH", earliest=400, latest=520, max_ride=90, max_wait=40)
    zmap = {z: i for i, z in enumerate(p.travel.zones)}
    append_trip(child, extra, zmap)
    assert score_stored(k, new_idx) == parent
    assert extra.id not in k.id_to_idx
    assert extra.id in child.id_to_idx


def test_group_bus_capacity_and_stretcher_exclusive_insert() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    bus = vehicle(
        "bus",
        capacity=18,
        wheelchairs=2,
        vtype="minibus",
        types=[WheelchairType.MANUAL, WheelchairType.POWER, WheelchairType.STRETCHER],
    )
    d = driver("d1")
    packed = [
        trip(f"g{i}", "Z_NORTH", "Z_SOCIAL", earliest=60 + i, latest=240, companions=2)
        for i in range(5)
    ]
    stretcher = trip(
        "st",
        "Z_EAST",
        "Z_HOSP_A",
        earliest=90,
        latest=200,
        wheelchair=WheelchairType.STRETCHER,
        lift=True,
        assist=True,
    )
    p = problem([bus], [d], [*packed, stretcher])
    res = solve_greedy(p)
    _assert_notary(p, res)
    if res.route_plans:
        _assert_native_lockstep(p, res)
    if stretcher.id in set(res.served_requests):
        assigned = next(rp for rp in res.route_plans if stretcher.id in rp.passenger_assignments)
        others = [tid for tid in assigned.passenger_assignments if tid != stretcher.id]
        assert others == []


def test_unavail_travel_window_and_service_area_insert() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    v = vehicle("v1", capacity=4, wheelchairs=1)
    v = v.model_copy(
        update={
            "unavailable_intervals": [(120, 140)],
            "service_area": ["Z_NORTH", "Z_SOUTH", "Z_HOSP_A", "Z_DEPOT_1"],
        }
    )
    d = driver("d1")
    inside = trip("in", "Z_NORTH", "Z_HOSP_A", earliest=60, latest=200, max_ride=120, max_wait=50)
    outside = trip("out", "Z_EAST", "Z_WEST", earliest=70, latest=210, max_ride=120, max_wait=50)
    p = problem([v], [d], [inside, outside])
    res = solve_greedy(p)
    _assert_notary(p, res)
    assert outside.id not in res.served_requests
    if res.route_plans:
        _assert_native_lockstep(p, res)


def test_combat_ops_stretcher_then_traffic_then_emergency() -> None:
    p = generate_ops_day("ops_stretcher", seed=42)
    day = solve_greedy(p)
    _assert_notary(p, day)
    traffic = apply_traffic_delay(p, 7)
    p2, r2, _ = recover_disruption(traffic, day, traffic_delay_minutes=7)
    _assert_notary(p2, r2)
    em = trip(
        "st-er",
        "Z_NORTH",
        "Z_HOSP_A",
        earliest=100,
        latest=180,
        max_ride=70,
        max_wait=30,
        wheelchair=WheelchairType.STRETCHER,
        lift=True,
        assist=True,
    )
    p3, r3, _ = recover_disruption(p2, r2, emergency_trip=em)
    _assert_notary(p3, r3)
    assert r3.status != "OPTIMAL"
    if r3.route_plans:
        _assert_native_lockstep(p3, r3)


def test_score_stored_is_deterministic_across_calls() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=33)
    k = attach_native(ProblemKernel.from_problem(p))
    rows = []
    vehs = []
    unas = []
    for v in p.vehicles:
        vk = k.vehicles[v.id]
        dk = k.drivers[p.drivers[0].id]
        veh, una = vehicle_payload(vk, dk)
        rows.append([])
        vehs.append(veh)
        unas.append(una)
    set_fleet(k, rows, [[] for _ in rows], vehs, unas)
    a = sorted(score_stored(k, 0))
    b = sorted(score_stored(k, 0))
    assert a == b
