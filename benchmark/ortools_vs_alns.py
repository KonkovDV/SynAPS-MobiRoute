"""OR-Tools Routing against the ALNS engine: same instances, same time, same verifier.

OR-Tools runs the industrial default for pickup and delivery
(PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH); ALNS runs with the
same wall-clock limit. Both plans are re-checked by
:func:`mobiroute.vrp.verify.verify`, which also re-prices them, so a plan
is compared on what it really costs, not on what its solver reports.

Usage:
  python benchmark/ortools_vs_alns.py --time-limit 10
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, plant_day
from mobiroute.vrp.io import load_benchmark
from mobiroute.vrp.model import Instance
from mobiroute.vrp.ortools_baseline import solve_ortools

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("solomon", "C101"),
    ("solomon", "R101"),
    ("solomon", "RC101"),
    ("solomon", "C201"),
    ("solomon", "R201"),
    ("solomon", "RC201"),
    ("lilim", "LC101"),
    ("sartori-buriol/n100", "bar-n100-1"),
    ("sartori-buriol/n100", "ber-n100-1"),
    ("sartori-buriol/n100", "nyc-n100-1"),
    ("sartori-buriol/n100", "poa-n100-1"),
    ("cordeau", "a2-16"),
    ("cordeau", "a4-24"),
    ("cordeau", "b4-32"),
    ("cordeau", "a6-48"),
]


def _references() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in ("solomon", "lilim", "sartori-buriol-n100", "cordeau"):
        out.update(
            json.loads((ROOT / "benchmark" / "references" / f"{name}.json").read_text())[
                "instances"
            ]
        )
    return out


def _row(
    inst: Instance, solver: str, verdict: Any, seconds: float, ref: dict[str, Any] | None
) -> dict[str, Any]:
    cost = verdict.cost
    money = cost.total
    row = {
        "instance": inst.name,
        "solver": solver,
        "orders": inst.n_requests,
        "served": len(verdict.served),
        "verified": verdict.feasible,
        "vehicles": cost.vehicles,
        "distance": round(cost.distance, 2),
        "cost": round(money, 2),
        "seconds": round(seconds, 2),
        "gap_pct": None,
    }
    if (
        ref is not None
        and verdict.feasible
        and verdict.complete
        and len(verdict.served) == inst.n_requests
    ):
        same_fleet = ref.get("vehicles") in (None, cost.vehicles)
        if same_fleet:
            gap = 100 * (cost.distance - ref["cost"]) / ref["cost"]
            row["gap_pct"] = 0.0 if abs(cost.distance - ref["cost"]) <= 0.005 else round(gap, 2)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--out", type=Path, default=ROOT / "benchmark" / "results" / "ortools_vs_alns.json"
    )
    ap.add_argument(
        "--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "ortools-vs-alns.md"
    )
    args = ap.parse_args()
    refs = _references()
    instances: list[tuple[Instance, dict[str, Any] | None]] = []
    for family, name in CASES:
        inst, _ = load_benchmark(ROOT / "benchmark" / "instances" / family / f"{name}.txt")
        instances.append((inst, refs.get(name)))
    for inst in (cargo_day(7, n_orders=60), cargo_day(11, n_orders=120), plant_day(5)):
        instances.append((inst, None))
    rows: list[dict[str, Any]] = []
    for inst, ref in instances:
        o = solve_ortools(inst, time_limit=args.time_limit)
        rows.append(_row(inst, "OR-Tools PCI+GLS", o.verdict, o.seconds, ref))
        a = solve(inst, AlnsConfig(iterations=10**9, time_limit=args.time_limit, seed=args.seed))
        rows.append(_row(inst, "ALNS (this repo)", a.verdict, a.seconds, ref))
        print(rows[-2])
        print(rows[-1])
    meta = {
        "time_limit_s": args.time_limit,
        "seed": args.seed,
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2) + "\n")
    lines = [
        "# OR-Tools Routing vs ALNS at equal time",
        "",
        f"Both solvers get {args.time_limit:g} s of wall clock per instance on one core "
        f"({meta['platform']}, Python {meta['python']}). OR-Tools: PARALLEL_CHEAPEST_INSERTION + "
        "GUIDED_LOCAL_SEARCH, integer time grid of 0.01 min rounded up, every order in a "
        "disjunction so a plan always comes back. ALNS: seed "
        f"{args.seed}. Both plans are re-timed and re-priced by the independent verifier.",
        "",
        "| Instance | Orders | Solver | Served | Vehicles | Distance | Cost | Gap to ref. | Verified |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        gap = "—" if r["gap_pct"] is None else f"{r['gap_pct']:.2f}%"
        lines.append(
            f"| {r['instance']} | {r['orders']} | {r['solver']} | {r['served']} | {r['vehicles']} "
            f"| {r['distance']:.2f} | {r['cost']:.2f} | {gap} | {'yes' if r['verified'] else 'NO'} |"
        )
    lines += [
        "",
        "Gap to reference is shown only for verified plans that serve every order, at the",
        "reference vehicle count where the reference ranks vehicles first. Cargo and plant",
        "days are synthetic and have no published reference; compare their cost columns.",
        "",
    ]
    args.markdown.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
