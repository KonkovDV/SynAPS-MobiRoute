"""Adaptive LNS for DARP. Pattern from SynAPS ALNS + Ropke/Pisinger. Never OPTIMAL.

Destroy: random, Shaw relatedness, worst contribution, whole route.
Repair: greedy reinsertion into the surviving seed. SA accepts equal-served
worse duration; never accepts fewer served (lexicographic social-taxi).
"""

from __future__ import annotations

import math
import random

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.models import SolutionStatus
from mobiroute.domain.requests import DayProblem, PlanningResult, Stop, TripRequest
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import acceleration_status

DESTROY_OPS = ("random", "shaw", "worst", "route")


def _alns_score(result: PlanningResult) -> tuple[int, int]:
    served = len(result.served_requests)
    duration = sum(rp.route_duration for rp in result.route_plans)
    return (served, -duration)


def _duration_cost(result: PlanningResult) -> int:
    return sum(rp.route_duration for rp in result.route_plans)


def _trip_vehicle(result: PlanningResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for rp in result.route_plans:
        for tid in rp.passenger_assignments:
            out[tid] = rp.vehicle_id
    return out


def _relatedness(problem: DayProblem, a: TripRequest, b: TripRequest, same_veh: bool) -> int:
    tau = problem.travel.travel
    spatial = tau(a.pickup_zone, b.pickup_zone) + tau(a.dropoff_zone, b.dropoff_zone)
    if a.via_zone and b.via_zone:
        spatial += tau(a.via_zone, b.via_zone)
    temporal = abs(a.earliest_pickup - b.earliest_pickup)
    return spatial + temporal + (0 if same_veh else 20)


def _roulette(weights: list[float], rng: random.Random) -> int:
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(weights))
    x = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if x <= acc:
            return i
    return len(weights) - 1


def _destroy_random(served: list[str], q: int, rng: random.Random) -> set[str]:
    q = min(q, max(1, len(served) - 1))
    return set(rng.sample(sorted(served), q))


def _destroy_shaw(
    problem: DayProblem,
    result: PlanningResult,
    served: list[str],
    q: int,
    rng: random.Random,
) -> set[str]:
    trips = {t.id: t for t in problem.requests}
    veh = _trip_vehicle(result)
    remaining = sorted(served)
    seed = rng.choice(remaining)
    destroyed = {seed}
    remaining.remove(seed)
    q = min(q, max(1, len(served) - 1))
    while len(destroyed) < q and remaining:
        ref = trips[rng.choice(sorted(destroyed))]
        ranked = sorted(
            remaining,
            key=lambda tid: (
                -_relatedness(
                    problem,
                    ref,
                    trips[tid],
                    veh.get(ref.id) == veh.get(tid),
                ),
                tid,
            ),
        )
        pick = ranked[0]
        if rng.random() >= 0.75 and len(ranked) > 1:
            pick = ranked[rng.randrange(min(5, len(ranked)))]
        destroyed.add(pick)
        remaining.remove(pick)
    return destroyed


