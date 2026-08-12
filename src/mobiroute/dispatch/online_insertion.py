"""Online insertion and disruption recovery with versioned plans P_k → P_{k+1}."""

from __future__ import annotations

import uuid

from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.models import BookingStatus, ReasonCode, SolutionStatus, StopType
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
    check_plan,
    passenger_rides,
    quota_caps,
    trial_exceeds_quota,
    trip_quota_remaining,
    used_quota_minutes,
)
from mobiroute.validation.reasons import diagnose_rejection, non_empty_reason


def _trip_arrivals(route: RoutePlan) -> dict[str, tuple[int, int]]:
    pu: dict[str, int] = {}
    do: dict[str, int] = {}
    for s in service_stops(list(route.ordered_stops)):
        if s.trip_id is None:
            continue
        t = route.arrival_times.get(s.id)
        if t is None:
            continue
        if s.stop_type == StopType.PICKUP:
            pu[s.trip_id] = t
        elif s.stop_type == StopType.DROPOFF:
            do[s.trip_id] = t
    return {tid: (pu[tid], do[tid]) for tid in pu if tid in do}


def _frozen_times_changed(old: RoutePlan | None, new: RoutePlan, frozen: set[str]) -> bool:
    if old is None:
        return False
    old_t = _trip_arrivals(old)
    new_t = _trip_arrivals(new)
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


def _event_id(base: str, event_type: str, payload: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mobiroute:event:{base}:{event_type}:{payload}"))


def compute_diff(baseline: PlanningResult, new: PlanningResult, frozen_ids: set[str]) -> PlanDiff:
    bmap = _trip_vehicle(baseline)
    nmap = _trip_vehicle(new)
    moved = [tid for tid in bmap if tid in nmap and bmap[tid] != nmap[tid]]
    removed = [tid for tid in bmap if tid not in nmap]
    added = [tid for tid in nmap if tid not in bmap]
    unchanged_frozen = [
        tid for tid in frozen_ids if tid in bmap and tid in nmap and bmap[tid] == nmap[tid]
    ]
    churn = {
        "changed_trips": float(len(moved) + len(removed) + len(added)),
        "changed_vehicles": float(len({bmap[t] for t in moved} | {nmap[t] for t in moved})),
        "weighted_critical_churn": float(
            sum(2.0 for t in moved) + sum(1.0 for t in added) + sum(1.0 for t in removed)
        ),
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
        unchanged_frozen_trips=sorted(unchanged_frozen),
        changed_routes=sorted({bmap[t] for t in moved} | {nmap.get(t, "") for t in moved}),
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
            parent = t.same_vehicle_as or t.insert_immediately_after
            if parent and parent not in active:
                active.discard(t.id)
                changed = True
    return active


def dependent_trip_ids(problem: DayProblem, trip_id: str) -> set[str]:
    """Outbound cancel/no-show also drops wait-return / insert-after children."""
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


def apply_cancellation(problem: DayProblem, trip_id: str) -> DayProblem:
    drop = dependent_trip_ids(problem, trip_id)
    reqs = []
    for t in problem.requests:
        if t.id in drop:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.CANCELLED}))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def apply_no_show(problem: DayProblem, trip_id: str) -> DayProblem:
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
    drivers = []
    for d in problem.drivers:
        if d.id == driver_id:
            drivers.append(d.model_copy(update={"availability": False}))
        else:
            drivers.append(d)
    return problem.model_copy(update={"drivers": drivers})


def apply_traffic_delay(problem: DayProblem, delay_minutes: int) -> DayProblem:
    from mobiroute.adapters.travel_time import TravelTimeService

    matrix = TravelTimeService(problem.travel).apply_traffic_delay(delay_minutes)
    return problem.model_copy(update={"travel": matrix})


def apply_appointment_change(
    problem: DayProblem,
    trip_id: str,
    *,
    appointment_start: int | None = None,
    appointment_end: int | None = None,
) -> DayProblem:
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
    event_type: str,
    event_id: str,
) -> PlanningResult:
    return new.model_copy(
        update={
            "base_plan_id": baseline.plan_id or baseline.input_hash,
            "event_id": event_id,
            "event_type": event_type,
        }
    )


