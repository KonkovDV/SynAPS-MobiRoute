"""An RHC stamp may not publish an exact-lane status."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.domain.models import ReasonCode, SolutionStatus
from mobiroute.domain.requests import PlanningResult, RejectedTrip
from mobiroute.solvers.finalize import plan_identity
from mobiroute.solvers.rolling_horizon import _stamp_rhc


def _inner_pass(status: str, *, rejected: list[RejectedTrip] | None = None) -> PlanningResult:
    """A stub inner pass: only the fields the RHC stamp reads or republishes."""
    return PlanningResult(
        status=status,
        solution_type="GREEDY_STUB",
        verified_feasible=True,
        served_requests=["t1"],
        rejected_requests=list(rejected or []),
        route_plans=[],
        objective_values={"served": 1.0, "rejected": 0.0},
        plan_id="inner-pass-id",
        input_hash="input-hash",
        config_hash="inner-config-hash",
        solver_config={"name": "GREEDY_STUB", "pooling": True},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
    )


def test_an_exact_label_is_downgraded() -> None:
    for exact in (SolutionStatus.OPTIMAL.value, SolutionStatus.FEASIBLE.value):
        stamped = _stamp_rhc(_inner_pass(exact), 180, 30, windows=3)
        assert stamped.status == SolutionStatus.HEURISTIC_FEASIBLE.value
        assert stamped.solution_type == "RHC"
        assert stamped.solver_config["proven_optimal"] is False


def test_an_exact_label_with_refusals_is_partial() -> None:
    refused = [RejectedTrip(trip_id="t2", reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)]
    for exact in (SolutionStatus.OPTIMAL.value, SolutionStatus.FEASIBLE.value):
        stamped = _stamp_rhc(_inner_pass(exact, rejected=refused), 180, 30, windows=3)
        assert stamped.status == SolutionStatus.PARTIAL.value


def test_a_refusing_or_heuristic_status_is_published_unchanged() -> None:
    for status in (
        SolutionStatus.HEURISTIC_FEASIBLE.value,
        SolutionStatus.PARTIAL.value,
        SolutionStatus.NOT_VERIFIED.value,
        SolutionStatus.INFEASIBLE.value,
    ):
        stamped = _stamp_rhc(_inner_pass(status), 180, 30, windows=1)
        assert stamped.status == status


def test_the_stamp_republishes_identity_and_keeps_the_input_hash() -> None:
    heuristic = SolutionStatus.HEURISTIC_FEASIBLE.value
    stamped = _stamp_rhc(_inner_pass(heuristic), 90, 15, windows=2)
    assert stamped.input_hash == "input-hash"
    assert stamped.config_hash != "inner-config-hash"
    assert stamped.plan_id != "inner-pass-id"
    assert stamped.plan_id == plan_identity(stamped)
    assert stamped.solver_config["windows"] == 2
