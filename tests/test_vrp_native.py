"""The Rust repair kernel reproduces the Python reference bit for bit."""

from __future__ import annotations

import random

import pytest

from mobiroute.vrp import native
from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, random_instance
from mobiroute.vrp.insertion import (
    Compiled,
    RouteState,
    apply_insertion,
    best_insertion,
    exact_feasible,
    regret_repair,
)
from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import Solution

pytestmark = pytest.mark.skipif(not native.available(), reason="mobiroute_native not built")


def _random_partial(c: Compiled, rng: random.Random) -> Solution:
    sol = regret_repair(c, Solution([], set(range(c.inst.n_requests))), regret=2)
    drop = {r for r in range(c.inst.n_requests) if rng.random() < 0.4}
    from mobiroute.vrp.insertion import remove_requests

    return remove_requests(c, sol, drop)


def test_best_insertion_and_exact_check_match() -> None:
    compared = 0
    for seed in range(80):
        inst = random_instance(seed, n_requests=8, n_types=3, ride_share=0.5)
        c = Compiled(inst)
        kernel = native.build_kernel(c)
        rng = random.Random(seed)
        sol = _random_partial(c, rng)
        for route in sol.routes:
            state = RouteState(c, route.vehicle_type, route.nodes)
            assert kernel.exact_feasible_route(route.vehicle_type, route.nodes) == exact_feasible(
                c, route.vehicle_type, route.nodes
            )
            for r in sorted(sol.unassigned):
                py = best_insertion(c, state, r)
                rs = kernel.best_insertion(route.vehicle_type, route.nodes, r)
                assert py == rs, (seed, r, py, rs)
                compared += 1
                if py is not None:
                    trial = apply_insertion(c, route.nodes, r, py[1], py[2])
                    assert kernel.exact_feasible_route(route.vehicle_type, trial)
    assert compared > 200


@pytest.mark.parametrize("noise", [0.0, 0.05])
@pytest.mark.parametrize("regret", [1, 2, 3])
def test_regret_repair_matches(regret: int, noise: float) -> None:
    for seed in range(30):
        inst = random_instance(seed, n_requests=10, n_types=3)
        c = Compiled(inst)
        fast = native.native_repair(c)
        assert fast is not None
        rng = random.Random(seed)
        partial = _random_partial(c, rng)
        cap = None if seed % 3 else max(1, partial.vehicles_used())
        py = regret_repair(c, partial, regret=regret, noise=noise, seed=seed, max_vehicles=cap)
        rs = fast(partial, regret, noise, seed, cap)
        assert py.as_lists() == rs.as_lists(), seed
        assert py.unassigned == rs.unassigned, seed


def test_alns_trajectory_is_identical_on_both_backends() -> None:
    inst = cargo_day(3, n_orders=30)
    py = solve(inst, AlnsConfig(backend="python", iterations=60, seed=5, segment=20))
    rs = solve(inst, AlnsConfig(backend="native", iterations=60, seed=5, segment=20))
    assert rs.backend == "native" and py.backend == "python"
    assert py.solution.as_lists() == rs.solution.as_lists()
    assert py.objective == rs.objective
    assert [p.objective for p in py.trace] == [p.objective for p in rs.trace]


def test_kernel_rejects_malformed_input() -> None:
    inst = random_instance(1, n_requests=4)
    kernel = native.build_kernel(Compiled(inst))
    with pytest.raises(ValueError, match="VRP_KERNEL"):
        kernel.best_insertion(99, [], 0)
    with pytest.raises(ValueError, match="VRP_KERNEL"):
        kernel.repair([(0, [0])], [], 2, 0.0, 1)
    with pytest.raises(ValueError, match="VRP_KERNEL"):
        kernel.repair([], [999], 2, 0.0, 1)


def test_guided_ejection_step_matches() -> None:
    from mobiroute.vrp.alns import Alns

    checked = 0
    for seed in range(25):
        inst = random_instance(seed, n_requests=10, n_types=2, ride_share=0.4)
        py = Alns(inst, AlnsConfig(backend="python", seed=seed))
        rs = Alns(inst, AlnsConfig(backend="native", seed=seed))
        rng = random.Random(seed)
        partial = _random_partial(py.c, rng)
        penalty = [rng.randint(1, 4) for _ in range(inst.n_requests)]
        for v in sorted(partial.unassigned):
            a = py._eject_insert(partial, v, penalty)
            b = rs._eject_insert(partial, v, penalty)
            assert (a is None) == (b is None), (seed, v)
            if a is not None and b is not None:
                assert a.as_lists() == b.as_lists() and a.unassigned == b.unassigned, (seed, v)
                checked += 1
    assert checked > 20


def _ruled(seed: int) -> Instance:
    from dataclasses import replace

    from mobiroute.vrp.model import BreakRule, add_reload_stops

    base = random_instance(seed, n_requests=10, n_types=2, ride_share=0.3)
    rng = random.Random(seed)
    types = tuple(
        replace(vt, breaks=BreakRule(rng.uniform(60.0, 220.0), rng.uniform(10.0, 50.0)))
        for vt in base.vehicle_types
    )
    return add_reload_stops(replace(base, vehicle_types=types), types[0].id, 3, 10.0)


