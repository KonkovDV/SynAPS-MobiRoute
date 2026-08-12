"""Independent feasibility notary for DARP plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from mobiroute.domain.constraints import (
    detour_limit,
    earliest_alight_time,
    occupancy_overlaps,
    pickup_service_minutes,
    push_past_unavail,
)
from mobiroute.domain.models import ReasonCode, StopType, WheelchairType
from mobiroute.domain.requests import DayProblem, PlanningResult, RoutePlan, TripRequest, Vehicle
from mobiroute.validation.completeness import incomplete_plan_issues


@dataclass
class FeasibilityReport:
    feasible: bool
    violations: list[str] = field(default_factory=list)
    reason_codes: dict[str, str] = field(default_factory=dict)


def _wheelchair_units(wt: WheelchairType) -> int:
    return 0 if wt == WheelchairType.NONE else 1


def default_wheelchair_types(vehicle: Vehicle) -> list[WheelchairType]:
    if vehicle.compatible_wheelchair_types:
        return list(vehicle.compatible_wheelchair_types)
    return [WheelchairType.MANUAL, WheelchairType.POWER]


def wheelchair_type_ok(vehicle: Vehicle, trip: TripRequest) -> bool:
    if trip.wheelchair_requirement == WheelchairType.NONE:
        return True
    return trip.wheelchair_requirement in default_wheelchair_types(vehicle)


def accessibility_compatible(vehicle: Vehicle, trip: TripRequest) -> ReasonCode | None:
    if trip.wheelchair_requirement != WheelchairType.NONE:
        if vehicle.wheelchair_capacity < 1:
            return ReasonCode.NO_WHEELCHAIR_CAPACITY
        if not wheelchair_type_ok(vehicle, trip):
            return ReasonCode.NO_COMPATIBLE_VEHICLE
        if trip.needs_lift and not vehicle.lift_available:
            return ReasonCode.NO_COMPATIBLE_VEHICLE
        if trip.needs_ramp and not (vehicle.ramp_available or vehicle.lift_available):
            return ReasonCode.NO_COMPATIBLE_VEHICLE
    if trip.needs_lift and not vehicle.lift_available:
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    if trip.needs_ramp and not (vehicle.ramp_available or vehicle.lift_available):
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    seats = 1 + trip.companion_count
    if seats > vehicle.passenger_capacity:
        return ReasonCode.NO_CAPACITY
    if vehicle.shift_end <= vehicle.shift_start:
        return ReasonCode.VEHICLE_UNAVAILABLE
    if vehicle.service_area and (
        trip.pickup_zone not in vehicle.service_area
        or trip.dropoff_zone not in vehicle.service_area
        or (trip.via_zone is not None and trip.via_zone not in vehicle.service_area)
    ):
        return ReasonCode.NO_COMPATIBLE_VEHICLE
    return None


def used_quota_minutes(problem: DayProblem, result: PlanningResult) -> dict[str, int]:
    trips = {t.id: t for t in problem.requests}
    used: dict[str, int] = {}
    for route in result.route_plans:
        for pid, ride in passenger_rides(route, trips).items():
            used[pid] = used.get(pid, 0) + ride
    return used


def passenger_rides(plan: RoutePlan, trips: dict[str, TripRequest]) -> dict[str, int]:
    used: dict[str, int] = {}
    for tid, ride in plan.ride_times.items():
        trip = trips.get(tid)
        if trip is None:
            continue
        pid = trip.pseudonymous_passenger_id
        used[pid] = used.get(pid, 0) + ride
    return used


def quota_caps(problem: DayProblem) -> dict[str, int]:
    caps: dict[str, int] = {}
    for t in problem.requests:
        if t.booking_status.value in {"CANCELLED", "NO_SHOW"}:
            continue
        cap = trip_quota_remaining(problem, t)
        if cap is None:
            continue
        pid = t.pseudonymous_passenger_id
        caps[pid] = cap if pid not in caps else min(caps[pid], cap)
    return caps


def trial_exceeds_quota(
    trial: RoutePlan,
    trips: dict[str, TripRequest],
    *,
    quota_cap: dict[str, int],
    used_now: dict[str, int],
    previous_on_vehicle: dict[str, int],
) -> bool:
    """True if accepting this vehicle's trial would exceed any passenger-day cap."""
    projected = dict(used_now)
    for pid, mins in previous_on_vehicle.items():
        projected[pid] = projected.get(pid, 0) - mins
    for pid, mins in passenger_rides(trial, trips).items():
        cap = quota_cap.get(pid)
        if cap is None:
            continue
        if projected.get(pid, 0) + mins > cap:
            return True
    return False


