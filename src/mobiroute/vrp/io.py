"""Readers for the public benchmark formats and a JSON format for cargo days.

Every reader is strict: a malformed file fails with a code instead of being
guessed at. Benchmarks with a hierarchical objective (fewest vehicles, then
distance) get a ``vehicle_penalty`` far above any route cost, so one scalar
objective ranks plans the way the published tables do.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mobiroute.vrp.model import (
    INF,
    BreakRule,
    Instance,
    Node,
    Profile,
    Request,
    SpeedProfile,
    VehicleType,
    euclidean_matrix,
    single_profile,
)

#: Vehicle penalty for hierarchical benchmarks; route costs there stay below 1e4.
HIERARCHICAL_PENALTY = 1e5


def _numbers(line: str) -> list[float]:
    return [float(tok) for tok in line.split()]


def parse_solomon(text: str, *, name: str | None = None) -> Instance:
    """Solomon (1987) VRPTW: every customer is a delivery from the depot."""
    lines = [ln.strip() for ln in text.splitlines()]
    nonempty = [ln for ln in lines if ln]
    if not nonempty:
        raise ValueError("SOLOMON_EMPTY")
    title = name or nonempty[0]
    try:
        k_idx = next(i for i, ln in enumerate(nonempty) if ln.upper().startswith("NUMBER"))
        fleet = _numbers(nonempty[k_idx + 1])
        c_idx = next(i for i, ln in enumerate(nonempty) if ln.upper().startswith("CUST"))
    except (StopIteration, IndexError, ValueError) as exc:
        raise ValueError("SOLOMON_HEADER") from exc
    if len(fleet) != 2:
        raise ValueError("SOLOMON_FLEET_LINE")
    rows = [_numbers(ln) for ln in nonempty[c_idx + 1 :] if ln[0].isdigit()]
    if not rows or any(len(row) != 7 for row in rows):
        raise ValueError("SOLOMON_CUSTOMER_LINE_MUST_HAVE_7_FIELDS")
    nodes: list[Node] = []
    points: list[tuple[float, float]] = []
    for k, (cid, x, y, _dem, ready, due, service) in enumerate(rows):
        if int(cid) != k:
            raise ValueError("SOLOMON_IDS_MUST_BE_SEQUENTIAL")
        nodes.append(Node(k, ready, due, service, x, y, name=str(k) if k else "depot"))
        points.append((x, y))
    requests = tuple(
        Request(str(k), None, k, (rows[k][3],)) for k in range(1, len(rows)) if rows[k][3] >= 0
    )
    if len(requests) != len(rows) - 1:
        raise ValueError("SOLOMON_NEGATIVE_DEMAND")
    matrix = euclidean_matrix(points)
    vtype = VehicleType(
        id="vehicle",
        capacity=(fleet[1],),
        count=int(fleet[0]),
        shift_start=nodes[0].earliest,
        shift_end=nodes[0].latest,
    )
    return Instance(
        name=title,
        nodes=tuple(nodes),
        requests=requests,
        vehicle_types=(vtype,),
        profiles=single_profile(matrix),
        vehicle_penalty=HIERARCHICAL_PENALTY,
        source="solomon",
    )


def parse_lilim(text: str, *, name: str) -> Instance:
    """Li & Lim (2001) PDPTW: ``K Q S`` then ``id x y demand e l s pickup delivery``."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("LILIM_EMPTY")
    head = _numbers(lines[0])
    if len(head) != 3:
        raise ValueError("LILIM_HEADER_MUST_BE_K_Q_S")
    rows = [_numbers(ln) for ln in lines[1:]]
    if any(len(row) != 9 for row in rows):
        raise ValueError("LILIM_LINE_MUST_HAVE_9_FIELDS")
    nodes: list[Node] = []
    points: list[tuple[float, float]] = []
    for k, (tid, x, y, _dem, ready, due, service, _p, _d) in enumerate(rows):
        if int(tid) != k:
            raise ValueError("LILIM_IDS_MUST_BE_SEQUENTIAL")
        nodes.append(Node(k, ready, due, service, x, y, name=str(k) if k else "depot"))
        points.append((x, y))
    requests: list[Request] = []
    for k, row in enumerate(rows[1:], start=1):
        demand, partner_pick, partner_deliv = row[3], int(row[7]), int(row[8])
        if demand > 0:
            if partner_pick != 0 or not 0 < partner_deliv < len(rows):
                raise ValueError("LILIM_PAIR_INVALID")
            back = rows[partner_deliv]
            if int(back[7]) != k or back[3] != -demand:
                raise ValueError("LILIM_PAIR_INVALID")
            requests.append(Request(str(k), k, partner_deliv, (demand,)))
        elif demand == 0 or partner_pick == 0:
            raise ValueError("LILIM_PAIR_INVALID")
    vtype = VehicleType(
        id="vehicle",
        capacity=(head[1],),
        count=int(head[0]),
        shift_start=nodes[0].earliest,
        shift_end=nodes[0].latest,
    )
    return Instance(
        name=name,
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=(vtype,),
        profiles=single_profile(euclidean_matrix(points)),
        vehicle_penalty=HIERARCHICAL_PENALTY,
        source="li-lim",
    )


