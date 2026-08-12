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


def _simulate_route(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    trips: list[TripRequest],
) -> RoutePlan | None:
    """Single-vehicle sequential serve: depot → PU → DO → … → depot."""
    if not trips:
        return RoutePlan(
            vehicle_id=vehicle.id,
            driver_id=driver_id,
            ordered_stops=[],
            passenger_assignments=[],
            arrival_times={},
            departure_times={},
        )
    stops: list[Stop] = []
    for t in trips:
        pu, do = _pair_stops(t)
        stops.extend([pu, do])
    loc = vehicle.depot_id
    tnow = vehicle.shift_start
    arr: dict[str, int] = {}
    dep: dict[str, int] = {}
    wait: dict[str, int] = {}
    ride: dict[str, int] = {}
    pickup_dep: dict[str, int] = {}
    load = 0
    wload = 0
    for stop in stops:
        tt = problem.travel.travel(loc, stop.location)
        arrive = tnow + tt
        trip = next(x for x in trips if x.id == stop.trip_id)
        if stop.stop_type == StopType.PICKUP:
            if arrive < trip.earliest_pickup:
                wait[trip.id] = trip.earliest_pickup - arrive
                arrive = trip.earliest_pickup
            if arrive > trip.latest_pickup:
                return None
            if accessibility_compatible(vehicle, trip) is not None:
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
    # return to depot
    tnow += problem.travel.travel(loc, vehicle.depot_id)
    if tnow > vehicle.shift_end + 30:
        return None
    return RoutePlan(
        vehicle_id=vehicle.id,
        driver_id=driver_id,
        ordered_stops=stops,
        passenger_assignments=[t.id for t in trips],
        arrival_times=arr,
        departure_times=dep,
        waiting_times=wait,
        ride_times=ride,
        route_duration=tnow - vehicle.shift_start,
    )


def _assign_driver(problem: DayProblem, vehicle_id: str) -> str | None:
    v = next(x for x in problem.vehicles if x.id == vehicle_id)
    for d in problem.drivers:
        if d.depot_id == v.depot_id and d.availability:
            return d.id
    return problem.drivers[0].id if problem.drivers else None


def solve_fifo(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=lambda t: (t.requested_at, t.id))
    return _greedy_core(problem, active, solution_type="FIFO")


def solve_greedy(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    return _greedy_core(problem, active, solution_type="GREEDY_INSERTION")


def _greedy_core(
    problem: DayProblem, ordered: list[TripRequest], solution_type: str
) -> PlanningResult:
    routes: dict[str, list[TripRequest]] = {v.id: [] for v in problem.vehicles}
    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}

    for trip in ordered:
        if trip.frozen:
            # frozen trips must already be assigned in a full system; here skip mutate
            pass
        best_vid = None
        # try each vehicle: append at end (simple insertion)
        candidates = []
        for v in problem.vehicles:
            reason = accessibility_compatible(v, trip)
            if reason is not None:
                continue
            trial = routes[v.id] + [trip]
            plan = _simulate_route(problem, v, _assign_driver(problem, v.id), trial)
            if plan is not None:
                candidates.append((plan.route_duration, v.id))
        if not candidates:
            # classify reason
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
        best_vid = candidates[0][1]
        routes[best_vid].append(trip)
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value

    route_plans: list[RoutePlan] = []
    for v in problem.vehicles:
        if not routes[v.id]:
            continue
        plan = _simulate_route(problem, v, _assign_driver(problem, v.id), routes[v.id])
        if plan is None:
            # should not happen; mark error
            for trip_obj in list(routes[v.id]):
                tid = trip_obj.id
                if tid in served:
                    served.remove(tid)
                rejected.append(
                    RejectedTrip(trip_id=tid, reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value)
                )
        else:
            route_plans.append(plan)

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
        solver_config={"name": solution_type},
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
