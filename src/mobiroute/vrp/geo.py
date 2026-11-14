"""From coordinates to an instance: geographic input and road matrices.

Format ``mobiroute.vrp.geo.v1`` (JSON). Times are ``"HH:MM"`` strings,
durations are minutes, distances kilometres::

    {
      "format": "mobiroute.vrp.geo.v1",
      "name": "city-day",
      "currency": "RUB",
      "dimensions": ["kg", "m3", "pallets"],
      "depots": [{"id": "DC", "lat": 55.74, "lon": 52.40, "open": "06:00",
                  "close": "22:00", "load_min": 20, "name": "warehouse"}],
      "orders": [{"id": "A17",
                  "pickup":   {"lat": ..., "lon": ..., "from": "08:00", "to": "10:00",
                               "service_min": 20, "name": "supplier"},
                  "delivery": {"lat": ..., "lon": ..., "from": "09:00", "to": "13:00",
                               "service_min": 15, "name": "customer"},
                  "demand": [420, 1.6, 1], "skills": ["cold"],
                  "penalty": null, "max_ride_min": null}],
      "vehicle_types": [{"id": "van", "count": 6, "capacity": [1500, 9, 4],
                         "depot": "DC", "end_depot": "DC",
                         "shift": ["06:00", "20:00"], "max_duration_min": 600,
                         "fixed_cost": 0, "cost_per_km": 18, "cost_per_hour": 450,
                         "skills": ["tail_lift"], "profile": "van", "hired": false,
                         "rests": {"max_driving_min": 270, "duration_min": 45},
                         "trips": {"max": 2, "reload_min": 30}}],
      "profiles": {"van": {"speed_kmh": 32, "detour": 1.3},
                   "truck": {"speed_kmh": 26, "detour": 1.3, "osrm_time_factor": 1.25}},
      "traffic": {"starts": ["00:00", "07:30", "10:00", "17:00", "19:30"],
                  "factors": [1.0, 0.55, 1.0, 0.6, 1.0]}
    }

An order without ``pickup`` is loaded at the depot; without ``delivery`` it
is a collection. ``rests``, ``trips``, ``traffic`` and ``currency`` (a label
for route sheets) are optional.

Road matrices come from one of two sources:

* ``haversine`` (offline): great-circle distance times a detour factor, at
  the profile's average speed. Good enough to try the engine on real
  places; a routing engine is better.
* ``osrm``: the ``table`` service of an OSRM server (Luxen & Vetter 2011),
  queried in blocks of ``block`` points, durations in seconds and distances
  in metres converted to minutes and kilometres; a profile's
  ``osrm_time_factor`` slows a car profile down for trucks.

Plane coordinates of the instance (for maps) are an equirectangular
projection around the mean latitude, in kilometres.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from mobiroute.vrp.model import (
    BreakRule,
    Instance,
    Matrix,
    Node,
    Profile,
    Request,
    SpeedProfile,
    VehicleType,
    add_reload_stops,
)

EARTH_KM = 6371.0088
FORMAT = "mobiroute.vrp.geo.v1"

#: ``points -> (minutes, kilometres)`` for one profile.
MatrixSource = Callable[[Sequence[tuple[float, float]], Mapping[str, Any]], tuple[Matrix, Matrix]]


@dataclass(frozen=True, slots=True)
class Place:
    """What a node of the instance is in the real world."""

    lat: float
    lon: float
    label: str
    order: str | None
    role: str  # "depot", "pickup", "delivery", "reload"


@dataclass(frozen=True, slots=True)
class GeoInstance:
    """An instance built from coordinates, with the places behind its nodes."""

    instance: Instance
    places: tuple[Place, ...]
    currency: str = ""


def minutes(text: str) -> float:
    """``"HH:MM"`` to minutes after midnight (``"24:00"`` and later allowed)."""
    if not isinstance(text, str):
        raise ValueError(f"GEO_TIME_INVALID:{text!r}")
    try:
        hours, mins = text.strip().split(":")
        value = int(hours) * 60 + int(mins)
    except ValueError as exc:
        raise ValueError(f"GEO_TIME_INVALID:{text}") from exc
    if not 0 <= int(mins) < 60 or value < 0:
        raise ValueError(f"GEO_TIME_INVALID:{text}")
    return float(value)


def clock(value: float) -> str:
    """Minutes after midnight to ``"HH:MM"`` (rounded to the minute)."""
    total = round(value)
    return f"{total // 60:02d}:{total % 60:02d}"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between ``(lat, lon)`` points in kilometres."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def haversine_matrices(
    points: Sequence[tuple[float, float]], profile: Mapping[str, Any]
) -> tuple[Matrix, Matrix]:
    """Offline matrices: great circle times ``detour``, at ``speed_kmh``."""
    detour = float(profile.get("detour", 1.3))
    speed = float(profile["speed_kmh"])
    if speed <= 0 or detour < 1.0:
        raise ValueError("GEO_PROFILE_INVALID")
    km = tuple(tuple(detour * haversine_km(a, b) for b in points) for a in points)
    mins = tuple(tuple(d / speed * 60.0 for d in row) for row in km)
    return mins, km


def osrm_source(
    base_url: str,
    *,
    osrm_profile: str = "driving",
    block: int = 100,
    timeout: float = 30.0,
    opener: Callable[[str, float], bytes] | None = None,
) -> MatrixSource:
    """Matrices from an OSRM ``table`` service, requested in blocks.

    ``block`` is the most points per request side (OSRM's default
    ``--max-table-size`` is 100). ``opener`` replaces the HTTP call in tests.
    """

    def fetch(url: str, limit: float) -> bytes:
        with urllib.request.urlopen(url, timeout=limit) as resp:
            body: bytes = resp.read()
            return body

    if urllib.parse.urlsplit(base_url).scheme not in {"http", "https"}:
        raise ValueError("GEO_OSRM_URL_INVALID")
    get = opener or fetch

    def source(
        points: Sequence[tuple[float, float]], profile: Mapping[str, Any]
    ) -> tuple[Matrix, Matrix]:
        n = len(points)
        factor = float(profile.get("osrm_time_factor", 1.0))
        secs = [[0.0] * n for _ in range(n)]
        metres = [[0.0] * n for _ in range(n)]
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        for i0 in range(0, n, block):
            src = list(range(i0, min(n, i0 + block)))
            for j0 in range(0, n, block):
                dst = list(range(j0, min(n, j0 + block)))
                query = urllib.parse.urlencode(
                    {
                        "sources": ";".join(map(str, src)),
                        "destinations": ";".join(map(str, dst)),
                        "annotations": "duration,distance",
                    }
                )
                url = f"{base_url.rstrip('/')}/table/v1/{osrm_profile}/{coords}?{query}"
                data = json.loads(get(url, timeout))
                if data.get("code") != "Ok":
                    raise ValueError(f"GEO_OSRM_{data.get('code', 'ERROR')}")
                for a, row in zip(src, data["durations"], strict=True):
                    for b, value in zip(dst, row, strict=True):
                        if value is None:
                            raise ValueError(f"GEO_OSRM_NO_ROUTE:{a}->{b}")
                        secs[a][b] = float(value)
                for a, row in zip(src, data["distances"], strict=True):
                    for b, value in zip(dst, row, strict=True):
                        metres[a][b] = 0.0 if value is None else float(value)
        mins = tuple(tuple(factor * v / 60.0 for v in row) for row in secs)
        km = tuple(tuple(v / 1000.0 for v in row) for row in metres)
        return mins, km

    return source


def _stop(raw: Mapping[str, Any], where: str) -> tuple[float, float, float, float, float, str]:
    if any(isinstance(raw.get(key), bool) for key in ("lat", "lon")):
        raise ValueError(f"GEO_STOP_INVALID:{where}")
    try:
        lat, lon = float(raw["lat"]), float(raw["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"GEO_STOP_INVALID:{where}") from exc
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"GEO_COORDINATES_INVALID:{where}")
    lo = minutes(raw["from"]) if raw.get("from") else 0.0
    hi = minutes(raw["to"]) if raw.get("to") else math.inf
    return lat, lon, lo, hi, float(raw.get("service_min", 0.0)), str(raw.get("name", ""))


def build(
    data: Mapping[str, Any],
    *,
    source: MatrixSource = haversine_matrices,
) -> GeoInstance:
    """Instance and places from a ``mobiroute.vrp.geo.v1`` document.

    Every malformed document ends in a ``ValueError`` whose message starts
    with a code: a missing field is ``GEO_FIELD_MISSING:<name>``, a field of
    the wrong shape ``GEO_FIELD_INVALID:<detail>``; the model's own checks
    follow (``VRP_...``).
    """
    if not isinstance(data, Mapping) or data.get("format") != FORMAT:
        raise ValueError("GEO_FORMAT")
    try:
        return _build(data, source)
    except KeyError as exc:
        raise ValueError(f"GEO_FIELD_MISSING:{exc.args[0]}") from exc
    except (TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"GEO_FIELD_INVALID:{exc}") from exc


def _build(data: Mapping[str, Any], source: MatrixSource) -> GeoInstance:
    dims = tuple(str(d) for d in data.get("dimensions", ("load",)))
    points: list[tuple[float, float]] = []
    places: list[Place] = []
    raw_nodes: list[tuple[float, float, float, str]] = []  # earliest, latest, service, name
    depot_index: dict[str, int] = {}
    for dep in data["depots"]:
        did = str(dep["id"])
        if did in depot_index:
            raise ValueError(f"GEO_DUPLICATE_DEPOT:{did}")
        lat, lon, _lo, _hi, _svc, name = _stop(dep, did)
        depot_index[did] = len(points)
        points.append((lat, lon))
        places.append(Place(lat, lon, name or did, None, "depot"))
        open_at = minutes(dep["open"]) if dep.get("open") else 0.0
        close_at = minutes(dep["close"]) if dep.get("close") else math.inf
        # Loading before the first departure counts in the shift and the windows.
        load_min = float(dep.get("load_min", 0.0))
        raw_nodes.append((open_at, close_at, load_min, name or did))
    requests: list[Request] = []
    seen: set[str] = set()
    for order in data["orders"]:
        oid = str(order["id"])
        if oid in seen:
            raise ValueError(f"GEO_DUPLICATE_ORDER:{oid}")
        seen.add(oid)
        ids: dict[str, int | None] = {"pickup": None, "delivery": None}
        for role in ("pickup", "delivery"):
            if order.get(role) is None:
                continue
            lat, lon, lo, hi, svc, name = _stop(order[role], f"{oid}.{role}")
            ids[role] = len(points)
            points.append((lat, lon))
            places.append(Place(lat, lon, name or f"{oid} {role}", oid, role))
            raw_nodes.append((lo, hi, svc, name))
        demand = tuple(float(q) for q in order.get("demand", (0.0,) * len(dims)))
        if len(demand) != len(dims):
            raise ValueError(f"GEO_DEMAND_DIMENSIONS:{oid}")
        ride = order.get("max_ride_min")
        penalty = order.get("penalty")
        requests.append(
            Request(
                oid,
                ids["pickup"],
                ids["delivery"],
                demand,
                frozenset(order.get("skills", ())),
                None if ride is None else float(ride),
                None if penalty is None else float(penalty),
            )
        )
    # Plane coordinates for maps: equirectangular around the mean latitude.
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    lon_ref = min(p[1] for p in points)
    lat_ref = min(p[0] for p in points)
    nodes = tuple(
        Node(
            k,
            lo,
            hi,
            svc,
            EARTH_KM * math.radians(lon - lon_ref) * math.cos(lat0),
            EARTH_KM * math.radians(lat - lat_ref),
            name,
        )
        for k, ((lat, lon), (lo, hi, svc, name)) in enumerate(zip(points, raw_nodes, strict=True))
    )
    traffic = data.get("traffic")
    speed = (
        None
        if traffic is None
        else SpeedProfile(
            tuple(minutes(x) for x in traffic["starts"]),
            tuple(float(f) for f in traffic["factors"]),
        )
    )
    profiles: dict[str, Profile] = {}
    for pname, prof in data["profiles"].items():
        mins, km = source(points, prof)
        profiles[str(pname)] = Profile(str(pname), mins, km, speed)
    if not profiles:
        raise ValueError("GEO_PROFILES_MISSING")
    types: list[VehicleType] = []
    trips: list[tuple[str, int, float]] = []
    for vt in data["vehicle_types"]:
        vid = str(vt["id"])
        start = depot_index.get(str(vt["depot"]))
        end = depot_index.get(str(vt.get("end_depot", vt["depot"])))
        if start is None or end is None:
            raise ValueError(f"GEO_UNKNOWN_DEPOT:{vid}")
        shift = vt.get("shift", ["00:00", "24:00"])
        rests = vt.get("rests")
        types.append(
            VehicleType(
                id=vid,
                capacity=tuple(float(q) for q in vt["capacity"]),
                count=int(vt.get("count", 1)),
                start_depot=start,
                end_depot=end,
                shift_start=minutes(shift[0]),
                shift_end=minutes(shift[1]),
                fixed_cost=float(vt.get("fixed_cost", 0.0)),
                cost_per_distance=float(vt.get("cost_per_km", 1.0)),
                cost_per_time=float(vt.get("cost_per_hour", 0.0)) / 60.0,
                max_duration=None
                if vt.get("max_duration_min") is None
                else float(vt["max_duration_min"]),
                skills=frozenset(vt.get("skills", ())),
                profile=str(vt.get("profile", next(iter(profiles)))),
                hired=bool(vt.get("hired", False)),
                breaks=None
                if rests is None
                else BreakRule(float(rests["max_driving_min"]), float(rests["duration_min"])),
            )
        )
        if vt.get("trips") and int(vt["trips"]["max"]) > 1:
            trips.append((vid, int(vt["trips"]["max"]), float(vt["trips"].get("reload_min", 0))))
    inst = Instance(
        name=str(data.get("name", "geo")),
        nodes=nodes,
        requests=tuple(requests),
        vehicle_types=tuple(types),
        profiles=profiles,
        dimensions=dims,
        source="geo input",
    )
    for vid, count, reload in trips:
        before = inst.n_nodes
        inst = add_reload_stops(inst, vid, count, reload)
        depot = next(vt for vt in inst.vehicle_types if vt.id == vid).start_depot
        home = replace(places[depot], role="reload")
        places += [home] * (inst.n_nodes - before)
    return GeoInstance(inst, tuple(places), str(data.get("currency", "")))


def load(path: str, *, osrm: str | None = None, osrm_profile: str = "driving") -> GeoInstance:
    """Read a geo file; road matrices from ``osrm`` if given, else offline."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    source = haversine_matrices if osrm is None else osrm_source(osrm, osrm_profile=osrm_profile)
    return build(data, source=source)
