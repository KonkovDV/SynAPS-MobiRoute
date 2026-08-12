"""Fairness metric computation (group-aware; never a single vanity score)."""

from __future__ import annotations

from collections import defaultdict

from mobiroute.domain.requests import DayProblem, FairnessMetrics, PlanningResult


def jain_index(values: list[float]) -> float | None:
    if not values:
        return None
    s = sum(values)
    if s == 0:
        return 1.0
    return (s * s) / (len(values) * sum(v * v for v in values))


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ys = sorted(values)
    idx = min(len(ys) - 1, round(0.95 * (len(ys) - 1)))
    return ys[idx]


def compute_fairness(problem: DayProblem, result: PlanningResult) -> FairnessMetrics:
    by_zone_req: dict[str, int] = defaultdict(int)
    by_zone_srv: dict[str, int] = defaultdict(int)
    by_elig_req: dict[str, int] = defaultdict(int)
    by_elig_srv: dict[str, int] = defaultdict(int)
    medical_total = 0
    medical_on_time = 0
    wheel_total = 0
    wheel_on_time = 0
    waits: dict[str, list[float]] = defaultdict(list)
    all_wait: list[float] = []
    all_ride: list[float] = []

    trip_map = {t.id: t for t in problem.requests}
    served = set(result.served_requests)
    late = set(result.late_requests)

    for tid in result.served_requests:
        t = trip_map[tid]
        by_zone_srv[t.pickup_zone] += 1
        by_elig_srv[t.eligibility_class.value] += 1
        if t.medical_priority:
            medical_total += 1
            if tid not in late:
                medical_on_time += 1
        if t.wheelchair_requirement.value != "NONE":
            wheel_total += 1
            if tid not in late:
                wheel_on_time += 1

    active_n = 0
    for t in problem.requests:
        if t.booking_status.value in {"CANCELLED", "NO_SHOW"}:
            continue
        active_n += 1
        by_zone_req[t.pickup_zone] += 1
        by_elig_req[t.eligibility_class.value] += 1

    for rp in result.route_plans:
        for it in rp.passenger_itineraries:
            trip = trip_map.get(it.trip_id)
            all_wait.append(float(it.waiting_time))
            all_ride.append(float(it.ride_time))
            if trip is not None:
                waits[trip.eligibility_class.value].append(float(it.waiting_time))
        for tid, w in rp.waiting_times.items():
            if tid in served and not rp.passenger_itineraries:
                trip = trip_map.get(tid)
                all_wait.append(float(w))
                if trip is not None:
                    waits[trip.eligibility_class.value].append(float(w))
        for tid, ride_t in rp.ride_times.items():
            if tid in served and not rp.passenger_itineraries:
                all_ride.append(float(ride_t))

    acc_zone = {
        z: (by_zone_srv[z] / by_zone_req[z] if by_zone_req[z] else 0.0) for z in by_zone_req
    }
    acc_elig = {
        e: (by_elig_srv[e] / by_elig_req[e] if by_elig_req[e] else 0.0) for e in by_elig_req
    }
    mean_wait = {g: (sum(vs) / len(vs) if vs else 0.0) for g, vs in waits.items()}
    all_means = list(mean_wait.values())
    worst = max(all_means) if all_means else None
    dispersion = None
    if len(all_means) >= 2:
        m = sum(all_means) / len(all_means)
        dispersion = sum((x - m) ** 2 for x in all_means) / len(all_means)
    disparity = (max(acc_elig.values()) - min(acc_elig.values())) if acc_elig else None

    unexplained = 0
    for rej in result.rejected_requests:
        if not rej.reason_code:
            unexplained += 1
    rej_n = len(result.rejected_requests)
    cancelled = sum(1 for t in problem.requests if t.booking_status.value == "CANCELLED")
    total_req = len(problem.requests) or 1

    return FairnessMetrics(
        acceptance_rate_by_zone=acc_zone,
        acceptance_rate_by_eligibility=acc_elig,
        medical_on_time_rate=(medical_on_time / medical_total if medical_total else None),
        wheelchair_on_time_rate=(wheel_on_time / wheel_total if wheel_total else None),
        mean_wait_by_group=mean_wait,
        wait_dispersion=dispersion,
        worst_group_wait=worst,
        average_waiting=(sum(all_wait) / len(all_wait) if all_wait else None),
        p95_waiting=_p95(all_wait),
        average_ride_time=(sum(all_ride) / len(all_ride) if all_ride else None),
        p95_ride_time=_p95(all_ride),
        rejected_rate=(len(result.rejected_requests) / active_n if active_n else 0.0),
        cancel_share=cancelled / total_req,
        unexplained_reject_share=(unexplained / rej_n if rej_n else 0.0),
        jain_index=jain_index(list(acc_elig.values())),
        max_disparity=disparity,
        service_coverage=(len(served) / active_n if active_n else 0.0),
        manual_override_disparity=None,
        fair_by_single_metric=False,
    )
