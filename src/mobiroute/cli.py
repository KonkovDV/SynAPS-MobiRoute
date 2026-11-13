"""MobiRoute CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from mobiroute.adapters.synthetic_data import MODES, generate_day
from mobiroute.dispatch.online_insertion import online_insert, recover_disruption
from mobiroute.domain.models import ServicePriority, WheelchairType
from mobiroute.domain.requests import DayProblem, PlanningResult, TripRequest
from mobiroute.reporting.json_report import write_csv_metrics, write_json, write_markdown
from mobiroute.solvers.alns import solve_alns
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.solvers.nearest import solve_nearest
from mobiroute.solvers.rolling_horizon import solve_rolling_horizon
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
        choices=["fifo", "greedy", "nearest", "cpsat", "beam", "alns", "rhc"],
        default="greedy",
    )
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--time-limit", type=float, default=10.0)

    d = sub.add_parser("demo", help="Morning plan → medical insert → cancel → breakdown")
    d.add_argument("--out-dir", type=Path, required=True)
    d.add_argument("--seed", type=int, default=42)

    o = sub.add_parser(
        "ops-benchmark",
        help="Synthetic Moscow-policy ops suite (not real MAST trips)",
    )
    o.add_argument("--out-dir", type=Path, required=True)
    o.add_argument("--seed", type=int, default=42)

    a = sub.add_parser(
        "academic-benchmark",
        help="Open-data instance through the operator kernel, with claim gating and a stamp",
    )
    a.add_argument("--instance", type=Path, required=True)
    a.add_argument(
        "--solver",
        choices=["fifo", "greedy", "nearest", "beam", "alns", "rhc", "cpsat"],
        default="greedy",
    )
    a.add_argument(
        "--profile",
        choices=["literature", "operator"],
        default="literature",
        help=(
            "declared intent label only: the operator-kernel adapter always applies its "
            "own algebra (integer minutes, 5-min curb wait, 30-min lobby slack), so no "
            "kernel run publishes a literature gap; use literature-benchmark for that"
        ),
    )
    a.add_argument("--time-limit", type=float, default=10.0, help="CP-SAT only")
    a.add_argument("--out-dir", type=Path, required=True)

    lit = sub.add_parser(
        "literature-benchmark",
        help="Exact CP-SAT or MIP on the published Cordeau (2006) algebra, independently verified",
    )
    lit.add_argument("--instance", type=Path, required=True)
    lit.add_argument("--solver", choices=["cpsat", "mip"], default="cpsat")
    lit.add_argument(
        "--backend",
        choices=["SCIP", "HIGHS", "CBC"],
        default="SCIP",
        help="MIP backend (only with --solver mip)",
    )
    lit.add_argument("--time-limit", type=float, default=60.0)
    lit.add_argument("--workers", type=int, default=1, help="CP-SAT workers; 1 is deterministic")
    lit.add_argument("--out-dir", type=Path, required=True)

    args = p.parse_args(argv)

    try:
        return _dispatch(args)
    except (ValueError, OSError) as exc:
        # Validation codes (UNKNOWN_DEPOT_ZONE, ...), schema errors and unreadable
        # files are input problems: report the code and exit 2, never a traceback.
        print(log_safe(f"error: {type(exc).__name__}: {str(exc)[:500]}"))
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "generate":
        if args.mode not in MODES:
            print(log_safe(f"unknown mode {args.mode}; allowed: {', '.join(MODES)}"))
            return 2
        day = generate_day(mode=args.mode, seed=args.seed)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(day.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(log_safe(f"wrote {args.out} mode={args.mode} seed={args.seed}"))
        return 0

    if args.cmd == "solve":
        problem = DayProblem.model_validate_json(args.problem.read_text(encoding="utf-8"))
        result = _run_kernel_solver(problem, args.solver, time_limit_s=args.time_limit)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_json(result, args.out_dir / "result.json")
        write_markdown(result, args.out_dir / "result.md")
        write_csv_metrics(result, args.out_dir / "metrics.csv")
        print(log_safe(f"status={result.status} feasible={result.verified_feasible}"))
        successful = {"OPTIMAL", "FEASIBLE", "HEURISTIC_FEASIBLE", "PARTIAL"}
        return 0 if result.verified_feasible and result.status in successful else 2

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

    if args.cmd == "ops-benchmark":
        from mobiroute.reporting.ops_benchmark import run_suite, write_suite

        rows = run_suite(args.seed)
        write_suite(rows, args.out_dir, seed=args.seed)
        print(
            log_safe(
                f"ops-benchmark -> {args.out_dir} rows={len(rows)} claim_level=synthetic_benchmark"
            )
        )
        return 0

    if args.cmd == "academic-benchmark":
        from mobiroute.adapters.cordeau import cordeau_node_routes, parse_cordeau_darp
        from mobiroute.benchmarks.academic import (
            CORDEAU_A2_16_REFERENCE,
            CORDEAU_A2_16_REFERENCE_SOURCE,
            BenchmarkProfile,
            build_academic_report,
            build_evidence,
        )
        from mobiroute.benchmarks.cordeau_exact import (
            CORDEAU_A2_16_SHA256,
            parse_cordeau_instance,
            verify_routes,
        )
        from mobiroute.validation.feasibility import check_plan

        profiles = {
            "literature": BenchmarkProfile.LITERATURE,
            "operator": BenchmarkProfile.OPERATOR,
        }
        # One read: the parsed bytes are the hashed bytes.
        raw = args.instance.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        is_a2_16 = digest == CORDEAU_A2_16_SHA256
        # The a2-16 reference attaches to the vendored bytes, never to a file name.
        instance_id = "cordeau-a2-16" if is_a2_16 else f"cordeau-{args.instance.stem}"
        text = raw.decode("utf-8")
        problem = parse_cordeau_darp(text, instance_id=instance_id)
        started = time.perf_counter()
        result = _run_kernel_solver(problem, args.solver, time_limit_s=args.time_limit)
        elapsed = time.perf_counter() - started
        notary = check_plan(problem, result)
        report = build_academic_report(
            problem,
            result,
            profile=profiles[args.profile],
            reference_objective=CORDEAU_A2_16_REFERENCE if is_a2_16 else None,
            reference_source=CORDEAU_A2_16_REFERENCE_SOURCE if is_a2_16 else None,
        )
        evidence = build_evidence(
            result,
            instance_path=str(args.instance),
            instance_sha256=digest,
            solver=args.solver,
            seed=problem.seed,
            wall_clock_seconds=elapsed,
            notary_feasible=notary.feasible,
            notary_violations=[str(item) for item in notary.violations],
            exit_code=0 if notary.feasible else 2,
        )
        # Re-time the kernel's sequences under the published algebra: this is the
        # machine-checked reason behind ALGEBRA_NOT_COMPARABLE, not a literature run.
        literature = parse_cordeau_instance(text, instance_id=instance_id)
        node_routes = cordeau_node_routes(result)
        strict = verify_routes(literature, node_routes)
        lobby = verify_routes(literature, node_routes, alight_slack=30)
        crosscheck = {
            "kernel_routes_literature_feasible": strict.feasible,
            "kernel_routes_literature_violations": strict.violations[:8],
            "kernel_routes_literature_cost": strict.cost,
            "feasible_with_operator_lobby_slack_30": lobby.feasible,
            "note": "diagnostic re-timing of operator-algebra sequences; never a gap",
        }
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "academic_benchmark.json").write_text(
            json.dumps(
                {
                    "report": report.model_dump(mode="json"),
                    "evidence": evidence.model_dump(mode="json"),
                    "literature_crosscheck": crosscheck,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        write_json(result, args.out_dir / "result.json")
        print(log_safe(report.allowed_claim))
        return 0 if notary.feasible else 2

    if args.cmd == "literature-benchmark":
        import platform

        from mobiroute import SYNAPS_COMMIT, __version__
        from mobiroute.benchmarks.cordeau_exact import (
            build_literature_report,
            load_cordeau_bytes,
            solve_exact_cpsat,
            solve_exact_mip,
            verify_routes,
        )

        raw = args.instance.read_bytes()
        instance, digest = load_cordeau_bytes(raw, instance_id=args.instance.stem)
        if args.solver == "mip":
            run = solve_exact_mip(instance, backend=args.backend, time_limit_s=args.time_limit)
        else:
            run = solve_exact_cpsat(instance, time_limit_s=args.time_limit, workers=args.workers)
        verdict = verify_routes(instance, run.routes)
        lit_report = build_literature_report(instance, digest, run, verdict)
        code = 0 if verdict.feasible and verdict.full_service else 2
        lit_evidence: dict[str, object] = {
            "mobiroute_version": __version__,
            "synaps_commit": SYNAPS_COMMIT,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "ortools_version": run.ortools_version,
            "instance_path": str(args.instance),
            "instance_sha256": digest,
            "time_limit_s": run.time_limit_s,
            "solver": run.solver,
            "backend": run.backend,
            "workers": run.workers,
            "scale": run.scale,
            "wall_clock_seconds": run.wall_clock_seconds,
            "exit_code": code,
        }
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "literature_benchmark.json").write_text(
            json.dumps(
                {
                    "report": lit_report.model_dump(mode="json"),
                    "run": run.model_dump(mode="json"),
                    "verdict": verdict.model_dump(mode="json"),
                    "evidence": lit_evidence,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(log_safe(lit_report.allowed_claim))
        return code

    return 1


def _run_kernel_solver(problem: DayProblem, solver: str, *, time_limit_s: float) -> PlanningResult:
    if solver == "fifo":
        return solve_fifo(problem)
    if solver == "nearest":
        return solve_nearest(problem)
    if solver == "beam":
        return solve_beam(problem)
    if solver == "alns":
        return solve_alns(problem)
    if solver == "rhc":
        return solve_rolling_horizon(problem)
    if solver == "cpsat":
        return solve_cpsat(problem, time_limit_s=time_limit_s)
    return solve_greedy(problem)


if __name__ == "__main__":
    raise SystemExit(main())
