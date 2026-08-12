"""Limited beam search over pooling insertions — heuristic, never OPTIMAL."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.models import ReasonCode, SolutionStatus, StopType
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
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import (
    _assign_driver,
    _needs_accessibility,
    simulate_stop_sequence,
    try_insert_trip,
)
from mobiroute.solvers.insertion_kernel import ProblemKernel
from mobiroute.solvers.native_accel import acceleration_status, attach_native
from mobiroute.validation.feasibility import accessibility_compatible
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


def _simulate_vehicle(
    problem: DayProblem,
    vehicle: Vehicle,
    stops: list[Stop],
    trips_by_id: dict[str, TripRequest],
    occupied: set[str],
    preferred: str | None,
) -> RoutePlan | None:
    need = _needs_accessibility(stops, trips_by_id)
    return simulate_stop_sequence(
        problem,
        vehicle,
        _assign_driver(
            problem,
            vehicle.id,
            needs_accessibility=need,
            occupied_driver_ids=occupied,
            preferred_id=preferred,
        ),
        stops,
        trips_by_id,
    )


def _total_duration(
    problem: DayProblem,
    stops: dict[str, list[Stop]],
    drivers: dict[str, str | None],
) -> int:
    trips_by_id = {t.id: t for t in problem.requests}
    total = 0
    for v in problem.vehicles:
        if not stops[v.id]:
            continue
        occ = {d for vid, d in drivers.items() if d and vid != v.id}
        plan = _simulate_vehicle(problem, v, stops[v.id], trips_by_id, occ, drivers[v.id])
        if plan is None:
            return 10**9
        total += plan.route_duration
    return total


def solve_beam(problem: DayProblem, beam_width: int = 3) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    trips_by_id = {t.id: t for t in problem.requests}
    kernel = attach_native(ProblemKernel.from_problem(problem))
    empty: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
    empty_drv: dict[str, str | None] = {v.id: None for v in problem.vehicles}
    beam: list[
        tuple[
            int,
            int,
            dict[str, list[Stop]],
            dict[str, str | None],
            list[str],
            list[RejectedTrip],
            dict[str, str],
        ]
    ] = [(0, 0, {k: list(v) for k, v in empty.items()}, dict(empty_drv), [], [], {})]
    for trip in active:
        expanded: list[
            tuple[
                int,
                int,
                dict[str, list[Stop]],
                dict[str, str | None],
                list[str],
                list[RejectedTrip],
                dict[str, str],
            ]
        ] = []
        for _rej, _dur, stops, drivers, served, rejected, reasons in beam:
            placed = False
            occupied = {d for d in drivers.values() if d}
            for v in problem.vehicles:
                if accessibility_compatible(v, trip) is not None:
                    continue
                occ = occupied - ({drivers[v.id]} if drivers[v.id] else set())
                did = drivers[v.id] or _assign_driver(
                    problem,
                    v.id,
                    needs_accessibility=trip.needs_boarding_assistance,
                    occupied_driver_ids=occ,
                    preferred_id=drivers[v.id],
                )
                if did is None:
                    continue
                inserted = try_insert_trip(
                    problem,
                    v,
                    did,
                    stops[v.id],
                    trip,
                    trips_by_id,
                    occupied_driver_ids=occ,
                    kernel=kernel,
                )
                if inserted is None:
                    continue
                _dur, _wait, seq, assigned = inserted
                new_stops = {k: list(val) for k, val in stops.items()}
                new_stops[v.id] = seq
                new_drv = dict(drivers)
                new_drv[v.id] = assigned
                expanded.append(
                    (
                        len(rejected),
                        _total_duration(problem, new_stops, new_drv),
                        new_stops,
                        new_drv,
                        [*served, trip.id],
                        list(rejected),
                        {**reasons, trip.id: ReasonCode.ACCEPTED.value},
                    )
                )
                placed = True
            if not placed:
                code = non_empty_reason(diagnose_rejection(problem, trip))
                expanded.append(
                    (
                        len(rejected) + 1,
                        _dur,
                        {k: list(val) for k, val in stops.items()},
                        dict(drivers),
                        list(served),
                        [*rejected, RejectedTrip(trip_id=trip.id, reason_code=code)],
                        {**reasons, trip.id: code},
                    )
                )
        expanded.sort(key=lambda x: (x[0], x[1], "".join(x[4])))
        beam = expanded[: max(1, beam_width)]

    _rej, _dur, stops, drivers, served, rejected, reasons = beam[0]
    route_plans = []
    for v in problem.vehicles:
        if not stops[v.id]:
            continue
        occ = {d for vid, d in drivers.items() if d and vid != v.id}
        built = _simulate_vehicle(problem, v, stops[v.id], trips_by_id, occ, drivers[v.id])
        if built is not None:
            route_plans.append(built)
        else:
            for stop in stops[v.id]:
                if stop.trip_id and stop.stop_type == StopType.PICKUP:
                    tid = stop.trip_id
                    if tid in served:
                        served.remove(tid)
                    rejected.append(
                        RejectedTrip(trip_id=tid, reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)
                    )
                    reasons[tid] = ReasonCode.TIME_WINDOW_CONFLICT.value
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
        solver_config={
            "name": "BEAM",
            "beam_width": beam_width,
            "pooling": True,
            **acceleration_status(),
        },
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
        event_type="DAY_AHEAD",
    )
    return finalize_result(problem, result)
