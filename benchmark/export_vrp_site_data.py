"""Write the data behind the site's fleet, dispatch and benchmark sections.

* ``site/data/fleet-mix.json`` - one synthetic freight day solved at several
  sizes (the first n orders of the same day), with routes by vehicle class;
* ``site/data/dispatch.json`` - a plant day replayed through the live
  dispatcher: every decision and every vehicle's executed plan;
* ``site/data/benchmarks.json`` and ``site/data/comparisons.json`` - copied
  from the result files of the benchmark scripts.

Usage (after the benchmark scripts):
  python benchmark/export_vrp_site_data.py
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, plant_day
from mobiroute.vrp.model import Instance
from mobiroute.vrp.realtime import simulate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
RESULTS = ROOT / "benchmark" / "results"


def _subset(inst: Instance, n: int) -> Instance:
    return replace(inst, name=f"{inst.name}-first-{n}", requests=inst.requests[:n])


def fleet_mix() -> dict[str, Any]:
    day = cargo_day(7, n_orders=160)
    sizes = [40, 70, 100, 130, 160]
    types = [
        {
            "id": vt.id,
            "cls": vt.id.replace("-hired", ""),
            "hired": vt.hired,
            "capacity": list(vt.capacity),
            "units": vt.count,
            "fixed": vt.fixed_cost,
            "perKm": round(vt.cost_per_distance, 2),
            "depot": vt.start_depot,
        }
        for vt in day.vehicle_types
    ]
    nodes = [{"x": round(nd.x, 2), "y": round(nd.y, 2), "name": nd.name} for nd in day.nodes]
    days = []
    for n in sizes:
        inst = _subset(day, n)
        res = solve(inst, AlnsConfig(iterations=6000, seed=1))
        v = res.verdict
        days.append(
            {
                "orders": n,
                "served": len(v.served),
                "feasible": v.feasible,
                "vehicles": v.cost.vehicles,
                "byType": v.cost.vehicles_by_type,
                "distance": round(v.cost.distance, 1),
                "cost": round(v.cost.total),
                "fixed": round(v.cost.fixed),
                "seconds": res.seconds,
                "routes": [
                    {"type": r.vehicle_type, "nodes": list(r.nodes)}
                    for r in res.solution.routes
                    if r.nodes
                ],
                "transfers": [
                    [q.pickup, q.delivery] for q in inst.requests if q.pickup is not None
                ],
            }
        )
        print(f"fleet {n}: {v.summary()} by type {v.cost.vehicles_by_type}")
    return {
        "name": day.name,
        "dims": list(day.dimensions),
        "depots": [0, 1],
        "nodes": nodes,
        "types": types,
        "days": days,
    }


def dispatch() -> dict[str, Any]:
    inst = plant_day(5)
    rep = simulate(inst, "insertion+alns", reoptimize_every=30.0, alns_iterations=300)
    types = [{"id": vt.id, "profile": vt.profile} for vt in inst.vehicle_types]
    plans = []
    for t, nodes, starts in rep.plans:
        vt = inst.vehicle_types[t]
        time = inst.profiles[vt.profile].time
        legs = []
        prev = vt.start_depot
        for node in nodes:
            legs.append(round(time[prev][node], 2))
            prev = node
        legs.append(round(time[prev][vt.end_depot], 2))
        plans.append(
            {
                "type": t,
                "nodes": list(nodes),
                "starts": list(starts),
                "service": [inst.nodes[n].service for n in nodes],
                "legs": legs,
            }
        )
    return {
        "name": inst.name,
        "kpi": rep.kpi,
        "verified": rep.verified,
        "types": types,
        "depot": 0,
        "nodes": [{"x": round(nd.x, 3), "y": round(nd.y, 3), "name": nd.name} for nd in inst.nodes],
        "requests": [
            {
                "id": r.id,
                "p": r.pickup,
                "d": r.delivery,
                "release": r.release,
                "pallets": r.demand[0],
            }
            for r in inst.requests
        ],
        "decisions": [
            {
                "id": d.request,
                "t": d.released,
                "ok": d.accepted,
                "veh": d.vehicle,
                "pick": d.pickup_start,
                "ms": d.latency_ms,
                "why": d.reason,
            }
            for d in rep.decisions
        ],
        "plans": plans,
    }


def _read(name: str) -> Any:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "fleet-mix.json").write_text(json.dumps(fleet_mix(), separators=(",", ":")) + "\n")
    (DATA / "dispatch.json").write_text(json.dumps(dispatch(), separators=(",", ":")) + "\n")
    bench = _read("vrp/vrp_benchmark.json")
    if bench is not None:
        keep = (
            "family",
            "instance",
            "requests",
            "vehicles",
            "ref_vehicles",
            "cost",
            "ref_cost",
            "gap_pct",
            "vehicle_delta",
            "seconds",
            "feasible",
            "complete",
        )
        slim = {
            "meta": bench["meta"],
            "summary": bench["summary"],
            "rows": [{k: r[k] for k in keep} for r in bench["rows"]],
        }
        (DATA / "benchmarks.json").write_text(json.dumps(slim, separators=(",", ":")) + "\n")
    comparisons = {
        "ortools": _read("ortools_vs_alns.json"),
        "exact": _read("exact_vs_alns.json"),
        "speed": _read("vrp_speed.json"),
        "realtime": _read("realtime_dispatch.json"),
    }
    if comparisons["exact"] is not None:
        comparisons["exact"] = {"summary": comparisons["exact"]["summary"]}
    (DATA / "comparisons.json").write_text(json.dumps(comparisons, separators=(",", ":")) + "\n")
    print("site data written")


if __name__ == "__main__":
    main()