def trip_quota_remaining(problem: DayProblem, trip: TripRequest) -> int | None:
    if trip.quota_minutes_remaining is not None:
        return trip.quota_minutes_remaining
    for p in problem.passengers:
        if p.pseudonymous_id == trip.pseudonymous_passenger_id:
            return p.quota_minutes_remaining
    return None


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
    seen_via: set[str] = set()
    prev_loc = vehicle.depot_id
    prev_dep = vehicle.shift_start
    driver = dmap.get(route.driver_id) if route.driver_id else None

    if route.driver_id:
        if driver is None:
            violations.append(f"UNKNOWN_DRIVER:{route.driver_id}")
        elif not driver.availability:
            violations.append(f"DRIVER_UNAVAILABLE:{route.driver_id}")
        elif driver.depot_id != vehicle.depot_id:
            violations.append(f"DRIVER_DEPOT:{route.driver_id}")
        elif (
            driver.qualified_vehicle_types
            and vehicle.vehicle_type not in driver.qualified_vehicle_types
        ):
            violations.append(f"DRIVER_VEHICLE_TYPE:{route.driver_id}")

    for stop in route.ordered_stops:
        arr = route.arrival_times.get(stop.id)
        dep = route.departure_times.get(stop.id)
        if arr is None or dep is None:
            violations.append(f"MISSING_TIMES:{stop.id}")
            continue
        if load == 0 and prev_loc == vehicle.depot_id and stop.stop_type != StopType.DEPOT_START:
            prev_dep = push_past_unavail(prev_dep, vehicle.unavailable_intervals)
        try:
            tt = problem.travel.travel(prev_loc, stop.location)
        except KeyError:
            violations.append(f"BLOCKED_LOCATION:{stop.id}:{stop.location}")
            prev_loc = stop.location
            prev_dep = dep
            continue
        if arr < prev_dep + tt:
            violations.append(f"TRAVEL_TIME:{stop.id}:arr={arr}<prev_dep+tt={prev_dep + tt}")
        expected = prev_dep + tt
        if stop.stop_type == StopType.DEPOT_START:
            if stop.location != vehicle.depot_id:
                violations.append(f"DEPOT_START:{route.vehicle_id}")
        elif stop.stop_type == StopType.DEPOT_END:
            if stop.location != vehicle.depot_id:
                violations.append(f"DEPOT_END:{route.vehicle_id}")
            if arr > vehicle.shift_end:
                violations.append(f"VEHICLE_SHIFT_END:{route.vehicle_id}")
        elif stop.stop_type == StopType.PICKUP and stop.trip_id:
            tid = stop.trip_id
            trip = trips.get(tid)
            if trip is None:
                violations.append(f"UNKNOWN_TRIP:{tid}")
                prev_loc = stop.location
                prev_dep = dep
                continue
            if tid in seen_pickup:
                violations.append(f"DUPLICATE_PICKUP:{tid}")
            seen_pickup.add(tid)
            raw_arr = prev_dep + tt
            if raw_arr < trip.earliest_pickup and load > 0:
                wait = trip.earliest_pickup - raw_arr
                if wait > trip.max_wait_time:
                    violations.append(f"MAX_WAIT:{tid}")
            if arr > trip.earliest_pickup and arr - trip.earliest_pickup > trip.max_wait_time:
                violations.append(f"MAX_WAIT:{tid}")
            if arr > trip.latest_pickup:
                violations.append(f"LATE_PICKUP:{tid}")
            floor = max(expected, trip.earliest_pickup)
            if arr > floor:
                violations.append(f"UNEXPLAINED_WAIT:{tid}")
            if trip.wheelchair_requirement == WheelchairType.STRETCHER and load > 0:
                violations.append(f"STRETCHER_EXCLUSIVE:{tid}")
            if any(
                trips[x].wheelchair_requirement == WheelchairType.STRETCHER
                for x in onboard
                if x in trips
            ):
                violations.append(f"STRETCHER_EXCLUSIVE:{tid}")
            seats = 1 + trip.companion_count
            load += seats
            wload += _wheelchair_units(trip.wheelchair_requirement)
            if load > vehicle.passenger_capacity:
                violations.append(f"CAPACITY:{tid}")
            if wload > vehicle.wheelchair_capacity:
                violations.append(f"WHEELCHAIR_CAPACITY:{tid}")
            acc = accessibility_compatible(vehicle, trip)
            if acc is not None:
                violations.append(f"{acc.value}:{tid}")
            if trip.needs_boarding_assistance:
                if driver is None:
                    violations.append(f"NO_DRIVER:{tid}")
                elif not driver.accessibility_training:
                    violations.append(f"DRIVER_QUAL:{tid}")
            if occupancy_overlaps(prev_dep, dep, vehicle.unavailable_intervals):
                violations.append(f"VEHICLE_UNAVAILABLE:{tid}")
            if dep - arr < pickup_service_minutes(trip.boarding_duration):
                violations.append(f"CURB_WAIT:{tid}")
            onboard.add(tid)
        elif stop.stop_type == StopType.VIA and stop.trip_id:
            tid = stop.trip_id
            trip = trips.get(tid)
            if trip is None:
                violations.append(f"UNKNOWN_TRIP:{tid}")
                prev_loc = stop.location
                prev_dep = dep
                continue
            if tid not in seen_pickup or tid not in onboard:
                violations.append(f"VIA_BEFORE_PICKUP:{tid}")
            if tid in seen_drop:
                violations.append(f"VIA_AFTER_DROPOFF:{tid}")
            if trip.via_zone and stop.location != trip.via_zone:
                violations.append(f"VIA_LOCATION:{tid}")
            if tid in seen_via:
                violations.append(f"DUPLICATE_VIA:{tid}")
            seen_via.add(tid)
            if arr > expected:
                violations.append(f"UNEXPLAINED_WAIT:{tid}")
            if occupancy_overlaps(prev_dep, dep, vehicle.unavailable_intervals):
                violations.append(f"VEHICLE_UNAVAILABLE:{tid}")
        elif stop.stop_type == StopType.DROPOFF and stop.trip_id:
            tid = stop.trip_id
            trip = trips.get(tid)
            if trip is None:
                violations.append(f"UNKNOWN_TRIP:{tid}")
                prev_loc = stop.location
                prev_dep = dep
                continue
            if tid not in seen_pickup:
                violations.append(f"DROPOFF_BEFORE_PICKUP:{tid}")
            if tid not in onboard:
                violations.append(f"PASSENGER_LEFT_EARLY:{tid}")
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
                try:
                    if trip.via_zone:
                        direct = (
                            problem.travel.travel(trip.pickup_zone, trip.via_zone)
                            + trip.via_service_duration
                            + problem.travel.travel(trip.via_zone, trip.dropoff_zone)
                        )
                    else:
                        direct = problem.travel.travel(trip.pickup_zone, trip.dropoff_zone)
                except KeyError:
                    violations.append(f"BLOCKED_LOCATION:{tid}")
                    direct = 0
                if direct > 0 and ride > detour_limit(direct, trip.max_detour_ratio):
                    violations.append(f"DETOUR:{tid}")
            if trip.via_zone and tid not in seen_via:
                violations.append(f"MISSING_VIA:{tid}")
            early_do = earliest_alight_time(trip.appointment_start)
            seats = 1 + trip.companion_count
            if early_do is not None and arr < early_do:
                violations.append(f"APPOINTMENT_EARLY:{tid}")
            if early_do is not None and prev_dep + tt < early_do and load > seats:
                violations.append(f"DROPOFF_HOLD_ONBOARD:{tid}")
            if trip.appointment_end is not None and arr > trip.appointment_end:
                violations.append(f"APPOINTMENT:{tid}")
            floor = expected
            if early_do is not None:
                floor = max(expected, early_do)
            if arr > floor:
                violations.append(f"UNEXPLAINED_WAIT:{tid}")
            if occupancy_overlaps(prev_dep, dep, vehicle.unavailable_intervals):
                violations.append(f"VEHICLE_UNAVAILABLE:{tid}")
            load -= seats
            wload -= _wheelchair_units(trip.wheelchair_requirement)
            if load < 0 or wload < 0:
                violations.append(f"NEGATIVE_LOAD:{tid}")
            onboard.discard(tid)
        recorded = route.passenger_load_after_stop.get(stop.id)
        if recorded is not None and recorded != load:
            violations.append(f"LOAD_MISMATCH:{stop.id}:{recorded}!={load}")
        wrec = route.wheelchair_load_after_stop.get(stop.id)
        if wrec is not None and wrec != wload:
            violations.append(f"WLOAD_MISMATCH:{stop.id}:{wrec}!={wload}")
        prev_loc = stop.location
        prev_dep = dep

    for tid in seen_pickup - seen_drop:
        violations.append(f"MISSING_DROPOFF:{tid}")
    if load != 0 or wload != 0:
        violations.append("END_LOAD_NOT_ZERO")
    if onboard:
        violations.append(f"ONBOARD_AT_END:{sorted(onboard)}")
    times = list(route.arrival_times.values()) + list(route.departure_times.values())
    if times and max(times) > vehicle.shift_end:
        violations.append(f"VEHICLE_SHIFT_END:{route.vehicle_id}")
    if driver is not None and times:
        if min(times) < driver.shift_start:
            violations.append(f"DRIVER_SHIFT_START:{route.driver_id}")
        if max(times) > driver.shift_end:
            violations.append(f"DRIVER_SHIFT_END:{route.driver_id}")
    return violations


