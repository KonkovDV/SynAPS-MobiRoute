"""SoA insertion kernel vs Pydantic simulation; optional native parity."""

from __future__ import annotations

import time

import pytest

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.domain.models import WheelchairType
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import _pair_stops, simulate_stop_sequence, solve_greedy
from mobiroute.solvers.insertion_kernel import (
    ProblemKernel,
    best_insert_python,
    pack_for_native,
    vehicle_payload,
)
from mobiroute.solvers.native_accel import (
    acceleration_status,
    attach_native,
    best_insert,
    native_available,
    score_fleet,
    score_stored,
    set_fleet,
)
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def _pydantic_best(
    p,
    veh,
    driver_id: str,
    current_stops,
    new_trip,
    trips_by_id: dict,
):
    pu, do = _pair_stops(new_trip)
    core = service_stops(current_stops)
    merged = {**trips_by_id, new_trip.id: new_trip}
    best = None
    best_key = None
    m = len(core)
    for i in range(m + 1):
        for j in range(i, m + 1):
            seq = [*core[:i], pu, *core[i:j], do, *core[j:]]
            plan = simulate_stop_sequence(p, veh, driver_id, seq, merged)
            if plan is None:
                continue
            mx = (
                max(plan.passenger_load_after_stop.values())
                if plan.passenger_load_after_stop
                else 0
            )
            key = (plan.route_duration, sum(plan.waiting_times.values()), -mx, i, j)
            if best_key is None or key < best_key:
                best_key = key
                best = (i, -1, j, plan.route_duration, sum(plan.waiting_times.values()), mx)
    return best


def test_python_soa_matches_pydantic_insertion():
    p = problem(
        [vehicle(capacity=4, wheelchairs=1)],
        [driver(trained=True)],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60, latest=220),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=70, latest=230),
            trip(
                "w",
                "Z_EAST",
                "Z_HOSP_A",
                wheelchair=WheelchairType.MANUAL,
                lift=True,
                assist=True,
                earliest=80,
                latest=240,
            ),
        ],
    )
    k = ProblemKernel.from_problem(p)
    trips_by_id = {t.id: t for t in p.requests}
    veh = p.vehicles[0]
    did = p.drivers[0].id
    current = []
    for new in p.requests:
        py_best = best_insert_python(
            k,
            k.vehicles[veh.id],
            k.drivers[did],
            *k.stops_to_arrays(current),
            k.id_to_idx[new.id],
        )
        pydantic_best = _pydantic_best(p, veh, did, current, new, trips_by_id)
        assert py_best == pydantic_best
        if py_best is None:
            break
        i, _mid, j, _dur, _wait, _mx = py_best
        pu, do = _pair_stops(new)
        core = service_stops(current)
        current = [*core[:i], pu, *core[i:j], do, *core[j:]]


def test_solver_config_reports_native_backend():
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=42)
    res = solve_greedy(p)
    assert res.solver_config["insertion_backend"] == "native"
    assert res.solver_config["native_available"] is True
    assert acceleration_status()["insertion_backend"] == "native"


def test_native_matches_python_when_available():
    p = generate_day("tiny", seed=3)
    k = ProblemKernel.from_problem(p)
    veh = p.vehicles[0]
    did = p.drivers[0].id
    vk = k.vehicles[veh.id]
    dk = k.drivers[did]
    new = p.requests[0]
    py_best = best_insert_python(k, vk, dk, [], [], k.id_to_idx[new.id])
    if not native_available():
        pytest.skip("mobiroute_native not built")
    packed = pack_for_native(k, vk, dk, [], [], k.id_to_idx[new.id])
    import mobiroute_native

    raw = mobiroute_native.best_insert(
        packed["travel"],
        packed["n_zones"],
        packed["trip_table"],
        packed["detour"],
        packed["stop_trip"],
        packed["stop_kind"],
        packed["new_idx"],
        packed["veh"],
        packed["unavail"],
    )
    attached = attach_native(ProblemKernel.from_problem(p))
    via_engine = best_insert(attached, vk, dk, [], [], k.id_to_idx[new.id])
    assert py_best is not None
    assert raw == py_best
    assert via_engine == py_best


def test_score_fleet_matches_per_vehicle_best_insert():
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=3)
    k = attach_native(ProblemKernel.from_problem(p))
    new = p.requests[0]
    new_idx = k.id_to_idx[new.id]
    stop_trips: list[list[int]] = []
    stop_kinds: list[list[int]] = []
    vehs: list[list[int]] = []
    unavails: list[list[int]] = []
    per: list[tuple[int, int, int, int, int, int] | None] = []

    for v in p.vehicles:
        vk = k.vehicles[v.id]
        dk = k.drivers[p.drivers[0].id]
        veh, una = vehicle_payload(vk, dk)
        stop_trips.append([])
        stop_kinds.append([])
        vehs.append(veh)
        unavails.append(una)
        per.append(best_insert(k, vk, dk, [], [], new_idx))
    fleet = score_fleet(k, stop_trips, stop_kinds, vehs, unavails, new_idx)
    by_idx = {row[0]: row[1:] for row in fleet}
    for i, one in enumerate(per):
        if one is None:
            assert i not in by_idx
        else:
            assert by_idx[i] == one


