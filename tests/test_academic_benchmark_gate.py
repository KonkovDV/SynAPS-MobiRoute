"""No comparable run, no published gap: the claim gate is a test, not a promise."""

from __future__ import annotations

from pathlib import Path

import pytest

from mobiroute import __version__
from mobiroute.adapters.cordeau import CORDEAU_A2_16_BKS, load_cordeau_a2_16
from mobiroute.benchmarks.academic import (
    CORDEAU_A2_16_REFERENCE,
    BenchmarkProfile,
    build_academic_report,
    build_cordeau_a2_16_report,
    build_evidence,
)
from mobiroute.domain.requests import PlanningResult
from mobiroute.solvers.native_accel import acceleration_status
from mobiroute.validation.feasibility import check_plan

_ROOT = Path(__file__).resolve().parents[1]
_INSTANCE = _ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt"


def _fixture_result(*, served: list[str], verified: bool, status: str) -> PlanningResult:
    """Accounting-only fixture: it carries no route plans, so the objective is 0.0."""
    return PlanningResult(
        status=status,
        solution_type="ADVERSARIAL",
        verified_feasible=verified,
        served_requests=list(served),
        rejected_requests=[],
        route_plans=[],
        input_hash="x",
        config_hash="y",
        mobiroute_version="0",
        synaps_commit="0",
        claim_level="open_data_benchmark",
    )


def test_adapted_cordeau_algebra_blocks_every_published_gap() -> None:
    problem = load_cordeau_a2_16(_INSTANCE)
    served = [trip.id for trip in problem.requests]
    result = _fixture_result(served=served, verified=True, status="HEURISTIC_FEASIBLE")

    report = build_cordeau_a2_16_report(problem, result)

    assert report.reference_objective == CORDEAU_A2_16_REFERENCE == CORDEAU_A2_16_BKS
    assert report.full_service
    assert report.service_rate == 1.0
    assert report.gap_percent is None
    assert report.gap_blockers == ["ALGEBRA_NOT_COMPARABLE"]
    assert "no gap against published results" in report.allowed_claim


def test_operator_profile_can_never_publish_a_literature_gap() -> None:
    problem = load_cordeau_a2_16(_INSTANCE)
    served = [trip.id for trip in problem.requests]
    result = _fixture_result(served=served, verified=True, status="HEURISTIC_FEASIBLE")

    report = build_cordeau_a2_16_report(
        problem, result, profile=BenchmarkProfile.OPERATOR, algebra_matches_reference=True
    )

    assert report.profile == BenchmarkProfile.OPERATOR
    assert report.gap_blockers == ["PROFILE_NOT_LITERATURE"]
    assert report.gap_percent is None


def test_unverified_partial_run_lists_every_blocker() -> None:
    problem = load_cordeau_a2_16(_INSTANCE)
    served = [trip.id for trip in problem.requests][:3]
    result = _fixture_result(served=served, verified=False, status="NOT_VERIFIED")

    report = build_cordeau_a2_16_report(problem, result)

    assert report.gap_percent is None
    assert set(report.gap_blockers) == {
        "ALGEBRA_NOT_COMPARABLE",
        "PLAN_NOT_VERIFIED",
        "STATUS_NOT_COMPARABLE",
        "SERVICE_INCOMPLETE",
        "ACCOUNTING_INCOMPLETE",
    }
    assert report.unaccounted_count == len(problem.requests) - 3
    assert report.service_rate == pytest.approx(3 / len(problem.requests))


def test_gap_formula_runs_only_when_every_gate_passes() -> None:
    problem = load_cordeau_a2_16(_INSTANCE)
    served = [trip.id for trip in problem.requests]
    result = _fixture_result(served=served, verified=True, status="HEURISTIC_FEASIBLE")

    report = build_academic_report(
        problem,
        result,
        profile=BenchmarkProfile.LITERATURE,
        reference_objective=200.0,
        reference_source="unit fixture, not a literature table",
        algebra_matches_reference=True,
    )

    # The fixture carries no route plans, so the kernel objective is 0.0 by
    # construction: this asserts the arithmetic and the gate, not plan quality.
    assert report.gap_blockers == []
    assert report.kernel_route_distance == 0.0
    assert report.gap_percent == pytest.approx(-100.0)
    assert "gap -100.00%" in report.allowed_claim


def test_greedy_a2_16_run_is_recorded_with_evidence_and_no_quality_claim() -> None:
    if not acceleration_status().get("native_available"):
        pytest.skip("mobiroute_native not built")
    from mobiroute.solvers.greedy import solve_greedy

    problem = load_cordeau_a2_16(_INSTANCE)
    result = solve_greedy(problem)
    notary = check_plan(problem, result)
    report = build_cordeau_a2_16_report(problem, result)
    evidence = build_evidence(
        result,
        instance_path=str(_INSTANCE),
        instance_sha256="",
        solver="greedy",
        seed=problem.seed,
        wall_clock_seconds=0.0,
        notary_feasible=notary.feasible,
        notary_violations=[str(item) for item in notary.violations],
        exit_code=0,
    )

    assert notary.feasible, notary.violations
    assert report.claim_level == "open_data_benchmark"
    assert report.served_count + report.rejected_count == report.requests_total
    assert report.unaccounted_count == 0
    assert report.kernel_route_distance > 0.0
    assert report.gap_percent is None
    assert "ALGEBRA_NOT_COMPARABLE" in report.gap_blockers
    assert evidence.mobiroute_version == __version__
    assert evidence.native_available
    assert evidence.notary_feasible
