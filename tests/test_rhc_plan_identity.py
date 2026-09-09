"""An RHC plan id must fingerprint RHC, not the greedy pass underneath."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.rolling_horizon import solve_rolling_horizon


def test_plan_id_matches_the_published_config() -> None:
    p = generate_day("tiny", seed=7)
    res = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    assert res.solution_type == "RHC"
    assert res.plan_id == plan_identity(res)


def test_different_windows_publish_different_plan_ids() -> None:
    p = generate_day("tiny", seed=7)
    a = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    b = solve_rolling_horizon(p, window_minutes=240, overlap_minutes=15)
    assert a.config_hash != b.config_hash
    assert a.plan_id != b.plan_id


def test_plan_id_is_deterministic_and_not_the_greedy_id() -> None:
    p = generate_day("tiny", seed=7)
    a = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    b = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    assert a.plan_id == b.plan_id
    assert a.plan_id != solve_greedy(p).plan_id
