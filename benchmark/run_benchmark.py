#!/usr/bin/env python3
"""Run baseline solvers on a synthetic instance and write metrics table."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.solvers.nearest import solve_nearest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="tiny")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    problem = generate_day(args.mode, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "problem.json").write_text(
        json.dumps(problem.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rows = []
    for name, fn in [
        ("FIFO", lambda: solve_fifo(problem)),
        ("NEAREST", lambda: solve_nearest(problem)),
        ("GREEDY", lambda: solve_greedy(problem)),
        ("BEAM", lambda: solve_beam(problem, beam_width=3)),
        ("CPSAT", lambda: solve_cpsat(problem, time_limit_s=10.0)),
    ]:
        t0 = time.perf_counter()
        res = fn()
        dt = time.perf_counter() - t0
        rows.append(
            {
                "algorithm": name,
                "seed": args.seed,
                "mode": args.mode,
                "status": res.status,
                "verified_feasible": res.verified_feasible,
                "served": len(res.served_requests),
                "rejected": len(res.rejected_requests),
                "service_rate": round(len(res.served_requests) / max(1, len(problem.requests)), 4),
                "runtime_s": round(dt, 4),
                "input_hash": res.input_hash,
                "config_hash": res.config_hash,
                "mobiroute_version": res.mobiroute_version,
                "synaps_commit": res.synaps_commit,
                "instance_size": len(problem.requests),
                "solver_status": res.status,
                "claim_level": res.claim_level,
                "jain_index": res.fairness_metrics.jain_index,
                "p95_waiting": res.fairness_metrics.p95_waiting,
                "p95_ride_time": res.fairness_metrics.p95_ride_time,
                "service_coverage": res.fairness_metrics.service_coverage,
                "plan_id": res.plan_id,
            }
        )
        (args.out_dir / f"result_{name}.json").write_text(
            json.dumps(res.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    with (args.out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(args.out_dir / "summary.csv")


if __name__ == "__main__":
    main()
