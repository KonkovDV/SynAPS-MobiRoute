"""Rolling horizon — heuristic, never OPTIMAL."""

from __future__ import annotations

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.rolling_horizon import _window_ends, solve_rolling_horizon
from mobiroute.validation.completeness import incomplete_plan_issues
from mobiroute.validation.feasibility import check_plan


def test_rhc_never_optimal_and_notary() -> None:
    p = generate_day("tiny", seed=42)
    res = solve_rolling_horizon(p, window_minutes=120, overlap_minutes=20)
    assert res.solution_type == "RHC"
    assert res.status != "OPTIMAL"
    assert res.solver_config.get("proven_optimal") is False
    assert res.solver_config.get("window_minutes") == 120
    report = check_plan(p, res)
    if res.verified_feasible:
        assert report.feasible
    assert not incomplete_plan_issues(p, res)


def test_rhc_deterministic() -> None:
    p = generate_day("tiny", seed=7)
    a = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    b = solve_rolling_horizon(p, window_minutes=90, overlap_minutes=15)
    assert a.served_requests == b.served_requests
    assert a.config_hash == b.config_hash
    assert a.input_hash == b.input_hash


def test_rhc_windows_cover_horizon() -> None:
    ends = _window_ends(60, 400, 180, 30)
    assert ends[0] == 240
    assert ends[-1] > 400
    assert all(ends[i] < ends[i + 1] for i in range(len(ends) - 1))


def test_rhc_accounts_every_active_trip() -> None:
    p = generate_day("tiny", seed=3)
    res = solve_rolling_horizon(p, window_minutes=60, overlap_minutes=10)
    accounted = set(res.served_requests) | {r.trip_id for r in res.rejected_requests}
    active = {t.id for t in p.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}}
    assert active <= accounted
    greedy = solve_greedy(p)
    # Windowed composition may serve fewer; must not claim OPTIMAL either way.
    assert res.status != "OPTIMAL"
    assert greedy.status != "OPTIMAL"
