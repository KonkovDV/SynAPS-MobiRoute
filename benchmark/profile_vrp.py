"""Where does an ALNS run spend its time? A profile one command reproduces.

Every optimisation in ``docs/native-acceleration.md`` started from a table
like the one this script prints: ``cProfile`` over one ALNS run, functions
ranked by own time (the time spent in the function itself, not in what it
calls). The same run is profiled on the Python reference and on the Rust
kernel, so the table shows both what the kernel took over and what is left
in Python, which is the next candidate.

A profiler slows Python code several times over and native code hardly at
all, so the shares inside one backend are meaningful and the two totals are
not a speed comparison; ``benchmark/measure_vrp_speed.py`` measures speed.

Usage:
  python benchmark/profile_vrp.py [--instance solomon/R101.txt] [--iterations 300] [--top 12]
"""

from __future__ import annotations

import argparse
import cProfile
import platform
import pstats
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.io import load_benchmark
from mobiroute.vrp.model import Instance
from mobiroute.vrp.native import available as native_available

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "benchmark" / "instances"
CASES = ("solomon/R101.txt", "sartori-buriol/n100/bar-n100-1.txt", "cordeau/a3-24.txt")


def _label(func: tuple[str, int, str]) -> str:
    filename, line, name = func
    if filename == "~":  # a built-in or an extension function
        return name.strip("<>").replace("built-in method ", "").replace("method ", "")
    path = Path(filename)
    where = path.name if "mobiroute" not in path.parts else "/".join(path.parts[-2:])
    return f"{where}:{line} {name}"


def profile(inst: Instance, backend: str, iterations: int, top: int) -> dict[str, Any]:
    """Own-time ranking of one ALNS run on ``backend`` (``python`` or ``native``)."""
    config = AlnsConfig(iterations=iterations, seed=1, backend=backend)  # type: ignore[arg-type]
    profiler = cProfile.Profile()
    profiler.enable()
    result = solve(inst, config)
    profiler.disable()
    stats = pstats.Stats(profiler)
    raw: dict[tuple[str, int, str], tuple[int, int, float, float, Any]] = stats.stats  # type: ignore[attr-defined]
    total = sum(row[2] for row in raw.values())
    ranked = sorted(raw.items(), key=lambda item: -item[1][2])[:top]
    return {
        "backend": result.backend,
        "iterations": result.iterations,
        "total_s": round(total, 3),
        "rows": [
            {
                "function": _label(func),
                "calls": row[1],
                "own_s": round(row[2], 3),
                "share_pct": round(100.0 * row[2] / total, 1) if total else 0.0,
            }
            for func, row in ranked
        ],
    }


def render(reports: list[tuple[str, int, list[dict[str, Any]]]], top: int) -> str:
    lines = [
        "# Where an ALNS run spends its time",
        "",
        f"`cProfile` over one run per instance and backend ({platform.system()} "
        f"{platform.machine()}, Python {platform.python_version()}), functions ranked by own "
        f"time, top {top}. Shares are of the profiled run; a profiler slows Python several "
        "times over and native code hardly at all, so compare shares inside a table, not "
        "totals between tables (speed: [vrp-speed.md](vrp-speed.md)). Produced by "
        "`python benchmark/profile_vrp.py`.",
        "",
    ]
    for name, requests, runs in reports:
        lines += [f"## {name} ({requests} orders)", ""]
        for run in runs:
            lines += [
                f"**{run['backend']}**, {run['iterations']} iterations, "
                f"{run['total_s']:.2f} s under the profiler",
                "",
                "| Function | Calls | Own time, s | Share |",
                "| --- | ---: | ---: | ---: |",
            ]
            for row in run["rows"]:
                lines.append(
                    f"| `{row['function']}` | {row['calls']} | {row['own_s']:.3f} "
                    f"| {row['share_pct']:.1f}% |"
                )
            lines.append("")
    lines += [
        "Reading: on the Python reference the insertion scan and the route-state rebuilds "
        "dominate, which is what moved to Rust. On the Rust kernel one call "
        "(`VrpKernel.repair`) holds the whole regret repair, and the rest of the table is what "
        "still runs in Python: destroy operators, cost bookkeeping, local search, the merge "
        "and vehicle-type operators. The largest of those is the next candidate for the "
        "kernel.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--instance", action="append", help="path under benchmark/instances")
    ap.add_argument("--iterations", type=int, default=300)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument(
        "--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "vrp-profile.md"
    )
    args = ap.parse_args()
    backends = ["python", "native"] if native_available() else ["python"]
    reports = []
    for rel in args.instance or CASES:
        inst, _digest = load_benchmark(INST / rel)
        runs = [profile(inst, backend, args.iterations, args.top) for backend in backends]
        reports.append((inst.name, inst.n_requests, runs))
        for run in runs:
            head = run["rows"][0]
            print(
                f"{inst.name} {run['backend']}: {run['total_s']:.2f} s, top: "
                f"{head['function']} {head['share_pct']:.1f}%"
            )
    args.markdown.write_text(render(reports, args.top))


if __name__ == "__main__":
    main()
