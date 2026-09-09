"""Incremental repair — disruption replan that prefers frozen assignments."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.dispatch.online_insertion import recover_disruption
from mobiroute.domain.requests import DayProblem, PlanDiff, PlanningResult
from mobiroute.solvers.finalize import plan_identity


def solve_incremental_repair(
    problem: DayProblem,
    baseline: PlanningResult,
    *,
    cancel_trip_id: str | None = None,
    no_show_trip_id: str | None = None,
    vehicle_unavailable_id: str | None = None,
    driver_unavailable_id: str | None = None,
    traffic_delay_minutes: int = 0,
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    """Named repair lane. Heuristic — never OPTIMAL."""
    updated, result, diff = recover_disruption(
        problem,
        baseline,
        cancel_trip_id=cancel_trip_id,
        no_show_trip_id=no_show_trip_id,
        vehicle_unavailable_id=vehicle_unavailable_id,
        driver_unavailable_id=driver_unavailable_id,
        traffic_delay_minutes=traffic_delay_minutes,
    )
    stamped = result.model_copy(
        update={
            "solution_type": "INCREMENTAL_REPAIR",
            "solver_config": {**result.solver_config, "name": "INCREMENTAL_REPAIR"},
            "config_hash": fingerprint(
                {
                    "solver": "INCREMENTAL_REPAIR",
                    "recovery": result.config_hash,
                    "version": __version__,
                    "synaps": SYNAPS_COMMIT,
                }
            ),
        }
    )
    # The recovery lane published its own identity. What leaves this function is
    # an incremental-repair plan, so the id must fingerprint this lane.
    return updated, stamped.model_copy(update={"plan_id": plan_identity(stamped)}), diff
