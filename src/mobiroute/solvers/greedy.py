"""Constructive baselines: FIFO and greedy insertion."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.models import ReasonCode, SolutionStatus, StopType
from mobiroute.domain.priorities import trip_sort_key
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TimeWindow,
    TripRequest,
    Vehicle,
)
from mobiroute.validation.feasibility import accessibility_compatible, check_plan


def _pair_stops(trip: TripRequest) -> tuple[Stop, Stop]:
    seats = 1 + trip.companion_count
    w = 0 if trip.wheelchair_requirement.value == "NONE" else 1
    pu = Stop(
        id=f"{trip.id}:PU",
        trip_id=trip.id,
        stop_type=StopType.PICKUP,
        location=trip.pickup_zone,
        service_duration=trip.boarding_duration,
        time_window=TimeWindow(earliest=trip.earliest_pickup, latest=trip.latest_pickup),
        load_delta=seats,
        wheelchair_load_delta=w,
    )
    do = Stop(
        id=f"{trip.id}:DO",
        trip_id=trip.id,
        stop_type=StopType.DROPOFF,
        location=trip.dropoff_zone,
        service_duration=trip.alighting_duration,
        time_window=(
            TimeWindow(earliest=0, latest=trip.appointment_end)
            if trip.appointment_end is not None
            else None
        ),
        load_delta=-seats,
        wheelchair_load_delta=-w,
    )
    return pu, do


def simulate_stop_sequence(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    stops: list[Stop],
    trips_by_id: dict[str, TripRequest],
) -> RoutePlan | None:
    """Simulate an interleaved pickup/dropoff sequence (pooling-capable)."""
    if not stops:
        return RoutePlan(
            vehicle_id=vehicle.id,
            driver_id=driver_id,
            ordered_stops=[],
            passenger_assignments=[],
            arrival_times={},
            departure_times={},
        )
    loc = vehicle.depot_id
    tnow = vehicle.shift_start
    arr: dict[str, int] = {}
    dep: dict[str, int] = {}
    wait: dict[str, int] = {}
    ride: dict[str, int] = {}
    pickup_dep: dict[str, int] = {}
    load = 0
    wload = 0
    dmap = {d.id: d for d in problem.drivers}
    driver = dmap.get(driver_id) if driver_id else None
    for stop in stops:
        if stop.trip_id is None:
            return None
        trip = trips_by_id[stop.trip_id]
        tt = problem.travel.travel(loc, stop.location)
        arrive = tnow + tt
        if stop.stop_type == StopType.PICKUP:
            if arrive < trip.earliest_pickup:
                wait[trip.id] = trip.earliest_pickup - arrive
                arrive = trip.earliest_pickup
            else:
                wait[trip.id] = 0
            if wait[trip.id] > trip.max_wait_time:
                return None
            if arrive > trip.latest_pickup:
                return None
            if accessibility_compatible(vehicle, trip) is not None:
                return None
            if trip.needs_boarding_assistance and (
                driver is None or not driver.accessibility_training
            ):
                return None
            load += 1 + trip.companion_count
            wload += 0 if trip.wheelchair_requirement.value == "NONE" else 1
            if load > vehicle.passenger_capacity or wload > vehicle.wheelchair_capacity:
                return None
        else:
            if trip.id not in pickup_dep:
                return None
            if arrive - pickup_dep[trip.id] > trip.max_ride_time:
                return None
            if trip.appointment_end is not None and arrive > trip.appointment_end:
                return None
            ride[trip.id] = arrive - pickup_dep[trip.id]
            load -= 1 + trip.companion_count
            wload -= 0 if trip.wheelchair_requirement.value == "NONE" else 1
        leave = arrive + stop.service_duration
        if leave > vehicle.shift_end:
            return None
        arr[stop.id] = arrive
        dep[stop.id] = leave
        if stop.stop_type == StopType.PICKUP:
            pickup_dep[trip.id] = leave
        loc = stop.location
        tnow = leave
    tnow += problem.travel.travel(loc, vehicle.depot_id)
    if tnow > vehicle.shift_end + 30:
        return None
    assigned: list[str] = []
    seen: set[str] = set()
    for stop in stops:
        if stop.trip_id and stop.trip_id not in seen:
            assigned.append(stop.trip_id)
            seen.add(stop.trip_id)
    return RoutePlan(
        vehicle_id=vehicle.id,
        driver_id=driver_id,
        ordered_stops=stops,
        passenger_assignments=assigned,
        arrival_times=arr,
        departure_times=dep,
        waiting_times=wait,
        ride_times=ride,
        route_duration=tnow - vehicle.shift_start,
    )


def _simulate_route(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    trips: list[TripRequest],
) -> RoutePlan | None:
    """Sequential serve without pooling: depot → PU → DO → … → depot."""
    stops: list[Stop] = []
    for t in trips:
        pu, do = _pair_stops(t)
        stops.extend([pu, do])
    return simulate_stop_sequence(problem, vehicle, driver_id, stops, {t.id: t for t in trips})


def try_insert_trip(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    current_stops: list[Stop],
    trip: TripRequest,
    trips_by_id: dict[str, TripRequest],
) -> tuple[int, list[Stop], RoutePlan] | None:
    """Classic DARP insertion: try all pickup/dropoff position pairs."""
    pu, do = _pair_stops(trip)
    merged = {**trips_by_id, trip.id: trip}
    best: tuple[int, list[Stop], RoutePlan] | None = None
    m = len(current_stops)
    for i in range(m + 1):
        for j in range(i, m + 1):
            seq = [*current_stops[:i], pu, *current_stops[i:j], do, *current_stops[j:]]
            need = _needs_accessibility(seq, merged)
            assigned = _assign_driver(problem, vehicle.id, needs_accessibility=need)
            if need and assigned is None:
                continue
            plan = simulate_stop_sequence(problem, vehicle, assigned, seq, merged)
            if plan is None:
                continue
            score = plan.route_duration
            if best is None or (score, vehicle.id) < (best[0], vehicle.id):
                best = (score, seq, plan)
    return best


def _assign_driver(
    problem: DayProblem, vehicle_id: str, *, needs_accessibility: bool = False
) -> str | None:
    v = next(x for x in problem.vehicles if x.id == vehicle_id)
    candidates = [d for d in problem.drivers if d.depot_id == v.depot_id and d.availability]
    if needs_accessibility:
        trained = [d for d in candidates if d.accessibility_training]
        if trained:
            return trained[0].id
        return None
    if candidates:
        return candidates[0].id
    return problem.drivers[0].id if problem.drivers else None


def _needs_accessibility(stops: list[Stop], trips_by_id: dict[str, TripRequest]) -> bool:
    return any(
        s.trip_id is not None and trips_by_id[s.trip_id].needs_boarding_assistance for s in stops
    )


def solve_fifo(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=lambda t: (t.requested_at, t.id))
    return _greedy_core(problem, active, solution_type="FIFO", pooling=False)


def solve_greedy(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    return _greedy_core(problem, active, solution_type="GREEDY_INSERTION", pooling=True)


def _greedy_core(
    problem: DayProblem,
    ordered: list[TripRequest],
    solution_type: str,
    *,
    pooling: bool = True,
) -> PlanningResult:
    trips_by_id = {t.id: t for t in problem.requests}
    route_stops: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}

    for trip in ordered:
        candidates: list[tuple[int, str, list[Stop], RoutePlan]] = []
        for v in problem.vehicles:
            if accessibility_compatible(v, trip) is not None:
                continue
            driver_id = _assign_driver(
                problem,
                v.id,
                needs_accessibility=trip.needs_boarding_assistance,
            )
            if trip.needs_boarding_assistance and driver_id is None:
                continue
            if pooling:
                inserted = try_insert_trip(
                    problem, v, driver_id, route_stops[v.id], trip, trips_by_id
                )
                if inserted is not None:
                    score, seq, plan = inserted
                    candidates.append((score, v.id, seq, plan))
            else:
                trial_trips = [
                    trips_by_id[s.trip_id]
                    for s in route_stops[v.id]
                    if s.trip_id and s.stop_type == StopType.PICKUP
                ] + [trip]
                seq_plan = _simulate_route(problem, v, driver_id, trial_trips)
                if seq_plan is not None:
                    candidates.append(
                        (seq_plan.route_duration, v.id, list(seq_plan.ordered_stops), seq_plan)
                    )
        if not candidates:
            reasons_found: list[ReasonCode] = [
                r for v in problem.vehicles if (r := accessibility_compatible(v, trip)) is not None
            ]
            code = (
                reasons_found[0].value if reasons_found else ReasonCode.TIME_WINDOW_CONFLICT.value
            )
            if all(accessibility_compatible(v, trip) is None for v in problem.vehicles):
                code = ReasonCode.TIME_WINDOW_CONFLICT.value
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            continue
        candidates.sort(key=lambda x: (x[0], x[1]))
        _score, best_vid, seq, _plan = candidates[0]
        route_stops[best_vid] = seq
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value

    route_plans: list[RoutePlan] = []
    for v in problem.vehicles:
        if not route_stops[v.id]:
            continue
        need = _needs_accessibility(route_stops[v.id], trips_by_id)
        final_plan = simulate_stop_sequence(
            problem,
            v,
            _assign_driver(problem, v.id, needs_accessibility=need),
            route_stops[v.id],
            trips_by_id,
        )
        if final_plan is None:
            for stop in route_stops[v.id]:
                if stop.trip_id and stop.stop_type == StopType.PICKUP:
                    tid = stop.trip_id
                    if tid in served:
                        served.remove(tid)
                    rejected.append(
                        RejectedTrip(trip_id=tid, reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)
                    )
        else:
            route_plans.append(final_plan)

    inp = fingerprint(problem.model_dump(mode="json"))
    cfg = fingerprint({"solver": solution_type, "version": __version__})
    result = PlanningResult(
        status=SolutionStatus.HEURISTIC_FEASIBLE.value,
        solution_type=solution_type,
        verified_feasible=False,
        served_requests=sorted(served),
        rejected_requests=rejected,
        route_plans=route_plans,
        objective_values={
            "served": float(len(served)),
            "rejected": float(len(rejected)),
        },
        reason_codes=reasons,
        input_hash=inp,
        config_hash=cfg,
        solver_config={"name": solution_type, "pooling": pooling},
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
    )
    report = check_plan(problem, result)
    result.verified_feasible = report.feasible
    if not report.feasible:
        result.status = SolutionStatus.NOT_VERIFIED.value
        result.objective_values["violations"] = float(len(report.violations))
    elif len(rejected) == 0:
        result.status = SolutionStatus.FEASIBLE.value
    else:
        result.status = SolutionStatus.PARTIAL.value
    result.fairness_metrics = compute_fairness(problem, result)
    # never claim OPTIMAL for greedy/FIFO
    return result
