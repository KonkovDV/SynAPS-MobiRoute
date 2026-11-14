"""Write the data behind the site's fleet, dispatch and benchmark sections.

* ``site/data/fleet-mix.json`` - one synthetic freight day solved at several
  sizes (the first n orders of the same day), with routes by vehicle class;
* ``site/data/dispatch.json`` - a plant day replayed through the live
  dispatcher: every decision and every vehicle's executed plan;
* ``site/data/benchmarks.json`` and ``site/data/comparisons.json`` - copied
  from the result files of the benchmark scripts;
* ``site/data/route-sheets.json`` - the synthetic Naberezhnye Chelny day
  (``examples/chelny-day.geo.json``) solved as ``vrp-solve --geo`` does: the
  route sheets of every vehicle and, per route, the windows and travel times
  the page needs to replay the departure choice of Lemma 4;
* ``site/data/prices.json`` - the same plan priced by LP duality: what each
  order costs, the rent of every vehicle type, and the day re-solved with one
  more unit of each type that ran out, to hold the rent against a direct count.

A result file that is absent keeps its part of ``comparisons.json`` as
published: re-running one study does not blank the others on the page.

Usage (after the benchmark scripts):
  python benchmark/export_vrp_site_data.py
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

from mobiroute.vrp import geo
from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, plant_day
from mobiroute.vrp.geo import GeoInstance
from mobiroute.vrp.model import Instance
from mobiroute.vrp.prices import Prices, solve_with_prices
from mobiroute.vrp.realtime import simulate
from mobiroute.vrp.schedule import compact_schedule, route_timing
from mobiroute.vrp.sheets import CURRENCY_SIGNS, route_sheets

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


def _num(value: float) -> float | None:
    """Minutes rounded for the page; an open bound becomes ``null``."""
    return round(value, 2) if math.isfinite(value) else None


CHELNY = ROOT / "examples" / "chelny-day.geo.json"
CHELNY_CONFIG = AlnsConfig(iterations=5000, seed=7)


def prices_day(built: GeoInstance, routes: list[list[int]], prices: Prices) -> dict[str, Any]:
    """Order prices and vehicle rents of the Chelny plan, with the rents checked.

    The check is a direct count: the day is solved again with one more unit of
    each type that carries a rent, and the saving is put next to the rent.
    """
    inst = built.instance
    vehicle_of = {n: k for k, nodes in enumerate(routes) for n in nodes}
    orders = []
    for req, price in zip(inst.requests, prices.orders, strict=True):
        node = req.delivery if req.delivery is not None else req.pickup
        assert node is not None and price.price is not None
        place = built.places[node]
        orders.append(
            {
                "id": req.id,
                "label": place.label,
                "lat": place.lat,
                "lon": place.lon,
                "veh": vehicle_of[node],
                "price": round(price.price, 2),
                "saving": None if price.saving is None else round(price.saving, 2),
                "q": list(req.demand),
            }
        )
    data = json.loads(CHELNY.read_text(encoding="utf-8"))
    rents = []
    for (vid, rent), vt in zip(prices.vehicles, inst.vehicle_types, strict=True):
        row: dict[str, Any] = {"type": vid, "hired": vt.hired, "units": vt.count}
        row["rent"] = round(rent, 2)
        if rent > 1e-6:
            more = json.loads(json.dumps(data))
            for item in more["vehicle_types"]:
                if item["id"] == vid:
                    item["count"] = int(item.get("count", 1)) + 1
            again = solve(geo.build(more).instance, CHELNY_CONFIG)
            assert again.verdict.feasible and not again.verdict.unassigned
            row["resolved"] = round(prices.plan_value - again.objective, 2)
            print(f"rent {vid}: LP {rent:.0f}, one more unit saves {row['resolved']:.0f}")
        rents.append(row)
    depot = built.places[inst.vehicle_types[0].start_depot]
    assert prices.lp_value is not None and prices.gap is not None
    return {
        "name": inst.name,
        "currency": CURRENCY_SIGNS.get(built.currency, built.currency),
        "dimensions": list(inst.dimensions),
        "plan": round(prices.plan_value, 2),
        "lp": round(prices.lp_value, 2),
        "gap": round(prices.gap, 2),
        "columns": prices.columns,
        "rentsTotal": round(prices.rents, 2),
        "depot": {"lat": depot.lat, "lon": depot.lon, "label": depot.label},
        "rents": rents,
        "orders": orders,
    }


def sheets_day() -> tuple[dict[str, Any], dict[str, Any]]:
    """Route sheets of the Chelny example with the data behind Lemma 4, and its prices."""
    built = geo.load(str(CHELNY))
    inst = built.instance
    result, prices = solve_with_prices(inst, CHELNY_CONFIG)
    assert result.verdict.feasible and not result.verdict.unassigned
    sheets = route_sheets(inst, result.solution, result.verdict, built.places)
    used = [r for r in result.solution.routes if r.nodes]
    vehicles = []
    for sheet, route in zip(sheets, used, strict=True):
        vt = inst.vehicle_types[route.vehicle_type]
        time = inst.profiles[vt.profile].time
        seq = [vt.start_depot, *route.nodes, vt.end_depot]
        timing = route_timing(inst, route.vehicle_type, route.nodes)
        tight = compact_schedule(inst, route.vehicle_type, route.nodes)
        early = [inst.nodes[n].earliest for n in seq]
        late = [inst.nodes[n].latest for n in seq]
        early[0] = max(early[0], vt.shift_start)
        late[0] = min(late[0], vt.shift_end)
        late[-1] = min(late[-1], vt.shift_end)
        vehicles.append(
            {
                "id": sheet.vehicle,
                "type": sheet.vehicle_type,
                "hired": sheet.hired,
                "trips": sheet.trips,
                "capacity": list(vt.capacity),
                "distance": round(sheet.distance, 2),
                "driving": round(sheet.driving, 1),
                "waiting": round(sheet.waiting, 1),
                "cost": round(sheet.cost, 2),
                "rows": [
                    {
                        "k": row.kind,
                        "t": row.trip,
                        "o": row.order,
                        "p": row.place,
                        "lat": row.lat,
                        "lon": row.lon,
                        "w": None if row.window is None else [_num(v) for v in row.window],
                        "a": round(row.arrive, 2),
                        "s": round(row.start, 2),
                        "e": round(row.end, 2),
                        "q": list(row.load),
                    }
                    for row in sheet.rows
                ],
                # One forward pass per departure reproduces the verifier's
                # schedules on this route (no ride limits, no traffic here).
                "lemma": {
                    "lo": _num(early[0]),
                    "hi": _num(timing.latest[0]),
                    "E": round(timing.earliest[-1], 2),
                    "c": round(timing.min_duration, 2),
                    "best": round(tight.earliest[0], 2),
                    "e": [_num(v) for v in early],
                    "l": [_num(v) for v in late],
                    "svc": [inst.nodes[n].service for n in seq],
                    "tt": [round(time[a][b], 3) for a, b in pairwise(seq)],
                    "gap": -1 if timing.rest_gap is None else timing.rest_gap,
                    "rest": 0.0 if vt.breaks is None else vt.breaks.duration,
                    "cap": vt.max_duration,
                    "names": [built.places[n].label for n in seq],
                },
            }
        )
    suppliers = sorted(
        {(p.lat, p.lon, p.label) for p in built.places if p.role == "pickup"},
        key=lambda x: x[2],
    )
    depot = built.places[inst.vehicle_types[0].start_depot]
    day = {
        "name": inst.name,
        "currency": CURRENCY_SIGNS.get(built.currency, built.currency),
        "dimensions": list(inst.dimensions),
        "orders": inst.n_requests,
        "cost": round(result.verdict.cost.total, 2),
        "distance": round(result.verdict.cost.distance, 2),
        "depot": {"lat": depot.lat, "lon": depot.lon, "label": depot.label},
        "suppliers": [{"lat": a, "lon": b, "label": c} for a, b, c in suppliers],
        "vehicles": vehicles,
    }
    return day, prices_day(built, [list(r.nodes) for r in used], prices)


def solvers_summary() -> dict[str, Any] | None:
    """Per family and solver: verified runs, runs at the best-known fleet, mean gap."""
    study = _read("solvers_study.json")
    if study is None:
        return None
    rows = [r for r in study["rows"] if not r.get("error")]
    out: dict[str, Any] = {"families": []}
    for family in sorted({r["family"] for r in rows}):
        fam = [r for r in rows if r["family"] == family]
        solvers = []
        for name in dict.fromkeys(r["solver"] for r in fam):
            mine = [r for r in fam if r["solver"] == name]
            good = [r for r in mine if r["verified"]]
            gaps = [
                100.0 * (r["distance"] / r["ref_distance"] - 1.0)
                for r in good
                if r.get("ref_distance")
            ]
            solvers.append(
                {
                    "solver": name,
                    "runs": len(mine),
                    "verified": len(good),
                    "atRefFleet": sum(
                        1
                        for r in good
                        if r.get("ref_vehicles") is not None and r["vehicles"] <= r["ref_vehicles"]
                    ),
                    "meanGap": round(sum(gaps) / len(gaps), 2) if gaps else None,
                }
            )
        out["families"].append({"family": family, "budget": fam[0]["budget_s"], "solvers": solvers})
    return out


def _read(name: str) -> Any:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "fleet-mix.json").write_text(json.dumps(fleet_mix(), separators=(",", ":")) + "\n")
    (DATA / "dispatch.json").write_text(json.dumps(dispatch(), separators=(",", ":")) + "\n")
    day, prices = sheets_day()
    for name, payload in (("route-sheets.json", day), ("prices.json", prices)):
        (DATA / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
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
    target = DATA / "comparisons.json"
    comparisons = json.loads(target.read_text()) if target.exists() else {}
    fresh = {
        "ortools": _read("ortools_vs_alns.json"),
        "exact": _read("exact_vs_alns.json"),
        "speed": _read("vrp_speed.json"),
        "realtime": _read("realtime_dispatch.json"),
        "solvers": solvers_summary(),
    }
    if fresh["exact"] is not None:
        fresh["exact"] = {
            "summary": fresh["exact"]["summary"],
            "selective": fresh["exact"].get("selective_summary"),
        }
    for key, value in fresh.items():
        if value is not None:
            comparisons[key] = value
        else:
            print(f"comparisons.{key}: no result file, kept as published")
    target.write_text(json.dumps(comparisons, separators=(",", ":")) + "\n")
    print("site data written")


if __name__ == "__main__":
    main()