def _destroy_worst(
    result: PlanningResult,
    served: list[str],
    q: int,
    rng: random.Random,
) -> set[str]:
    contrib: dict[str, int] = {}
    for rp in result.route_plans:
        for tid in rp.passenger_assignments:
            contrib[tid] = rp.ride_times.get(tid, 0) + rp.waiting_times.get(tid, 0)
    ranked = sorted(served, key=lambda tid: (-contrib.get(tid, 0), tid))
    destroyed: set[str] = set()
    q = min(q, max(1, len(served) - 1))
    pool = list(ranked)
    while len(destroyed) < q and pool:
        if rng.random() < 0.8:
            pick = pool.pop(0)
        else:
            idx = rng.randrange(min(len(pool), max(1, len(pool) // 2)))
            pick = pool.pop(idx)
        destroyed.add(pick)
    return destroyed


def _destroy_route(
    result: PlanningResult, served: list[str], q: int, rng: random.Random
) -> set[str]:
    routes = [rp for rp in result.route_plans if rp.passenger_assignments]
    if not routes:
        return _destroy_random(served, q, rng)
    routes = sorted(routes, key=lambda rp: rp.vehicle_id)
    host = routes[rng.randrange(len(routes))]
    ids = sorted(host.passenger_assignments)
    q = min(q, max(1, len(served) - 1))
    if len(ids) <= q:
        if len(ids) >= len(served):
            return _destroy_random(served, q, rng)
        return set(ids)
    return set(ids[:q])


def _apply_destroy(
    name: str,
    problem: DayProblem,
    result: PlanningResult,
    served: list[str],
    q: int,
    rng: random.Random,
) -> set[str]:
    if name == "shaw":
        return _destroy_shaw(problem, result, served, q, rng)
    if name == "worst":
        return _destroy_worst(result, served, q, rng)
    if name == "route":
        return _destroy_route(result, served, q, rng)
    return _destroy_random(served, q, rng)


def _seed_from(
    result: PlanningResult, destroyed: set[str], problem: DayProblem
) -> tuple[
    dict[str, list[Stop]],
    dict[str, str | None],
]:
    seed_stops: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
    seed_drivers: dict[str, str | None] = {v.id: None for v in problem.vehicles}
    for rp in result.route_plans:
        kept_ids = {tid for tid in rp.passenger_assignments if tid not in destroyed}
        kept = [s for s in service_stops(rp.ordered_stops) if s.trip_id in kept_ids]
        seed_stops[rp.vehicle_id] = kept
        seed_drivers[rp.vehicle_id] = rp.driver_id if kept else None
    return seed_stops, seed_drivers


def _sa_accept(delta: int, temperature: float, rng: random.Random) -> bool:
    if delta <= 0:
        return True
    if temperature < 1e-9:
        return False
    return rng.random() < math.exp(-delta / temperature)


def solve_alns(
    problem: DayProblem,
    *,
    destroy_frac: float = 0.25,
    iterations: int = 12,
    rng_seed: int | None = None,
    sa_initial_temp: float = 40.0,
    sa_cooling: float = 0.92,
) -> PlanningResult:
    """Adaptive destroy/repair. Heuristic only — never OPTIMAL."""
    seed = problem.seed if rng_seed is None else rng_seed
    rng = random.Random(seed)
    current = solve_greedy(problem)
    best = current
    weights = [1.0] * len(DESTROY_OPS)
    scores = [0.0] * len(DESTROY_OPS)
    attempts = [0] * len(DESTROY_OPS)
    temperature = sa_initial_temp
    segment = 4
    for it in range(iterations):
        served = list(current.served_requests)
        if len(served) < 2:
            break
        op_idx = _roulette(weights, rng)
        op_name = DESTROY_OPS[op_idx]
        n_destroy = max(1, int(len(served) * destroy_frac))
        n_destroy = min(n_destroy, len(served) - 1)
        destroyed = _apply_destroy(op_name, problem, current, served, n_destroy, rng)
        seed_stops, seed_drivers = _seed_from(current, destroyed, problem)
        cand = solve_greedy(problem, seed_stops=seed_stops, seed_drivers=seed_drivers)
        cur_s, _cur_neg = _alns_score(current)
        cand_s, _cand_neg = _alns_score(cand)
        accepted = False
        improved = False
        if cand_s < cur_s:
            accepted = False
        elif cand_s > cur_s:
            accepted = True
            improved = True
        else:
            delta = _duration_cost(cand) - _duration_cost(current)
            accepted = _sa_accept(delta, temperature, rng)
            improved = delta < 0
        reward = 0.0
        if accepted and _alns_score(cand) > _alns_score(best):
            best = cand
            current = cand
            reward = 4.0
        elif accepted and improved:
            current = cand
            reward = 2.0
        elif accepted:
            current = cand
            reward = 1.0
        scores[op_idx] += reward
        attempts[op_idx] += 1
        if (it + 1) % segment == 0:
            for i in range(len(DESTROY_OPS)):
                avg = scores[i] / attempts[i] if attempts[i] else 0.0
                weights[i] = 0.8 * weights[i] + 0.2 * (avg + 0.1)
            scores = [0.0] * len(DESTROY_OPS)
            attempts = [0] * len(DESTROY_OPS)
        temperature *= sa_cooling
    cfg = {
        **best.solver_config,
        "name": "ALNS",
        "proven_optimal": False,
        "destroy_frac": destroy_frac,
        "iterations": iterations,
        "rng_seed": seed,
        "destroy_operators": list(DESTROY_OPS),
        "operator_weights": {n: round(w, 4) for n, w in zip(DESTROY_OPS, weights, strict=True)},
        "sa_initial_temp": sa_initial_temp,
        "sa_cooling": sa_cooling,
        **acceleration_status(),
    }
    status = best.status
    if status in {SolutionStatus.OPTIMAL.value, SolutionStatus.FEASIBLE.value}:
        status = SolutionStatus.HEURISTIC_FEASIBLE.value
    return best.model_copy(
        update={
            "solution_type": "ALNS",
            "status": status,
            "config_hash": fingerprint(
                {
                    "solver": "ALNS",
                    "version": __version__,
                    "synaps": SYNAPS_COMMIT,
                    "destroy_frac": destroy_frac,
                    "iterations": iterations,
                    "rng_seed": seed,
                    "ops": list(DESTROY_OPS),
                    "sa": [sa_initial_temp, sa_cooling],
                }
            ),
            "solver_config": cfg,
        }
    )
