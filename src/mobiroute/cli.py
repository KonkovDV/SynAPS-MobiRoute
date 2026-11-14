"""MobiRoute CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
    lit.add_argument("--svg", action="store_true", help="also write routes.svg and timeline.svg")

    v = sub.add_parser(
        "vrp-solve",
        help="Rich VRP: heterogeneous fleet, capacity vector, windows, pickup and delivery",
    )
    src = v.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--instance", type=Path, help="Solomon, Li & Lim, Sartori-Buriol, Cordeau or JSON file"
    )
    src.add_argument(
        "--generate", choices=["cargo", "shuttle", "plant"], help="synthetic operating day"
    )
    src.add_argument(
        "--geo", type=Path, help="orders and fleet with coordinates (mobiroute.vrp.geo.v1 JSON)"
    )
    v.add_argument(
        "--osrm", default=None, help="OSRM server URL for road matrices of --geo (else offline)"
    )
    v.add_argument("--osrm-profile", default="driving")
    v.add_argument(
        "--sheets",
        action="store_true",
        help="also write route sheets: route-sheets.csv, .md and a Gantt chart .svg",
    )
    v.add_argument("--lang", choices=["ru", "en"], default="ru", help="language of route sheets")
    v.add_argument("--seed", type=int, default=7)
    v.add_argument("--orders", type=int, default=None, help="size of a generated day")
    v.add_argument("--solver", choices=["alns", "ortools", "exact"], default="alns")
    v.add_argument("--iterations", type=int, default=5000)
    v.add_argument("--time-limit", type=float, default=None)
    v.add_argument("--backend", choices=["auto", "python", "native"], default="auto")
    v.add_argument("--out-dir", type=Path, required=True)
    v.add_argument("--svg", action="store_true", help="also write routes.svg")

    rt = sub.add_parser(
        "vrp-dispatch", help="Replay a day of live orders through a dispatch policy"
    )
    rt.add_argument("--day", choices=["shuttle", "plant"], default="shuttle")
    rt.add_argument("--seed", type=int, default=11)
    rt.add_argument(
        "--policy", choices=["insertion", "insertion+alns", "ortools-resolve"], default="insertion"
    )
    rt.add_argument("--out-dir", type=Path, required=True)

    args = p.parse_args(argv)

    try:
        return _dispatch(args)
    except (ValueError, OSError) as exc:
        # Validation codes (UNKNOWN_DEPOT_ZONE, ...), schema errors and unreadable
        # files are input problems: report the code on stderr and exit 2, never
        # a traceback.
        print(log_safe(f"error: {type(exc).__name__}: {str(exc)[:500]}"), file=sys.stderr)
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
        if args.svg and verdict.routes:
            from mobiroute.reporting.svg import route_map_svg, timeline_svg

            name = instance.instance_id
            (args.out_dir / "routes.svg").write_text(
                route_map_svg(
                    instance, verdict, title=f"{name}: verified plan, cost {verdict.cost:.2f}"
                ),
                encoding="utf-8",
            )
            (args.out_dir / "timeline.svg").write_text(
                timeline_svg(instance, verdict, title=f"{name}: when each request is served"),
                encoding="utf-8",
            )
        for cert in verdict.certificates:
            print(log_safe(cert.explanation_en))
        print(log_safe(lit_report.allowed_claim))
        return code

    if args.cmd == "vrp-solve":
        return _vrp_solve(args)

    if args.cmd == "vrp-dispatch":
        return _vrp_dispatch(args)

    return 1


def _vrp_instance(args: argparse.Namespace) -> tuple[object, object]:
    """The instance and, for ``--geo``, the :class:`GeoInstance` it came from."""
    from mobiroute.vrp.generators import cargo_day, plant_day, shuttle_day
    from mobiroute.vrp.io import load_benchmark

    if args.geo is not None:
        from mobiroute.vrp import geo

        built = geo.load(str(args.geo), osrm=args.osrm, osrm_profile=args.osrm_profile)
        return built.instance, built
    if args.instance is not None:
        inst, _digest = load_benchmark(args.instance)
        return inst, None
    if args.generate == "cargo":
        return cargo_day(args.seed, n_orders=args.orders or 120), None
    if args.generate == "shuttle":
        return shuttle_day(args.seed, n_orders=args.orders or 160), None
    return plant_day(args.seed, n_moves=args.orders or 140), None


def _vrp_solve(args: argparse.Namespace) -> int:
    from mobiroute.vrp.alns import AlnsConfig, solve
    from mobiroute.vrp.exact import solve_exact
    from mobiroute.vrp.model import Instance
    from mobiroute.vrp.ortools_lane import solve_ortools
    from mobiroute.vrp.verify import Verdict

    inst, built = _vrp_instance(args)
    assert isinstance(inst, Instance)
    started = time.perf_counter()
    verdict: Verdict
    if args.solver == "ortools":
        run = solve_ortools(inst, time_limit=args.time_limit or 10.0)
        solution, verdict, label = run.solution, run.verdict, f"OR-Tools {run.status}"
    elif args.solver == "exact":
        ex = solve_exact(inst, time_limit=args.time_limit or 60.0)
        solution, verdict, label = ex.solution, ex.verdict, f"CP-SAT {ex.status}"
    else:
        res = solve(
            inst,
            AlnsConfig(
                iterations=args.iterations,
                time_limit=args.time_limit,
                seed=args.seed,
                backend=args.backend,
            ),
        )
        solution, verdict, label = (
            res.solution,
            res.verdict,
            f"ALNS {res.iterations} it, {res.backend}",
        )
    elapsed = time.perf_counter() - started
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "solution.json").write_text(solution.to_json(inst), encoding="utf-8")
    report = {
        "instance": inst.name,
        "solver": label,
        "seconds": round(elapsed, 3),
        "feasible": verdict.feasible,
        "complete": verdict.complete,
        "violations": list(verdict.violations),
        "vehicles": verdict.cost.vehicles,
        "vehicles_by_type": verdict.cost.vehicles_by_type,
        "distance": round(verdict.cost.distance, 4),
        "cost": round(verdict.cost.total, 4),
        "unassigned": list(verdict.unassigned),
        "routes": [
            {
                "vehicle_type": r.vehicle_type,
                "stops": list(r.nodes),
                "service_start": [round(x, 3) for x in r.start_times],
                "peak_load": list(r.peak_load),
                "min_duration": round(r.min_duration, 3),
            }
            for r in verdict.routes
        ],
    }
    (args.out_dir / "verdict.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.svg:
        from mobiroute.vrp.render import routes_svg

        (args.out_dir / "routes.svg").write_text(
            routes_svg(inst, solution, title=f"{inst.name}: {label}"), encoding="utf-8"
        )
    if args.sheets and verdict.feasible:
        from mobiroute.vrp.geo import GeoInstance
        from mobiroute.vrp.sheets import route_sheets, sheets_csv, sheets_markdown, sheets_svg

        geo_in = built if isinstance(built, GeoInstance) else None
        sheets = route_sheets(inst, solution, verdict, geo_in.places if geo_in else None)
        (args.out_dir / "route-sheets.csv").write_text(
            sheets_csv(sheets, inst.dimensions), encoding="utf-8"
        )
        markdown = sheets_markdown(
            sheets, inst.dimensions, lang=args.lang, currency=geo_in.currency if geo_in else ""
        )
        (args.out_dir / "route-sheets.md").write_text(markdown, encoding="utf-8")
        gantt = sheets_svg(
            sheets,
            title=f"{inst.name}: {'route sheets' if args.lang == 'en' else 'путевые листы'}",
            lang=args.lang,
            currency=geo_in.currency if geo_in else "",
        )
        (args.out_dir / "route-sheets.svg").write_text(gantt, encoding="utf-8")
    print(log_safe(f"{inst.name}: {verdict.summary()} [{label}, {elapsed:.1f} s]"))
    return 0 if verdict.feasible else 2


def _vrp_dispatch(args: argparse.Namespace) -> int:
    from mobiroute.vrp.generators import plant_day, shuttle_day
    from mobiroute.vrp.realtime import simulate

    inst = shuttle_day(args.seed) if args.day == "shuttle" else plant_day(args.seed)
    report = simulate(inst, args.policy)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "instance": report.instance,
        "policy": report.policy,
        "verified": report.verified,
        "kpi": report.kpi,
        "decisions": [
            {
                "order": d.request,
                "released": d.released,
                "accepted": d.accepted,
                "vehicle": d.vehicle,
                "pickup_start": d.pickup_start,
                "latency_ms": d.latency_ms,
                "reason": d.reason,
            }
            for d in report.decisions
        ],
    }
    (args.out_dir / "dispatch.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    k = report.kpi
    print(
        log_safe(
            f"{report.instance} [{report.policy}]: "
            f"accepted {k['accepted']:.0f}/{k['orders']:.0f}, "
            f"call-to-pickup {k['response_mean_min']:.1f} min, "
            f"decision {k['decision_ms_mean']:.2f} ms, verified={report.verified}"
        )
    )
    return 0 if report.verified else 2


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
