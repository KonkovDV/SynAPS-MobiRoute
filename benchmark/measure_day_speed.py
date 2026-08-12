"""Wall-clock of a synthetic social-taxi day. Not real MAST trips. Never OPTIMAL.

Usage:
  python benchmark/measure_day_speed.py
  python benchmark/measure_day_speed.py --backend python --modes small,medium
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import platform
import pstats
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

from mobiroute.adapters.synthetic_data import generate_day
from mobiroute.solvers.alns import solve_alns
from mobiroute.solvers.beam import solve_beam
from mobiroute.solvers.cpsat import solve_cpsat
from mobiroute.solvers.greedy import solve_fifo, solve_greedy
from mobiroute.solvers.native_accel import acceleration_status
from mobiroute.solvers.nearest import solve_nearest

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmark" / "results" / "speed-2026-08-12"


def _host() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }


def _instance_stats(problem) -> dict[str, object]:
    reqs = problem.requests
    return {
        "vehicles": len(problem.vehicles),
        "drivers": len(problem.drivers),
        "requests": len(reqs),
        "via_trips": sum(1 for t in reqs if t.via_zone),
        "medical_trips": sum(1 for t in reqs if t.medical_priority),
        "wheelchair_trips": sum(1 for t in reqs if t.wheelchair_requirement.value != "NONE"),
        "problem_id": problem.problem_id,
        "claim_level": problem.claim_level,
        "data_provenance": str(problem.data_provenance),
    }


def _row(name: str, mode: str, problem, fn) -> dict:
    stats = _instance_stats(problem)
    t0 = time.perf_counter()
    res = fn()
    dt = time.perf_counter() - t0
    n = max(1, len(problem.requests))
    out = {
        "algorithm": name,
        "mode": mode,
        **stats,
        "served": len(res.served_requests),
        "rejected": len(res.rejected_requests),
        "service_rate": round(len(res.served_requests) / n, 4),
        "status": res.status,
        "verified_feasible": res.verified_feasible,
        "runtime_s": round(dt, 4),
        "insertion_backend": res.solver_config.get("insertion_backend"),
        "solution_type": res.solution_type,
        "plan_id": res.plan_id,
        "mobiroute_version": res.mobiroute_version,
    }
    print(
        f"{name:18} {mode:16} {out['requests']:4} req  "
        f"{out['served']:4} served  {dt:8.3f}s  "
        f"backend={out['insertion_backend']}  {out['status']}",
        flush=True,
    )
    return out


def _run_native_suite(modes: set[str]) -> list[dict]:
    rows: list[dict] = []
    print("accel", acceleration_status(), flush=True)
    if "tiny" in modes:
        tiny = generate_day("tiny", 42)
        rows.append(_row("GREEDY", "tiny", tiny, lambda: solve_greedy(tiny)))
        rows.append(_row("FIFO", "tiny", tiny, lambda: solve_fifo(tiny)))
        rows.append(_row("NEAREST", "tiny", tiny, lambda: solve_nearest(tiny)))
        rows.append(_row("BEAM", "tiny", tiny, lambda: solve_beam(tiny, beam_width=3)))
        rows.append(_row("CPSAT", "tiny", tiny, lambda: solve_cpsat(tiny, time_limit_s=5.0)))
        rows.append(_row("ALNS", "tiny", tiny, lambda: solve_alns(tiny, iterations=12)))
    if "ops_clinic_peak" in modes:
        clinic = generate_day("ops_clinic_peak", 42)
        rows.append(_row("GREEDY", "ops_clinic_peak", clinic, lambda: solve_greedy(clinic)))
    if "small" in modes:
        small = generate_day("small", 42)
        rows.append(_row("GREEDY", "small", small, lambda: solve_greedy(small)))
    if "medium" in modes:
        medium = generate_day("medium", 42)
        rows.append(_row("GREEDY", "medium", medium, lambda: solve_greedy(medium)))
    return rows


def _run_python_suite(modes: set[str]) -> list[dict]:
    if os.getenv("MOBIROUTE_DISABLE_NATIVE") != "1":
        raise RuntimeError("python suite must run with MOBIROUTE_DISABLE_NATIVE=1")
    rows: list[dict] = []
    print("accel", acceleration_status(), flush=True)
    if "tiny" in modes:
        tiny = generate_day("tiny", 42)
        rows.append(_row("GREEDY_PYTHON", "tiny", tiny, lambda: solve_greedy(tiny)))
    if "small" in modes:
        small = generate_day("small", 42)
        rows.append(_row("GREEDY_PYTHON", "small", small, lambda: solve_greedy(small)))
        profiler = cProfile.Profile()
        profiler.enable()
        solve_greedy(small)
        profiler.disable()
        buf = StringIO()
        stats = pstats.Stats(profiler, stream=buf).sort_stats("tottime")
        stats.print_stats(25)
        (OUT_DIR / "cprofile_small_python.txt").write_text(buf.getvalue(), encoding="utf-8")
        print("wrote", OUT_DIR / "cprofile_small_python.txt", flush=True)
    if "medium" in modes:
        medium = generate_day("medium", 42)
        rows.append(_row("GREEDY_PYTHON", "medium", medium, lambda: solve_greedy(medium)))
    return rows


def _spawn_python(modes: set[str]) -> list[dict]:
    env = os.environ.copy()
    env["MOBIROUTE_DISABLE_NATIVE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--backend",
        "python",
        "--modes",
        ",".join(sorted(modes)),
        "--write-partial",
    ]
    print("spawn python-only", cmd, flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=True, capture_output=False)
    if proc.returncode != 0:
        raise RuntimeError("python-only subprocess failed")
    partial = OUT_DIR / "day_speed_python.json"
    payload = json.loads(partial.read_text(encoding="utf-8"))
    return list(payload["rows"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["native", "python", "all"], default="native")
    p.add_argument(
        "--modes",
        default="tiny,ops_clinic_peak,small,medium",
        help="comma-separated generator modes",
    )
    p.add_argument("--write-partial", action="store_true")
    args = p.parse_args()
    modes = {m.strip() for m in args.modes.split(",") if m.strip()}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.backend == "python":
        rows = _run_python_suite(modes)
        payload = {"host": _host(), "accel": acceleration_status(), "rows": rows}
        (OUT_DIR / "day_speed_python.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return

    rows: list[dict] = []
    if args.backend in {"native", "all"}:
        rows.extend(_run_native_suite(modes))
    if args.backend == "all":
        py_modes = modes & {"tiny", "small", "medium"}
        rows.extend(_spawn_python(py_modes))

    payload = {
        "claim_level": "synthetic_benchmark",
        "note": (
            "Synthetic Moscow-zone day (generator medium = 60 vehicles / 1000 requests). "
            "Not real MAST trips. Greedy/ALNS/beam never OPTIMAL."
        ),
        "host": _host(),
        "accel_native": acceleration_status(),
        "rows": rows,
    }
    out = OUT_DIR / "day_speed.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
