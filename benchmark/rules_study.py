"""Operating rules on synthetic days: driver rests and multi-trip vehicles.

1. Rests. City freight days (120 orders, eight vehicle classes) are solved
   twice: without the 4.5 h / 45 min rule, then with it. The first plan is
   checked by the verifier *under* the rule, which tells how many of its
   routes no rest can be fitted into; the second shows what compliance costs.
2. Trips. Store deliveries from one DC in a morning and an afternoon wave,
   with the rest rule on: own vehicles allowed one, two or three trips.
3. Rush hours. The freight days with speeds that drop to 55% in the
   morning and 60% in the evening peak: a plan made on free-flow times is
   checked under traffic, then a plan is made with it.

Every plan is re-checked by the verifier. Synthetic days: they exercise the
method and describe no operator.

Usage:
  python benchmark/rules_study.py [--seeds 5] [--iterations 3000]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, dc_day
from mobiroute.vrp.model import BreakRule, Instance
from mobiroute.vrp.traffic import lateness, with_traffic
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]


def with_rests(inst: Instance) -> Instance:
    types = tuple(replace(vt, breaks=BreakRule()) for vt in inst.vehicle_types)
    return replace(inst, vehicle_types=types, name=inst.name + "-rests")


def rest_rows(seeds: int, iterations: int) -> list[dict[str, Any]]:
    rows = []
    for seed in range(1, seeds + 1):
        plain_inst = cargo_day(seed, n_orders=120)
        ruled_inst = with_rests(plain_inst)
        plain = solve(plain_inst, AlnsConfig(iterations=iterations, seed=1))
        ruled = solve(ruled_inst, AlnsConfig(iterations=iterations, seed=1))
        audit = verify(ruled_inst, plain.solution)
        long_routes = sum(1 for r in plain.verdict.routes if r.driving > 270.0)
        broken = [v for v in audit.violations if v.startswith("SCHEDULE")]
        short = [float(v.split("short_by=")[1].split(":")[0]) for v in broken]
        rows.append(
            {
                "day": plain_inst.name,
                "plain_cost": round(plain.verdict.cost.total, 2),
                "plain_vehicles": plain.verdict.cost.vehicles,
                "routes_over_4_5h": long_routes,
                "routes_breaking_rule": len(broken),
                "minutes_short": round(sum(short), 1),
                "ruled_cost": round(ruled.verdict.cost.total, 2),
                "ruled_vehicles": ruled.verdict.cost.vehicles,
                "rests_taken": sum(1 for r in ruled.verdict.routes if r.rest_after is not None),
                "ruled_verified": ruled.verdict.feasible and not ruled.verdict.unassigned,
                "cost_of_compliance_pct": round(
                    100 * (ruled.verdict.cost.total / plain.verdict.cost.total - 1), 2
                ),
            }
        )
        print(rows[-1], flush=True)
    return rows


def trip_rows(seeds: int, iterations: int) -> list[dict[str, Any]]:
    rows = []
    for seed in range(1, seeds + 1):
        for trips in (1, 2, 3):
            inst = dc_day(seed, trips=trips)
            res = solve(inst, AlnsConfig(iterations=iterations, seed=1))
            v = res.verdict
            hired = sum(n for k, n in v.cost.vehicles_by_type.items() if k.endswith("-hired"))
            rows.append(
                {
                    "day": f"dc-day-{seed}",
                    "trips": trips,
                    "served": len(v.served),
                    "orders": inst.n_requests,
                    "vehicles": v.cost.vehicles,
                    "hired": hired,
                    "reloads": sum(r.trips - 1 for r in v.routes),
                    "cost": round(v.cost.total, 2),
                    "verified": v.feasible,
                }
            )
            print(rows[-1], flush=True)
    return rows


def traffic_rows(seeds: int, iterations: int) -> list[dict[str, Any]]:
    rows = []
    for seed in range(1, seeds + 1):
        free_inst = cargo_day(seed, n_orders=120)
        jam = with_traffic(free_inst)
        free = solve(free_inst, AlnsConfig(iterations=iterations, seed=1))
        audit = verify(jam, free.solution)
        late = [lateness(jam, r.vehicle_type, r.nodes) for r in free.solution.routes if r.nodes]
        aware = solve(jam, AlnsConfig(iterations=iterations, seed=1))
        rows.append(
            {
                "day": free_inst.name,
                "free_flow_cost": round(free.verdict.cost.total, 2),
                "routes_failing": sum(1 for v in audit.violations if v.startswith("SCHEDULE")),
                "stops_late": sum(1 for lst in late for x in lst[1:-1] if x > 1e-6),
                "minutes_late": round(sum(sum(lst[1:-1]) for lst in late), 1),
                "aware_cost": round(aware.verdict.cost.total, 2),
                "aware_vehicles": aware.verdict.cost.vehicles,
                "free_flow_vehicles": free.verdict.cost.vehicles,
                "aware_verified": aware.verdict.feasible and not aware.verdict.unassigned,
                "cost_of_traffic_pct": round(
                    100 * (aware.verdict.cost.total / free.verdict.cost.total - 1), 2
                ),
            }
        )
        print(rows[-1], flush=True)
    return rows


def render(
    rest: list[dict[str, Any]],
    trips: list[dict[str, Any]],
    jams: list[dict[str, Any]],
    iterations: int,
) -> str:
    lines = [
        "# Operating rules: driver rests and multi-trip vehicles",
        "",
        f"ALNS, {iterations} iterations, seed 1, Rust kernel; every plan re-checked by the "
        "verifier. Synthetic days.",
        "",
        "## Rests: 4.5 h of driving, then 45 minutes",
        "",
        "City freight days, 120 orders, eight vehicle classes, 10-hour shifts. *Plain*: "
        "the plan made without the rule, then checked under it. *With rule*: the plan made "
        "with it.",
        "",
        "| Day | Plain cost | Routes > 4.5 h driving | Routes with no room for a rest | "
        "Minutes short | With rule: cost | Rests taken | Cost of compliance | Verified |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rest:
        lines.append(
            f"| {r['day']} | {r['plain_cost']:.0f} | {r['routes_over_4_5h']} | "
            f"{r['routes_breaking_rule']} | {r['minutes_short']:.1f} | {r['ruled_cost']:.0f} | "
            f"{r['rests_taken']} | {r['cost_of_compliance_pct']:+.2f}% | "
            f"{'yes' if r['ruled_verified'] else 'NO'} |"
        )
    lines += [
        "",
        "A route that drives more than 4.5 hours is not wrong by itself: the driver can rest "
        "while waiting for a window. The verifier looks for such a place in every gap between "
        "two services; *no room* means none exists, and the certificate names the conflict.",
        "",
        "## Trips: reload at the DC between waves",
        "",
        "60 stores, half with a 07:00-10:00 slot and half with 13:00-16:00, 1-4 pallets each; "
        "own fleet 6 vans and 3 trucks, up to 8 hired vans and 4 hired trucks; reload 30 min; "
        "rest rule on.",
        "",
        "| Day | Trips allowed | Served | Vehicles | Hired | Reloads | Cost | Verified |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in trips:
        lines.append(
            f"| {r['day']} | {r['trips']} | {r['served']}/{r['orders']} | {r['vehicles']} | "
            f"{r['hired']} | {r['reloads']} | {r['cost']:.0f} | "
            f"{'yes' if r['verified'] else 'NO'} |"
        )
    lines += [
        "",
        "With one trip per vehicle the day cannot be covered even with every hired vehicle; "
        "a second trip per own vehicle covers it. Cost is money only (fees and running cost), "
        "so a plan that leaves stores out looks cheaper than it is.",
        "",
        "## Rush hours: speeds by time of day",
        "",
        "The freight days with 55% of free-flow speed 07:30-10:00 and 60% 17:00-19:30 "
        "(Ichoua-Gendreau-Potvin model, FIFO). *Free-flow plan*: made on static times, then "
        "driven in traffic as early as possible. *Aware*: made with the speed profile.",
        "",
        "| Day | Free-flow cost | Routes failing in traffic | Stops late | Minutes late | "
        "Aware: cost | Vehicles (free-flow / aware) | Cost of traffic | Verified |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in jams:
        lines.append(
            f"| {r['day']} | {r['free_flow_cost']:.0f} | {r['routes_failing']} | "
            f"{r['stops_late']} | {r['minutes_late']:.1f} | {r['aware_cost']:.0f} | "
            f"{r['free_flow_vehicles']} / {r['aware_vehicles']} | "
            f"{r['cost_of_traffic_pct']:+.2f}% | {'yes' if r['aware_verified'] else 'NO'} |"
        )
    lines += [
        "",
        "Time costs are charged on free-flow minutes in both plans, so the cost column shows "
        "what the routing change costs, not the extra hours spent in traffic. The time-aware "
        "search runs on the Python reference (the Rust kernel covers static travel times).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--iterations", type=int, default=3000)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "rules.json")
    ap.add_argument("--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "rules.md")
    args = ap.parse_args()
    rest = rest_rows(args.seeds, args.iterations)
    trips = trip_rows(args.seeds, args.iterations)
    jams = traffic_rows(args.seeds, args.iterations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"rests": rest, "trips": trips, "traffic": jams}, indent=2) + "\n"
    )
    args.markdown.write_text(render(rest, trips, jams, args.iterations))


if __name__ == "__main__":
    main()
