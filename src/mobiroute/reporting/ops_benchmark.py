"""Run the synthetic ops scenario suite and collect honest metrics."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

from mobiroute.adapters.ops_scenarios import OPS_MODES, SCRIPTS, generate_ops_day
from mobiroute.dispatch.online_insertion import recover_disruption
from mobiroute.domain.requests import DayProblem, PlanningResult
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.validation.feasibility import check_plan


def write_suite(rows: list[dict[str, object]], out_dir: Path, *, seed: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ops_summary.json").write_text(
        json.dumps(
            {
                "claim_level": "synthetic_benchmark",
                "research_date": "2026-08-12",
                "seed": seed,
                "note": (
                    "Synthetic Moscow-zone policy shapes. Not real MAST trips. "
                    "Greedy never OPTIMAL."
                ),
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with (out_dir / "ops_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _row(
    *,
    scenario: str,
    stage: str,
    algorithm: str,
    problem: DayProblem,
    result: PlanningResult,
    runtime_s: float,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    reasons = Counter(result.reason_codes.values())
    fm = result.fairness_metrics
    report = check_plan(problem, result)
    row: dict[str, object] = {
        "scenario": scenario,
        "stage": stage,
        "algorithm": algorithm,
        "status": result.status,
        "verified_feasible": result.verified_feasible,
        "notary_feasible": report.feasible,
        "served": len(result.served_requests),
        "rejected": len(result.rejected_requests),
        "n_requests": len(problem.requests),
        "n_vehicles": len(problem.vehicles),
        "service_rate": round(len(result.served_requests) / max(1, len(problem.requests)), 4),
        "runtime_s": round(runtime_s, 4),
        "medical_on_time_rate": fm.medical_on_time_rate,
        "wheelchair_on_time_rate": fm.wheelchair_on_time_rate,
        "p95_waiting": fm.p95_waiting,
        "p95_ride_time": fm.p95_ride_time,
        "service_coverage": fm.service_coverage,
        "jain_index": fm.jain_index,
        "fair_by_single_metric": fm.fair_by_single_metric,
        "claim_level": result.claim_level,
        "data_provenance": str(result.data_provenance),
        "input_hash": result.input_hash,
        "config_hash": result.config_hash,
        "plan_id": result.plan_id,
        "event_type": result.event_type,
        "insertion_backend": result.solver_config.get("insertion_backend"),
        "reason_histogram": json.dumps(dict(reasons), sort_keys=True),
        "optimal_claimed": result.status == "OPTIMAL",
    }
    if extra:
        row.update(extra)
    return row


def run_suite(seed: int = 42) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for mode in OPS_MODES:
        script = SCRIPTS[mode]
        problem = generate_ops_day(mode, seed)
        t0 = time.perf_counter()
        greedy = solve_greedy(problem)
        gdt = time.perf_counter() - t0
        rows.append(
            _row(
                scenario=mode,
                stage="day_ahead",
                algorithm="GREEDY",
                problem=problem,
                result=greedy,
                runtime_s=gdt,
                extra={"title": script.title},
            )
        )
        t1 = time.perf_counter()
        fifo = solve_fifo(problem)
        fdt = time.perf_counter() - t1
        rows.append(
            _row(
                scenario=mode,
                stage="day_ahead",
                algorithm="FIFO",
                problem=problem,
                result=fifo,
                runtime_s=fdt,
                extra={"title": script.title},
            )
        )
        for event in script.events:
            if event.kind == "day_ahead":
                continue
            if event.kind == "no_show" and greedy.served_requests:
                updated, rec, diff = recover_disruption(
                    problem, greedy, no_show_trip_id=greedy.served_requests[0]
                )
                rows.append(
                    _row(
                        scenario=mode,
                        stage="no_show",
                        algorithm="DISRUPTION_RECOVERY",
                        problem=updated,
                        result=rec,
                        runtime_s=0.0,
                        extra={
                            "title": script.title,
                            "churn_changed_trips": diff.plan_churn.get("changed_trips"),
                        },
                    )
                )
            if event.kind == "cancel" and greedy.served_requests:
                updated, rec, diff = recover_disruption(
                    problem, greedy, cancel_trip_id=greedy.served_requests[0]
                )
                rows.append(
                    _row(
                        scenario=mode,
                        stage="cancel",
                        algorithm="DISRUPTION_RECOVERY",
                        problem=updated,
                        result=rec,
                        runtime_s=0.0,
                        extra={
                            "title": script.title,
                            "churn_changed_trips": diff.plan_churn.get("changed_trips"),
                        },
                    )
                )
            if event.kind == "breakdown" and problem.vehicles:
                vid = event.vehicle_id or problem.vehicles[0].id
                updated, rec, diff = recover_disruption(problem, greedy, vehicle_unavailable_id=vid)
                rows.append(
                    _row(
                        scenario=mode,
                        stage="breakdown",
                        algorithm="DISRUPTION_RECOVERY",
                        problem=updated,
                        result=rec,
                        runtime_s=0.0,
                        extra={
                            "title": script.title,
                            "churn_changed_trips": diff.plan_churn.get("changed_trips"),
                        },
                    )
                )
    return rows
