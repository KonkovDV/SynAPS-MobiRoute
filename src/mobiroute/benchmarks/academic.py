"""Feasibility-first gating for open-data benchmark claims.

A green CI job is not a benchmark result. This module turns the review rule
"no published gap without a comparable, fully served, notary-verified run"
into an executable contract: :func:`build_academic_report` fills
``gap_percent`` only when every gate passes, and otherwise publishes the
blockers that stopped it.

Profiles
--------
``literature_profile_a``
    Run intended to be comparable with published results: literature
    objective only, no operator policy, no extra dwell.
``operator_profile_b``
    Run with Moscow social-taxi operator policy on top of the instance.
    Never comparable with a literature best-known solution.

Even under profile A the vendored Cordeau loader rounds Euclidean travel to
integer minutes and applies a curb dwell, so ``algebra_matches_reference``
stays ``False`` until a loader reproduces the published cost algebra.
"""

from __future__ import annotations

import platform
from collections.abc import Mapping, Sequence
from enum import StrEnum

from mobiroute.domain.models import StrictModel
from mobiroute.domain.requests import DayProblem, PlanningResult

# Ho, S.C. et al. (2018) survey table for Cordeau (2006) instance a2-16.
CORDEAU_A2_16_REFERENCE = 294.25
CORDEAU_A2_16_REFERENCE_SOURCE = "Ho et al. (2018) survey table for Cordeau (2006) a2-16"

_COMPARABLE_STATUSES = frozenset({"OPTIMAL", "FEASIBLE", "HEURISTIC_FEASIBLE"})


class BenchmarkProfile(StrEnum):
    """Which constraint algebra a benchmark run used."""

    LITERATURE = "literature_profile_a"
    OPERATOR = "operator_profile_b"


class GapBlocker(StrEnum):
    """Why a gap against a published objective may not be quoted."""

    PROFILE_NOT_LITERATURE = "PROFILE_NOT_LITERATURE"
    ALGEBRA_NOT_COMPARABLE = "ALGEBRA_NOT_COMPARABLE"
    PLAN_NOT_VERIFIED = "PLAN_NOT_VERIFIED"
    STATUS_NOT_COMPARABLE = "STATUS_NOT_COMPARABLE"
    SERVICE_INCOMPLETE = "SERVICE_INCOMPLETE"
    ACCOUNTING_INCOMPLETE = "ACCOUNTING_INCOMPLETE"
    NO_REFERENCE_OBJECTIVE = "NO_REFERENCE_OBJECTIVE"


class AcademicBenchmarkReport(StrictModel):
    """One open-data run with a machine-checked claim gate."""

    instance_id: str
    profile: BenchmarkProfile
    claim_level: str
    status: str
    verified_feasible: bool
    algebra_matches_reference: bool
    requests_total: int
    served_count: int
    rejected_count: int
    unaccounted_count: int
    full_service: bool
    service_rate: float
    kernel_route_distance: float
    kernel_route_duration: int
    reference_objective: float | None
    reference_source: str | None
    gap_percent: float | None
    gap_blockers: list[str]
    allowed_claim: str


class BenchmarkEvidence(StrictModel):
    """Reproducibility stamp published next to every benchmark number."""

    mobiroute_version: str
    synaps_commit: str
    python_version: str
    platform: str
    native_available: bool
    insertion_backend: str
    instance_path: str
    instance_sha256: str
    solver: str
    seed: int
    input_hash: str
    config_hash: str
    plan_id: str
    wall_clock_seconds: float
    notary_feasible: bool
    notary_violations: list[str]
    exit_code: int


