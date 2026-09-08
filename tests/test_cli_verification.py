"""CLI success requires both notary verification and a successful status."""

from pathlib import Path

import pytest

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.cli import main
from mobiroute.domain.models import SolutionStatus
from mobiroute.domain.requests import PlanningResult


@pytest.mark.parametrize("status", [*SolutionStatus, "UNKNOWN_STATUS"])
@pytest.mark.parametrize("verified", [False, True])
def test_solve_exit_requires_verified_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, verified: bool
) -> None:
    source = tmp_path / "problem.json"
    source.write_text(generate_day("tiny", seed=2).model_dump_json(), encoding="utf-8")
    result = PlanningResult(
        status=status,
        solution_type="TEST",
        verified_feasible=verified,
        served_requests=[],
        rejected_requests=[],
        route_plans=[],
        input_hash="test",
        config_hash="test",
        mobiroute_version="test",
        synaps_commit="test",
    )
    monkeypatch.setattr("mobiroute.cli.solve_greedy", lambda _: result)
    success = verified and status in {"OPTIMAL", "FEASIBLE", "HEURISTIC_FEASIBLE", "PARTIAL"}
    code = main(["solve", "--problem", str(source), "--out-dir", str(tmp_path / "out")])
    assert code == (0 if success else 2)
    assert (tmp_path / "out" / "result.json").exists()
