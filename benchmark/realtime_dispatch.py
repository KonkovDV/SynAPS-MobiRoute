"""Live dispatch policies on synthetic operating days.

* ``insertion`` - every order is answered at once by the cheapest feasible
  insertion into the part of a plan not yet driven;
* ``insertion+alns`` - the same, plus an ALNS pass over the live state every
  30 minutes of simulated time;
* ``ortools-resolve`` - the whole live state is re-solved by OR-Tools
  Routing for every new order (``--ortools-limit`` seconds, 3 by default),
  the pattern of re-optimising per passenger.

KPIs: acceptance, call-to-pickup time (vehicle arrival lead time), ride
time, distance, cost, decision latency. Every final plan is re-checked by the
verifier.

Usage:
  python benchmark/realtime_dispatch.py [--with-ortools] [--ortools-limit 3]
  python benchmark/realtime_dispatch.py --from-json benchmark/results/realtime_dispatch.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mobiroute.vrp.generators import plant_day, shuttle_day
from mobiroute.vrp.realtime import Policy, simulate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--with-ortools", action="store_true")
    ap.add_argument("--ortools-limit", type=float, default=3.0, help="seconds per re-solve")
    ap.add_argument("--ortools-days", default="plant-5-140", help="days for the re-solve policy")
    ap.add_argument(
        "--out", type=Path, default=ROOT / "benchmark" / "results" / "realtime_dispatch.json"
    )
    ap.add_argument(
        "--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "realtime-dispatch.md"
    )
    ap.add_argument(
        "--from-json", type=Path, default=None, help="re-render the table from a saved run"
    )
    args = ap.parse_args()
    if args.from_json is not None:
        saved = json.loads(args.from_json.read_text())
        rows: list[dict[str, Any]] = saved["rows"]
        limit = float(saved.get("ortools_limit", args.ortools_limit))
    else:
        rows = run(args)
        limit = args.ortools_limit
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"ortools_limit": limit, "rows": rows}, indent=2) + "\n")
    args.markdown.write_text(render(rows, limit))


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    days = [shuttle_day(11), plant_day(5), plant_day(9, n_moves=200)]
    ortools_days = {d.strip() for d in args.ortools_days.split(",") if d.strip()}
    rows: list[dict[str, Any]] = []
    for inst in days:
        policies: list[Policy] = ["insertion", "insertion+alns"]
        if args.with_ortools and inst.name in ortools_days:
            policies.append("ortools-resolve")
        for policy in policies:
            rep = simulate(
                inst,
                policy,
                reoptimize_every=30.0,
                alns_iterations=300,
                ortools_time_limit=args.ortools_limit,
            )
            rows.append({"day": inst.name, "policy": policy, "verified": rep.verified, **rep.kpi})
            print(rows[-1])
    return rows


def reading(rows: list[dict[str, Any]]) -> list[str]:
    """Plain-language comparison of the policies, computed from the rows."""
    by = {(r["day"], r["policy"]): r for r in rows}
    out: list[str] = []
    fast = [r for r in rows if r["policy"] != "ortools-resolve"]
    if fast:
        worst = max(r["decision_ms_max"] for r in fast)
        out.append(
            f"* Insertion answers every order in at most {worst:.2f} ms on every day, "
            "background passes excluded."
        )
    for day in dict.fromkeys(r["day"] for r in rows):
        ins, alns = by.get((day, "insertion")), by.get((day, "insertion+alns"))
        if ins and alns and alns["reoptimize_gain"] > 0:
            out.append(
                f"* {day}: ALNS passes every 30 min change acceptance by "
                f"{100 * (alns['acceptance_rate'] - ins['acceptance_rate']):+.1f} pp and cost by "
                f"{100 * (alns['cost'] / ins['cost'] - 1):+.1f}%; the passes take "
                f"{alns['reoptimize_seconds']:.1f} s over the whole day."
            )
        ort = by.get((day, "ortools-resolve"))
        if alns and ort:
            cost = 100 * (ort["cost"] / alns["cost"] - 1)
            wait = ort["response_mean_min"] - alns["response_mean_min"]
            out.append(
                f"* {day}: re-solving with OR-Tools for every order accepts "
                f"{100 * ort['acceptance_rate']:.1f}% against {100 * alns['acceptance_rate']:.1f}% "
                f"and is {abs(cost):.1f}% {'cheaper' if cost < 0 else 'dearer'}, but a decision "
                f"takes {ort['decision_ms_mean'] / 1000:.1f} s instead of "
                f"{alns['decision_ms_mean']:.2f} ms and vehicles reach the pickup "
                f"{abs(wait):.1f} min {'later' if wait > 0 else 'earlier'} on average"
                + (": the re-solve minimises cost, not waiting." if wait > 0 else ".")
            )
    return out


def render(rows: list[dict[str, Any]], limit: float) -> str:
    lines = [
        "# Live dispatch on synthetic days",
        "",
        "Orders become known at their release time and are answered immediately. Shuttle:",
        "160 calls, 10 eight-seat buses, pickup within 30 min of the call, arrival within 45.",
        "Plant: pallet moves between workshops, tow tractors, flatbeds with a crane and a",
        "covered van; pickup within 40 min of release, delivery within 90, 12-hour shifts.",
        "",
        "| Day | Policy | Accepted | Call to pickup, mean / p95 (min) | Ride, mean (min) | Distance | Cost | Vehicles | Decision, mean / max (ms) | Verified |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['day']} | {r['policy']} | {100 * r['acceptance_rate']:.1f}% "
            f"| {r['response_mean_min']:.1f} / {r['response_p95_min']:.1f} | {r['ride_mean_min']:.1f} "
            f"| {r['distance']:.1f} | {r['cost']:.0f} | {r['vehicles_used']:.0f} "
            f"| {r['decision_ms_mean']:.2f} / {r['decision_ms_max']:.2f} | {'yes' if r['verified'] else 'NO'} |"
        )
    lines += [
        "",
        "Decision latency for `insertion+alns` excludes the background passes; their total time",
        "is in the JSON (`reoptimize_seconds`). `ortools-resolve` re-solves the whole live state",
        f"with OR-Tools Routing for every order ({limit:g} s limit, no warm start) and",
        "accepts the order only if every earlier promise is kept. Synthetic days: they exercise",
        "the method, they describe no real operator.",
        "",
    ]
    notes = reading(rows)
    if notes:
        lines += ["## Reading the table", "", *notes, ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