def parse_sartori_buriol(text: str) -> Instance:
    """Sartori & Buriol (2020) PDPTW on real road travel times (OSRM, minutes)."""
    lines = text.splitlines()
    header: dict[str, str] = {}
    idx = 0
    while idx < len(lines) and lines[idx].strip() != "NODES":
        key, _, value = lines[idx].partition(":")
        if key.strip():
            header[key.strip().upper()] = value.strip()
        idx += 1
    try:
        size = int(header["SIZE"])
        capacity = float(header["CAPACITY"])
        horizon = float(header["ROUTE-TIME"])
        name = header["NAME"]
    except (KeyError, ValueError) as exc:
        raise ValueError("SB_HEADER") from exc
    node_rows = [ln.split() for ln in lines[idx + 1 : idx + 1 + size]]
    if len(node_rows) != size or any(len(row) != 9 for row in node_rows):
        raise ValueError("SB_NODE_LINE_MUST_HAVE_9_FIELDS")
    edge_at = idx + 1 + size
    if edge_at >= len(lines) or lines[edge_at].strip() != "EDGES":
        raise ValueError("SB_EDGES_MISSING")
    matrix_rows = [lines[edge_at + 1 + k].split() for k in range(size)]
    if any(len(row) != size for row in matrix_rows):
        raise ValueError("SB_MATRIX_SHAPE")
    matrix = tuple(tuple(float(v) for v in row) for row in matrix_rows)
    nodes: list[Node] = []
    requests: list[Request] = []
    for k, row in enumerate(node_rows):
        nid, lat, lon, dem, etw, ltw, dur, pick, deliv = row
        if int(nid) != k:
            raise ValueError("SB_IDS_MUST_BE_SEQUENTIAL")
        nodes.append(
            Node(
                k,
                float(etw),
                float(ltw),
                float(dur),
                float(lon),
                float(lat),
                "depot" if k == 0 else str(k),
            )
        )
        if int(dem) > 0:
            if int(pick) != 0 or not 0 < int(deliv) < size:
                raise ValueError("SB_PAIR_INVALID")
            requests.append(Request(str(k), k, int(deliv), (float(dem),)))
    vtype = VehicleType(
        id="vehicle",
        capacity=(capacity,),
        count=len(requests),
        shift_start=0.0,
        shift_end=horizon,
    )
    return Instance(
        name=name,
        nodes=tuple(nodes),
        requests=tuple(requests),
        vehicle_types=(vtype,),
        profiles=single_profile(matrix),
        vehicle_penalty=HIERARCHICAL_PENALTY,
        source="sartori-buriol",
    )


def parse_cordeau_vrp(text: str, *, name: str) -> Instance:
    """Cordeau (2006) DARP as a rich VRP: pairs, ride limit ``L``, duration ``T``."""
    from mobiroute.benchmarks.cordeau_exact import parse_cordeau_instance

    darp = parse_cordeau_instance(text, instance_id=name)
    n = darp.n_requests
    end = darp.end_depot
    nodes = tuple(
        Node(
            k,
            float(nd.earliest),
            float(nd.latest),
            float(nd.service),
            nd.x,
            nd.y,
            "depot" if k in (0, end) else (f"+{k}" if k <= n else f"-{k - n}"),
        )
        for k, nd in enumerate(darp.nodes)
    )
    points = [(nd.x, nd.y) for nd in darp.nodes]
    requests = tuple(
        Request(str(i), i, i + n, (float(darp.nodes[i].load),), max_ride=float(darp.max_ride_time))
        for i in range(1, n + 1)
    )
    vtype = VehicleType(
        id="vehicle",
        capacity=(float(darp.capacity),),
        count=darp.n_vehicles,
        start_depot=0,
        end_depot=end,
        shift_start=nodes[0].earliest,
        shift_end=nodes[end].latest,
        max_duration=float(darp.max_route_duration),
    )
    return Instance(
        name=name,
        nodes=nodes,
        requests=requests,
        vehicle_types=(vtype,),
        profiles=single_profile(euclidean_matrix(points)),
        source="cordeau",
    )


def load_benchmark(path: str | Path) -> tuple[Instance, str]:
    """Read any vendored benchmark file; return the instance and its SHA-256."""
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    family = path.parent.name.lower()
    stem = path.stem
    if family == "solomon":
        return parse_solomon(text, name=stem), digest
    if family == "lilim":
        return parse_lilim(text, name=stem), digest
    if family == "n100" or "sartori" in str(path).lower():
        return parse_sartori_buriol(text), digest
    if family == "cordeau":
        return parse_cordeau_vrp(text, name=stem), digest
    if path.suffix == ".json":
        return instance_from_json(text), digest
    raise ValueError(f"UNKNOWN_BENCHMARK_FAMILY:{family}")


def _finite(value: float) -> float | None:
    return None if value == INF else value


