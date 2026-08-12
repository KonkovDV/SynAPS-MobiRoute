"""MobiRoute CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.models import ServicePriority, WheelchairType
from mobiroute.domain.requests import TripRequest
from mobiroute.reporting.json_report import write_csv_metrics, write_json, write_markdown
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.solvers.nearest import solve_nearest
from mobiroute.validation.privacy import log_safe


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mobiroute", description="Accessible DARP planning kernel")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate synthetic Moscow-zone day")
    g.add_argument("--mode", default="tiny")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", type=Path, required=True)

    s = sub.add_parser("solve", help="Solve a problem JSON")
    s.add_argument("--problem", type=Path, required=True)
    s.add_argument(
        "--solver",
        choices=["fifo", "greedy", "nearest", "cpsat", "beam"],
        default="greedy",
    )
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--time-limit", type=float, default=10.0)

    d = sub.add_parser("demo", help="Morning plan → medical insert → cancel → breakdown")
    d.add_argument("--out-dir", type=Path, required=True)
    d.add_argument("--seed", type=int, default=42)

    args = p.parse_args(argv)

    if args.cmd == "generate":
        day = generate_day(mode=args.mode, seed=args.seed)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(day.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(log_safe(f"wrote {args.out} mode={args.mode} seed={args.seed}"))
        return 0

    if args.cmd == "solve":
        from mobiroute.domain.requests import DayProblem

        problem = DayProblem.model_validate_json(args.problem.read_text(encoding="utf-8"))
        if args.solver == "fifo":
            result = solve_fifo(problem)
        elif args.solver == "cpsat":
            result = solve_cpsat(problem, time_limit_s=args.time_limit)
        elif args.solver == "nearest":
            result = solve_nearest(problem)
        elif args.solver == "beam":
            result = solve_beam(problem)
        else:
            result = solve_greedy(problem)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_json(result, args.out_dir / "result.json")
        write_markdown(result, args.out_dir / "result.md")
        write_csv_metrics(result, args.out_dir / "metrics.csv")
        print(log_safe(f"status={result.status} feasible={result.verified_feasible}"))
        return 0 if result.verified_feasible or result.status != "ERROR" else 2

    if args.cmd == "demo":
        out = args.out_dir
        out.mkdir(parents=True, exist_ok=True)
        problem = generate_day("tiny", seed=args.seed)
        baseline = solve_greedy(problem)
        write_json(baseline, out / "01_baseline.json")
        write_markdown(baseline, out / "01_baseline.md")

        # new medical request
        medical = TripRequest(
            id="00000000-0000-4000-8000-00000000med1",
            pseudonymous_passenger_id="00000000-0000-4000-8000-00000000pmed",
            pickup_zone="Z_NORTH",
            dropoff_zone="Z_HOSP_A",
            requested_at=30,
            earliest_pickup=90,
            latest_pickup=130,
            appointment_start=120,
            appointment_end=160,
            max_ride_time=50,
            max_wait_time=25,
            wheelchair_requirement=WheelchairType.MANUAL,
            companion_count=1,
            service_priority=ServicePriority.MEDICAL_URGENT,
            needs_lift=True,
            medical_priority=True,
        )
        problem2, res2, diff2 = online_insert(problem, baseline, medical)
        write_json(res2, out / "02_after_medical.json")
        write_markdown(res2, out / "02_after_medical.md", diff2)
        (out / "02_diff.json").write_text(
            json.dumps(diff2.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # cancel first served if any
        cancel_id = baseline.served_requests[0] if baseline.served_requests else None
        problem3, res3, diff3 = recover_disruption(problem2, res2, cancel_trip_id=cancel_id)
        write_markdown(res3, out / "03_after_cancel.md", diff3)

        # traffic delay
        problem3b, res3b, diff3b = recover_disruption(problem3, res3, traffic_delay_minutes=10)
        write_markdown(res3b, out / "03b_after_traffic.md", diff3b)

        # vehicle breakdown
        vid = problem3b.vehicles[0].id
        _problem4, res4, diff4 = recover_disruption(problem3b, res3b, vehicle_unavailable_id=vid)
        write_markdown(res4, out / "04_after_breakdown.md", diff4)
        write_json(res4, out / "04_after_breakdown.json")
        print(log_safe(f"demo complete -> {out}"))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
