"""Harsh 200-vehicle synthetic day + disruption shake. Rust greedy. Not real MAST."""

from __future__ import annotations

import json
import time
from pathlib import Path

from mobiroute.adapters.stress_day import N_REQUESTS, N_VEHICLES, generate_stress_day, inventory
from mobiroute.adapters.synthetic_data import _stable_uuid
from mobiroute.dispatch.online_insertion import (
    active_trip_ids,
    apply_appointment_change,
    apply_cancellation,
    apply_driver_unavailable,
    apply_no_show,
    apply_traffic_delay,
    apply_vehicle_unavailable,
    online_insert,
)
from mobiroute.domain.models import ServicePriority, WheelchairType
from mobiroute.domain.requests import DayProblem, PlanningResult, TripRequest
from mobiroute.domain.route_graph import service_stops
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import acceleration_status, native_available
from mobiroute.validation.feasibility import check_plan

OUT_DIR = Path("benchmark/results/stress-2026-08-12")


def _row(
    name: str, dt: float, problem: DayProblem, res: PlanningResult, extra: dict | None = None
) -> dict:
    n = max(1, len(problem.requests))
    active = sum(
        1 for t in problem.requests if t.booking_status.value not in {"CANCELLED", "NO_SHOW"}
    )
    report = check_plan(problem, res)
    out = {
        "phase": name,
        "runtime_s": round(dt, 4),
        "served": len(res.served_requests),
        "rejected": len(res.rejected_requests),
        "active_requests": active,
        "service_rate_active": round(len(res.served_requests) / max(1, active), 4),
        "service_rate_all": round(len(res.served_requests) / n, 4),
        "status": res.status,
        "verified_feasible": res.verified_feasible,
        "notary_feasible": report.feasible,
        "notary_violations": len(report.violations),
        "insertion_backend": res.solver_config.get("insertion_backend"),
        "solution_type": res.solution_type,
        "routes": len(res.route_plans),
        "claim_level": res.claim_level,
    }
    if extra:
        out.update(extra)
    print(
        f"{name:22} {dt:8.3f}s  served={out['served']:4}/{active}  "
        f"status={out['status']}  notary={out['notary_feasible']}  "
        f"backend={out['insertion_backend']}",
        flush=True,
    )
    return out


def _seeded_replan(problem: DayProblem, baseline: PlanningResult) -> PlanningResult:
    disabled_v = {v.id for v in problem.vehicles if v.shift_end <= v.shift_start}
    disabled_d = {d.id for d in problem.drivers if not d.availability}
    active_ids = active_trip_ids(problem)
    seed_stops = {v.id: [] for v in problem.vehicles}
    seed_drivers: dict[str, str | None] = {v.id: None for v in problem.vehicles}
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
    return solve_greedy(problem, seed_stops=seed_stops, seed_drivers=seed_drivers)


def _busiest(res: PlanningResult, n: int) -> list[str]:
    ranked = sorted(res.route_plans, key=lambda rp: len(rp.passenger_assignments), reverse=True)
    return [rp.vehicle_id for rp in ranked[:n]]


def _served(res: PlanningResult, n: int) -> list[str]:
    return list(res.served_requests)[:n]


def _emergency(seed: int, k: int) -> TripRequest:
    return TripRequest(
        id=_stable_uuid(seed, "stress_emergency", k),
        pseudonymous_passenger_id=_stable_uuid(seed, "stress_emergency_p", k),
        pickup_zone="Z_NORTH",
        dropoff_zone="Z_HOSP_A",
        requested_at=400,
        earliest_pickup=420 + k * 3,
        latest_pickup=455 + k * 3,
        appointment_start=460 + k * 3,
        appointment_end=510 + k * 3,
        max_ride_time=50,
        max_wait_time=25,
        wheelchair_requirement=WheelchairType.MANUAL if k % 2 == 0 else WheelchairType.NONE,
        companion_count=1 if k % 3 == 0 else 0,
        service_priority=ServicePriority.MEDICAL_URGENT,
        needs_lift=k % 2 == 0,
        needs_boarding_assistance=k % 2 == 0,
        medical_priority=True,
        trip_purpose="MEDICAL",
    )


