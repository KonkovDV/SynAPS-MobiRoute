"""Differential and robustness fuzzing, at a scale the unit tests do not run.

Usage:
  python benchmark/fuzz_differential.py [SEEDS]   (default 300; 4000 takes about 30 s)

1. Rust kernel vs Python reference: best insertion and exact route check on
   random instances with every rule the kernel covers (ride limits, rests
   whole and split, reloads, rush hours), many more seeds than the tests.
2. Shortest shift with rests vs enumeration of every rest place.
3. Verifier vs random garbage plans: never raises, never reports a non-finite cost.
4. Every plan ALNS returns on random instances passes the verifier, on both backends,
   and both backends return the same plan.
"""

from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import replace
from itertools import pairwise

from mobiroute.vrp import native
from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.insertion import (
    Compiled,
    RouteState,
    best_insertion,
    regret_repair,
    remove_requests,
    route_exact,
)
from mobiroute.vrp.model import BreakRule, Instance, SpeedProfile, add_reload_stops
from mobiroute.vrp.schedule import TIME_EPS, _timing_with, route_timing
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.traffic import with_traffic
from mobiroute.vrp.verify import verify

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 300


def variant(seed: int) -> Instance:
    rng = random.Random(seed * 7919 + 13)
    kind = seed % 4
    if kind == 3:  # rush hours: no ride limits, no rests
        base = random_instance(
            seed, n_requests=rng.randint(4, 12), n_types=rng.randint(1, 3), ride_share=0.0
        )
        speed = SpeedProfile(
            tuple(
                sorted({0.0, *(round(rng.uniform(10, 280), 1) for _ in range(rng.randint(1, 4)))})
            ),
            (),
        )
        speed = SpeedProfile(
            speed.starts, tuple(round(rng.uniform(0.3, 1.2), 2) for _ in speed.starts)
        )
        inst = with_traffic(base, speed)
    else:
        inst = random_instance(
            seed,
            n_requests=rng.randint(4, 12),
            n_types=rng.randint(1, 3),
            ride_share=rng.choice([0.0, 0.3, 0.6]),
            tight=rng.random() < 0.3,
        )
        if kind >= 1:
            split = (15.0, 30.0) if kind == 2 else None
            types = tuple(
                replace(vt, breaks=BreakRule(rng.uniform(40.0, 200.0), 45.0, split))
                for vt in inst.vehicle_types
            )
            inst = replace(inst, vehicle_types=types)
    if rng.random() < 0.5:
        inst = add_reload_stops(
            inst, inst.vehicle_types[0].id, rng.randint(2, 3), rng.choice([5.0, 15.0])
        )
    return inst


def part1() -> int:
    compared = mismatches = 0
    for seed in range(SEEDS):
        inst = variant(seed)
        c = Compiled(inst)
        kernel = native.build_kernel(c)
        assert kernel is not None
        rng = random.Random(seed)
        sol = regret_repair(c, Solution([], set(range(inst.n_requests))), regret=2)
        sol = remove_requests(c, sol, {r for r in range(inst.n_requests) if rng.random() < 0.4})
        for route in sol.routes:
            t, nodes = route.vehicle_type, list(route.nodes)
            for trial in (nodes, rng.sample(nodes, len(nodes))):
                if kernel.exact_feasible_route(t, trial) != route_exact(c, t, trial):
                    mismatches += 1
                    print("exact mismatch", seed, t, trial)
            st = RouteState(c, t, nodes)
            for r in sorted(sol.unassigned):
                py = best_insertion(c, st, r)
                rs = kernel.best_insertion(t, nodes, r)
                compared += 1
                if py != rs:
                    mismatches += 1
                    print("insertion mismatch", seed, r, py, rs)
    print(f"[1] kernel vs reference: {compared} insertions compared, {mismatches} mismatches")
    return mismatches


