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


def compute_fairness(problem: DayProblem, result: PlanningResult) -> FairnessMetrics:
    set(result.served_requests)
    by_zone_req: dict[str, int] = defaultdict(int)
    by_zone_srv: dict[str, int] = defaultdict(int)
    by_elig_req: dict[str, int] = defaultdict(int)
    by_elig_srv: dict[str, int] = defaultdict(int)
    medical_total = 0
    medical_on_time = 0
    waits: dict[str, list[float]] = defaultdict(list)

    trip_map = {t.id: t for t in problem.requests}
    for tid in result.served_requests:
        t = trip_map[tid]
        by_zone_srv[t.pickup_zone] += 1
        by_elig_srv[t.eligibility_class.value] += 1
        if t.medical_priority:
            medical_total += 1
            # late_requests listed separately
            if tid not in result.late_requests:
                medical_on_time += 1

    for t in problem.requests:
        if t.booking_status.value in {"CANCELLED", "NO_SHOW"}:
            continue
        by_zone_req[t.pickup_zone] += 1
        by_elig_req[t.eligibility_class.value] += 1

    # Wait proxies from route ride/wait maps
    for rp in result.route_plans:
        for tid, w in rp.waiting_times.items():
            trip = trip_map.get(tid)
            if trip is not None:
                waits[trip.eligibility_class.value].append(float(w))

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
    for r in result.rejected_requests:
        if not r.reason_code:
            unexplained += 1
    rej_n = len(result.rejected_requests)

    return FairnessMetrics(
        acceptance_rate_by_zone=acc_zone,
        acceptance_rate_by_eligibility=acc_elig,
        medical_on_time_rate=(medical_on_time / medical_total if medical_total else None),
        mean_wait_by_group=mean_wait,
        wait_dispersion=dispersion,
        worst_group_wait=worst,
        cancel_share=None,
        unexplained_reject_share=(unexplained / rej_n if rej_n else 0.0),
        jain_index=jain_index(list(acc_elig.values())),
        max_disparity=disparity,
    )
