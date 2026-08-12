"""Limited beam search over pooling insertions — heuristic, never OPTIMAL."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.models import ReasonCode, SolutionStatus
from mobiroute.domain.priorities import trip_sort_key
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TripRequest,
    Vehicle,
)
from mobiroute.solvers.greedy import (
    _assign_driver,
    _needs_accessibility,
    simulate_stop_sequence,
    try_insert_trip,
)
from mobiroute.validation.feasibility import accessibility_compatible, check_plan


def _simulate_vehicle(
    problem: DayProblem,
    vehicle: Vehicle,
    stops: list[Stop],
    trips_by_id: dict[str, TripRequest],
) -> RoutePlan | None:
    need = _needs_accessibility(stops, trips_by_id)
    return simulate_stop_sequence(
        problem,
        vehicle,
        _assign_driver(problem, vehicle.id, needs_accessibility=need),
        stops,
        trips_by_id,
    )


def _total_duration(problem: DayProblem, stops: dict[str, list[Stop]]) -> int:
    trips_by_id = {t.id: t for t in problem.requests}
    total = 0
    for v in problem.vehicles:
        if not stops[v.id]:
            continue
        plan = _simulate_vehicle(problem, v, stops[v.id], trips_by_id)
        if plan is None:
            return 10**9
        total += plan.route_duration
    return total


def solve_beam(problem: DayProblem, beam_width: int = 3) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    trips_by_id = {t.id: t for t in problem.requests}
    empty: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
    beam: list[
        tuple[int, int, dict[str, list[Stop]], list[str], list[RejectedTrip], dict[str, str]]
    ] = [(0, 0, {k: list(v) for k, v in empty.items()}, [], [], {})]
    for trip in active:
        expanded: list[
            tuple[int, int, dict[str, list[Stop]], list[str], list[RejectedTrip], dict[str, str]]
        ] = []
        for _rej, _dur, stops, served, rejected, reasons in beam:
            placed = False
            for v in problem.vehicles:
                if accessibility_compatible(v, trip) is not None:
                    continue
                inserted = try_insert_trip(
                    problem,
                    v,
                    _assign_driver(problem, v.id),
                    stops[v.id],
                    trip,
                    trips_by_id,
                )
                if inserted is None:
                    continue
                _score, seq, _plan = inserted
                new_stops = {k: list(val) for k, val in stops.items()}
                new_stops[v.id] = seq
                expanded.append(
                    (
                        len(rejected),
                        _total_duration(problem, new_stops),
                        new_stops,
                        [*served, trip.id],
                        list(rejected),
                        {**reasons, trip.id: ReasonCode.ACCEPTED.value},
                    )
                )
                placed = True
            if not placed:
                code = ReasonCode.TIME_WINDOW_CONFLICT.value
                expanded.append(
                    (
                        len(rejected) + 1,
                        _dur,
                        {k: list(val) for k, val in stops.items()},
                        list(served),
                        [*rejected, RejectedTrip(trip_id=trip.id, reason_code=code)],
                        {**reasons, trip.id: code},
                    )
                )
        expanded.sort(key=lambda x: (x[0], x[1], "".join(x[3])))
        beam = expanded[: max(1, beam_width)]

    _rej, _dur, stops, served, rejected, reasons = beam[0]
    route_plans = []
    for v in problem.vehicles:
        if not stops[v.id]:
            continue
        plan = _simulate_vehicle(problem, v, stops[v.id], trips_by_id)
        if plan is not None:
            route_plans.append(plan)
    result = PlanningResult(
        status=SolutionStatus.HEURISTIC_FEASIBLE.value,
        solution_type="BEAM",
        verified_feasible=False,
        served_requests=sorted(served),
        rejected_requests=rejected,
        route_plans=route_plans,
        objective_values={"served": float(len(served)), "rejected": float(len(rejected))},
        reason_codes=reasons,
        input_hash=fingerprint(problem.model_dump(mode="json")),
        config_hash=fingerprint({"solver": "BEAM", "width": beam_width, "version": __version__}),
        solver_config={"name": "BEAM", "beam_width": beam_width, "pooling": True},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
    )
    report = check_plan(problem, result)
    result.verified_feasible = report.feasible
    if not report.feasible:
        result.status = SolutionStatus.NOT_VERIFIED.value
    elif rejected:
        result.status = SolutionStatus.PARTIAL.value
    else:
        result.status = SolutionStatus.HEURISTIC_FEASIBLE.value
    result.fairness_metrics = compute_fairness(problem, result)
    return result