def test_stored_fleet_matches_score_fleet() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=42)
    k = attach_native(ProblemKernel.from_problem(p))
    new_idx = 0
    stop_trips = [[] for _ in p.vehicles]
    stop_kinds = [[] for _ in p.vehicles]
    vehs: list[list[int]] = []
    unavails: list[list[int]] = []
    for v in p.vehicles:
        vk = k.vehicles[v.id]
        dk = k.drivers[p.drivers[0].id]
        veh, una = vehicle_payload(vk, dk)
        vehs.append(veh)
        unavails.append(una)
    copied = score_fleet(k, stop_trips, stop_kinds, vehs, unavails, new_idx)
    set_fleet(k, stop_trips, stop_kinds, vehs, unavails)
    stored = score_stored(k, new_idx)
    assert sorted(copied) == sorted(stored)


def test_score_stored_subset_and_max_dur_keep_winner() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("tiny", seed=42)
    k = attach_native(ProblemKernel.from_problem(p))
    stop_trips = [[] for _ in p.vehicles]
    stop_kinds = [[] for _ in p.vehicles]
    vehs: list[list[int]] = []
    unavails: list[list[int]] = []
    for v in p.vehicles:
        vk = k.vehicles[v.id]
        dk = k.drivers[p.drivers[0].id]
        veh, una = vehicle_payload(vk, dk)
        vehs.append(veh)
        unavails.append(una)
    set_fleet(k, stop_trips, stop_kinds, vehs, unavails)
    full = score_stored(k, 0)
    assert full
    subset = score_stored(k, 0, list(range(min(2, len(p.vehicles)))))
    by_idx = {row[0]: row for row in full}
    for row in subset:
        assert row == by_idx[row[0]]
    best = min(full, key=lambda r: (r[4], r[5], r[0]))
    capped = score_stored(k, 0, max_dur=best[4])
    assert all(row[4] <= best[4] for row in capped)
    assert any(row[0] == best[0] and row[4] == best[4] for row in capped)


def test_eval_route_matches_pydantic_times() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    from mobiroute.solvers.greedy import route_plan_from_eval
    from mobiroute.solvers.native_accel import eval_route

    p = generate_day("tiny", seed=7)
    res = solve_greedy(p)
    assert res.route_plans
    k = attach_native(ProblemKernel.from_problem(p))
    rp = res.route_plans[0]
    v = next(x for x in p.vehicles if x.id == rp.vehicle_id)
    core = service_stops(list(rp.ordered_stops))
    st, sk = k.stops_to_arrays(core)
    dk = k.drivers.get(rp.driver_id) if rp.driver_id else None
    veh, una = vehicle_payload(k.vehicles[v.id], dk)
    set_fleet(k, [st], [sk], [veh], [una])
    row = eval_route(k, 0)
    native_plan = route_plan_from_eval(v, rp.driver_id, core, k, row)
    py_plan = simulate_stop_sequence(p, v, rp.driver_id, core, {t.id: t for t in p.requests})
    assert native_plan is not None
    assert py_plan is not None
    assert native_plan.route_duration == py_plan.route_duration
    assert native_plan.ride_times == py_plan.ride_times
    assert native_plan.waiting_times == py_plan.waiting_times


def test_greedy_small_finishes_quickly():
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("small", seed=42)
    t0 = time.perf_counter()
    res = solve_greedy(p)
    elapsed = time.perf_counter() - t0
    assert elapsed < 20.0, f"small greedy took {elapsed:.2f}s"
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
    assert res.status != "OPTIMAL"


def test_greedy_medium_finishes_quickly():
    """medium = 60 vehicles / 1000 requests. Rust scoring is required."""
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("medium", seed=42)
    t0 = time.perf_counter()
    res = solve_greedy(p)
    elapsed = time.perf_counter() - t0
    assert elapsed < 12.0, f"medium greedy took {elapsed:.2f}s"
    assert len(p.requests) == 1000
    assert len(p.vehicles) == 60
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
    assert res.status != "OPTIMAL"
    assert res.solver_config["insertion_backend"] == "native"


def test_unknown_depot_raises_value_error() -> None:
    p = problem(
        [vehicle("v1", depot="Z_DEPOT_99")],
        [driver("d1")],
        [trip("t", "Z_NORTH", "Z_SOUTH")],
    )
    with pytest.raises(ValueError, match="not in the travel matrix"):
        ProblemKernel.from_problem(p)
