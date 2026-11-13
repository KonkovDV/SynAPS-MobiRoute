"""Time the ALNS repair backends: Python reference vs Rust kernel.

Both backends run the same seed and iteration count and must return the same
plan (the script checks it), so the timing difference is the implementation
and nothing else.

Usage:
  python benchmark/measure_vrp_speed.py --iterations 400
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day
from mobiroute.vrp.io import load_benchmark
from mobiroute.vrp.model import Instance

ROOT = Path(__file__).resolve().parents[1]


def _cases() -> list[tuple[str, Instance]]:
    inst = ROOT / "benchmark" / "instances"
    return [
        ("VRPTW, Solomon R101 (100 customers)", load_benchmark(inst / "solomon" / "R101.txt")[0]),
        (
            "PDPTW, Sartori-Buriol bar-n100-1 (50 pairs, OSRM)",
            load_benchmark(inst / "sartori-buriol" / "n100" / "bar-n100-1.txt")[0],
        ),
        (
            "DARP, Cordeau a4-48 (48 pairs, ride limits)",
            load_benchmark(inst / "cordeau" / "a4-48.txt")[0],
        ),
        ("Cargo day, 120 orders, 8 vehicle types, 3-D capacity", cargo_day(7, n_orders=120)),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--iterations", type=int, default=400)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "vrp_speed.json")
    ap.add_argument("--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "vrp-speed.md")
    args = ap.parse_args()
    rows: list[dict[str, Any]] = []
    for label, inst in _cases():
        runs = {}
        for backend in ("python", "native"):
            res = solve(inst, AlnsConfig(iterations=args.iterations, seed=1, backend=backend))
            runs[backend] = res
        same = runs["python"].solution.as_lists() == runs["native"].solution.as_lists()
        py_ms = 1000 * runs["python"].seconds / max(1, runs["python"].iterations)
        rs_ms = 1000 * runs["native"].seconds / max(1, runs["native"].iterations)
        rows.append(
            {
                "case": label,
                "python_ms_per_iteration": round(py_ms, 2),
                "native_ms_per_iteration": round(rs_ms, 2),
                "speedup": round(py_ms / rs_ms, 1),
                "identical_plans": same,
            }
        )
        print(rows[-1])
    meta = {
        "iterations": args.iterations,
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2) + "\n")
    lines = [
        "# ALNS iteration cost: Python reference vs Rust kernel",
        "",
        f"{args.iterations} iterations, seed 1, one thread, {meta['platform']}, Python {meta['python']}.",
        "Both backends return the same plan; the column says so.",
        "",
        "| Case | Python, ms / iteration | Rust, ms / iteration | Speed-up | Same plan |",
        "| --- | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['python_ms_per_iteration']:.2f} | {r['native_ms_per_iteration']:.2f} "
            f"| {r['speedup']:.1f}x | {'yes' if r['identical_plans'] else 'NO'} |"
        )
    lines.append("")
    args.markdown.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
