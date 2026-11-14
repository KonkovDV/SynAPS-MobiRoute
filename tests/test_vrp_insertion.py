"""Constant-time insertion tests agree with brute force judged by the verifier."""

from __future__ import annotations

import random

import pytest

from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.insertion import (
    Compiled,
    RouteState,
    SplitMix64,
    apply_insertion,
    best_insertion,
    regret_repair,
)
from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import Route, Solution, route_cost
from mobiroute.vrp.verify import verify


def _route_feasible(inst: Instance, t: int, nodes: list[int]) -> bool:
    on_route = {inst.request_of(n) for n in nodes}
    rest = set(range(inst.n_requests)) - on_route
    return verify(inst, Solution([Route(t, nodes)], rest)).feasible


def _money(inst: Instance, t: int, nodes: list[int]) -> float:
    if not nodes:
        return 0.0
    vt = inst.vehicle_types[t]
    d, drive, svc = route_cost(inst, t, nodes)
    return (
        vt.fixed_cost
        + inst.vehicle_penalty
        + vt.cost_per_distance * d
        + vt.cost_per_time * (drive + svc)
    )


def _brute_force(c: Compiled, t: int, nodes: list[int], r: int) -> tuple[float, int, int] | None:
    inst = c.inst
    m = len(nodes)
    base = _money(inst, t, nodes)
    pair = c.pick[r] >= 0 and c.deliv[r] >= 0
    best: tuple[float, int, int] | None = None
    for i in range(m + 1):
        for j in range(i, m + 1) if pair else (i,):
            trial = apply_insertion(c, nodes, r, i, j)
            if not _route_feasible(inst, t, trial):
                continue
            cand = (_money(inst, t, trial) - base, i, j)
            if best is None or cand[0] < best[0] - 1e-9:
                best = cand
    return best


def _random_route(c: Compiled, rng: random.Random) -> tuple[int, list[int], list[int]]:
    t = rng.randrange(c.n_types)
    nodes: list[int] = []
    order = list(range(c.inst.n_requests))
    rng.shuffle(order)
    outside: list[int] = []
    for r in order:
        if rng.random() < 0.5:
            found = best_insertion(c, RouteState(c, t, nodes), r)
            if found is not None:
                nodes = apply_insertion(c, nodes, r, found[1], found[2])
                continue
        outside.append(r)
    return t, nodes, outside


@pytest.mark.parametrize("tight", [False, True])
def test_best_insertion_matches_brute_force(tight: bool) -> None:
    checked = 0
    for seed in range(150):
        inst = random_instance(seed, n_requests=7, tight=tight)
        c = Compiled(inst)
        rng = random.Random(seed)
        t, nodes, outside = _random_route(c, rng)
        assert _route_feasible(inst, t, nodes), (seed, nodes)
        state = RouteState(c, t, nodes)
        for r in outside:
            fast = best_insertion(c, state, r)
            brute = _brute_force(c, t, nodes, r)
            assert (fast is None) == (brute is None), (seed, r, fast, brute)
            if fast is None or brute is None:
                continue
            assert fast[0] == pytest.approx(brute[0], abs=1e-6), (seed, r, fast, brute)
            assert _route_feasible(inst, t, apply_insertion(c, nodes, r, fast[1], fast[2]))
            checked += 1
    assert checked > 100


def test_regret_repair_output_always_verifies() -> None:
    for seed in range(40):
        inst = random_instance(seed, n_requests=9, n_types=3)
        c = Compiled(inst)
        for regret in (1, 2, 3):
            for noise in (0.0, 0.1):
                sol = regret_repair(
                    c,
                    Solution([], set(range(inst.n_requests))),
                    regret=regret,
                    noise=noise,
                    seed=seed,
                )
                verdict = verify(inst, sol)
                assert verdict.feasible, (seed, regret, verdict.violations)


def test_regret_repair_is_deterministic() -> None:
    inst = random_instance(3, n_requests=9, n_types=3)
    c = Compiled(inst)
    start = Solution([], set(range(inst.n_requests)))
    a = regret_repair(c, start, regret=2, noise=0.2, seed=99)
    b = regret_repair(c, start, regret=2, noise=0.2, seed=99)
    assert a.as_lists() == b.as_lists() and a.unassigned == b.unassigned


def test_splitmix64_reference_values() -> None:
    # Reference stream for seed 1234567 (Vigna's splitmix64.c).
    rng = SplitMix64(1234567)
    assert [rng.next_u64() for _ in range(3)] == [
        6457827717110365317,
        3203168211198807973,
        9817491932198370423,
    ]


def test_fast_exact_check_agrees_with_labelled_bellman_ford() -> None:
    from mobiroute.vrp.insertion import exact_feasible
    from mobiroute.vrp.schedule import route_timing

    agree = infeasible = 0
    for seed in range(120):
        inst = random_instance(seed, n_requests=6, ride_share=0.8)
        c = Compiled(inst)
        rng = random.Random(seed)
        for _ in range(6):
            t = rng.randrange(c.n_types)
            picked = rng.sample(range(inst.n_requests), rng.randint(1, 4))
            nodes = [n for r in picked for n in inst.requests[r].nodes]
            rng.shuffle(nodes)
            # restore pickup-before-delivery so only timing decides
            for r in picked:
                req = inst.requests[r]
                if req.is_pair:
                    a, b = nodes.index(req.pickup), nodes.index(req.delivery)
                    if a > b:
                        nodes[a], nodes[b] = nodes[b], nodes[a]
            fast = exact_feasible(c, t, nodes)
            assert fast == route_timing(inst, t, nodes).feasible, (seed, t, nodes)
            agree += 1
            infeasible += not fast
    assert agree == 720 and 50 < infeasible < 700