def online_insert(
    problem: DayProblem,
    baseline: PlanningResult,
    new_trip: TripRequest,
    *,
    protect_frozen: bool = True,
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    """Insert into existing routes; do not rebuild the day plan from scratch."""
    from mobiroute.solvers.greedy import (
        _assign_driver,
        _trip_stops,
        simulate_stop_sequence,
        try_insert_trip,
    )
    from mobiroute.solvers.insertion_kernel import ProblemKernel
    from mobiroute.solvers.native_accel import attach_native

    frozen = {t.id for t in problem.requests if t.frozen} | (
        set(baseline.served_requests) if protect_frozen else set()
    )
    reqs = [*list(problem.requests), new_trip]
    if protect_frozen:
        reqs = [
            t.model_copy(update={"frozen": True}) if t.id in frozen and t.id != new_trip.id else t
            for t in reqs
        ]
    updated = problem.model_copy(update={"requests": reqs})
    trips_by_id = {t.id: t for t in updated.requests}
    kernel = attach_native(ProblemKernel.from_problem(updated))
    vmap = {v.id: v for v in updated.vehicles}
    occupied = {rp.driver_id for rp in baseline.route_plans if rp.driver_id}

    candidates: list[tuple[int, int, str, list[Stop], str]] = []
    used = {rp.vehicle_id for rp in baseline.route_plans}
    alt_no: list[str] = []
    for rp in baseline.route_plans:
        v = vmap[rp.vehicle_id]
        if accessibility_compatible(v, new_trip) is not None:
            alt_no.append(f"{v.id}:NO_COMPATIBLE_VEHICLE")
            continue
        occ = occupied - ({rp.driver_id} if rp.driver_id else set())
        inserted = try_insert_trip(
            updated,
            v,
            rp.driver_id,
            service_stops(list(rp.ordered_stops)),
            new_trip,
            trips_by_id,
            occupied_driver_ids=occ,
            kernel=kernel,
        )
        if inserted is not None:
            dur, wait_s, seq, assigned = inserted
            candidates.append((dur, wait_s, v.id, seq, assigned))
        else:
            alt_no.append(f"{v.id}:INSERT_INFEASIBLE")
    for v in updated.vehicles:
        if v.id in used:
            continue
        if accessibility_compatible(v, new_trip) is not None:
            alt_no.append(f"{v.id}:NO_COMPATIBLE_VEHICLE")
            continue
        did = _assign_driver(
            updated,
            v.id,
            needs_accessibility=new_trip.needs_boarding_assistance,
            occupied_driver_ids=occupied,
        )
        if did is None:
            alt_no.append(f"{v.id}:NO_DRIVER")
            continue
        inserted = try_insert_trip(
            updated,
            v,
            did,
            [],
            new_trip,
            trips_by_id,
            occupied_driver_ids=occupied,
            kernel=kernel,
        )
        if inserted is not None:
            dur, wait_s, seq, assigned = inserted
            candidates.append((dur, wait_s, v.id, seq, assigned))
        else:
            alt_no.append(f"{v.id}:EMPTY_INSERT_INFEASIBLE")

    eid = _event_id(baseline.plan_id or baseline.input_hash, "NEW_REQUEST", new_trip.id)

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    new_plan = None
    vid = ""
    quota_blocked = False
    cap = trip_quota_remaining(updated, new_trip)
    used_q = used_quota_minutes(problem, baseline)
    qleft = None if cap is None else cap - used_q.get(new_trip.pseudonymous_passenger_id, 0)
    if qleft is not None and qleft <= 0:
        quota_blocked = True
        candidates = []
    quota_cap = quota_caps(updated)
    baseline_by_v = {rp.vehicle_id: rp for rp in baseline.route_plans}
    trips_for_quota = {**trips_by_id, new_trip.id: new_trip}
    for _dur, _wait_s, cand_vid, seq, did in candidates:
        trial = simulate_stop_sequence(updated, vmap[cand_vid], did, seq, trips_by_id)
        if trial is None:
            continue
        old_rp = baseline_by_v.get(cand_vid)
        prev = passenger_rides(old_rp, trips_by_id) if old_rp is not None else {}
        if trial_exceeds_quota(
            trial,
            trips_for_quota,
            quota_cap=quota_cap,
            used_now=used_q,
            previous_on_vehicle=prev,
        ):
            quota_blocked = True
            continue
        if protect_frozen and _frozen_times_changed(old_rp, trial, frozen):
            core = service_stops(list(old_rp.ordered_stops)) if old_rp is not None else []
            trial = simulate_stop_sequence(
                updated, vmap[cand_vid], did, [*core, *_trip_stops(new_trip)], trips_by_id
            )
            if trial is None:
                continue
            if trial_exceeds_quota(
                trial,
                trips_for_quota,
                quota_cap=quota_cap,
                used_now=used_q,
                previous_on_vehicle=prev,
            ):
                quota_blocked = True
                continue
            if _frozen_times_changed(old_rp, trial, frozen):
                continue
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
            deep=True,
            update={
                "solution_type": "ONLINE_INSERTION",
                "status": SolutionStatus.PARTIAL.value,
                "rejected_requests": rejected,
                "reason_codes": {**baseline.reason_codes, new_trip.id: code},
            },
        )
        new_result = _stamp_version(baseline, new_result, event_type="NEW_REQUEST", event_id=eid)
        new_result.fairness_metrics = compute_fairness(updated, new_result)
        diff = compute_diff(baseline, new_result, frozen)
        return updated, new_result, diff

    routes = []
    for rp in baseline.route_plans:
        if rp.vehicle_id == vid:
            routes.append(new_plan)
        else:
            routes.append(
                rp.model_copy(update={"ordered_stops": service_stops(list(rp.ordered_stops))})
            )
    if vid not in used:
        routes.append(new_plan)
    new_result = baseline.model_copy(
        deep=True,
        update={
            "solution_type": "ONLINE_INSERTION",
            "served_requests": sorted([*baseline.served_requests, new_trip.id]),
            "route_plans": routes,
            "reason_codes": {**baseline.reason_codes, new_trip.id: ReasonCode.ACCEPTED.value},
            "objective_values": {
                **baseline.objective_values,
                "served": float(len(baseline.served_requests) + 1),
            },
            "solver_config": {
                "name": "ONLINE_INSERTION",
                "pooling": True,
                **acceleration_status(),
            },
            "explanations": [],
        },
    )
    bmap = _trip_vehicle(baseline)
    nmap = _trip_vehicle(new_result)
    frozen_broken = [
        tid for tid in frozen if tid in bmap and (tid not in nmap or nmap[tid] != bmap[tid])
    ]
    if protect_frozen and frozen_broken:
        code = ReasonCode.TIME_WINDOW_CONFLICT.value
        restored = baseline.model_copy(deep=True)
        restored.solution_type = "ONLINE_INSERTION"
        restored.rejected_requests = [
            *list(baseline.rejected_requests),
            RejectedTrip(
                trip_id=new_trip.id,
                reason_code=code,
                detail="insertion would change frozen trips",
            ),
        ]
        restored.reason_codes = {**baseline.reason_codes, new_trip.id: code}
        restored.status = SolutionStatus.PARTIAL.value
        restored = _stamp_version(baseline, restored, event_type="NEW_REQUEST", event_id=eid)
        diff = compute_diff(baseline, restored, frozen)
        return updated, restored, diff
    new_result = finalize_result(updated, new_result)
    new_result = _stamp_version(baseline, new_result, event_type="NEW_REQUEST", event_id=eid)
    report = check_plan(updated, new_result)
    new_result.verified_feasible = report.feasible
    if not report.feasible:
        new_result.status = SolutionStatus.NOT_VERIFIED.value
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
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    updated = problem
    event_type = "DISRUPTION"
    payload = ""
    if cancel_trip_id:
        updated = apply_cancellation(updated, cancel_trip_id)
        event_type = "CANCELLATION"
        payload = cancel_trip_id
    if no_show_trip_id:
        updated = apply_no_show(updated, no_show_trip_id)
        event_type = "NO_SHOW"
        payload = no_show_trip_id
    if vehicle_unavailable_id:
        updated = apply_vehicle_unavailable(updated, vehicle_unavailable_id)
        event_type = "VEHICLE_BREAKDOWN"
        payload = vehicle_unavailable_id
    if driver_unavailable_id:
        updated = apply_driver_unavailable(updated, driver_unavailable_id)
        event_type = "DRIVER_UNAVAILABLE"
        payload = driver_unavailable_id
    if traffic_delay_minutes:
        updated = apply_traffic_delay(updated, traffic_delay_minutes)
        event_type = "TRAFFIC_DELAY"
        payload = str(traffic_delay_minutes)
    if appointment_trip_id:
        updated = apply_appointment_change(
            updated,
            appointment_trip_id,
            appointment_start=appointment_start,
            appointment_end=appointment_end,
        )
        event_type = "APPOINTMENT_CHANGED"
        payload = appointment_trip_id
    if emergency_trip is not None:
        return online_insert(updated, baseline, emergency_trip, protect_frozen=True)

    seed_stops: dict[str, list[Stop]] | None = None
    seed_drivers: dict[str, str | None] | None = None
    retiming = bool(traffic_delay_minutes) or appointment_trip_id is not None
    if not retiming:
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
    new_result = new_result.model_copy(update={"solution_type": "DISRUPTION_RECOVERY"})
    eid = _event_id(baseline.plan_id or baseline.input_hash, event_type, payload)
    new_result = _stamp_version(baseline, new_result, event_type=event_type, event_id=eid)
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
