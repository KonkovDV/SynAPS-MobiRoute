"""ADR-0004 pin bump: fail-closed coverage and calendar encode on pinned SynAPS."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("synaps")

from synaps.model import (
    Operation,
    Order,
    ScheduleProblem,
    ScheduleResult,
    ShiftInterval,
    SolverStatus,
    State,
    WorkCenter,
)
from synaps.solvers.coverage_outcome import (
    CoverageClass,
    process_exit_code,
    stamp_honest_coverage,
)
from synaps.solvers.feasibility_checker import FeasibilityChecker
from synaps.solvers.registry import create_solver

from mobiroute import SYNAPS_COMMIT

H0 = datetime(2026, 4, 1, tzinfo=UTC)
HE = H0 + timedelta(hours=16)


def _one_op_problem(*, calendar: list[ShiftInterval]) -> ScheduleProblem:
    state = State(code="s")
    work_center = WorkCenter(code="M", capability_group="G", calendar=calendar)
    order = Order(external_ref="O", due_date=HE)
    operation = Operation(
        order_id=order.id,
        seq_in_order=1,
        state_id=state.id,
        base_duration_min=60,
        eligible_wc_ids=[work_center.id],
    )
    return ScheduleProblem(
        states=[state],
        orders=[order],
        operations=[operation],
        work_centers=[work_center],
        setup_matrix=[],
        planning_horizon_start=H0,
        planning_horizon_end=HE,
    )


def test_pin_is_residuals_kernel_sha() -> None:
    assert SYNAPS_COMMIT == "6178c93b705ff58be21fa74a98651883a2da1169"


def test_empty_feasible_stamps_error_and_exit_3() -> None:
    problem = _one_op_problem(calendar=[])
    stamped = stamp_honest_coverage(
        problem,
        ScheduleResult(solver_name="GREED", status=SolverStatus.FEASIBLE, assignments=[]),
    )
    assert stamped.status is SolverStatus.ERROR
    assert process_exit_code(stamped.status, CoverageClass.EMPTY) == 3


def test_process_exit_codes_match_adr_0005() -> None:
    assert process_exit_code(SolverStatus.FEASIBLE, CoverageClass.FULL) == 0
    assert process_exit_code(SolverStatus.FEASIBLE, CoverageClass.INCOMPLETE) == 2
    assert process_exit_code(SolverStatus.ERROR, CoverageClass.EMPTY) == 3
    assert process_exit_code(SolverStatus.ERROR, CoverageClass.INCOMPLETE) == 1


def test_cpsat_alns_lbbd_encode_nonempty_calendar() -> None:
    """Named exact/ALNS configs encode occupancy; they do not schedule 24/7."""

    problem = _one_op_problem(
        calendar=[ShiftInterval(start=H0 + timedelta(hours=8), end=HE)],
    )
    for name in ("CPSAT-10", "ALNS-300", "LBBD-5"):
        solver, kwargs = create_solver(name)
        result = solver.solve(problem, **kwargs, auto_greedy_warm_start=False)
        assert result.assignments, name
        assert result.assignments[0].start_time >= H0 + timedelta(hours=8), name
        assert not FeasibilityChecker().check(problem, result.assignments, exhaustive=True), name
        assert result.metadata.get("calendar_unsupported") is not True, name
