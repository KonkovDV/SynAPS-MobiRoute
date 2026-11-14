"""Solver lab: one instance, every lane, one independent verifier.

Literature lane (Cordeau 2006 algebra, comparable with the published optimum):
CP-SAT on a conservative integer grid, the compact two-index MIP on SCIP, HiGHS
and CBC, and the LP relaxation bound. Operator lane (integer minutes, curb wait,
appointment lobby; never comparable with the literature): the kernel heuristics
and tiny CP-SAT, plus a re-timing of their sequences under the literature algebra.

Usage:
  python benchmark/solver_lab.py [--instance PATH] [--mip-time-limit 60] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from mobiroute import __version__
from mobiroute.adapters.cordeau import cordeau_node_routes, parse_cordeau_darp
from mobiroute.benchmarks.cordeau_exact import (
    REFERENCES,
    load_cordeau_bytes,
    lp_relaxation_bound,
    solve_exact_cpsat,
    solve_exact_mip,
    verify_routes,
)
from mobiroute.solvers.alns import solve_alns
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.rolling_horizon import solve_rolling_horizon
from mobiroute.validation.feasibility import check_plan
from mobiroute.vrp.alns import AlnsConfig
from mobiroute.vrp.alns import solve as vrp_solve
from mobiroute.vrp.io import parse_cordeau_vrp
from mobiroute.vrp.ortools_lane import solve_ortools

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTANCE = ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt"


def _literature_rows(raw: bytes, mip_limit: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    instance, digest = load_cordeau_bytes(raw, instance_id="a2-16")
    reference = REFERENCES.get(digest)
    rows: list[dict[str, Any]] = []
    runs: list[tuple[str, Callable[[], Any]]] = [
        ("CP-SAT", partial(solve_exact_cpsat, instance, time_limit_s=60.0))
    ]
    for backend in ("SCIP", "HIGHS", "CBC"):
        mip = partial(
            solve_exact_mip, instance, backend=backend, time_limit_s=mip_limit, with_lp_bound=False
        )
        runs.append((f"MIP · {backend}", mip))
    for label, run_fn in runs:
        run = run_fn()
        verdict = verify_routes(instance, run.routes)
        gap = None
        if reference is not None and verdict.full_service and verdict.feasible:
            gap = 100.0 * (verdict.cost - reference.objective) / reference.objective
        rows.append(
            {
                "lane": "literature",
                "solver": label,
                "status": run.status,
                "verified": verdict.feasible and verdict.full_service,
                "feasible": verdict.feasible,
                "served": f"{len(verdict.served_requests)}/{verdict.requests_total}",
                "cost": round(verdict.cost, 4) if run.routes else None,
                "bound": None if run.model_bound is None else round(run.model_bound, 4),
                "gap_to_published_pct": None if gap is None else round(gap, 4),
                "seconds": run.wall_clock_seconds,
            }
        )
    # Heuristics of the rich-VRP engine on the same published algebra, judged
    # by the same Cordeau verifier (node ids coincide).
    vrp_inst = parse_cordeau_vrp(raw.decode("utf-8"), name="a2-16")
    started = time.perf_counter()
    alns = vrp_solve(vrp_inst, AlnsConfig(iterations=10000, seed=1))
    alns_seconds = time.perf_counter() - started
    ort = solve_ortools(vrp_inst, time_limit=10.0)
    for label, routes, status, seconds in (
        ("ALNS, rich-VRP engine (10k it)", alns.solution, "HEURISTIC", alns_seconds),
        ("OR-Tools Routing PCI+GLS (10 s)", ort.solution, ort.status, ort.seconds),
    ):
        node_routes = [list(r.nodes) for r in routes.routes if r.nodes]
        verdict = verify_routes(instance, node_routes)
        gap = None
        if reference is not None and verdict.full_service and verdict.feasible:
            gap = 100.0 * (verdict.cost - reference.objective) / reference.objective
        rows.append(
            {
                "lane": "literature",
                "solver": label,
                "status": status,
                "verified": verdict.feasible and verdict.full_service,
                "feasible": verdict.feasible,
                "served": f"{len(verdict.served_requests)}/{verdict.requests_total}",
                "cost": round(verdict.cost, 4) if node_routes else None,
                "bound": None,
                "gap_to_published_pct": None if gap is None else round(gap, 4),
                "seconds": round(seconds, 3),
            }
        )
    started = time.perf_counter()
    bound = lp_relaxation_bound(instance)
    rows.append(
        {
            "lane": "literature",
            "solver": "LP relaxation · GLOP",
            "status": "BOUND",
            "verified": None,
            "cost": None,
            "bound": None if bound is None else round(bound, 4),
            "gap_to_published_pct": None,
            "seconds": round(time.perf_counter() - started, 3),
        }
    )
    meta = {
        "instance": "Cordeau (2006) a2-16",
        "sha256": digest,
        "published_optimum": None if reference is None else reference.objective,
        "published_source": None if reference is None else reference.source,
    }
    return rows, meta


def _operator_rows(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8")
    problem = parse_cordeau_darp(text, instance_id="cordeau-a2-16")
    instance, _ = load_cordeau_bytes(raw, instance_id="a2-16")
    rows: list[dict[str, Any]] = []
    for label, fn in (
        ("Greedy insertion (Rust)", solve_greedy),
        ("Beam search", solve_beam),
        ("ALNS", solve_alns),
        ("Rolling horizon", solve_rolling_horizon),
        ("CP-SAT tiny (sequential)", solve_cpsat),
    ):
        started = time.perf_counter()
        result = fn(problem)
        seconds = time.perf_counter() - started
        routes = cordeau_node_routes(result)
        rows.append(
            {
                "lane": "operator",
                "solver": label,
                "status": result.status,
                "verified": check_plan(problem, result).feasible,
                "served": f"{len(result.served_requests)}/{len(problem.requests)}",
                "kernel_distance": round(sum(r.route_distance for r in result.route_plans), 1),
                "literature_feasible": verify_routes(instance, routes).feasible,
                "feasible_with_lobby_slack_30": verify_routes(
                    instance, routes, alight_slack=30
                ).feasible,
                "seconds": round(seconds, 3),
            }
        )
    return rows


def _gap_text(gap: float | None) -> str:
    if gap is None:
        return "—"
    # The published optimum is printed to 0.01: smaller differences carry no sign.
    if abs(gap) < 0.005 / 294.25 * 100 + 1e-9 or abs(gap) < 0.002:
        return "0.00% (within rounding)"
    return f"{gap:.2f}%"


def _verified_text(row: dict[str, Any]) -> str:
    if row["verified"] is None:
        return "—"
    if row["verified"]:
        return "yes"
    # A feasible plan that leaves requests out is cheaper than the optimum and
    # must not read as a better answer.
    if row.get("feasible"):
        return f"feasible, {row['served']} served"
    return "no"


def _markdown(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    lines = [
        "# Solver lab: Cordeau a2-16",
        "",
        f"Instance SHA-256 `{meta['sha256']}`; published optimum "
        f"{meta['published_optimum']} ({meta['published_source']}).",
        f"Machine: {payload['host']['platform']}, Python {payload['host']['python']}, "
        f"mobiroute {payload['host']['mobiroute']}. Wall-clock, single thread.",
        "",
        "## Literature algebra (comparable)",
        "",
        "| Solver | Status | Verified | Cost | Bound | Gap to published | Time, s |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["literature"]:
        gap = row["gap_to_published_pct"]
        lines.append(
            f"| {row['solver']} | {row['status']} | {_verified_text(row)} | "
            f"{'—' if row['cost'] is None else f'{row["cost"]:.2f}'} | "
            f"{'—' if row['bound'] is None else f'{row["bound"]:.2f}'} | "
            f"{_gap_text(gap)} | {row['seconds']:.1f} |"
        )
    lines += [
        "",
        "## Operator algebra (not comparable: integer minutes, 5-min curb, 30-min lobby)",
        "",
        "| Solver | Status | Served | Notary | Kernel distance | Literature-feasible | "
        "With 30-min lobby | Time, s |",
        "| --- | --- | --- | --- | ---: | --- | --- | ---: |",
    ]
    for row in payload["operator"]:
        lines.append(
            f"| {row['solver']} | {row['status']} | {row['served']} | "
            f"{'yes' if row['verified'] else 'no'} | {row['kernel_distance']} | "
            f"{'yes' if row['literature_feasible'] else 'no'} | "
            f"{'yes' if row['feasible_with_lobby_slack_30'] else 'no'} | {row['seconds']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--mip-time-limit", type=float, default=60.0)
    parser.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "solver-lab")
    args = parser.parse_args()
    raw = args.instance.read_bytes()
    literature, meta = _literature_rows(raw, args.mip_time_limit)
    payload = {
        "meta": meta,
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "mobiroute": __version__,
        },
        "literature": literature,
        "operator": _operator_rows(raw),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "solver_lab.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (args.out / "solver_lab.md").write_text(_markdown(payload), encoding="utf-8")
    print(_markdown(payload))


if __name__ == "__main__":
    main()