def check_plan(problem: DayProblem, result: PlanningResult) -> FeasibilityReport:
    trips = {t.id: t for t in problem.requests}
    violations: list[str] = []
    assigned: dict[str, str] = {}
    drivers_used: dict[str, str] = {}
    seen_vehicles: set[str] = set()
    for route in result.route_plans:
        if route.vehicle_id in seen_vehicles:
            violations.append(f"DUPLICATE_VEHICLE_ROUTE:{route.vehicle_id}")
        seen_vehicles.add(route.vehicle_id)
        violations.extend(check_route(problem, route, trips))
        if route.driver_id:
            if (
                route.driver_id in drivers_used
                and drivers_used[route.driver_id] != route.vehicle_id
            ):
                violations.append(f"DRIVER_DOUBLE_BOOK:{route.driver_id}")
            drivers_used[route.driver_id] = route.vehicle_id
        for tid in route.passenger_assignments:
            if tid in assigned and assigned[tid] != route.vehicle_id:
                violations.append(f"SPLIT_VEHICLE:{tid}")
            if tid in assigned:
                violations.append(f"DUPLICATE_ASSIGNMENT:{tid}")
            assigned[tid] = route.vehicle_id
    for tid in result.served_requests:
        if tid not in assigned:
            violations.append(f"SERVED_BUT_UNASSIGNED:{tid}")
    for tid, _vehicle_id in assigned.items():
        if tid not in result.served_requests:
            violations.append(f"ASSIGNED_NOT_SERVED:{tid}")
    for r in result.rejected_requests:
        if not r.reason_code:
            violations.append(f"NO_REASON:{r.trip_id}")
    rejected_ids = {r.trip_id for r in result.rejected_requests}
    for t in problem.requests:
        if (
            t.frozen
            and t.booking_status.value not in {"CANCELLED", "NO_SHOW"}
            and t.id not in assigned
            and t.id not in rejected_ids
        ):
            violations.append(f"FROZEN_UNSERVED:{t.id}")
    violations.extend(incomplete_plan_issues(problem, result))
    used_quota = used_quota_minutes(problem, result)
    for pid, cap in quota_caps(problem).items():
        if used_quota.get(pid, 0) > cap:
            violations.append(f"QUOTA:{pid}")
    return FeasibilityReport(feasible=len(violations) == 0, violations=violations)
