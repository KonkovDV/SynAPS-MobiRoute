"""Online insertion and disruption recovery with versioned plans P_k → P_{k+1}."""

from __future__ import annotations

import uuid

from mobiroute import SYNAPS_COMMIT, __version__
from mobiroute.adapters.fingerprint import fingerprint, fingerprint_problem
from mobiroute.domain.linked_trips import dependent_ids, linked_parents
from mobiroute.domain.models import BookingStatus, ReasonCode, SolutionStatus, StopType
from mobiroute.domain.policy import DispatchAuthority, PoolingMode
from mobiroute.domain.requests import (
    DayProblem,
    PlanDiff,
    PlanningResult,
    RejectedTrip,
    RoutePlan,
    Stop,
    TripRequest,
)
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.finalize import finalize_result
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import acceleration_status
from mobiroute.validation.feasibility import (
    accessibility_compatible,
    passenger_quota_debits,
    pooling_stops_violate,
    quota_caps,
    trial_exceeds_quota,
    trial_exceeds_quota_rides,
    trip_quota_remaining,
    used_quota_minutes,
)
from mobiroute.validation.input import validate_problem, validate_trip
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason

TripClocks = tuple[int | None, int | None, int | None, int | None]


def _trip_clocks(route: RoutePlan) -> dict[str, TripClocks]:
    """Pickup/dropoff arrival and departure. Dwell-only shifts are still retiming."""
    pu_arr: dict[str, int] = {}
    pu_dep: dict[str, int] = {}
    do_arr: dict[str, int] = {}
    do_dep: dict[str, int] = {}
    for s in service_stops(list(route.ordered_stops)):
        if s.trip_id is None:
            continue
        if s.stop_type == StopType.PICKUP:
            if s.id in route.arrival_times:
                pu_arr[s.trip_id] = route.arrival_times[s.id]
            if s.id in route.departure_times:
                pu_dep[s.trip_id] = route.departure_times[s.id]
        elif s.stop_type == StopType.DROPOFF:
            if s.id in route.arrival_times:
                do_arr[s.trip_id] = route.arrival_times[s.id]
            if s.id in route.departure_times:
                do_dep[s.trip_id] = route.departure_times[s.id]
    ids = set(pu_arr) | set(pu_dep) | set(do_arr) | set(do_dep)
    return {
        tid: (pu_arr.get(tid), pu_dep.get(tid), do_arr.get(tid), do_dep.get(tid)) for tid in ids
    }


def _frozen_times_changed(old: RoutePlan | None, new: RoutePlan, frozen: set[str]) -> bool:
    if old is None:
        return False
    old_t = _trip_clocks(old)
    new_t = _trip_clocks(new)
    for tid in frozen:
        if tid not in old_t:
            continue
        if new_t.get(tid) != old_t[tid]:
            return True
    return False


