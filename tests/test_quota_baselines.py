"""Baselines respect the passenger-day quota instead of handing the notary a breach."""

from __future__ import annotations

import pytest

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.native_accel import native_available
from mobiroute.solvers.nearest import solve_nearest
from mobiroute.validation.feasibility import check_plan, quota_caps, used_quota_minutes


@pytest.mark.parametrize("solver", [solve_nearest, solve_beam])
def test_quota_scenario_is_verified_with_an_explained_refusal(solver) -> None:  # type: ignore[no-untyped-def]
    if not native_available():
        pytest.skip("mobiroute_native not built")
    p = generate_day("ops_quota", seed=42)
    res = solver(p)
    assert check_plan(p, res).feasible
    assert res.verified_feasible
    assert res.status == "PARTIAL"
    used = used_quota_minutes(p, res)
    assert all(used.get(pid, 0) <= cap for pid, cap in quota_caps(p).items())
    assert any(r.reason_code == "QUOTA_EXCEEDED" for r in res.rejected_requests)
