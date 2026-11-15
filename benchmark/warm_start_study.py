"""Where ALNS stops short of the optimum, and what a warm start of CP-SAT adds.

The exact-vs-ALNS study (8 orders) finds ALNS equal to the proven optimum on
every instance. This one takes the same generator to 14 orders, where some
orders cannot all be served and the plan has to choose: ALNS (2000
iterations) against CP-SAT started cold and CP-SAT started from the ALNS
plan (``solve_exact(..., hint=...)``). Both CP-SAT runs are deterministic
(:data:`mobiroute.vrp.exact.DETERMINISTIC_FRACTION` of the time limit as
deterministic time, eight workers in one interleaved search), so every row
repeats on any machine. Every plan is priced by the verifier.

Usage:
  python benchmark/warm_start_study.py [--instances 20] [--time-limit 20]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, search_objective, solve
from mobiroute.vrp.exact import ExactRun, solve_exact
from mobiroute.vrp.generators import random_instance

ROOT = Path(__file__).resolve().parents[1]


def _objective(run: ExactRun, inst: Any) -> float | None:
    if run.status not in ("OPTIMAL", "FEASIBLE") or not run.verdict.feasible:
        return None
    return round(search_objective(inst, run.solution), 2)


def rows(instances: int, requests: int, iterations: int, time_limit: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for k in range(instances):
        seed = 2000 + k
        inst = random_instance(
            seed, n_requests=requests, n_types=2 + k % 2, ride_share=0.4, penalty=1000.0
        )
        heur = solve(inst, AlnsConfig(iterations=iterations, seed=1))
        cold = solve_exact(inst, time_limit=time_limit, workers=8, deterministic=True)
        warm = solve_exact(
            inst, time_limit=time_limit, workers=8, deterministic=True, hint=heur.solution
        )
        row = {
            "seed": seed,
            "vehicle_types": len(inst.vehicle_types),
            "alns": round(search_objective(inst, heur.solution), 2),
            "alns_left_out": len(heur.solution.unassigned),
            "alns_verified": heur.verdict.feasible,
            "cold_status": cold.status,
            "cold": _objective(cold, inst),
            "cold_seconds": cold.seconds,
            "warm_status": warm.status,
            "warm": _objective(warm, inst),
            "warm_left_out": len(warm.solution.unassigned),
            "warm_seconds": warm.seconds,
            "warm_bound": None if warm.model_bound is None else round(warm.model_bound, 2),
            "reproducible": cold.reproducible and warm.reproducible,
        }
        out.append(row)
        print(row, flush=True)
    return out


def summary(data: list[dict[str, Any]]) -> dict[str, Any]:
    def best(r: dict[str, Any]) -> float:
        return min(float(v) for v in (r["alns"], r["cold"], r["warm"]) if v is not None)

    def gap(value: float | None, r: dict[str, Any]) -> float | None:
        b = best(r)
        return None if value is None else 100.0 * (value - b) / b

    alns_gaps = [g for r in data if (g := gap(r["alns"], r)) is not None]
    return {
        "instances": len(data),
        "warm_optimal": sum(1 for r in data if r["warm_status"] == "OPTIMAL"),
        "cold_optimal": sum(1 for r in data if r["cold_status"] == "OPTIMAL"),
        "alns_at_best": sum(1 for g in alns_gaps if g <= 1e-6),
        "alns_mean_gap_pct": round(statistics.fmean(alns_gaps), 2),
        "alns_max_gap_pct": round(max(alns_gaps), 2),
        "warm_at_best": sum(1 for r in data if r["warm"] is not None and r["warm"] <= best(r)),
        "cold_at_best": sum(1 for r in data if r["cold"] is not None and r["cold"] <= best(r)),
        "warm_never_worse_than_alns": all(
            r["warm"] is not None and r["warm"] <= r["alns"] + 1e-6 for r in data
        ),
        "cold_worse_than_alns": sum(
            1 for r in data if r["cold"] is None or r["cold"] > r["alns"] + 1e-6
        ),
        "both_at_best": sum(
            1
            for r in data
            if min(v for v in (r["cold"], r["warm"], r["alns"]) if v is not None) <= best(r)
        ),
        "mean_warm_seconds": round(statistics.fmean(r["warm_seconds"] for r in data), 2),
        "mean_cold_seconds": round(statistics.fmean(r["cold_seconds"] for r in data), 2),
        "all_reproducible": all(r["reproducible"] for r in data),
        "all_verified": all(r["alns_verified"] for r in data),
    }


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render(data: list[dict[str, Any]], s: dict[str, Any], args: argparse.Namespace) -> str:
    lines = [
        "# Warm start: CP-SAT from the ALNS plan",
        "",
        f"{s['instances']} random instances of the full model with {args.requests} orders "
        "(the generator of the exact-vs-ALNS study), two or three vehicle types, ride "
        "limits on 40% of pairs, every order optional at a price of 1000. ALNS runs "
        f"{args.iterations} iterations (seed 1). CP-SAT runs twice with "
        f"`deterministic=True`, eight workers and a {args.time_limit:g} s limit "
        f"({args.time_limit / 2:g} s of deterministic time): cold, and with the ALNS "
        "plan as a hint. *Best* is the lowest verified objective of the three; "
        "objectives include the price of refused orders.",
        "",
        f"* CP-SAT proves the optimum: cold {s['cold_optimal']} / {s['instances']}, "
        f"warm {s['warm_optimal']} / {s['instances']}",
        f"* ALNS at the best value: {s['alns_at_best']} / {s['instances']}; mean gap "
        f"{s['alns_mean_gap_pct']}%, worst {s['alns_max_gap_pct']}%",
        f"* warm CP-SAT at the best value: {s['warm_at_best']} / {s['instances']}, "
        f"never worse than ALNS: {s['warm_never_worse_than_alns']}",
        f"* cold CP-SAT worse than ALNS (or no plan): {s['cold_worse_than_alns']} / "
        f"{s['instances']}",
        f"* both runs, cheaper verified plan kept (what `vrp-solve --solver exact` does): "
        f"at the best value {s['both_at_best']} / {s['instances']}",
        f"* mean time: cold {s['mean_cold_seconds']} s, warm {s['mean_warm_seconds']} s; "
        f"every run ended by the deterministic stop or a proof: {s['all_reproducible']}",
        "",
        "| Seed | Types | ALNS | Left out | Cold CP-SAT | Status | Warm CP-SAT | Status "
        "| Left out | Warm time |",
        "| ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |",
    ]
    for r in data:
        lines.append(
            f"| {r['seed']} | {r['vehicle_types']} | {_num(r['alns'])} | {r['alns_left_out']} "
            f"| {_num(r['cold'])} | {r['cold_status']} | {_num(r['warm'])} | "
            f"{r['warm_status']} | {r['warm_left_out']} | {r['warm_seconds']:.2f} s |"
        )

    def best(r: dict[str, Any]) -> float:
        return min(float(v) for v in (r["alns"], r["cold"], r["warm"]) if v is not None)

    short = [str(r["seed"]) for r in data if r["alns"] > best(r) + 1e-6]
    cold_better = [
        str(r["seed"])
        for r in data
        if r["cold"] is not None and r["warm"] is not None and r["cold"] < r["warm"] - 1e-6
    ]
    lines += [
        "",
        f"ALNS stops short of the best plan on seeds {', '.join(short) or 'none'}, by "
        f"{s['alns_max_gap_pct']}% at most. Until 0.7 it also stopped 16% short on seed "
        "2004: the better plan serves one more order, and getting there takes two "
        "changes at once, the new pair into a route and a stop already on it moved. "
        "One destroy-and-repair step makes one of them; the exact re-sequencing of "
        "short routes (`vrp.reseat`) makes both, and ALNS now ends at the value CP-SAT "
        "proves with a longer budget. The hint has a price too: started from the ALNS "
        "plan, CP-SAT can stay near it, and the cold run ends lower on seeds "
        f"{', '.join(cold_better) or 'none'}. `mobiroute vrp-solve --solver exact` "
        "therefore runs both, each on half of `--time-limit`, skips the cold run when "
        "the warm one proves the optimum, and keeps the cheapest verified plan, "
        "ALNS's included.",
        "",
        "Reproducibility costs proofs. With the batch size of the interleaved search "
        "left to OR-Tools 9.15, the 0.6.1 run of this study got 5 optimality proofs, "
        "but 2 of 8 identical runs of one instance returned another plan; with the "
        "batch size fixed (as `solve_exact` does) every run repeats, and "
        f"{s['cold_optimal']} cold and {s['warm_optimal']} warm proofs fit in the "
        "budget. A longer one proves more: with 60 s, seed 2004 is proven optimal "
        "(the slow test in `tests/test_vrp_engine.py`).",
        "",
        "Reproduce: `python benchmark/warm_start_study.py`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--instances", type=int, default=20)
    ap.add_argument("--requests", type=int, default=14)
    ap.add_argument("--iterations", type=int, default=2000)
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "warm_start.json")
    ap.add_argument("--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "warm-start.md")
    ap.add_argument("--render-only", action="store_true", help="re-render --out as Markdown")
    args = ap.parse_args()
    if args.render_only:
        data = json.loads(args.out.read_text())["rows"]
    else:
        data = rows(args.instances, args.requests, args.iterations, args.time_limit)
    s = summary(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": s, "rows": data}, indent=2) + "\n")
    args.markdown.write_text(render(data, s, args), encoding="utf-8")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
