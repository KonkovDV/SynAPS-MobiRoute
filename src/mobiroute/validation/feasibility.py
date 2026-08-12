"""Independent feasibility notary for DARP plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from mobiroute.domain.models import ReasonCode, StopType, WheelchairType
from mobiroute.domain.requests import DayProblem, PlanningResult, RoutePlan, TripRequest, Vehicle


@dataclass
class FeasibilityReport:
    feasible: bool
    violations: list[str] = field(default_factory=list)
    reason_codes: dict[str, str] = field(default_factory=dict)


def _wheelchair_units(wt: WheelchairType) -> int:
    return 0 if wt == WheelchairType.NONE else 1


def check_route(
    problem: DayProblem,
    route: RoutePlan,
    trips: dict[str, TripRequest],
) -> list[str]:
    vmap = {v.id: v for v in problem.vehicles}
    dmap = {d.id: d for d in problem.drivers}
    vehicle = vmap.get(route.vehicle_id)
    if vehicle is None:
        return [f"UNKNOWN_VEHICLE:{route.vehicle_id}"]
    violations: list[str] = []
    load = 0
    wload = 0
    onboard: set[str] = set()
    seen_pickup: set[str] = set()
    seen_drop: set[str] = set()
    prev_loc = None
    prev_dep = vehicle.shift_start

    if route.driver_id:
        driver = dmap.get(route.driver_id)
        if driver is None:
            violations.append(f"UNKNOWN_DRIVER:{route.driver_id}")
        elif not driver.availability:
            violations.append(f"DRIVER_UNAVAILABLE:{route.driver_id}")

    for stop in route.ordered_stops:
        arr = route.arrival_times.get(stop.id)
        dep = route.departure_times.get(stop.id)
        if arr is None or dep is None:
            violations.append(f"MISSING_TIMES:{stop.id}")
            continue
        if prev_loc is not None:
            tt = problem.travel.travel(prev_loc, stop.location)
            if arr < prev_dep + tt:
                violations.append(f"TRAVEL_TIME:{stop.id}:arr={arr}<prev_dep+tt={prev_dep + tt}")
        if stop.stop_type == StopType.PICKUP and stop.trip_id:
            tid = stop.trip_id
            trip = trips[tid]
            if tid in seen_pickup:
                violations.append(f"DUPLICATE_PICKUP:{tid}")
            seen_pickup.add(tid)
            if arr > trip.latest_pickup:
                violations.append(f"LATE_PICKUP:{tid}")
            if arr < trip.earliest_pickup:
                # waiting allowed; departure after earliest
                pass
            seats = 1 + trip.companion_count
            load += seats
            wload += _wheelchair_units(trip.wheelchair_requirement)
            if load > vehicle.passenger_capacity:
                violations.append(f"CAPACITY:{tid}")
            if wload > vehicle.wheelchair_capacity:
                violations.append(f"WHEELCHAIR_CAPACITY:{tid}")
            if trip.needs_lift and not vehicle.lift_available:
                violations.append(f"LIFT_REQUIRED:{tid}")
            if trip.needs_ramp and not (vehicle.ramp_available or vehicle.lift_available):
                violations.append(f"RAMP_REQUIRED:{tid}")
            if trip.needs_boarding_assistance and route.driver_id:
                driver = dmap.get(route.driver_id)
                if driver and not driver.accessibility_training:
                    violations.append(f"DRIVER_QUAL:{tid}")
            onboard.add(tid)
        elif stop.stop_type == StopType.DROPOFF and stop.trip_id:
            tid = stop.trip_id
            trip = trips[tid]
            if tid not in seen_pickup:
                violations.append(f"DROPOFF_BEFORE_PICKUP:{tid}")
            if tid in seen_drop:
                violations.append(f"DUPLICATE_DROPOFF:{tid}")
            seen_drop.add(tid)
            pickup_dep = None
            for s in route.ordered_stops:
                if s.trip_id == tid and s.stop_type == StopType.PICKUP:
                    pickup_dep = route.departure_times.get(s.id)
                    break
            if pickup_dep is not None:
                ride = arr - pickup_dep
                if ride > trip.max_ride_time:
                    violations.append(f"MAX_RIDE_TIME:{tid}")
                route.ride_times[tid] = ride
            if trip.appointment_end is not None and arr > trip.appointment_end:
                violations.append(f"APPOINTMENT:{tid}")
            seats = 1 + trip.companion_count
            load -= seats
            wload -= _wheelchair_units(trip.wheelchair_requirement)
            if load < 0 or wload < 0:
                violations.append(f"NEGATIVE_LOAD:{tid}")
            onboard.discard(tid)
        prev_loc = stop.location
        prev_dep = dep

    for tid in seen_pickup - seen_drop:
        violations.append(f"MISSING_DROPOFF:{tid}")
    if load != 0 or wload != 0:
        violations.append("END_LOAD_NOT_ZERO")
    return violations


def check_plan(problem: DayProblem, result: PlanningResult) -> FeasibilityReport:
    trips = {t.id: t for t in problem.requests}
    violations: list[str] = []
    assigned: dict[str, str] = {}
    for route in result.route_plans:
        violations.extend(check_route(problem, route, trips))
        for tid in route.passenger_assignments:
            if tid in assigned and assigned[tid] != route.vehicle_id:
                violations.append(f"SPLIT_VEHICLE:{tid}")
            if tid in assigned:
                violations.append(f"DUPLICATE_ASSIGNMENT:{tid}")
            assigned[tid] = route.vehicle_id
    # served must appear exactly once
    for tid in result.served_requests:
        if tid not in assigned:
            violations.append(f"SERVED_BUT_UNASSIGNED:{tid}")
    for tid, _vehicle_id in assigned.items():
        if tid not in result.served_requests:
            violations.append(f"ASSIGNED_NOT_SERVED:{tid}")
    # rejected must have reason
    for r in result.rejected_requests:
        if not r.reason_code:
            violations.append(f"NO_REASON:{r.trip_id}")
    return FeasibilityReport(feasible=len(violations) == 0, violations=violations)


def accessibility_compatible(vehicle: Vehicle, trip: TripRequest) -> ReasonCode | None:
    if trip.wheelchair_requirement != WheelchairType.NONE:
        if vehicle.wheelchair_capacity < 1:
            return ReasonCode.NO_WHEELCHAIR_CAPACITY
        if trip.needs_lift and not vehicle.lift_available:
            return ReasonCode.NO_COMPATIBLE_VEHICLE
        if trip.needs_ramp and not (vehicle.ramp_available or vehicle.lift_available):
            return ReasonCode.NO_COMPATIBLE_VEHICLE
    seats = 1 + trip.companion_count
    if seats > vehicle.passenger_capacity:
        return ReasonCode.NO_CAPACITY
    return None
