"""Online insertion and disruption recovery with plan diffs."""

from __future__ import annotations

from mobiroute.domain.models import BookingStatus, ReasonCode
from mobiroute.domain.requests import DayProblem, PlanDiff, PlanningResult, TripRequest
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.feasibility import check_plan


def _trip_vehicle(result: PlanningResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for rp in result.route_plans:
        for tid in rp.passenger_assignments:
            out[tid] = rp.vehicle_id
    return out


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
        objective_delta={
            "served": float(len(new.served_requests) - len(baseline.served_requests)),
        },
        plan_churn=churn,
    )


def apply_cancellation(problem: DayProblem, trip_id: str) -> DayProblem:
    reqs = []
    for t in problem.requests:
        if t.id == trip_id:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.CANCELLED}))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def apply_no_show(problem: DayProblem, trip_id: str) -> DayProblem:
    reqs = []
    for t in problem.requests:
        if t.id == trip_id:
            reqs.append(t.model_copy(update={"booking_status": BookingStatus.NO_SHOW}))
        else:
            reqs.append(t)
    return problem.model_copy(update={"requests": reqs})


def apply_vehicle_unavailable(problem: DayProblem, vehicle_id: str) -> DayProblem:
    vehs = []
    for v in problem.vehicles:
        if v.id == vehicle_id:
            vehs.append(v.model_copy(update={"shift_end": v.shift_start}))
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


def online_insert(
    problem: DayProblem,
    baseline: PlanningResult,
    new_trip: TripRequest,
    *,
    protect_frozen: bool = True,
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    """Insert into existing routes; do not rebuild the day plan from scratch."""
    from mobiroute.domain.models import SolutionStatus
    from mobiroute.domain.requests import RejectedTrip
    from mobiroute.solvers.greedy import _assign_driver, try_insert_trip

    frozen = {t.id for t in problem.requests if t.frozen}
    reqs = [*list(problem.requests), new_trip]
    if protect_frozen:
        served = set(baseline.served_requests)
        reqs = [
            t.model_copy(update={"frozen": True}) if t.id in served and t.id != new_trip.id else t
            for t in reqs
        ]
    updated = problem.model_copy(update={"requests": reqs})
    trips_by_id = {t.id: t for t in updated.requests}
    vmap = {v.id: v for v in updated.vehicles}

    candidates: list[tuple[int, str, object]] = []
    used = {rp.vehicle_id for rp in baseline.route_plans}
    for rp in baseline.route_plans:
        v = vmap[rp.vehicle_id]
        inserted = try_insert_trip(
            updated, v, rp.driver_id, list(rp.ordered_stops), new_trip, trips_by_id
        )
        if inserted is not None:
            score, _seq, plan = inserted
            candidates.append((score, v.id, plan))
    for v in updated.vehicles:
        if v.id in used:
            continue
        inserted = try_insert_trip(
            updated, v, _assign_driver(updated, v.id), [], new_trip, trips_by_id
        )
        if inserted is not None:
            score, _seq, plan = inserted
            candidates.append((score, v.id, plan))

    if not candidates:
        rejected = [
            *list(baseline.rejected_requests),
            RejectedTrip(
                trip_id=new_trip.id,
                reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value,
                detail="no feasible insertion into existing routes",
            ),
        ]
        new_result = baseline.model_copy(
            deep=True,
            update={
                "solution_type": "ONLINE_INSERTION",
                "status": SolutionStatus.PARTIAL.value,
                "rejected_requests": rejected,
                "reason_codes": {
                    **baseline.reason_codes,
                    new_trip.id: ReasonCode.TIME_WINDOW_CONFLICT.value,
                },
            },
        )
        diff = compute_diff(baseline, new_result, frozen)
        return updated, new_result, diff

    candidates.sort(key=lambda x: (x[0], x[1]))
    _score, vid, new_plan = candidates[0]
    routes = []
    for rp in baseline.route_plans:
        if rp.vehicle_id == vid:
            routes.append(new_plan)
        else:
            routes.append(rp)
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
            "solver_config": {"name": "ONLINE_INSERTION", "pooling": True},
        },
    )
    bmap = _trip_vehicle(baseline)
    nmap = _trip_vehicle(new_result)
    frozen_broken = [
        tid for tid in frozen if tid in bmap and (tid not in nmap or nmap[tid] != bmap[tid])
    ]
    if protect_frozen and frozen_broken:
        restored = baseline.model_copy(deep=True)
        restored.solution_type = "ONLINE_INSERTION"
        restored.rejected_requests = [
            *list(baseline.rejected_requests),
            RejectedTrip(
                trip_id=new_trip.id,
                reason_code=ReasonCode.TIME_WINDOW_CONFLICT.value,
                detail="insertion would change frozen trips",
            ),
        ]
        restored.reason_codes = {
            **baseline.reason_codes,
            new_trip.id: ReasonCode.TIME_WINDOW_CONFLICT.value,
        }
        restored.status = SolutionStatus.PARTIAL.value
        diff = compute_diff(baseline, restored, frozen)
        return updated, restored, diff
    report = check_plan(updated, new_result)
    new_result.verified_feasible = report.feasible
    if report.feasible:
        new_result.status = (
            SolutionStatus.PARTIAL.value
            if new_result.rejected_requests
            else SolutionStatus.HEURISTIC_FEASIBLE.value
        )
    else:
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
) -> tuple[DayProblem, PlanningResult, PlanDiff]:
    updated = problem
    if cancel_trip_id:
        updated = apply_cancellation(updated, cancel_trip_id)
    if no_show_trip_id:
        updated = apply_no_show(updated, no_show_trip_id)
    if vehicle_unavailable_id:
        updated = apply_vehicle_unavailable(updated, vehicle_unavailable_id)
    if driver_unavailable_id:
        updated = apply_driver_unavailable(updated, driver_unavailable_id)
    if traffic_delay_minutes:
        updated = apply_traffic_delay(updated, traffic_delay_minutes)
    new_result = solve_greedy(updated)
    frozen = {t.id for t in updated.requests if t.frozen}
    diff = compute_diff(baseline, new_result, frozen)
    if cancel_trip_id:
        diff.reason_codes[cancel_trip_id] = ReasonCode.CANCELLED.value
        diff.removed_trips = sorted(set(diff.removed_trips) | {cancel_trip_id})
    if no_show_trip_id:
        diff.reason_codes[no_show_trip_id] = ReasonCode.NO_SHOW.value
    if vehicle_unavailable_id or driver_unavailable_id or traffic_delay_minutes:
        for tid in diff.moved_trips + diff.removed_trips:
            diff.reason_codes.setdefault(tid, ReasonCode.DISRUPTION.value)
    return updated, new_result, diff
