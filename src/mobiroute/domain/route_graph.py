"""Explicit route graph: depot start → service stops → depot end, with loads."""

from __future__ import annotations

from mobiroute.domain.driver_assignment import assignment_record
from mobiroute.domain.models import StopType
from mobiroute.domain.requests import (
    DayProblem,
    PassengerItinerary,
    PlanningResult,
    RoutePlan,
    Stop,
)


def service_stops(stops: list[Stop]) -> list[Stop]:
    return [s for s in stops if s.stop_type in (StopType.PICKUP, StopType.VIA, StopType.DROPOFF)]


def enrich_route(problem: DayProblem, route: RoutePlan) -> RoutePlan:
    vmap = {v.id: v for v in problem.vehicles}
    vehicle = vmap.get(route.vehicle_id)
    if vehicle is None:
        return route
    trips = {t.id: t for t in problem.requests}
    core = service_stops(list(route.ordered_stops))
    arr = dict(route.arrival_times)
    dep = dict(route.departure_times)

    start = Stop(
        id=f"{vehicle.id}:DEPOT_START",
        trip_id=None,
        stop_type=StopType.DEPOT_START,
        location=vehicle.depot_id,
    )
    end = Stop(
        id=f"{vehicle.id}:DEPOT_END",
        trip_id=None,
        stop_type=StopType.DEPOT_END,
        location=vehicle.depot_id,
    )
    start_t = vehicle.shift_start
    if route.driver_id:
        dmap = {d.id: d for d in problem.drivers}
        drv = dmap.get(route.driver_id)
        if drv is not None:
            start_t = max(start_t, drv.shift_start)
    arr[start.id] = start_t
    dep[start.id] = start_t
    if core:
        last = core[-1]
        last_dep = dep.get(last.id, vehicle.shift_start)
        ret = last_dep + problem.travel.travel(last.location, vehicle.depot_id)
        arr[end.id] = ret
        dep[end.id] = ret
    else:
        arr[end.id] = vehicle.shift_start
        dep[end.id] = vehicle.shift_start

    ordered = [start, *core, end]
    load = 0
    wload = 0
    pload: dict[str, int] = {}
    wloads: dict[str, int] = {}
    pu_stop: dict[str, Stop] = {}
    do_stop: dict[str, Stop] = {}
    for stop in ordered:
        if stop.stop_type == StopType.PICKUP and stop.trip_id:
            trip = trips[stop.trip_id]
            load += 1 + trip.companion_count
            wload += 0 if trip.wheelchair_requirement.value == "NONE" else 1
            pu_stop[stop.trip_id] = stop
        elif stop.stop_type == StopType.VIA and stop.trip_id:
            pass
        elif stop.stop_type == StopType.DROPOFF and stop.trip_id:
            trip = trips[stop.trip_id]
            load -= 1 + trip.companion_count
            wload -= 0 if trip.wheelchair_requirement.value == "NONE" else 1
            do_stop[stop.trip_id] = stop
        pload[stop.id] = load
        wloads[stop.id] = wload

    deadhead = 0
    onboard: set[str] = set()
    prev_loc = vehicle.depot_id
    prev_dep = vehicle.shift_start
    for stop in ordered:
        tt = problem.travel.travel(prev_loc, stop.location)
        a = arr.get(stop.id, prev_dep + tt)
        d = dep.get(stop.id, a)
        if not onboard:
            deadhead += tt
        if stop.stop_type == StopType.PICKUP and stop.trip_id:
            onboard.add(stop.trip_id)
        elif stop.stop_type == StopType.DROPOFF and stop.trip_id:
            onboard.discard(stop.trip_id)
        prev_loc = stop.location
        prev_dep = d

    itineraries: list[PassengerItinerary] = []
    wait = dict(route.waiting_times)
    ride = dict(route.ride_times)
    for tid in route.passenger_assignments:
        pu = pu_stop.get(tid)
        do = do_stop.get(tid)
        tr = trips.get(tid)
        if pu is None or do is None or tr is None:
            continue
        pu_t = arr.get(pu.id, 0)
        do_t = arr.get(do.id, pu_t)
        ride_t = ride.get(tid, max(0, do_t - dep.get(pu.id, pu_t)))
        slack = None
        if tr.appointment_end is not None:
            slack = tr.appointment_end - do_t
        if tr.via_zone:
            hop_a = problem.travel.shortest_path(tr.pickup_zone, tr.via_zone)
            hop_b = problem.travel.shortest_path(tr.via_zone, tr.dropoff_zone)
            path = hop_a + hop_b[1:]
        else:
            path = problem.travel.shortest_path(tr.pickup_zone, tr.dropoff_zone)
        itineraries.append(
            PassengerItinerary(
                trip_id=tid,
                vehicle_id=vehicle.id,
                driver_id=route.driver_id,
                pickup_stop_id=pu.id,
                dropoff_stop_id=do.id,
                pickup_time=pu_t,
                dropoff_time=do_t,
                ride_time=ride_t,
                waiting_time=wait.get(tid, 0),
                appointment_slack=slack,
                travel_path=path,
            )
        )
        ride[tid] = ride_t

    frozen_ids = [
        s.id
        for s in core
        if s.trip_id is not None and trips.get(s.trip_id) is not None and trips[s.trip_id].frozen
    ]
    need = any(
        trips[tid].needs_boarding_assistance for tid in route.passenger_assignments if tid in trips
    )
    duration = 0
    if ordered:
        duration = dep[end.id] - arr[start.id]
    dist = 0.0
    prev = vehicle.depot_id
    for stop in ordered:
        dist += float(problem.travel.travel(prev, stop.location))
        prev = stop.location

    return route.model_copy(
        update={
            "ordered_stops": ordered,
            "arrival_times": arr,
            "departure_times": dep,
            "waiting_times": wait,
            "ride_times": ride,
            "passenger_load_after_stop": pload,
            "wheelchair_load_after_stop": wloads,
            "deadhead_time": deadhead,
            "frozen_stop_ids": frozen_ids,
            "passenger_itineraries": itineraries,
            "route_duration": duration,
            "route_distance": dist,
            "driver_assignment": assignment_record(
                problem, vehicle.id, route.driver_id, needs_accessibility=need
            ),
        }
    )


def enrich_planning_result(
    problem: DayProblem,
    result: PlanningResult,
    *,
    only_vehicles: set[str] | None = None,
) -> PlanningResult:
    routes = [
        enrich_route(problem, rp) if only_vehicles is None or rp.vehicle_id in only_vehicles else rp
        for rp in result.route_plans
    ]
    assignments = [rp.driver_assignment for rp in routes if rp.driver_assignment is not None]
    late: list[str] = []
    trips = {t.id: t for t in problem.requests}
    for rp in routes:
        for it in rp.passenger_itineraries:
            trip = trips.get(it.trip_id)
            if trip is None:
                continue
            if trip.appointment_end is not None and it.dropoff_time > trip.appointment_end:
                late.append(it.trip_id)
            if it.pickup_time > trip.latest_pickup:
                late.append(it.trip_id)
    return result.model_copy(
        update={
            "route_plans": routes,
            "driver_assignments": assignments,
            "late_requests": sorted(set(late)),
        }
    )
