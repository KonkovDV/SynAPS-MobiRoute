"""Rolling-horizon day-ahead composition. Heuristic — never OPTIMAL.

Pattern: SynAPS RHC (window + overlap + freeze) and Gaul et al. ATMOS-style
event horizons. Each window inserts only trips whose earliest pickup is visible
(``earliest_pickup < window_end``), seeding the previous committed routes.
Leftovers retry in later windows. Last window uses an open end so every active
request is considered.

Not a stochastic ADP policy and not an exact Benders master.
"""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.models import SolutionStatus
from mobiroute.domain.requests import DayProblem, PlanningResult, Stop
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import acceleration_status


def _window_ends(
    t0: int,
    t_last: int,
    window_minutes: int,
    overlap_minutes: int,
) -> list[int]:
    window_minutes = max(1, window_minutes)
    overlap_minutes = min(max(0, overlap_minutes), window_minutes - 1)
    step = max(1, window_minutes - overlap_minutes)
    ends: list[int] = []
    end = t0 + window_minutes
    while True:
        ends.append(end)
        if end > t_last:
            break
        end += step
    return ends


def solve_rolling_horizon(
    problem: DayProblem,
    *,
    window_minutes: int = 180,
    overlap_minutes: int = 30,
) -> PlanningResult:
    """Day-ahead RHC over greedy pooling insertion. Never OPTIMAL."""
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    if not active:
        result = solve_greedy(problem)
        return _stamp_rhc(result, window_minutes, overlap_minutes, windows=0)

    t0 = min(t.earliest_pickup for t in active)
    t_last = max(t.earliest_pickup for t in active)
    ends = _window_ends(t0, t_last, window_minutes, overlap_minutes)

    seed_stops: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
    seed_drivers: dict[str, str | None] = {v.id: None for v in problem.vehicles}
    result: PlanningResult | None = None

    for i, window_end in enumerate(ends):
        last = i == len(ends) - 1
        visible_ids = {
            t.id
            for t in active
            if last or t.earliest_pickup < window_end or t.id in _seeded_ids(seed_stops)
        }
        sliced = problem.model_copy(
            update={
                "requests": [
                    t
                    for t in problem.requests
                    if t.id in visible_ids or t.booking_status.value in {"CANCELLED", "NO_SHOW"}
                ]
            }
        )
        result = solve_greedy(sliced, seed_stops=seed_stops, seed_drivers=seed_drivers)
        seed_stops = {v.id: [] for v in problem.vehicles}
        seed_drivers = {v.id: None for v in problem.vehicles}
        for rp in result.route_plans:
            seed_stops[rp.vehicle_id] = service_stops(list(rp.ordered_stops))
            seed_drivers[rp.vehicle_id] = rp.driver_id

    assert result is not None
    # Final pass already used the open last window on the full visible set.
    # Re-finalize against the original problem so cancelled/unseen ids account.
    if len(result.served_requests) + len(result.rejected_requests) < len(problem.requests):
        result = solve_greedy(problem, seed_stops=seed_stops, seed_drivers=seed_drivers)
    return _stamp_rhc(result, window_minutes, overlap_minutes, windows=len(ends))


def _seeded_ids(seed_stops: dict[str, list[Stop]]) -> set[str]:
    return {s.trip_id for stops in seed_stops.values() for s in stops if s.trip_id}


def _stamp_rhc(
    result: PlanningResult,
    window_minutes: int,
    overlap_minutes: int,
    *,
    windows: int,
) -> PlanningResult:
    cfg = {
        **result.solver_config,
        "name": "RHC",
        "window_minutes": window_minutes,
        "overlap_minutes": overlap_minutes,
        "windows": windows,
        "proven_optimal": False,
        **acceleration_status(),
    }
    status = result.status
    if status == SolutionStatus.OPTIMAL.value:
        status = (
            SolutionStatus.PARTIAL.value
            if result.rejected_requests
            else SolutionStatus.HEURISTIC_FEASIBLE.value
        )
    return result.model_copy(
        update={
            "status": status,
            "solution_type": "RHC",
            "solver_config": cfg,
            "config_hash": fingerprint(
                {
                    "solver": "RHC",
                    "window": window_minutes,
                    "overlap": overlap_minutes,
                    "version": __version__,
                    "synaps": SYNAPS_COMMIT,
                }
            ),
        }
    )