def run_stress(seed: int = 42, out_dir: Path | None = None) -> dict:
    dest = out_dir or OUT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not native_available():
        raise RuntimeError("stress_200 requires mobiroute_native")
    print("accel", acceleration_status(), flush=True)

    t_gen0 = time.perf_counter()
    problem = generate_stress_day(seed)
    gen_s = time.perf_counter() - t_gen0
    inv = inventory(problem)
    print("inventory", inv, flush=True)
    print(
        f"{'generate':22} {gen_s:8.3f}s  {inv['vehicles']} veh / {inv['requests']} req", flush=True
    )

    t0 = time.perf_counter()
    day = solve_greedy(problem)
    day_s = time.perf_counter() - t0
    rows = [_row("day_ahead_greedy", day_s, problem, day)]

    shaken = problem
    broken = _busiest(day, 5)
    for vid in broken:
        shaken = apply_vehicle_unavailable(shaken, vid)
    drivers_on_routes = [rp.driver_id for rp in day.route_plans if rp.driver_id]
    for did in drivers_on_routes[:3]:
        shaken = apply_driver_unavailable(shaken, did)
    for tid in _served(day, 25):
        shaken = apply_cancellation(shaken, tid)
    for tid in _served(day, 45)[25:45]:
        shaken = apply_no_show(shaken, tid)
    medical_ids = [
        t.id for t in problem.requests if t.medical_priority and t.id in set(day.served_requests)
    ]
    for tid in medical_ids[:8]:
        orig = next(t for t in shaken.requests if t.id == tid)
        if orig.appointment_end is not None:
            shaken = apply_appointment_change(
                shaken,
                tid,
                appointment_start=orig.appointment_start,
                appointment_end=max(0, orig.appointment_end - 20),
            )

    t1 = time.perf_counter()
    after_batch = _seeded_replan(shaken, day)
    after_batch = after_batch.model_copy(update={"solution_type": "DISRUPTION_RECOVERY"})
    batch_s = time.perf_counter() - t1
    rows.append(
        _row(
            "batch_disruption",
            batch_s,
            shaken,
            after_batch,
            extra={
                "broken_vehicles": len(broken),
                "cancelled": 25,
                "no_shows": 20,
                "drivers_down": 3,
            },
        )
    )

    traffic = apply_traffic_delay(shaken, 8)
    t2 = time.perf_counter()
    after_traffic = solve_greedy(traffic)
    after_traffic = after_traffic.model_copy(update={"solution_type": "DISRUPTION_RECOVERY"})
    traffic_s = time.perf_counter() - t2
    rows.append(_row("traffic_delay_8min", traffic_s, traffic, after_traffic))

    current_p, current_r = traffic, after_traffic
    insert_times: list[float] = []
    inserted = 0
    rejected_online = 0
    for k in range(8):
        em = _emergency(seed, k)
        t3 = time.perf_counter()
        current_p, current_r, _diff = online_insert(current_p, current_r, em)
        insert_times.append(time.perf_counter() - t3)
        if em.id in set(current_r.served_requests):
            inserted += 1
        else:
            rejected_online += 1
    online_s = sum(insert_times)
    rows.append(
        _row(
            "online_insert_x8",
            online_s,
            current_p,
            current_r,
            extra={
                "inserts_attempted": 8,
                "inserts_accepted": inserted,
                "inserts_rejected": rejected_online,
                "per_insert_s": [round(x, 4) for x in insert_times],
            },
        )
    )

    total = gen_s + day_s + batch_s + traffic_s + online_s
    payload = {
        "claim_level": "synthetic_benchmark",
        "note": (
            "Synthetic 200-vehicle social-taxi stress day. Not real MAST trips. "
            "Greedy never OPTIMAL. Rust insertion required."
        ),
        "accel": acceleration_status(),
        "inventory": inv,
        "generate_s": round(gen_s, 4),
        "total_s": round(total, 4),
        "vehicles": N_VEHICLES,
        "requests": N_REQUESTS,
        "rows": rows,
    }
    (dest / "stress_200.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"{'TOTAL':22} {total:8.3f}s  wrote {dest / 'stress_200.json'}", flush=True)
    return payload


def main() -> None:
    run_stress()


if __name__ == "__main__":
    main()