def _trip_vehicle(result: PlanningResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for rp in result.route_plans:
        for tid in rp.passenger_assignments:
            out[tid] = rp.vehicle_id
    return out


def _base_plan_id(baseline: PlanningResult) -> str:
    return baseline.plan_id or fingerprint(baseline.model_dump(mode="json"))


def _trip_driver(result: PlanningResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for rp in result.route_plans:
        driver = rp.driver_id or ""
        for tid in rp.passenger_assignments:
            out[tid] = driver
    return out


def _result_clocks(result: PlanningResult) -> dict[str, TripClocks]:
    clocks: dict[str, TripClocks] = {}
    for rp in result.route_plans:
        clocks.update(_trip_clocks(rp))
    return clocks


def _active_route_passengers(result: PlanningResult) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for rp in result.route_plans:
        if rp.passenger_assignments:
            out[rp.vehicle_id] = tuple(sorted(rp.passenger_assignments))
    return out


def _event_id(base: str, event_type: str, payload: object) -> str:
    key = fingerprint({"base": base, "type": event_type, "payload": payload})
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mobiroute:event:v2:{key}"))


def compute_diff(baseline: PlanningResult, new: PlanningResult, frozen_ids: set[str]) -> PlanDiff:
    bmap = _trip_vehicle(baseline)
    nmap = _trip_vehicle(new)
    bdrv = _trip_driver(baseline)
    ndrv = _trip_driver(new)
    bclock = _result_clocks(baseline)
    nclock = _result_clocks(new)
    moved = [tid for tid in bmap if tid in nmap and bmap[tid] != nmap[tid]]
    removed = [tid for tid in bmap if tid not in nmap]
    added = [tid for tid in nmap if tid not in bmap]
    retimed = [
        tid
        for tid in bmap
        if tid in nmap and bmap[tid] == nmap[tid] and bclock.get(tid) != nclock.get(tid)
    ]
    changed_drivers = [
        tid for tid in bmap if tid in nmap and bdrv.get(tid, "") != ndrv.get(tid, "")
    ]
    broken_frozen = sorted(
        tid
        for tid in frozen_ids
        if tid in bmap
        and (
            tid not in nmap
            or bmap[tid] != nmap[tid]
            or bdrv.get(tid, "") != ndrv.get(tid, "")
            or bclock.get(tid) != nclock.get(tid)
        )
    )
    unchanged_frozen = sorted(
        tid
        for tid in frozen_ids
        if tid in bmap
        and tid in nmap
        and bmap[tid] == nmap[tid]
        and bdrv.get(tid, "") == ndrv.get(tid, "")
        and bclock.get(tid) == nclock.get(tid)
    )
    broutes = _active_route_passengers(baseline)
    nroutes = _active_route_passengers(new)
    added_routes = sorted(set(nroutes) - set(broutes))
    removed_routes = sorted(set(broutes) - set(nroutes))
    retimed_routes = sorted({nmap[tid] for tid in retimed if tid in nmap})
    composition_changed = {
        vid for vid in set(broutes) | set(nroutes) if broutes.get(vid) != nroutes.get(vid)
    }
    driver_routes = {nmap[tid] for tid in changed_drivers if tid in nmap} | {
        bmap[tid] for tid in changed_drivers if tid in bmap
    }
    changed_routes = sorted(composition_changed | set(retimed_routes) | driver_routes)
    churn = {
        "changed_trips": float(len(moved) + len(removed) + len(added)),
        "changed_vehicles": float(len({bmap[t] for t in moved} | {nmap[t] for t in moved})),
        "weighted_critical_churn": float(
            sum(2.0 for t in moved) + sum(1.0 for t in added) + sum(1.0 for t in removed)
        ),
        "retimed_trips": float(len(retimed)),
        "changed_drivers": float(len(changed_drivers)),
        "broken_frozen": float(len(broken_frozen)),
        "temporal_churn": float(len(retimed)),
        "changed_routes": float(len(changed_routes)),
    }
    bf = baseline.fairness_metrics
    nf = new.fairness_metrics
    fairness_delta: dict[str, float] = {}
    if bf.jain_index is not None and nf.jain_index is not None:
        fairness_delta["jain_index"] = nf.jain_index - bf.jain_index
    if bf.max_disparity is not None and nf.max_disparity is not None:
        fairness_delta["max_disparity"] = nf.max_disparity - bf.max_disparity
    if bf.service_coverage is not None and nf.service_coverage is not None:
        fairness_delta["service_coverage"] = nf.service_coverage - bf.service_coverage
    return PlanDiff(
        baseline_fingerprint=baseline.input_hash + ":" + baseline.config_hash,
        new_fingerprint=new.input_hash + ":" + new.config_hash,
        added_trips=sorted(added),
        removed_trips=sorted(removed),
        moved_trips=sorted(moved),
        retimed_trips=sorted(retimed),
        changed_driver_trips=sorted(changed_drivers),
        broken_frozen_trips=broken_frozen,
        unchanged_frozen_trips=unchanged_frozen,
        added_routes=added_routes,
        removed_routes=removed_routes,
        retimed_routes=sorted(retimed_routes),
        changed_routes=changed_routes,
        changed_vehicle_assignments=sorted(moved),
        newly_rejected_trips=[
            r
            for r in new.rejected_requests
            if r.trip_id not in {x.trip_id for x in baseline.rejected_requests}
        ],
        reason_codes=new.reason_codes,
        fairness_delta=fairness_delta,
        objective_delta={
            "served": float(len(new.served_requests) - len(baseline.served_requests)),
        },
        plan_churn=churn,
    )


def active_trip_ids(problem: DayProblem) -> set[str]:
    """Active requests minus wait-return orphans whose outbound was cancelled."""
    active = {
        t.id for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}
    }
    changed = True
    while changed:
        changed = False
        for t in problem.requests:
            if t.id not in active:
                continue
            if any(parent not in active for parent in linked_parents(t)):
                active.discard(t.id)
                changed = True
    return active


def dependent_trip_ids(problem: DayProblem, trip_id: str) -> set[str]:
    """Outbound cancel/no-show also drops wait-return / insert-after children."""
    return dependent_ids(problem.requests, {trip_id})


def apply_cancellation(problem: DayProblem, trip_id: str) -> DayProblem:
    problem = validate_problem(problem)
    drop = dependent_trip_ids(problem, trip_id)
    reqs = []
    for t in problem.requests:
        if t.id in drop:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.CANCELLED}))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def apply_no_show(problem: DayProblem, trip_id: str) -> DayProblem:
    problem = validate_problem(problem)
    drop = dependent_trip_ids(problem, trip_id)
    reqs = []
    for t in problem.requests:
        if t.id == trip_id:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.NO_SHOW}))
        elif t.id in drop:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.CANCELLED}))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def apply_vehicle_unavailable(problem: DayProblem, vehicle_id: str) -> DayProblem:
    problem = validate_problem(problem)
    vehs = []
    for v in problem.vehicles:
        if v.id == vehicle_id:
            vehs.append(
                v.model_copy(
                    update={
                        "shift_end": v.shift_start,
                        "unavailable_intervals": [(v.shift_start, v.shift_end)],
                    }
                )
            )
        else:
            vehs.append(v)
    return problem.model_copy(update={"vehicles": vehs})