def build_academic_report(
    problem: DayProblem,
    result: PlanningResult,
    *,
    profile: BenchmarkProfile,
    reference_objective: float | None = None,
    reference_source: str | None = None,
    algebra_matches_reference: bool = False,
) -> AcademicBenchmarkReport:
    """Report one run and gate the gap behind every comparability condition."""
    trip_ids = {trip.id for trip in problem.requests}
    served = set(result.served_requests)
    rejected = {record.trip_id for record in result.rejected_requests}
    unaccounted = trip_ids - served - rejected
    total = len(trip_ids)
    full_service = bool(trip_ids) and trip_ids.issubset(served)
    service_rate = len(trip_ids & served) / total if total else 0.0

    blockers: list[str] = []
    if profile is not BenchmarkProfile.LITERATURE:
        blockers.append(GapBlocker.PROFILE_NOT_LITERATURE.value)
    if not algebra_matches_reference:
        blockers.append(GapBlocker.ALGEBRA_NOT_COMPARABLE.value)
    if not result.verified_feasible:
        blockers.append(GapBlocker.PLAN_NOT_VERIFIED.value)
    if result.status not in _COMPARABLE_STATUSES:
        blockers.append(GapBlocker.STATUS_NOT_COMPARABLE.value)
    if not full_service:
        blockers.append(GapBlocker.SERVICE_INCOMPLETE.value)
    if unaccounted:
        blockers.append(GapBlocker.ACCOUNTING_INCOMPLETE.value)
    if reference_objective is None or reference_objective <= 0.0:
        blockers.append(GapBlocker.NO_REFERENCE_OBJECTIVE.value)

    distance = float(sum(plan.route_distance for plan in result.route_plans))
    duration = int(sum(plan.route_duration for plan in result.route_plans))

    gap: float | None = None
    if not blockers and reference_objective is not None:
        gap = 100.0 * (distance - reference_objective) / reference_objective

    if gap is None:
        blocked = ", ".join(blockers)
        claim = f"{result.claim_level}: run recorded, no publishable gap ({blocked})"
    else:
        source = reference_source or "the reference objective"
        claim = f"{result.claim_level}: full-service verified run, gap {gap:.2f}% vs {source}"

    return AcademicBenchmarkReport(
        instance_id=problem.problem_id,
        profile=profile,
        claim_level=result.claim_level,
        status=result.status,
        verified_feasible=result.verified_feasible,
        algebra_matches_reference=algebra_matches_reference,
        requests_total=total,
        served_count=len(served),
        rejected_count=len(rejected),
        unaccounted_count=len(unaccounted),
        full_service=full_service,
        service_rate=service_rate,
        kernel_route_distance=distance,
        kernel_route_duration=duration,
        reference_objective=reference_objective,
        reference_source=reference_source,
        gap_percent=gap,
        gap_blockers=blockers,
        allowed_claim=claim,
    )


def build_cordeau_a2_16_report(
    problem: DayProblem,
    result: PlanningResult,
    *,
    profile: BenchmarkProfile = BenchmarkProfile.LITERATURE,
    algebra_matches_reference: bool = False,
) -> AcademicBenchmarkReport:
    """a2-16 report wired to the literature BKS; the gap stays gated."""
    return build_academic_report(
        problem,
        result,
        profile=profile,
        reference_objective=CORDEAU_A2_16_REFERENCE,
        reference_source=CORDEAU_A2_16_REFERENCE_SOURCE,
        algebra_matches_reference=algebra_matches_reference,
    )


def build_evidence(
    result: PlanningResult,
    *,
    instance_path: str,
    instance_sha256: str,
    solver: str,
    seed: int,
    wall_clock_seconds: float,
    notary_feasible: bool,
    notary_violations: Sequence[str],
    exit_code: int,
) -> BenchmarkEvidence:
    """Collect the run stamp a reviewer needs to reproduce or reject a number."""
    from mobiroute import SYNAPS_COMMIT, __version__
    from mobiroute.solvers.native_accel import acceleration_status

    status: Mapping[str, object] = acceleration_status()
    return BenchmarkEvidence(
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        python_version=platform.python_version(),
        platform=platform.platform(),
        native_available=bool(status.get("native_available", False)),
        insertion_backend=str(status.get("insertion_backend", "unknown")),
        instance_path=instance_path,
        instance_sha256=instance_sha256,
        solver=solver,
        seed=seed,
        input_hash=result.input_hash,
        config_hash=result.config_hash,
        plan_id=result.plan_id,
        wall_clock_seconds=round(wall_clock_seconds, 3),
        notary_feasible=notary_feasible,
        notary_violations=[str(item) for item in notary_violations],
        exit_code=exit_code,
    )