def brute(inst: Instance, nodes: list[int]) -> float:
    vt = inst.vehicle_types[0]
    rule = vt.breaks
    assert rule is not None
    time = inst.profiles[vt.profile].time
    seq = [vt.start_depot, *nodes, vt.end_depot]
    legs = [time[a][b] for a, b in pairwise(seq)]
    driving = math.fsum(legs)
    if driving <= rule.max_driving + TIME_EPS:
        return _timing_with(inst, 0, nodes, None, driving).min_duration
    best, done, adm = math.inf, 0.0, []
    for k, leg in enumerate(legs):
        before, after = done, done + leg
        done = after
        if any(
            driving - rule.max_driving - TIME_EPS <= x <= rule.max_driving + TIME_EPS
            for x in (before, after)
        ):
            adm.append(k)
            tm = _timing_with(inst, 0, nodes, k, driving)
            if tm.feasible:
                best = min(best, tm.min_duration)
    if rule.split:
        for k in adm:
            for f in range(k):
                tm = _timing_with(inst, 0, nodes, k, driving, f)
                if tm.feasible:
                    best = min(best, tm.min_duration)
    return best


def _rest_route(seed: int) -> tuple[Instance, list[int]]:
    """One vehicle, depot deliveries with wide windows, a 2-hour driving limit."""
    from mobiroute.vrp.model import Node, Request, VehicleType, euclidean_matrix, single_profile

    rng = random.Random(seed)
    n = rng.randint(3, 7)
    pts = [(0.0, 0.0)] + [(rng.uniform(-80, 80), rng.uniform(-80, 80)) for _ in range(n)]
    nodes = [Node(0, 0.0, 2000.0, 0.0)]
    for k in range(1, n + 1):
        lo = rng.uniform(0.0, 600.0)
        nodes.append(Node(k, lo, lo + rng.uniform(30.0, 400.0), rng.choice([5.0, 10.0, 20.0])))
    split = (15.0, 30.0) if rng.random() < 0.5 else None
    inst = Instance(
        "rest",
        tuple(nodes),
        tuple(Request(f"r{k}", None, k, (1.0,)) for k in range(1, n + 1)),
        (VehicleType("v", (99.0,), count=1, breaks=BreakRule(120.0, 45.0, split)),),
        single_profile(euclidean_matrix(pts)),
    )
    order = list(range(1, n + 1))
    rng.shuffle(order)
    return inst, order


def part2() -> int:
    checked = bad = 0
    for seed in range(SEEDS * 4):
        inst, order = _rest_route(seed)
        tm = route_timing(inst, 0, order)
        if not tm.feasible:
            continue
        checked += 1
        if abs(tm.min_duration - brute(inst, order)) > 1e-6:
            bad += 1
            print("shift mismatch", seed)
    print(f"[2] shortest shift vs enumeration: {checked} feasible routes, {bad} mismatches")
    return bad


def part3() -> int:
    raised = bad_cost = 0
    rng = random.Random(5)
    for k in range(SEEDS * 20):
        inst = random_instance(k % 50, n_requests=6)
        routes = [
            Route(
                rng.randint(-2, 4),
                [rng.randint(-3, inst.n_nodes + 2) for _ in range(rng.randint(0, 7))],
            )
            for _ in range(rng.randint(0, 4))
        ]
        plan = Solution(routes, {rng.randint(-2, 9) for _ in range(rng.randint(0, 3))})
        try:
            v = verify(inst, plan)
            if not math.isfinite(v.cost.total):
                bad_cost += 1
        except Exception as exc:
            raised += 1
            print("verify raised", type(exc).__name__, exc)
    print(
        f"[3] verifier on {SEEDS * 20} garbage plans: {raised} raised, {bad_cost} non-finite costs"
    )
    return raised + bad_cost


def part4() -> int:
    infeasible = differ = 0
    n = max(10, SEEDS // 10)
    for seed in range(n):
        inst = variant(seed)
        a = solve(inst, AlnsConfig(iterations=60, seed=seed, backend="python", segment=20))
        b = solve(inst, AlnsConfig(iterations=60, seed=seed, backend="native", segment=20))
        if not (a.verdict.feasible and b.verdict.feasible):
            infeasible += 1
            print("infeasible plan", seed, a.verdict.violations[:3], b.verdict.violations[:3])
        if a.solution.as_lists() != b.solution.as_lists() or a.objective != b.objective:
            differ += 1
            print("trajectory differs", seed)
    print(
        f"[4] ALNS on {n} rich instances, both backends: {infeasible} infeasible, {differ} differ"
    )
    return infeasible + differ


if __name__ == "__main__":
    t0 = time.perf_counter()
    failures = sum(part() for part in (part1, part2, part3, part4))
    print(f"done in {time.perf_counter() - t0:.0f} s, {failures} failures")
    sys.exit(1 if failures else 0)