def apply_driver_unavailable(problem: DayProblem, driver_id: str) -> DayProblem:
    problem = validate_problem(problem)
    drivers = []
    for d in problem.drivers:
        if d.id == driver_id:
            drivers.append(d.model_copy(update={"availability": False}))
        else:
            drivers.append(d)
    return problem.model_copy(update={"drivers": drivers})


def apply_traffic_delay(problem: DayProblem, delay_minutes: int) -> DayProblem:
    from mobiroute.adapters.travel_time import TravelTimeService

    problem = validate_problem(problem)
    matrix = TravelTimeService(problem.travel).apply_traffic_delay(delay_minutes)
    return problem.model_copy(update={"travel": matrix})


def apply_appointment_change(
    problem: DayProblem,
    trip_id: str,
    *,
    appointment_start: int | None = None,
    appointment_end: int | None = None,
) -> DayProblem:
    problem = validate_problem(problem)
    reqs = []
    for t in problem.requests:
        if t.id == trip_id:
            upd: dict[str, object] = {}
            if appointment_start is not None:
                upd["appointment_start"] = appointment_start
            if appointment_end is not None:
                upd["appointment_end"] = appointment_end
            reqs.append(t.model_copy(update=upd))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def _stamp_version(
    baseline: PlanningResult,
    new: PlanningResult,
    *,
    problem: DayProblem,
    solver_config: dict[str, object],
    event_type: str,
    event_id: str,
) -> PlanningResult:
    """Every exit is a detached, fully reverified child, never an inherited proof."""
    new = new.model_copy(deep=True)
    config = {
        k: v for k, v in solver_config.items() if k not in {"verified_feasible", "proven_optimal"}
    }
    new.plan_id = ""
    new.base_plan_id = _base_plan_id(baseline)
    new.event_id = event_id
    new.event_type = event_type
    new.input_hash = fingerprint_problem(problem)
    new.config_hash = fingerprint(config)
    new.solver_config = config
    new.mobiroute_version = __version__
    new.synaps_commit = SYNAPS_COMMIT
    # Old explanations can describe different clocks or omit the new rejection.
    new.explanations = []
    new = finalize_result(problem, new)
    key = fingerprint(
        {
            "base": new.base_plan_id,
            "event": event_id,
            "input": new.input_hash,
            "config": new.config_hash,
            "type": new.solution_type,
            "status": new.status,
            "served": new.served_requests,
            "rejected": [r.model_dump(mode="json") for r in new.rejected_requests],
            "routes": [r.model_dump(mode="json") for r in new.route_plans],
            "version": __version__,
            "synaps": SYNAPS_COMMIT,
        }
    )
    new.plan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mobiroute:plan:v2:{key}"))
    return new


