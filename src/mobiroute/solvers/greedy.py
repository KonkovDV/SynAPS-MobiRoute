"""Constructive baselines: FIFO (no pooling) and greedy pooling insertion."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint, fingerprint_problem
from mobiroute.domain.constraints import (
    detour_limit,
    earliest_alight_time,
    occupancy_overlaps,
    pickup_service_minutes,
    push_past_unavail,
)
from mobiroute.domain.driver_assignment import select_driver
from mobiroute.domain.models import ReasonCode, SolutionStatus, StopType, WheelchairType
from mobiroute.domain.priorities import fifo_sort_key, trip_sort_key
from mobiroute.domain.requests import (
    DayProblem,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TimeWindow,
    TripExplanation,
    TripRequest,
    Vehicle,
)
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.insertion_kernel import ProblemKernel, vehicle_payload
from mobiroute.solvers.native_accel import (
    NativeEval,
    acceleration_status,
    attach_native,
    commit_insert,
    eval_fleet,
    eval_route,
    score_fleet,
    score_stored,
    set_fleet,
    set_route,
    set_vehicle,
    stash_kernel,
    trial_rides,
)
from mobiroute.solvers.native_accel import best_insert as kernel_best_insert
from mobiroute.validation.feasibility import (
    accessibility_compatible,
    passenger_rides,
    quota_caps,
    trial_exceeds_quota,
    trial_exceeds_quota_rides,
)
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


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
            TimeWindow(
                earliest=earliest_alight_time(trip.appointment_start) or 0,
                latest=trip.appointment_end if trip.appointment_end is not None else 10**9,
            )
            if trip.appointment_start is not None or trip.appointment_end is not None
            else None
        ),
        load_delta=-seats,
        wheelchair_load_delta=-w,
    )
    return pu, do


def _via_stop(trip: TripRequest) -> Stop | None:
    if not trip.via_zone:
        return None
    return Stop(
        id=f"{trip.id}:VIA",
        trip_id=trip.id,
        stop_type=StopType.VIA,
        location=trip.via_zone,
        service_duration=trip.via_service_duration,
        load_delta=0,
        wheelchair_load_delta=0,
    )


def _trip_stops(trip: TripRequest) -> list[Stop]:
    pu, do = _pair_stops(trip)
    via = _via_stop(trip)
    if via is None:
        return [pu, do]
    return [pu, via, do]


def simulate_stop_sequence(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    stops: list[Stop],
    trips_by_id: dict[str, TripRequest],
) -> RoutePlan | None:
    """Simulate an interleaved pickup/dropoff sequence (pooling-capable)."""
    core = service_stops(stops)
    if not core:
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
    pload: dict[str, int] = {}
    wloads: dict[str, int] = {}
    onboard: set[str] = set()
    dmap = {d.id: d for d in problem.drivers}
    driver = dmap.get(driver_id) if driver_id else None
    if driver is not None:
        tnow = max(tnow, driver.shift_start)
        loc_shift_end = min(vehicle.shift_end, driver.shift_end)
    else:
        loc_shift_end = vehicle.shift_end

    for stop in core:
        if stop.trip_id is None:
            return None
        trip = trips_by_id[stop.trip_id]
        if load == 0 and loc == vehicle.depot_id:
            tnow = push_past_unavail(tnow, vehicle.unavailable_intervals)
        t_begin = tnow
        try:
            tt = problem.travel.travel(loc, stop.location)
        except KeyError:
            return None
        arrive = tnow + tt
        if stop.stop_type == StopType.PICKUP:
            if arrive < trip.earliest_pickup:
                hold = trip.earliest_pickup - arrive
                arrive = trip.earliest_pickup
                pwait = 0
            else:
                hold = 0
                pwait = arrive - trip.earliest_pickup
            if hold > trip.max_wait_time and load > 0:
                return None
            if pwait > trip.max_wait_time:
                return None
            wait[trip.id] = pwait
            if arrive > trip.latest_pickup:
                return None
            if accessibility_compatible(vehicle, trip) is not None:
                return None
            if trip.needs_boarding_assistance and (
                driver is None or not driver.accessibility_training
            ):
                return None
            if trip.wheelchair_requirement == WheelchairType.STRETCHER and load > 0:
                return None
            if any(
                trips_by_id[tid].wheelchair_requirement == WheelchairType.STRETCHER
                for tid in onboard
            ):
                return None
            load += 1 + trip.companion_count
            wload += 0 if trip.wheelchair_requirement.value == "NONE" else 1
            if load > vehicle.passenger_capacity or wload > vehicle.wheelchair_capacity:
                return None
            onboard.add(trip.id)
        elif stop.stop_type == StopType.VIA:
            if trip.id not in pickup_dep:
                return None
            if trip.via_zone and stop.location != trip.via_zone:
                return None
            svc_via = stop.service_duration or trip.via_service_duration
            leave = arrive + svc_via
            if leave > loc_shift_end:
                return None
            if occupancy_overlaps(t_begin, leave, vehicle.unavailable_intervals):
                return None
            arr[stop.id] = arrive
            dep[stop.id] = leave
            pload[stop.id] = load
            wloads[stop.id] = wload
            loc = stop.location
            tnow = leave
            continue
        else:
            if trip.id not in pickup_dep:
                return None
            early_do = earliest_alight_time(trip.appointment_start)
            if early_do is not None and arrive < early_do:
                if load > 1 + trip.companion_count:
                    return None
                arrive = early_do
            if arrive - pickup_dep[trip.id] > trip.max_ride_time:
                return None
            if trip.via_zone:
                direct = (
                    problem.travel.travel(trip.pickup_zone, trip.via_zone)
                    + trip.via_service_duration
                    + problem.travel.travel(trip.via_zone, trip.dropoff_zone)
                )
            else:
                direct = problem.travel.travel(trip.pickup_zone, trip.dropoff_zone)
            ride_so_far = arrive - pickup_dep[trip.id]
            if direct > 0 and ride_so_far > detour_limit(direct, trip.max_detour_ratio):
                return None
            if trip.appointment_end is not None and arrive > trip.appointment_end:
                return None
            ride[trip.id] = arrive - pickup_dep[trip.id]
            load -= 1 + trip.companion_count
            wload -= 0 if trip.wheelchair_requirement.value == "NONE" else 1
            if load < 0 or wload < 0:
                return None
            onboard.discard(trip.id)
        if stop.stop_type == StopType.PICKUP:
            leave = arrive + pickup_service_minutes(stop.service_duration)
        else:
            leave = arrive + stop.service_duration
        if leave > loc_shift_end:
            return None
        if occupancy_overlaps(t_begin, leave, vehicle.unavailable_intervals):
            return None
        arr[stop.id] = arrive
        dep[stop.id] = leave
        pload[stop.id] = load
        wloads[stop.id] = wload
        if stop.stop_type == StopType.PICKUP:
            pickup_dep[trip.id] = leave
        loc = stop.location
        tnow = leave
    try:
        t_ret = tnow
        tnow += problem.travel.travel(loc, vehicle.depot_id)
    except KeyError:
        return None
    if occupancy_overlaps(t_ret, tnow, vehicle.unavailable_intervals):
        return None
    if tnow > loc_shift_end:
        return None
    assigned: list[str] = []
    seen: set[str] = set()
    for stop in core:
        if stop.trip_id and stop.trip_id not in seen:
            assigned.append(stop.trip_id)
            seen.add(stop.trip_id)
    return RoutePlan(
        vehicle_id=vehicle.id,
        driver_id=driver_id,
        ordered_stops=core,
        passenger_assignments=assigned,
        arrival_times=arr,
        departure_times=dep,
        waiting_times=wait,
        ride_times=ride,
        route_duration=tnow - vehicle.shift_start,
        passenger_load_after_stop=pload,
        wheelchair_load_after_stop=wloads,
    )


def route_plan_from_eval(
    vehicle: Vehicle,
    driver_id: str | None,
    stops: list[Stop],
    kernel: ProblemKernel,
    row: NativeEval | None,
) -> RoutePlan | None:
    if row is None:
        return None
    core = service_stops(stops)
    dur, _wait_sum, rides, waits, stop_times = row
    if not core:
        return RoutePlan(
            vehicle_id=vehicle.id,
            driver_id=driver_id,
            ordered_stops=[],
            passenger_assignments=[],
            arrival_times={},
            departure_times={},
        )
    if len(stop_times) != len(core):
        return None
    arr: dict[str, int] = {}
    dep: dict[str, int] = {}
    pload: dict[str, int] = {}
    wloads: dict[str, int] = {}
    for stop, (arrive, leave, load, wload) in zip(core, stop_times, strict=True):
        arr[stop.id] = arrive
        dep[stop.id] = leave
        pload[stop.id] = load
        wloads[stop.id] = wload
    ids = kernel.trip_ids
    wait_d: dict[str, int] = {}
    ride_d: dict[str, int] = {}
    for idx, mins in waits:
        if 0 <= idx < len(ids):
            wait_d[ids[idx]] = mins
    for idx, mins in rides:
        if 0 <= idx < len(ids):
            ride_d[ids[idx]] = mins
    assigned: list[str] = []
    seen: set[str] = set()
    for stop in core:
        if stop.trip_id and stop.trip_id not in seen:
            assigned.append(stop.trip_id)
            seen.add(stop.trip_id)
    return RoutePlan(
        vehicle_id=vehicle.id,
        driver_id=driver_id,
        ordered_stops=core,
        passenger_assignments=assigned,
        arrival_times=arr,
        departure_times=dep,
        waiting_times=wait_d,
        ride_times=ride_d,
        route_duration=dur,
        passenger_load_after_stop=pload,
        wheelchair_load_after_stop=wloads,
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
        stops.extend(_trip_stops(t))
    return simulate_stop_sequence(problem, vehicle, driver_id, stops, {t.id: t for t in trips})


def try_insert_trip(
    problem: DayProblem,
    vehicle: Vehicle,
    driver_id: str | None,
    current_stops: list[Stop],
    trip: TripRequest,
    trips_by_id: dict[str, TripRequest],
    *,
    occupied_driver_ids: set[str] | None = None,
    kernel: ProblemKernel | None = None,
) -> tuple[int, int, list[Stop], str] | None:
    """Score pickup/dropoff slots in the SoA kernel; materialize later."""
    pu, do = _pair_stops(trip)
    via = _via_stop(trip)
    merged = {**trips_by_id, trip.id: trip}
    core = service_stops(current_stops)
    need_new = trip.needs_boarding_assistance or _needs_accessibility(core, merged)
    assigned = driver_id
    if assigned is None:
        assigned = select_driver(
            problem,
            vehicle,
            needs_accessibility=need_new,
            occupied_driver_ids=occupied_driver_ids or set(),
        )
    if assigned is None:
        return None
    dmap = {d.id: d for d in problem.drivers}
    if need_new:
        drv = dmap.get(assigned) if assigned else None
        if drv is None or not drv.accessibility_training:
            return None
    k = kernel or attach_native(ProblemKernel.from_problem(problem))
    if trip.insert_immediately_after:
        after_id = trip.insert_immediately_after
        drop_idx = next(
            (
                idx
                for idx, s in enumerate(core)
                if s.trip_id == after_id and s.stop_type == StopType.DROPOFF
            ),
            None,
        )
        if drop_idx is None:
            return None
        i = drop_idx + 1
        block = [pu, via, do] if via is not None else [pu, do]
        seq = [*core[:i], *block, *core[i:]]
        plan = simulate_stop_sequence(problem, vehicle, assigned, seq, merged)
        if plan is None:
            return None
        return (plan.route_duration, sum(plan.waiting_times.values()), seq, assigned)
    vk = k.vehicles[vehicle.id]
    dk = k.drivers.get(assigned) if assigned else None
    stop_trip, stop_kind = k.stops_to_arrays(core)
    new_idx = k.id_to_idx.get(trip.id)
    if new_idx is None:
        return None
    found = kernel_best_insert(k, vk, dk, stop_trip, stop_kind, new_idx)
    if found is None:
        return None
    i, mid, j, dur, wait, _mx = found
    if via is None or mid < 0:
        seq = [*core[:i], pu, *core[i:j], do, *core[j:]]
    else:
        seq = [*core[:i], pu, *core[i:mid], via, *core[mid:j], do, *core[j:]]
    return (dur, wait, seq, assigned)


def _materialize_insert(
    core: list[Stop],
    pu: Stop,
    via: Stop | None,
    do: Stop,
    i: int,
    mid: int,
    j: int,
) -> list[Stop]:
    if via is None or mid < 0:
        return [*core[:i], pu, *core[i:j], do, *core[j:]]
    return [*core[:i], pu, *core[i:mid], via, *core[mid:j], do, *core[j:]]


def _pool_candidates_native(
    problem: DayProblem,
    trip: TripRequest,
    kernel: ProblemKernel,
    route_stops: dict[str, list[Stop]],
    vehicle_driver: dict[str, str | None],
    occupied: set[str],
    allowed_vids: set[str] | None,
    trips_by_id: dict[str, TripRequest],
) -> tuple[list[tuple[int, int, str, list[Stop], str]], list[str], list[str]]:
    """One Rust score_fleet call; Python keeps driver/access filters and materialization."""
    pu, do = _pair_stops(trip)
    via = _via_stop(trip)
    stop_trips: list[list[int]] = []
    stop_kinds: list[list[int]] = []
    vehs: list[list[int]] = []
    unavails: list[list[int]] = []
    metas: list[tuple[str, str, list[Stop]]] = []
    alt_no: list[str] = []
    new_idx = kernel.id_to_idx.get(trip.id)
    if new_idx is None:
        return [], [], [f"{trip.id}:UNKNOWN_TRIP"]
    for v in problem.vehicles:
        if allowed_vids is not None and v.id not in allowed_vids:
            alt_no.append(f"{v.id}:NOT_PAIRED_VEHICLE")
            continue
        acc = accessibility_compatible(v, trip)
        if acc is not None:
            alt_no.append(f"{v.id}:{acc.value}")
            continue
        occ = occupied - ({vehicle_driver[v.id]} if vehicle_driver[v.id] else set())
        driver_id = vehicle_driver[v.id] or _assign_driver(
            problem,
            v.id,
            needs_accessibility=trip.needs_boarding_assistance
            or _needs_accessibility(route_stops[v.id], trips_by_id),
            occupied_driver_ids=occ,
            preferred_id=vehicle_driver[v.id],
        )
        if driver_id is None:
            alt_no.append(f"{v.id}:NO_DRIVER")
            continue
        core = service_stops(route_stops[v.id])
        st, sk = kernel.stops_to_arrays(core)
        vk = kernel.vehicles[v.id]
        dk = kernel.drivers.get(driver_id)
        veh, una = vehicle_payload(vk, dk)
        stop_trips.append(st)
        stop_kinds.append(sk)
        vehs.append(veh)
        unavails.append(una)
        metas.append((v.id, driver_id, core))
    if not metas:
        return [], [], alt_no
    scored = score_fleet(kernel, stop_trips, stop_kinds, vehs, unavails, new_idx)
    feasible = {row[0] for row in scored}
    for idx, (vid, _did, _core) in enumerate(metas):
        if idx not in feasible:
            alt_no.append(f"{vid}:INSERT_INFEASIBLE")
    alt_ok = [metas[row[0]][0] for row in scored]
    candidates: list[tuple[int, int, str, list[Stop], str]] = []
    for fleet_i, i, mid, j, dur, wait, _mx in scored:
        vid, did, core = metas[fleet_i]
        seq = _materialize_insert(core, pu, via, do, i, mid, j)
        candidates.append((dur, wait, vid, seq, did))
    return candidates, alt_ok, alt_no


def _sync_native_fleet(
    kernel: ProblemKernel,
    problem: DayProblem,
    route_stops: dict[str, list[Stop]],
    vehicle_driver: dict[str, str | None],
) -> None:
    stop_trips: list[list[int]] = []
    stop_kinds: list[list[int]] = []
    vehs: list[list[int]] = []
    unavails: list[list[int]] = []
    for v in problem.vehicles:
        core = service_stops(route_stops[v.id])
        st, sk = kernel.stops_to_arrays(core)
        did = vehicle_driver[v.id]
        dk = kernel.drivers.get(did) if did else None
        veh, una = vehicle_payload(kernel.vehicles[v.id], dk)
        stop_trips.append(st)
        stop_kinds.append(sk)
        vehs.append(veh)
        unavails.append(una)
    set_fleet(kernel, stop_trips, stop_kinds, vehs, unavails)


def _clear_native_slot(kernel: ProblemKernel, fleet_i: int, vehicle_id: str) -> None:
    set_route(kernel, fleet_i, [], [])
    veh, una = vehicle_payload(kernel.vehicles[vehicle_id], None)
    set_vehicle(kernel, fleet_i, veh, una)


def _rides_by_pid(
    ride_pairs: list[tuple[int, int]],
    kernel: ProblemKernel,
    trips_by_id: dict[str, TripRequest],
) -> dict[str, int]:
    used: dict[str, int] = {}
    ids = kernel.trip_ids
    for idx, mins in ride_pairs:
        if idx < 0 or idx >= len(ids):
            continue
        trip = trips_by_id.get(ids[idx])
        if trip is None:
            continue
        pid = trip.pseudonymous_passenger_id
        used[pid] = used.get(pid, 0) + mins
    return used


def _assign_driver(
    problem: DayProblem,
    vehicle_id: str,
    *,
    needs_accessibility: bool = False,
    occupied_driver_ids: set[str] | None = None,
    preferred_id: str | None = None,
    vehicle: Vehicle | None = None,
) -> str | None:
    v = vehicle if vehicle is not None else next(x for x in problem.vehicles if x.id == vehicle_id)
    return select_driver(
        problem,
        v,
        needs_accessibility=needs_accessibility,
        occupied_driver_ids=occupied_driver_ids or set(),
        preferred_id=preferred_id,
    )


def _direct_ride_minutes(problem: DayProblem, trip: TripRequest) -> int:
    if trip.via_zone:
        return (
            problem.travel.travel(trip.pickup_zone, trip.via_zone)
            + trip.via_service_duration
            + problem.travel.travel(trip.via_zone, trip.dropoff_zone)
        )
    return problem.travel.travel(trip.pickup_zone, trip.dropoff_zone)


def _linked_trip_ids(problem: DayProblem, trip_id: str) -> set[str]:
    found = {trip_id}
    changed = True
    while changed:
        changed = False
        for t in problem.requests:
            if t.id in found:
                continue
            parent = t.same_vehicle_as or t.insert_immediately_after
            if parent in found:
                found.add(t.id)
                changed = True
    return found


def _strip_trip_ids(stops: list[Stop], drop: set[str]) -> list[Stop]:
    return [s for s in stops if s.trip_id not in drop]


def _unserve_trips(
    served: list[str],
    rejected: list[RejectedTrip],
    reasons: dict[str, str],
    tids: set[str],
    code: str,
) -> None:
    already = {r.trip_id for r in rejected}
    for tid in tids:
        if tid in served:
            served.remove(tid)
        if tid not in already:
            rejected.append(RejectedTrip(trip_id=tid, reason_code=code))
            already.add(tid)
        reasons[tid] = code


def _active_seed_stops(
    route_stops: dict[str, list[Stop]],
    active_ids: set[str],
    trips_by_id: dict[str, TripRequest],
) -> None:
    """Keep only still-booked seed stops; drop wait-return orphans."""
    for vid, stops in route_stops.items():
        route_stops[vid] = [s for s in stops if s.trip_id in active_ids]
    seeded = {s.trip_id for stops in route_stops.values() for s in stops if s.trip_id}
    changed = True
    while changed:
        changed = False
        for tid in list(seeded):
            trip = trips_by_id.get(tid)
            if trip is None:
                continue
            parent = trip.same_vehicle_as or trip.insert_immediately_after
            if parent and parent not in seeded:
                seeded.discard(tid)
                changed = True
    for vid, stops in route_stops.items():
        route_stops[vid] = [s for s in stops if s.trip_id in seeded]


def _rebuild_vehicle_plan(
    problem: DayProblem,
    vehicle: Vehicle,
    route_stops: dict[str, list[Stop]],
    vehicle_driver: dict[str, str | None],
    trips_by_id: dict[str, TripRequest],
    *,
    kernel: ProblemKernel | None = None,
    fleet_i: int | None = None,
) -> RoutePlan | None:
    if not route_stops[vehicle.id]:
        return None
    need = _needs_accessibility(route_stops[vehicle.id], trips_by_id)
    occ = {d for vid, d in vehicle_driver.items() if d and vid != vehicle.id}
    did = _assign_driver(
        problem,
        vehicle.id,
        needs_accessibility=need,
        occupied_driver_ids=occ,
        preferred_id=vehicle_driver[vehicle.id],
    )
    if kernel is not None and fleet_i is not None:
        core = service_stops(route_stops[vehicle.id])
        st, sk = kernel.stops_to_arrays(core)
        set_route(kernel, fleet_i, st, sk)
        dk = kernel.drivers.get(did) if did else None
        veh, una = vehicle_payload(kernel.vehicles[vehicle.id], dk)
        set_vehicle(kernel, fleet_i, veh, una)
        plan = route_plan_from_eval(vehicle, did, core, kernel, eval_route(kernel, fleet_i))
        if plan is not None:
            return plan
    return simulate_stop_sequence(
        problem,
        vehicle,
        did,
        route_stops[vehicle.id],
        trips_by_id,
    )


def _peel_final_quota(
    problem: DayProblem,
    *,
    route_plans: list[RoutePlan],
    route_stops: dict[str, list[Stop]],
    vehicle_driver: dict[str, str | None],
    trips_by_id: dict[str, TripRequest],
    served: list[str],
    rejected: list[RejectedTrip],
    reasons: dict[str, str],
    quota_cap: dict[str, int],
    vmap: dict[str, Vehicle],
    kernel: ProblemKernel,
    vid_index: dict[str, int],
) -> list[RoutePlan]:
    """Drop longest over-quota rides until the notary would accept the caps."""
    plans = list(route_plans)
    for _ in range(max(1, len(served) + 1)):
        used: dict[str, int] = {}
        owners: dict[str, str] = {}
        ride_of: dict[str, int] = {}
        for rp in plans:
            for tid, mins in rp.ride_times.items():
                owners[tid] = rp.vehicle_id
                ride_of[tid] = mins
            for pid, mins in passenger_rides(rp, trips_by_id).items():
                used[pid] = used.get(pid, 0) + mins
        over = [pid for pid, mins in used.items() if pid in quota_cap and mins > quota_cap[pid]]
        if not over:
            break
        drop_tid: str | None = None
        drop_mins = -1
        for pid in over:
            for t in problem.requests:
                if t.pseudonymous_passenger_id != pid or t.id not in ride_of:
                    continue
                if ride_of[t.id] > drop_mins:
                    drop_mins = ride_of[t.id]
                    drop_tid = t.id
        if drop_tid is None:
            break
        vid = owners[drop_tid]
        drop = _linked_trip_ids(problem, drop_tid) & set(owners)
        primary_pid = trips_by_id[drop_tid].pseudonymous_passenger_id
        for tid in drop:
            code = (
                ReasonCode.QUOTA_EXCEEDED.value
                if trips_by_id[tid].pseudonymous_passenger_id == primary_pid
                else ReasonCode.SAME_VEHICLE_UNAVAILABLE.value
            )
            _unserve_trips(served, rejected, reasons, {tid}, code)
        route_stops[vid] = _strip_trip_ids(route_stops[vid], drop)
        plans = [rp for rp in plans if rp.vehicle_id != vid]
        if not service_stops(route_stops[vid]):
            route_stops[vid] = []
            vehicle_driver[vid] = None
            fi = vid_index.get(vid)
            if fi is not None:
                _clear_native_slot(kernel, fi, vid)
            continue
        rebuilt = _rebuild_vehicle_plan(
            problem,
            vmap[vid],
            route_stops,
            vehicle_driver,
            trips_by_id,
            kernel=kernel,
            fleet_i=vid_index.get(vid),
        )
        if rebuilt is None:
            leftover = {
                s.trip_id for s in route_stops[vid] if s.trip_id and s.stop_type == StopType.PICKUP
            }
            _unserve_trips(
                served,
                rejected,
                reasons,
                leftover,
                ReasonCode.TIME_WINDOW_CONFLICT.value,
            )
            route_stops[vid] = []
            vehicle_driver[vid] = None
            fi = vid_index.get(vid)
            if fi is not None:
                _clear_native_slot(kernel, fi, vid)
        else:
            plans.append(rebuilt)
            vehicle_driver[vid] = rebuilt.driver_id
            route_stops[vid] = list(rebuilt.ordered_stops)
    return plans


def _needs_accessibility(stops: list[Stop], trips_by_id: dict[str, TripRequest]) -> bool:
    return any(
        s.trip_id is not None and trips_by_id[s.trip_id].needs_boarding_assistance for s in stops
    )


def solve_fifo(problem: DayProblem) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=fifo_sort_key)
    return _greedy_core(problem, active, solution_type="FIFO", pooling=False)


def solve_greedy(
    problem: DayProblem,
    *,
    seed_stops: dict[str, list[Stop]] | None = None,
    seed_drivers: dict[str, str | None] | None = None,
) -> PlanningResult:
    active = [t for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}]
    active.sort(key=trip_sort_key)
    return _greedy_core(
        problem,
        active,
        solution_type="GREEDY_INSERTION",
        pooling=True,
        seed_stops=seed_stops,
        seed_drivers=seed_drivers,
    )


def _greedy_core(
    problem: DayProblem,
    ordered: list[TripRequest],
    solution_type: str,
    *,
    pooling: bool = True,
    seed_stops: dict[str, list[Stop]] | None = None,
    seed_drivers: dict[str, str | None] | None = None,
) -> PlanningResult:
    trips_by_id = {t.id: t for t in problem.requests}
    kernel = attach_native(ProblemKernel.from_problem(problem))
    vmap = {v.id: v for v in problem.vehicles}
    route_stops: dict[str, list[Stop]] = {
        v.id: list((seed_stops or {}).get(v.id, [])) for v in problem.vehicles
    }
    vehicle_driver: dict[str, str | None] = {
        v.id: (seed_drivers or {}).get(v.id) for v in problem.vehicles
    }
    served: list[str] = []
    rejected: list[RejectedTrip] = []
    reasons: dict[str, str] = {}
    explanations: list[TripExplanation] = []
    quota_cap = quota_caps(problem)
    quota_left = dict(quota_cap)
    used_now: dict[str, int] = {}
    veh_used: dict[str, dict[str, int]] = {v.id: {} for v in problem.vehicles}
    _active_seed_stops(route_stops, {t.id for t in ordered}, trips_by_id)
    vid_index = {v.id: i for i, v in enumerate(problem.vehicles)}

    for v in problem.vehicles:
        if not route_stops[v.id]:
            continue
        occ = {d for vid, d in vehicle_driver.items() if d and vid != v.id}
        need = _needs_accessibility(route_stops[v.id], trips_by_id)
        vehicle_driver[v.id] = vehicle_driver[v.id] or _assign_driver(
            problem,
            v.id,
            needs_accessibility=need,
            occupied_driver_ids=occ,
            preferred_id=vehicle_driver[v.id],
        )
    _sync_native_fleet(kernel, problem, route_stops, vehicle_driver)
    seed_evals = eval_fleet(kernel)
    for fi, v in enumerate(problem.vehicles):
        if not route_stops[v.id]:
            continue
        row = seed_evals[fi] if fi < len(seed_evals) else None
        did = vehicle_driver[v.id]
        while row is not None:
            trial_used = _rides_by_pid(row[2], kernel, trips_by_id)
            over = {
                pid
                for pid, mins in trial_used.items()
                if pid in quota_cap and used_now.get(pid, 0) + mins > quota_cap[pid]
            }
            if not over:
                break
            drop = {t.id for t in problem.requests if t.pseudonymous_passenger_id in over}
            route_stops[v.id] = _strip_trip_ids(route_stops[v.id], drop)
            if not service_stops(route_stops[v.id]):
                row = None
                break
            st, sk = kernel.stops_to_arrays(service_stops(route_stops[v.id]))
            set_route(kernel, fi, st, sk)
            row = eval_route(kernel, fi)
        seed_plan = route_plan_from_eval(v, did, route_stops[v.id], kernel, row)
        if seed_plan is None or not seed_plan.passenger_assignments:
            route_stops[v.id] = []
            vehicle_driver[v.id] = None
            _clear_native_slot(kernel, fi, v.id)
            continue
        vehicle_driver[v.id] = seed_plan.driver_id
        route_stops[v.id] = list(seed_plan.ordered_stops)
        for tid in seed_plan.passenger_assignments:
            if tid not in served:
                served.append(tid)
                reasons[tid] = ReasonCode.ACCEPTED.value
        rides = passenger_rides(seed_plan, trips_by_id)
        veh_used[v.id] = rides
        for pid, mins in rides.items():
            used_now[pid] = used_now.get(pid, 0) + mins
            if pid in quota_cap:
                quota_left[pid] = quota_cap[pid] - used_now[pid]

    fleet_ids = [v.id for v in problem.vehicles]
    _sync_native_fleet(kernel, problem, route_stops, vehicle_driver)

    for trip in ordered:
        if trip.id in served:
            continue
        qleft = quota_left.get(trip.pseudonymous_passenger_id)
        if qleft is not None and _direct_ride_minutes(problem, trip) > qleft:
            code = ReasonCode.QUOTA_EXCEEDED.value
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            explanations.append(
                TripExplanation(
                    trip_id=trip.id,
                    accepted=False,
                    why_this_route="Remaining hour quota is below the shortest door-to-door ride.",
                    reason_code=code,
                )
            )
            continue
        occupied = {d for vid, d in vehicle_driver.items() if d}
        candidates: list[tuple[int, int, str, list[Stop], str]] = []
        alt_ok: list[str] = []
        alt_no: list[str] = []
        allowed_vids: set[str] | None = None
        if trip.same_vehicle_as:
            allowed_vids = {
                vid
                for vid, stops in route_stops.items()
                if any(s.trip_id == trip.same_vehicle_as for s in stops)
            }
            if not allowed_vids:
                code = ReasonCode.SAME_VEHICLE_UNAVAILABLE.value
                rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
                reasons[trip.id] = code
                explanations.append(
                    TripExplanation(
                        trip_id=trip.id,
                        accepted=False,
                        why_this_route="Return/wait trip has no served outbound on a vehicle.",
                        reason_code=code,
                    )
                )
                continue
        use_pool = pooling and not trip.insert_immediately_after
        if use_pool:
            new_idx = kernel.id_to_idx.get(trip.id)
            if new_idx is None:
                code = non_empty_reason(diagnose_rejection(problem, trip))
                rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
                reasons[trip.id] = code
                continue
            tentative: dict[str, str] = {}
            for fi, v in enumerate(problem.vehicles):
                if vehicle_driver[v.id]:
                    continue
                if allowed_vids is not None and v.id not in allowed_vids:
                    continue
                did0 = _assign_driver(
                    problem,
                    v.id,
                    vehicle=v,
                    needs_accessibility=trip.needs_boarding_assistance
                    or _needs_accessibility(route_stops[v.id], trips_by_id),
                    occupied_driver_ids=occupied,
                )
                if did0 is None:
                    alt_no.append(f"{v.id}:NO_DRIVER")
                    continue
                tentative[v.id] = did0
                vk = kernel.vehicles[v.id]
                dk = kernel.drivers.get(did0)
                veh, una = vehicle_payload(vk, dk)
                set_vehicle(kernel, fi, veh, una)
            scored = score_stored(kernel, new_idx)
            scored.sort(key=lambda r: (r[4], r[5], r[0]))
            merged = {**trips_by_id, trip.id: trip}
            pu, do = _pair_stops(trip)
            via = _via_stop(trip)
            quota_blocked = False
            n_feas = 0
            picked: tuple[int, int, int, int, str, str, dict[str, int], int, int] | None = None
            for fleet_i, i, mid, j, _dur, wait_s, _mx in scored:
                vid = fleet_ids[fleet_i]
                if allowed_vids is not None and vid not in allowed_vids:
                    continue
                n_feas += 1
                did = vehicle_driver[vid] or tentative.get(vid)
                if not did:
                    alt_no.append(f"{vid}:NO_DRIVER")
                    continue
                ride_pairs = trial_rides(kernel, fleet_i, i, mid, j, new_idx)
                if ride_pairs is None:
                    continue
                trial_used = _rides_by_pid(ride_pairs, kernel, merged)
                if trial_exceeds_quota_rides(
                    trial_used,
                    quota_cap=quota_cap,
                    used_now=used_now,
                    previous_on_vehicle=veh_used.get(vid, {}),
                ):
                    quota_blocked = True
                    continue
                ride_t = next((mins for idx, mins in ride_pairs if idx == new_idx), 0)
                picked = (fleet_i, i, mid, j, vid, did, trial_used, wait_s, ride_t)
                break
            if picked is None:
                code = (
                    ReasonCode.QUOTA_EXCEEDED.value
                    if quota_blocked
                    else non_empty_reason(diagnose_rejection(problem, trip))
                )
                rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
                reasons[trip.id] = code
                explanations.append(
                    TripExplanation(
                        trip_id=trip.id,
                        accepted=False,
                        why_this_route="No feasible insertion under hard constraints.",
                        alternatives_considered=alt_ok,
                        alternatives_rejected=alt_no,
                        reason_code=code,
                    )
                )
                continue
            fleet_i, i, mid, j, best_vid, did, trial_used, wait_s, ride_t = picked
            commit_insert(kernel, fleet_i, i, mid, j, new_idx)
            seq = _materialize_insert(service_stops(route_stops[best_vid]), pu, via, do, i, mid, j)
            route_stops[best_vid] = seq
            vehicle_driver[best_vid] = did
            served.append(trip.id)
            reasons[trip.id] = ReasonCode.ACCEPTED.value
            for pid, mins in veh_used.get(best_vid, {}).items():
                used_now[pid] = used_now.get(pid, 0) - mins
            veh_used[best_vid] = trial_used
            for pid, mins in veh_used[best_vid].items():
                used_now[pid] = used_now.get(pid, 0) + mins
                if pid in quota_cap:
                    quota_left[pid] = quota_cap[pid] - used_now[pid]
            explanations.append(
                TripExplanation(
                    trip_id=trip.id,
                    accepted=True,
                    vehicle_id=best_vid,
                    driver_id=did,
                    waiting_time=wait_s,
                    ride_time=ride_t,
                    why_this_route=(
                        f"Lexicographic insertion: min duration then wait among {n_feas} "
                        f"feasible vehicles (pooling={pooling})."
                    ),
                    alternatives_considered=alt_ok,
                    alternatives_rejected=alt_no,
                    reason_code=ReasonCode.ACCEPTED.value,
                    active_constraints=["PAIRING", "CAPACITY", "WINDOWS", "ACCESSIBILITY"],
                )
            )
            continue
        for v in problem.vehicles:
            if allowed_vids is not None and v.id not in allowed_vids:
                alt_no.append(f"{v.id}:NOT_PAIRED_VEHICLE")
                continue
            acc = accessibility_compatible(v, trip)
            if acc is not None:
                alt_no.append(f"{v.id}:{acc.value}")
                continue
            occ = occupied - ({vehicle_driver[v.id]} if vehicle_driver[v.id] else set())
            driver_id = vehicle_driver[v.id] or _assign_driver(
                problem,
                v.id,
                vehicle=v,
                needs_accessibility=trip.needs_boarding_assistance
                or _needs_accessibility(route_stops[v.id], trips_by_id),
                occupied_driver_ids=occ,
                preferred_id=vehicle_driver[v.id],
            )
            if driver_id is None:
                alt_no.append(f"{v.id}:NO_DRIVER")
                continue
            use_insert = bool(trip.insert_immediately_after) or bool(trip.same_vehicle_as)
            if use_insert:
                inserted = try_insert_trip(
                    problem,
                    v,
                    driver_id,
                    route_stops[v.id],
                    trip,
                    trips_by_id,
                    occupied_driver_ids=occ,
                    kernel=kernel,
                )
                if inserted is not None:
                    dur, wait_s, cand_seq, assigned = inserted
                    candidates.append((dur, wait_s, v.id, cand_seq, assigned))
                    alt_ok.append(v.id)
                else:
                    alt_no.append(f"{v.id}:INSERT_INFEASIBLE")
            else:
                trial_trips = [
                    trips_by_id[s.trip_id]
                    for s in route_stops[v.id]
                    if s.trip_id and s.stop_type == StopType.PICKUP
                ] + [trip]
                seq_plan = _simulate_route(problem, v, driver_id, trial_trips)
                if seq_plan is not None:
                    candidates.append(
                        (
                            seq_plan.route_duration,
                            sum(seq_plan.waiting_times.values()),
                            v.id,
                            list(seq_plan.ordered_stops),
                            driver_id,
                        )
                    )
                    alt_ok.append(v.id)
                else:
                    alt_no.append(f"{v.id}:SEQUENTIAL_INFEASIBLE")
        if not candidates:
            code = non_empty_reason(diagnose_rejection(problem, trip))
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            explanations.append(
                TripExplanation(
                    trip_id=trip.id,
                    accepted=False,
                    why_this_route="No feasible insertion under hard constraints.",
                    alternatives_considered=alt_ok,
                    alternatives_rejected=alt_no,
                    reason_code=code,
                )
            )
            continue
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        plan: RoutePlan | None = None
        best_vid = ""
        chosen_seq: list[Stop] = []
        merged = {**trips_by_id, trip.id: trip}
        quota_blocked = False
        for _dur, _wait_s, vid, cand_seq, did in candidates:
            trial = simulate_stop_sequence(problem, vmap[vid], did, cand_seq, merged)
            if trial is None:
                continue
            if trial_exceeds_quota(
                trial,
                merged,
                quota_cap=quota_cap,
                used_now=used_now,
                previous_on_vehicle=veh_used.get(vid, {}),
            ):
                quota_blocked = True
                continue
            plan = trial
            best_vid = vid
            chosen_seq = cand_seq
            break
        if plan is None:
            code = (
                ReasonCode.QUOTA_EXCEEDED.value
                if quota_blocked
                else (
                    ReasonCode.WAIT_RETURN_INFEASIBLE.value
                    if trip.insert_immediately_after
                    else ReasonCode.TIME_WINDOW_CONFLICT.value
                )
            )
            rejected.append(RejectedTrip(trip_id=trip.id, reason_code=code))
            reasons[trip.id] = code
            explanations.append(
                TripExplanation(
                    trip_id=trip.id,
                    accepted=False,
                    why_this_route="Kernel insertion failed independent simulation.",
                    alternatives_considered=alt_ok,
                    alternatives_rejected=alt_no,
                    reason_code=code,
                )
            )
            continue
        route_stops[best_vid] = chosen_seq
        vehicle_driver[best_vid] = plan.driver_id
        served.append(trip.id)
        reasons[trip.id] = ReasonCode.ACCEPTED.value
        for pid, mins in veh_used.get(best_vid, {}).items():
            used_now[pid] = used_now.get(pid, 0) - mins
        veh_used[best_vid] = passenger_rides(plan, merged)
        for pid, mins in veh_used[best_vid].items():
            used_now[pid] = used_now.get(pid, 0) + mins
            if pid in quota_cap:
                quota_left[pid] = quota_cap[pid] - used_now[pid]
        explanations.append(
            TripExplanation(
                trip_id=trip.id,
                accepted=True,
                vehicle_id=best_vid,
                driver_id=plan.driver_id,
                waiting_time=plan.waiting_times.get(trip.id, 0),
                ride_time=plan.ride_times.get(trip.id, 0),
                why_this_route=(
                    f"Lexicographic insertion: min duration then wait among {len(candidates)} "
                    f"feasible vehicles (pooling={pooling})."
                ),
                alternatives_considered=alt_ok,
                alternatives_rejected=alt_no,
                reason_code=ReasonCode.ACCEPTED.value,
                active_constraints=["PAIRING", "CAPACITY", "WINDOWS", "ACCESSIBILITY"],
            )
        )

    route_plans: list[RoutePlan] = []
    emit_evals = eval_fleet(kernel)
    for fi, v in enumerate(problem.vehicles):
        if not route_stops[v.id]:
            continue
        row = emit_evals[fi] if fi < len(emit_evals) else None
        final_plan = route_plan_from_eval(v, vehicle_driver[v.id], route_stops[v.id], kernel, row)
        if final_plan is None:
            final_plan = _rebuild_vehicle_plan(
                problem,
                v,
                route_stops,
                vehicle_driver,
                trips_by_id,
                kernel=kernel,
                fleet_i=fi,
            )
        if final_plan is None:
            leftover = {
                s.trip_id for s in route_stops[v.id] if s.trip_id and s.stop_type == StopType.PICKUP
            }
            _unserve_trips(
                served,
                rejected,
                reasons,
                leftover,
                ReasonCode.TIME_WINDOW_CONFLICT.value,
            )
            route_stops[v.id] = []
            vehicle_driver[v.id] = None
            _clear_native_slot(kernel, fi, v.id)
        else:
            vehicle_driver[v.id] = final_plan.driver_id
            route_stops[v.id] = list(final_plan.ordered_stops)
            route_plans.append(final_plan)

    route_plans = _peel_final_quota(
        problem,
        route_plans=route_plans,
        route_stops=route_stops,
        vehicle_driver=vehicle_driver,
        trips_by_id=trips_by_id,
        served=served,
        rejected=rejected,
        reasons=reasons,
        quota_cap=quota_cap,
        vmap=vmap,
        kernel=kernel,
        vid_index=vid_index,
    )

    inp = fingerprint_problem(problem)
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
        explanations=explanations,
        input_hash=inp,
        config_hash=cfg,
        solver_config={
            "name": solution_type,
            "pooling": pooling,
            **acceleration_status(),
            "fleet_state": True,
            "parallel_vehicles": True,
        },
        mobiroute_version=__version__,
        synaps_commit=SYNAPS_COMMIT,
        data_provenance=problem.data_provenance,
        claim_level="synthetic_benchmark",
        event_type="DAY_AHEAD",
    )
    result = finalize_result(problem, result, explanations=explanations)
    stash_kernel(result, kernel)
    return result
