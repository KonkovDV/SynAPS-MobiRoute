"""ALNS destroy/repair heuristic — never OPTIMAL."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.alns import _relatedness, solve_alns
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan
from tests.factories import driver, problem, trip, vehicle


def test_alns_never_optimal_and_notary() -> None:
    p = generate_day("tiny", seed=42)
    res = solve_alns(p, iterations=4, destroy_frac=0.3)
    assert res.solution_type == "ALNS"
    assert res.status != "OPTIMAL"
    assert res.solver_config.get("proven_optimal") is False
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
    assert res.solver_config.get("destroy_operators") == ["random", "shaw", "worst", "route"]
    greedy = solve_greedy(p)
    assert len(res.served_requests) >= len(greedy.served_requests)


def test_alns_shaw_prefers_related_trips() -> None:
    p = problem(
        [vehicle("v1")],
        [driver("d1")],
        [
            trip("a", "Z_NORTH", "Z_SOUTH", earliest=60),
            trip("b", "Z_NORTH", "Z_SOUTH", earliest=65),
            trip("c", "Z_EAST", "Z_WEST", earliest=200),
        ],
    )
    trips = {t.id: t for t in p.requests}
    near = _relatedness(p, trips["a"], trips["b"], True)
    far = _relatedness(p, trips["a"], trips["c"], False)
    assert near < far


def test_alns_deterministic() -> None:
    p = generate_day("tiny", seed=7)
    a = solve_alns(p, iterations=3, rng_seed=7)
    b = solve_alns(p, iterations=3, rng_seed=7)
    assert a.served_requests == b.served_requests
    assert a.config_hash == b.config_hash
    assert a.status != "OPTIMAL"