def online_insert(
    problem: DayProblem,
    baseline: PlanningResult,
    new_trip: TripRequest,
    *,
    protect_frozen: bool = True,
    dispatch_mode: str = "COMMIT",
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    """Insert into existing routes; do not rebuild the day plan from scratch."""
    from mobiroute.solvers.greedy import (
        _assign_driver,
        _materialize_insert,
        _pair_stops,
        _rides_by_pid,
        _sync_native_fleet,
        _trip_stops,
        _via_stop,
        route_plan_from_eval,
        simulate_stop_sequence,
    )
    from mobiroute.solvers.insertion_kernel import ProblemKernel, vehicle_payload
    from mobiroute.solvers.native_accel import (
        append_trip,
        attach_native,
        commit_insert,
        fork_kernel,
        kernel_for,
        score_stored,
        set_route,
        set_vehicle,
        stash_kernel,
        trial_eval,
    )

    problem = validate_problem(problem)
    new_trip = validate_trip(new_trip)
    if dispatch_mode not in {"COMMIT", "SHADOW"}:
        raise ValueError("UNKNOWN_DISPATCH_MODE")
    shadow = (
        dispatch_mode == "SHADOW"
        or problem.operator_policy.dispatch_authority == DispatchAuthority.SHADOW
    )
    frozen = {t.id for t in problem.requests if t.frozen} | (
        set(baseline.served_requests) if protect_frozen else set()
    )
    reqs = [*list(problem.requests), new_trip]
    if protect_frozen:
        reqs = [
            t.model_copy(update={"frozen": True}) if t.id in frozen and t.id != new_trip.id else t
            for t in reqs
        ]
    updated = validate_problem(problem.model_copy(update={"requests": reqs}))
    trips_by_id = {t.id: t for t in updated.requests}
    vmap = {v.id: v for v in updated.vehicles}
    occupied = {rp.driver_id for rp in baseline.route_plans if rp.driver_id}
    used = {rp.vehicle_id for rp in baseline.route_plans}
    baseline_by_v = {rp.vehicle_id: rp for rp in baseline.route_plans}
    zmap = {z: i for i, z in enumerate(updated.travel.zones)}
    stored = kernel_for(baseline)
    if stored is not None:
        kernel = fork_kernel(stored)
    else:
        kernel = attach_native(ProblemKernel.from_problem(problem))
        seed_stops: dict[str, list[Stop]] = {v.id: [] for v in problem.vehicles}
        seed_drivers: dict[str, str | None] = {v.id: None for v in problem.vehicles}
        for rp in baseline.route_plans:
            if rp.vehicle_id in seed_stops:
                seed_stops[rp.vehicle_id] = service_stops(list(rp.ordered_stops))
                seed_drivers[rp.vehicle_id] = rp.driver_id
        _sync_native_fleet(kernel, problem, seed_stops, seed_drivers)
    new_idx = append_trip(kernel, new_trip, zmap)
    fleet_ids = [v.id for v in updated.vehicles]
    alt_no: list[str] = []
    tentative: dict[str, str] = {}
    scored_idx: list[int] = []
    for fi, v in enumerate(updated.vehicles):
        existing = baseline_by_v.get(v.id)
        if existing is not None and existing.driver_id:
            if accessibility_compatible(v, new_trip) is None:
                scored_idx.append(fi)
            continue
        if accessibility_compatible(v, new_trip) is not None:
            alt_no.append(f"{v.id}:NO_COMPATIBLE_VEHICLE")
            continue
        did0 = _assign_driver(
            updated,
            v.id,
            vehicle=v,
            needs_accessibility=new_trip.needs_boarding_assistance,
            occupied_driver_ids=occupied,
        )
        if did0 is None:
            alt_no.append(f"{v.id}:NO_DRIVER")
            continue
        tentative[v.id] = did0
        dk = kernel.drivers.get(did0)
        veh, una = vehicle_payload(kernel.vehicles[v.id], dk)
        set_vehicle(kernel, fi, veh, una)
        scored_idx.append(fi)

    scored = score_stored(kernel, new_idx, scored_idx) if scored_idx else []
    scored.sort(key=lambda r: (r[4], r[5], r[0]))
    pu, do = _pair_stops(new_trip)
    via = _via_stop(new_trip)
    online_config: dict[str, object] = {
        "name": "ONLINE_INSERTION",
        "pooling": problem.operator_policy.pooling_mode != PoolingMode.FORBIDDEN,
        "protect_frozen": protect_frozen,
        "dispatch_mode": "SHADOW" if shadow else "COMMIT",
        "operational_authorization": False,
        **acceleration_status(),
    }
    eid = _event_id(
        _base_plan_id(baseline),
        "NEW_REQUEST",
        {
            "request": new_trip.model_dump(mode="json"),
            "input_hash": fingerprint_problem(updated),
            "config": online_config,
        },
    )

    new_plan = None
    vid = ""
    quota_blocked = False
    cap = trip_quota_remaining(updated, new_trip)
    used_q = used_quota_minutes(problem, baseline)
    qleft = None if cap is None else cap - used_q.get(new_trip.pseudonymous_passenger_id, 0)
    if qleft is not None and qleft <= 0:
        quota_blocked = True
        scored = []
    quota_cap = quota_caps(updated)
    trips_for_quota = {**trips_by_id, new_trip.id: new_trip}
    for fleet_i, i, mid, j, _dur, _wait_s, _mx in scored:
        cand_vid = fleet_ids[fleet_i]
        old_rp = baseline_by_v.get(cand_vid)
        if accessibility_compatible(vmap[cand_vid], new_trip) is not None:
            continue
        did = (old_rp.driver_id if old_rp is not None else None) or tentative.get(cand_vid)
        if not did:
            alt_no.append(f"{cand_vid}:NO_DRIVER")
            continue
        ev = trial_eval(kernel, fleet_i, i, mid, j, new_idx)
        if ev is None:
            continue
        trial_used = _rides_by_pid(ev[2], kernel, trips_for_quota, updated)
        prev = passenger_quota_debits(updated, old_rp) if old_rp is not None else {}
        if trial_exceeds_quota_rides(
            trial_used,
            quota_cap=quota_cap,
            used_now=used_q,
            previous_on_vehicle=prev,
        ):
            quota_blocked = True
            continue
        core = service_stops(list(old_rp.ordered_stops)) if old_rp is not None else []
        seq = _materialize_insert(core, pu, via, do, i, mid, j)
        if pooling_stops_violate(updated, seq):
            continue
        trial = route_plan_from_eval(vmap[cand_vid], did, seq, kernel, ev)
        if trial is None:
            continue
        if protect_frozen and _frozen_times_changed(old_rp, trial, frozen):
            trial = simulate_stop_sequence(
                updated, vmap[cand_vid], did, [*core, *_trip_stops(new_trip)], trips_by_id
            )
            if trial is None:
                continue
            if pooling_stops_violate(updated, list(trial.ordered_stops)):
                continue
            if trial_exceeds_quota(
                trial,
                trips_for_quota,
                quota_cap=quota_cap,
                used_now=used_q,
                previous_on_vehicle=prev,
                problem=updated,
            ):
                quota_blocked = True
                continue
            if _frozen_times_changed(old_rp, trial, frozen):
                continue
            st, sk = kernel.stops_to_arrays(service_stops(list(trial.ordered_stops)))
            set_route(kernel, fleet_i, st, sk)
            new_plan = trial
            vid = cand_vid
            break
        commit_insert(kernel, fleet_i, i, mid, j, new_idx)
        new_plan = trial
        vid = cand_vid
        break

    if new_plan is None:
        code = (
            ReasonCode.QUOTA_EXCEEDED.value
            if quota_blocked
            else non_empty_reason(diagnose_rejection(updated, new_trip))
        )
        rejected = [
            *list(baseline.rejected_requests),
            RejectedTrip(
                trip_id=new_trip.id,
                reason_code=code,
                detail="no feasible insertion into existing routes; " + "; ".join(alt_no[:8]),
            ),
        ]
        new_result = baseline.model_copy(
            update={
                "solution_type": "ONLINE_INSERTION",
                "status": SolutionStatus.PARTIAL.value,
                "rejected_requests": rejected,
                "reason_codes": {**baseline.reason_codes, new_trip.id: code},
            },
        )
        new_result = _stamp_version(
            baseline,
            new_result,
            problem=updated,
            solver_config=online_config,
            event_type="NEW_REQUEST",
            event_id=eid,
        )
        diff = compute_diff(baseline, new_result, frozen)
        return updated, new_result, diff

    routes = []
    for rp in baseline.route_plans:
        if rp.vehicle_id == vid:
            routes.append(new_plan)
        else:
            routes.append(rp)
    if vid not in used:
        routes.append(new_plan)
    new_result = baseline.model_copy(
        update={
            "plan_id": "",
            "solution_type": "ONLINE_INSERTION",
            "served_requests": sorted([*baseline.served_requests, new_trip.id]),
            "route_plans": routes,
            "reason_codes": {**baseline.reason_codes, new_trip.id: ReasonCode.ACCEPTED.value},
            "objective_values": {
                **baseline.objective_values,
                "served": float(len(baseline.served_requests) + 1),
            },
        },
    )
    bmap = _trip_vehicle(baseline)
    nmap = _trip_vehicle(new_result)
    frozen_broken = [
        tid for tid in frozen if tid in bmap and (tid not in nmap or nmap[tid] != bmap[tid])
    ]
    if protect_frozen and frozen_broken:
        code = ReasonCode.TIME_WINDOW_CONFLICT.value
        restored = baseline.model_copy(
            update={
                "solution_type": "ONLINE_INSERTION",
                "status": SolutionStatus.PARTIAL.value,
                "rejected_requests": [
                    *list(baseline.rejected_requests),
                    RejectedTrip(
                        trip_id=new_trip.id,
                        reason_code=code,
                        detail="insertion would change frozen trips",
                    ),
                ],
                "reason_codes": {**baseline.reason_codes, new_trip.id: code},
            }
        )
        restored = _stamp_version(
            baseline,
            restored,
            problem=updated,
            solver_config=online_config,
            event_type="NEW_REQUEST",
            event_id=eid,
        )
        diff = compute_diff(baseline, restored, frozen)
        return updated, restored, diff
    new_result = _stamp_version(
        baseline,
        new_result,
        problem=updated,
        solver_config=online_config,
        event_type="NEW_REQUEST",
        event_id=eid,
    )
    fleet_stops: dict[str, list[Stop]] = {v.id: [] for v in updated.vehicles}
    fleet_drivers: dict[str, str | None] = {v.id: None for v in updated.vehicles}
    for rp in new_result.route_plans:
        fleet_stops[rp.vehicle_id] = service_stops(list(rp.ordered_stops))
        fleet_drivers[rp.vehicle_id] = rp.driver_id
    _sync_native_fleet(kernel, updated, fleet_stops, fleet_drivers)
    stash_kernel(new_result, kernel)
    diff = compute_diff(baseline, new_result, frozen | {t.id for t in updated.requests if t.frozen})
    return updated, new_result, diff


def recover_disruption(
    problem: DayProblem,
    baseline: PlanningResult,
    *,
    cancel_trip_id: str | None = None,
    no_show_trip_id: str | None = None,
    vehicle_unavailable_id: str | None = None,
    driver_unavailable_id: str | None = None,
    traffic_delay_minutes: int = 0,
    appointment_trip_id: str | None = None,
    appointment_start: int | None = None,
    appointment_end: int | None = None,
    emergency_trip: TripRequest | None = None,
    dispatch_mode: str = "COMMIT",
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    problem = validate_problem(problem)
    if dispatch_mode not in {"COMMIT", "SHADOW"}:
        raise ValueError("UNKNOWN_DISPATCH_MODE")
    updated = problem
    event_type = "DISRUPTION"
    payload: dict[str, object] = {}
    if cancel_trip_id:
        updated = apply_cancellation(updated, cancel_trip_id)
        event_type = "CANCELLATION"
        payload[event_type] = cancel_trip_id
    if no_show_trip_id:
        updated = apply_no_show(updated, no_show_trip_id)
        event_type = "NO_SHOW"
        payload[event_type] = no_show_trip_id
    if vehicle_unavailable_id:
        updated = apply_vehicle_unavailable(updated, vehicle_unavailable_id)
        event_type = "VEHICLE_BREAKDOWN"
        payload[event_type] = vehicle_unavailable_id
    if driver_unavailable_id:
        updated = apply_driver_unavailable(updated, driver_unavailable_id)
        event_type = "DRIVER_UNAVAILABLE"
        payload[event_type] = driver_unavailable_id
    if traffic_delay_minutes:
        updated = apply_traffic_delay(updated, traffic_delay_minutes)
        event_type = "TRAFFIC_DELAY"
        payload[event_type] = traffic_delay_minutes
    if appointment_trip_id:
        updated = apply_appointment_change(
            updated,
            appointment_trip_id,
            appointment_start=appointment_start,
            appointment_end=appointment_end,
        )
        event_type = "APPOINTMENT_CHANGED"
        payload[event_type] = {
            "trip_id": appointment_trip_id,
            "start": appointment_start,
            "end": appointment_end,
        }
    if emergency_trip is not None:
        structural = bool(
            cancel_trip_id
            or no_show_trip_id
            or vehicle_unavailable_id
            or driver_unavailable_id
            or traffic_delay_minutes
            or appointment_trip_id
        )
        if structural:
            updated, mid, _diff = recover_disruption(
                problem,
                baseline,
                cancel_trip_id=cancel_trip_id,
                no_show_trip_id=no_show_trip_id,
                vehicle_unavailable_id=vehicle_unavailable_id,
                driver_unavailable_id=driver_unavailable_id,
                traffic_delay_minutes=traffic_delay_minutes,
                appointment_trip_id=appointment_trip_id,
                appointment_start=appointment_start,
                appointment_end=appointment_end,
                dispatch_mode=dispatch_mode,
            )
            return online_insert(
                updated, mid, emergency_trip, protect_frozen=True, dispatch_mode=dispatch_mode
            )
        return online_insert(
            updated, baseline, emergency_trip, protect_frozen=True, dispatch_mode=dispatch_mode
        )

    seed_stops: dict[str, list[Stop]] | None = None
    seed_drivers: dict[str, str | None] | None = None
    disabled_v = {vehicle_unavailable_id} if vehicle_unavailable_id else set()
    disabled_d = {driver_unavailable_id} if driver_unavailable_id else set()
    active_ids = active_trip_ids(updated)
    seed_stops = {v.id: [] for v in updated.vehicles}
    seed_drivers = {v.id: None for v in updated.vehicles}
    for rp in baseline.route_plans:
        if rp.vehicle_id in disabled_v:
            continue
        if rp.driver_id and rp.driver_id in disabled_d:
            continue
        if rp.vehicle_id not in seed_stops:
            continue
        core = [s for s in service_stops(list(rp.ordered_stops)) if s.trip_id in active_ids]
        seed_stops[rp.vehicle_id] = core
        seed_drivers[rp.vehicle_id] = rp.driver_id

    new_result = solve_greedy(updated, seed_stops=seed_stops, seed_drivers=seed_drivers)
    shadow = (
        dispatch_mode == "SHADOW"
        or updated.operator_policy.dispatch_authority == DispatchAuthority.SHADOW
    )
    new_result = new_result.model_copy(
        update={
            "solution_type": "DISRUPTION_RECOVERY",
            "solver_config": {
                **new_result.solver_config,
                "dispatch_mode": "SHADOW" if shadow else "COMMIT",
                "operational_authorization": False,
            },
        }
    )
    if len(payload) > 1:
        event_type = "DISRUPTION"
    eid = _event_id(
        _base_plan_id(baseline),
        event_type,
        {"changes": payload, "input_hash": fingerprint_problem(updated)},
    )
    new_result = _stamp_version(
        baseline,
        new_result,
        problem=updated,
        solver_config=new_result.solver_config,
        event_type=event_type,
        event_id=eid,
    )
    frozen = {t.id for t in updated.requests if t.frozen}
    diff = compute_diff(baseline, new_result, frozen)
    if cancel_trip_id:
        dropped = dependent_trip_ids(problem, cancel_trip_id)
        for tid in dropped:
            diff.reason_codes[tid] = ReasonCode.CANCELLED.value
        diff.removed_trips = sorted(set(diff.removed_trips) | dropped)
    if no_show_trip_id:
        dropped = dependent_trip_ids(problem, no_show_trip_id)
        diff.reason_codes[no_show_trip_id] = ReasonCode.NO_SHOW.value
        for tid in dropped - {no_show_trip_id}:
            diff.reason_codes[tid] = ReasonCode.CANCELLED.value
        diff.removed_trips = sorted(set(diff.removed_trips) | dropped)
    if vehicle_unavailable_id or driver_unavailable_id or traffic_delay_minutes:
        for tid in diff.moved_trips + diff.removed_trips:
            diff.reason_codes.setdefault(tid, ReasonCode.DISRUPTION.value)
    return updated, new_result, diff
