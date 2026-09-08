"""Cordeau a2-16 data and correctness gates, not literature-quality certification."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mobiroute.adapters.cordeau import CORDEAU_A2_16_BKS, load_cordeau_a2_16, parse_cordeau_darp
from mobiroute.solvers.native_accel import acceleration_status
from mobiroute.validation.feasibility import check_plan

_ROOT = Path(__file__).resolve().parents[1]
_INSTANCE = _ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt"
_SUMS = _ROOT / "benchmark" / "instances" / "cordeau" / "SHA256SUMS.txt"


def test_a2_16_header_is_two_vehicles_sixteen_requests() -> None:
    text = _INSTANCE.read_text(encoding="utf-8")
    header = text.splitlines()[0].split()
    assert header == ["2", "16", "480", "3", "30"]
    problem = parse_cordeau_darp(text, instance_id="cordeau-a2-16")
    assert len(problem.requests) == 16
    assert len(problem.vehicles) == 2
    assert problem.claim_level == "open_data_benchmark"
    assert problem.requests[0].max_ride_time == 30


def test_a2_16_sha256sums_match_working_tree_bytes() -> None:
    listed: dict[str, str] = {}
    for line in _SUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        listed[name] = digest.lower()
    assert "a2-16.txt" in listed
    digest = hashlib.sha256(_INSTANCE.read_bytes()).hexdigest()
    assert digest == listed["a2-16.txt"]


def test_a2_16_literature_bks_is_not_claimed_as_this_kernel() -> None:
    assert CORDEAU_A2_16_BKS == 294.25
    problem = load_cordeau_a2_16(_INSTANCE)
    # Integer Euclidean depot->n1 is not the real BKS cost.
    assert problem.travel.travel("depot", "n1") != CORDEAU_A2_16_BKS


def test_finalize_keeps_open_data_claim_level() -> None:
    from mobiroute.domain.requests import PlanningResult
    from mobiroute.solvers.finalize import finalize_result

    problem = load_cordeau_a2_16(_INSTANCE)
    result = PlanningResult(
        status="HEURISTIC_FEASIBLE",
        solution_type="ADVERSARIAL",
        verified_feasible=False,
        served_requests=[],
        rejected_requests=[],
        route_plans=[],
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
        claim_level="synthetic_benchmark",
    )
    out = finalize_result(problem, result)
    assert out.claim_level == "open_data_benchmark"
    assert out.status == "NOT_VERIFIED"
    assert not out.verified_feasible


def test_a2_16_greedy_has_verified_nonempty_accounting() -> None:
    if not acceleration_status().get("native_available"):
        pytest.skip("mobiroute_native not built")
    from mobiroute.solvers.greedy import solve_greedy

    problem = load_cordeau_a2_16(_INSTANCE)
    result = solve_greedy(problem)
    report = check_plan(problem, result)
    assert report.feasible, report.violations
    assert result.verified_feasible
    assert result.status in {"HEURISTIC_FEASIBLE", "PARTIAL"}
    assert result.claim_level == "open_data_benchmark"
    served = set(result.served_requests)
    rejected = {r.trip_id for r in result.rejected_requests}
    # A nonempty feasible partial plan is not a BKS or full-service quality claim.
    assert served
    assert len(served) == len(result.served_requests)
    assert len(rejected) == len(result.rejected_requests)
    assert not served & rejected
    assert served | rejected == {t.id for t in problem.requests}
    assert all(r.reason_code.strip() for r in result.rejected_requests)
    assert result.objective_values["served"] == len(served)
