"""How often does ALNS find the proven optimum? CP-SAT decides.

Random small instances of the full rich model (two or three vehicle types,
capacity vector, skills, two travel profiles, ride limits, shift caps,
optional orders with a price) are solved to proven optimality by the exact
CP-SAT model and heuristically by ALNS. Both plans are priced by the same
verifier.

Usage:
  python benchmark/exact_vs_alns.py --instances 40
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, search_objective, solve
from mobiroute.vrp.exact import solve_exact
from mobiroute.vrp.generators import random_instance

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--instances", type=int, default=40)
    ap.add_argument("--requests", type=int, default=8)
    ap.add_argument("--alns-iterations", type=int, default=2000)
    ap.add_argument("--exact-time-limit", type=float, default=120.0)
    ap.add_argument(
        "--out", type=Path, default=ROOT / "benchmark" / "results" / "exact_vs_alns.json"
    )
    ap.add_argument(
        "--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "exact-vs-alns.md"
    )
    args = ap.parse_args()
    rows: list[dict[str, Any]] = []
    for k in range(args.instances):
        seed = 1000 + k
        inst = random_instance(
            seed, n_requests=args.requests, n_types=2 + k % 2, ride_share=0.4, penalty=1000.0
        )
        ex = solve_exact(inst, time_limit=args.exact_time_limit, workers=8)
        al = solve(inst, AlnsConfig(iterations=args.alns_iterations, seed=1))
        eo = search_objective(inst, ex.solution)
        ao = search_objective(inst, al.solution)
        rows.append(
            {
                "seed": seed,
                "requests": inst.n_requests,
                "vehicle_types": len(inst.vehicle_types),
                "exact_status": ex.status,
                "exact_objective": round(eo, 4),
                "exact_seconds": ex.seconds,
                "exact_verified": ex.verdict.feasible,
                "alns_objective": round(ao, 4),
                "alns_seconds": al.seconds,
                "alns_verified": al.verdict.feasible,
                "gap_pct": round(100 * (ao - eo) / eo, 4) if eo else 0.0,
            }
        )
        print(rows[-1])
    proven = [r for r in rows if r["exact_status"] == "OPTIMAL"]
    matched = [r for r in proven if abs(r["gap_pct"]) <= 1e-6]
    better = [r for r in rows if r["gap_pct"] < -1e-6]
    summary = {
        "instances": len(rows),
        "proven_optimal": len(proven),
        "alns_matches_optimum": len(matched),
        "alns_better_than_exact": len(better),
        "mean_gap_pct_on_proven": round(statistics.fmean(r["gap_pct"] for r in proven), 4)
        if proven
        else None,
        "max_gap_pct_on_proven": round(max(r["gap_pct"] for r in proven), 4) if proven else None,
        "mean_exact_seconds": round(statistics.fmean(r["exact_seconds"] for r in rows), 2),
        "mean_alns_seconds": round(statistics.fmean(r["alns_seconds"] for r in rows), 2),
        "all_verified": all(r["exact_verified"] and r["alns_verified"] for r in rows),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n")
    lines = [
        "# ALNS against proven optima",
        "",
        f"{summary['instances']} random instances of the full model, {args.requests} orders each, "
        "two or three vehicle types, capacity vector, skills, ride limits on 40% of pairs, shift "
        "caps, optional orders priced at 1000. CP-SAT (8 workers, "
        f"{args.exact_time_limit:g} s limit) proves the optimum of its model, whose travel times "
        "are rounded up to 0.01 min; ALNS runs "
        f"{args.alns_iterations} iterations. Both plans are priced by the verifier.",
        "",
        f"* proven optimal by CP-SAT: **{summary['proven_optimal']} / {summary['instances']}**",
        f"* ALNS equal to the proven optimum: **{summary['alns_matches_optimum']} / {summary['proven_optimal']}**",
        f"* mean / max gap on proven instances: {summary['mean_gap_pct_on_proven']}% / {summary['max_gap_pct_on_proven']}%",
        f"* mean time: CP-SAT {summary['mean_exact_seconds']} s, ALNS {summary['mean_alns_seconds']} s",
        f"* every plan verified: {summary['all_verified']}",
        "",
        "| Seed | Types | CP-SAT status | Optimum | ALNS | Gap | CP-SAT time | ALNS time |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['seed']} | {r['vehicle_types']} | {r['exact_status']} | {r['exact_objective']:.2f} "
            f"| {r['alns_objective']:.2f} | {r['gap_pct']:.2f}% | {r['exact_seconds']:.2f} s | {r['alns_seconds']:.2f} s |"
        )
    lines.append("")
    args.markdown.write_text("\n".join(lines))
    print(summary)


if __name__ == "__main__":
    main()