def instance_to_dict(inst: Instance) -> dict[str, Any]:
    """Self-contained JSON form (matrices included)."""
    return {
        "format": "mobiroute.vrp.v1",
        "name": inst.name,
        "source": inst.source,
        "dimensions": list(inst.dimensions),
        "vehicle_penalty": inst.vehicle_penalty,
        "nodes": [
            {
                "id": nd.id,
                "name": nd.name,
                "x": nd.x,
                "y": nd.y,
                "earliest": nd.earliest,
                "latest": _finite(nd.latest),
                "service": nd.service,
            }
            for nd in inst.nodes
        ],
        "requests": [
            {
                "id": r.id,
                "pickup": r.pickup,
                "delivery": r.delivery,
                "demand": list(r.demand),
                "skills": sorted(r.skills),
                "max_ride": r.max_ride,
                "penalty": r.penalty,
                "release": r.release,
            }
            for r in inst.requests
        ],
        "vehicle_types": [
            {
                "id": vt.id,
                "capacity": list(vt.capacity),
                "count": vt.count,
                "start_depot": vt.start_depot,
                "end_depot": vt.end_depot,
                "shift_start": vt.shift_start,
                "shift_end": _finite(vt.shift_end),
                "fixed_cost": vt.fixed_cost,
                "cost_per_distance": vt.cost_per_distance,
                "cost_per_time": vt.cost_per_time,
                "max_duration": vt.max_duration,
                "skills": sorted(vt.skills),
                "profile": vt.profile,
                "hired": vt.hired,
                "breaks": None
                if vt.breaks is None
                else {"max_driving": vt.breaks.max_driving, "duration": vt.breaks.duration},
                "reload_nodes": list(vt.reload_nodes),
                "max_trips": vt.max_trips,
            }
            for vt in inst.vehicle_types
        ],
        "profiles": {
            name: {
                "time": [list(r) for r in p.time],
                "distance": [list(r) for r in p.distance],
                "speed": None
                if p.speed is None
                else {"starts": list(p.speed.starts), "factors": list(p.speed.factors)},
            }
            for name, p in inst.profiles.items()
        },
    }


def _inf(value: float | None) -> float:
    return INF if value is None else float(value)


def instance_from_dict(data: Mapping[str, Any]) -> Instance:
    if data.get("format") != "mobiroute.vrp.v1":
        raise ValueError("VRP_JSON_FORMAT")
    profiles = {
        name: Profile(
            name,
            tuple(tuple(float(v) for v in row) for row in p["time"]),
            tuple(tuple(float(v) for v in row) for row in p["distance"]),
            None
            if p.get("speed") is None
            else SpeedProfile(
                tuple(float(x) for x in p["speed"]["starts"]),
                tuple(float(x) for x in p["speed"]["factors"]),
            ),
        )
        for name, p in data["profiles"].items()
    }
    return Instance(
        name=str(data["name"]),
        source=str(data.get("source", "")),
        dimensions=tuple(data["dimensions"]),
        vehicle_penalty=float(data.get("vehicle_penalty", 0.0)),
        nodes=tuple(
            Node(
                int(nd["id"]),
                float(nd["earliest"]),
                _inf(nd["latest"]),
                float(nd["service"]),
                float(nd.get("x", 0.0)),
                float(nd.get("y", 0.0)),
                str(nd.get("name", "")),
            )
            for nd in data["nodes"]
        ),
        requests=tuple(
            Request(
                str(r["id"]),
                r["pickup"],
                r["delivery"],
                tuple(float(q) for q in r["demand"]),
                frozenset(r.get("skills", ())),
                r.get("max_ride"),
                r.get("penalty"),
                float(r.get("release", 0.0)),
            )
            for r in data["requests"]
        ),
        vehicle_types=tuple(
            VehicleType(
                id=str(vt["id"]),
                capacity=tuple(float(c) for c in vt["capacity"]),
                count=int(vt["count"]),
                start_depot=int(vt["start_depot"]),
                end_depot=int(vt["end_depot"]),
                shift_start=float(vt["shift_start"]),
                shift_end=_inf(vt["shift_end"]),
                fixed_cost=float(vt["fixed_cost"]),
                cost_per_distance=float(vt["cost_per_distance"]),
                cost_per_time=float(vt["cost_per_time"]),
                max_duration=vt.get("max_duration"),
                skills=frozenset(vt.get("skills", ())),
                profile=str(vt.get("profile", "default")),
                hired=bool(vt.get("hired", False)),
                breaks=None
                if vt.get("breaks") is None
                else BreakRule(float(vt["breaks"]["max_driving"]), float(vt["breaks"]["duration"])),
                reload_nodes=tuple(int(x) for x in vt.get("reload_nodes", ())),
                max_trips=int(vt.get("max_trips", 1)),
            )
            for vt in data["vehicle_types"]
        ),
        profiles=profiles,
    )


def instance_to_json(inst: Instance) -> str:
    return json.dumps(instance_to_dict(inst), separators=(",", ":"))


def instance_from_json(text: str) -> Instance:
    return instance_from_dict(json.loads(text))