def test_rests_and_reloads_match_on_both_backends() -> None:
    from mobiroute.vrp.insertion import route_exact

    compared = 0
    for seed in range(40):
        inst = _ruled(seed)
        c = Compiled(inst)
        kernel = native.build_kernel(c)
        rng = random.Random(seed)
        sol = _random_partial(c, rng)
        stops = list(inst.vehicle_types[0].reload_nodes)
        for route in sol.routes:
            nodes = list(route.nodes)
            if route.vehicle_type == 0 and stops and len(nodes) > 1:
                nodes.insert(rng.randint(1, len(nodes) - 1), stops.pop())
            t = route.vehicle_type
            assert kernel.exact_feasible_route(t, nodes) == route_exact(c, t, nodes), seed
            state = RouteState(c, t, nodes)
            for r in sorted(sol.unassigned):
                py = best_insertion(c, state, r)
                rs = kernel.best_insertion(t, nodes, r)
                assert py == rs, (seed, r, py, rs)
                compared += 1
    assert compared > 150


def test_alns_trajectory_with_rests_and_trips_is_identical() -> None:
    inst = _ruled(7)
    py = solve(inst, AlnsConfig(backend="python", iterations=80, seed=2, segment=20))
    rs = solve(inst, AlnsConfig(backend="native", iterations=80, seed=2, segment=20))
    assert py.solution.as_lists() == rs.solution.as_lists()
    assert [p.objective for p in py.trace] == [p.objective for p in rs.trace]
    assert py.verdict.feasible


def _split(seed: int) -> Instance:
    """Rests that may be split 15 + 30, on a random rich instance with reloads."""
    from dataclasses import replace

    from mobiroute.vrp.model import BreakRule, add_reload_stops

    base = random_instance(seed, n_requests=10, n_types=2, ride_share=0.3)
    rng = random.Random(seed)
    types = tuple(
        replace(vt, breaks=BreakRule(rng.uniform(60.0, 200.0), 45.0, (15.0, 30.0)))
        for vt in base.vehicle_types
    )
    return add_reload_stops(replace(base, vehicle_types=types), types[0].id, 3, 10.0)


def _rush(seed: int) -> Instance:
    """Time-dependent travel (two rush hours) on a random instance without ride
    limits or rests, the combination the model admits, with a multi-trip type."""
    from mobiroute.vrp.model import SpeedProfile, add_reload_stops
    from mobiroute.vrp.traffic import with_traffic

    base = random_instance(seed, n_requests=10, n_types=2, ride_share=0.0)
    speed = SpeedProfile((0.0, 40.0, 110.0, 190.0), (1.0, 0.5, 1.0, 0.7))
    inst = with_traffic(base, speed)
    return add_reload_stops(inst, inst.vehicle_types[0].id, 2, 8.0)


@pytest.mark.parametrize("build", [_split, _rush], ids=["split-break", "traffic"])
def test_split_breaks_and_traffic_match_on_both_backends(build: object) -> None:
    from collections.abc import Callable

    from mobiroute.vrp.insertion import route_exact

    make: Callable[[int], Instance] = build  # type: ignore[assignment]
    compared = 0
    for seed in range(40):
        inst = make(seed)
        c = Compiled(inst)
        kernel = native.build_kernel(c)
        assert kernel is not None
        rng = random.Random(seed)
        sol = _random_partial(c, rng)
        for route in sol.routes:
            t, nodes = route.vehicle_type, list(route.nodes)
            assert kernel.exact_feasible_route(t, nodes) == route_exact(c, t, nodes), seed
            # Shuffled orders exercise the infeasible side of the exact check.
            shuffled = nodes[:]
            rng.shuffle(shuffled)
            pairs_ok = all(
                shuffled.index(c.pick[r]) < shuffled.index(c.deliv[r])
                for r in c.requests_of(shuffled)
                if c.pick[r] >= 0 and c.deliv[r] >= 0
            )
            if pairs_ok:
                assert kernel.exact_feasible_route(t, shuffled) == route_exact(c, t, shuffled)
            state = RouteState(c, t, nodes)
            for r in sorted(sol.unassigned):
                py = best_insertion(c, state, r)
                rs = kernel.best_insertion(t, nodes, r)
                assert py == rs, (seed, r, py, rs)
                compared += 1
    assert compared > 150


@pytest.mark.parametrize("build", [_split, _rush], ids=["split-break", "traffic"])
def test_alns_trajectory_with_split_breaks_and_traffic_is_identical(build: object) -> None:
    from collections.abc import Callable

    make: Callable[[int], Instance] = build  # type: ignore[assignment]
    inst = make(11)
    py = solve(inst, AlnsConfig(backend="python", iterations=80, seed=2, segment=20))
    rs = solve(inst, AlnsConfig(backend="native", iterations=80, seed=2, segment=20))
    assert rs.backend == "native" and py.backend == "python"
    assert py.solution.as_lists() == rs.solution.as_lists()
    assert [p.objective for p in py.trace] == [p.objective for p in rs.trace]
    assert py.verdict.feasible


def test_cargo_day_with_rush_hours_runs_on_the_kernel() -> None:
    from mobiroute.vrp.traffic import with_traffic

    inst = with_traffic(cargo_day(3, n_orders=30))
    py = solve(inst, AlnsConfig(backend="python", iterations=40, seed=5, segment=20))
    rs = solve(inst, AlnsConfig(backend="native", iterations=40, seed=5, segment=20))
    assert rs.backend == "native"
    assert py.solution.as_lists() == rs.solution.as_lists()
    assert py.objective == rs.objective and rs.verdict.feasible


def test_kernel_rejects_a_malformed_speed_profile() -> None:
    inst = random_instance(2, n_requests=4)
    c = Compiled(inst)
    module = native._module()
    assert module is not None
    kernel = native.build_kernel(c)
    assert kernel is not None
    args = list(native.kernel_args(c))
    args[-1] = [([0.0, 0.0], [1.0, 1.0])] + [None] * (c.n_types - 1)  # starts not increasing
    with pytest.raises(ValueError, match="VRP_KERNEL_SHAPE:speed"):
        module.VrpKernel(*args)
