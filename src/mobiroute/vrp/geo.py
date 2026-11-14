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
      "zones": [{"id": "center", "polygon": [[55.75, 52.38], [55.77, 52.38],
                                             [55.77, 52.43], [55.75, 52.43]],
                 "max_gross_weight_t": 3.5, "max_height_m": 3.0,
                 "banned_types": []}],
      "vehicle_types": [{"id": "van", "count": 6, "capacity": [1500, 9, 4],
                         "gross_weight_t": 3.5, "height_m": 2.7,
                         "depot": "DC", "end_depot": "DC",
                         "shift": ["06:00", "20:00"], "max_duration_min": 600,
                         "fixed_cost": 0, "cost_per_km": 18, "cost_per_hour": 450,
                         "skills": ["tail_lift"], "profile": "van", "hired": false,
                         "rests": {"max_driving_min": 270, "duration_min": 45,
                                   "split_min": [15, 30]},
                         "trips": {"max": 2, "reload_min": 30}}],
      "profiles": {"van": {"speed_kmh": 32, "detour": 1.3},
                   "truck": {"speed_kmh": 26, "detour": 1.3, "osrm_time_factor": 1.25}},
      "traffic": {"starts": ["00:00", "07:30", "10:00", "17:00", "19:30"],
                  "factors": [1.0, 0.55, 1.0, 0.6, 1.0]}
    }

A ``zone`` is a polygon or a circle (``center``, ``radius_km``) with road-sign
limits: ``max_gross_weight_t`` (sign 3.11), ``max_axle_load_t`` (3.12),
``max_height_m`` (3.13), ``banned_types`` (3.4 or a pass regime). Stops inside
it may be served only by vehicle types that keep every limit; those types
must state ``gross_weight_t``, ``axle_load_t`` or ``height_m`` as needed.
A profile may carry ``"valhalla": {"costing": "truck", "options": {"weight":
12, "height": 3.8, "axle_load": 8, "hazmat": false}}`` for truck-aware
matrices from a Valhalla server (``vrp-solve --valhalla URL``).

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


@dataclass(frozen=True, slots=True)
class Zone:
    """An area some vehicles may not serve: a polygon or a circle with limits.

    The limits read like road signs: gross weight (3.11), axle load (3.12),
    height (3.13), or listed vehicle types (3.4, a pass regime). A stop inside
    the zone requires the zone's skill; a vehicle type gets it when it keeps
    every limit. Through traffic is the router's business (a truck-aware
    matrix such as :func:`valhalla_source`).
    """

    id: str
    polygon: tuple[tuple[float, float], ...] = ()
    center: tuple[float, float] | None = None
    radius_km: float = 0.0
    max_gross_weight_t: float | None = None
    max_axle_load_t: float | None = None
    max_height_m: float | None = None
    banned_types: frozenset[str] = frozenset()

    @property
    def skill(self) -> str:
        return f"zone:{self.id}"

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> Zone:
        zid = str(raw.get("id", ""))
        if not zid:
            raise ValueError("GEO_ZONE_INVALID:id")
        polygon = tuple((float(a), float(b)) for a, b in raw.get("polygon", ()))
        center = raw.get("center")
        if (len(polygon) < 3) == (center is None):
            raise ValueError(f"GEO_ZONE_INVALID:{zid}:polygon_or_circle")

        def limit(key: str) -> float | None:
            value = raw.get(key)
            return None if value is None else float(value)

        return cls(
            id=zid,
            polygon=polygon,
            center=None if center is None else (float(center[0]), float(center[1])),
            radius_km=float(raw.get("radius_km", 0.0)),
            max_gross_weight_t=limit("max_gross_weight_t"),
            max_axle_load_t=limit("max_axle_load_t"),
            max_height_m=limit("max_height_m"),
            banned_types=frozenset(str(t) for t in raw.get("banned_types", ())),
        )

    def contains(self, lat: float, lon: float) -> bool:
        if self.center is not None:
            return haversine_km((lat, lon), self.center) <= self.radius_km
        inside = False  # ray casting on (lon, lat), fine at city scale
        pts = self.polygon
        for (lat1, lon1), (lat2, lon2) in zip(pts, pts[1:] + pts[:1], strict=True):
            if (lat1 > lat) != (lat2 > lat):
                cross = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
                if lon < cross:
                    inside = not inside
        return inside

    def admits(self, type_id: str, vt: Mapping[str, Any]) -> bool:
        """Whether a vehicle type keeps every limit of the zone."""
        if type_id in self.banned_types:
            return False
        for key, limit in (
            ("gross_weight_t", self.max_gross_weight_t),
            ("axle_load_t", self.max_axle_load_t),
            ("height_m", self.max_height_m),
        ):
            if limit is None:
                continue
            value = vt.get(key)
            if value is None:
                raise ValueError(f"GEO_VEHICLE_ATTRIBUTE_MISSING:{type_id}:{key}:{self.id}")
            if float(value) > limit:
                return False
        return True


def valhalla_source(
    base_url: str,
    *,
    block: int = 50,
    timeout: float = 60.0,
    opener: Callable[[str, bytes, float], bytes] | None = None,
) -> MatrixSource:
    """Matrices from Valhalla's ``sources_to_targets``, with truck costing.

    A profile's ``valhalla`` entry picks the costing (``auto``, ``truck``,
    ...) and its options; for trucks those are the vehicle's weight, axle
    load, height, width, length and hazmat flag, so the router avoids roads
    the truck may not use (Valhalla's truck costing). Requests go in blocks
    of ``block`` points; ``opener`` replaces the HTTP call in tests.
    """
    if urllib.parse.urlsplit(base_url).scheme not in {"http", "https"}:
        raise ValueError("GEO_VALHALLA_URL_INVALID")

    def post(url: str, body: bytes, limit: float) -> bytes:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=limit) as resp:
            out: bytes = resp.read()
            return out

    send = opener or post
    url = f"{base_url.rstrip('/')}/sources_to_targets"

    def source(
        points: Sequence[tuple[float, float]], profile: Mapping[str, Any]
    ) -> tuple[Matrix, Matrix]:
        opts = profile.get("valhalla", {})
        costing = str(opts.get("costing", "auto"))
        n = len(points)
        mins = [[0.0] * n for _ in range(n)]
        km = [[0.0] * n for _ in range(n)]
        locs = [{"lat": lat, "lon": lon} for lat, lon in points]
        for i0 in range(0, n, block):
            src = list(range(i0, min(n, i0 + block)))
            for j0 in range(0, n, block):
                dst = list(range(j0, min(n, j0 + block)))
                body = {
                    "sources": [locs[i] for i in src],
                    "targets": [locs[j] for j in dst],
                    "costing": costing,
                    "costing_options": {costing: dict(opts.get("options", {}))},
                    "units": "kilometers",
                }
                data = json.loads(send(url, json.dumps(body).encode(), timeout))
                if "error" in data or "error_code" in data:
                    raise ValueError(f"GEO_VALHALLA_{data.get('error_code', 'ERROR')}")
                for a, row in zip(src, _valhalla_rows(data, len(src), len(dst)), strict=True):
                    for b, (seconds, dist) in zip(dst, row, strict=True):
                        if seconds is None:
                            raise ValueError(f"GEO_VALHALLA_NO_ROUTE:{a}->{b}")
                        mins[a][b] = float(seconds) / 60.0
                        km[a][b] = float(dist or 0.0)
        return tuple(map(tuple, mins)), tuple(map(tuple, km))

    return source


def _valhalla_rows(data: Mapping[str, Any], rows: int, cols: int) -> list[list[tuple[Any, Any]]]:
    """Both answer shapes: verbose cells, or flat ``durations`` / ``distances``."""
    if "sources_to_targets" in data:
        table = data["sources_to_targets"]
        if isinstance(table, Mapping):  # concise answer (verbose=false)
            durations, distances = table["durations"], table["distances"]
            return [list(zip(durations[i], distances[i], strict=True)) for i in range(rows)]
        return [[(cell.get("time"), cell.get("distance")) for cell in row] for row in table]
    raise ValueError("GEO_VALHALLA_ANSWER")


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
    zones = [Zone.parse(raw) for raw in data.get("zones", ())]
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
        in_zones: set[str] = set()
        for role in ("pickup", "delivery"):
            if order.get(role) is None:
                continue
            lat, lon, lo, hi, svc, name = _stop(order[role], f"{oid}.{role}")
            in_zones |= {z.skill for z in zones if z.contains(lat, lon)}
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
                frozenset(order.get("skills", ())) | in_zones,
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
                skills=frozenset(vt.get("skills", ()))
                | {z.skill for z in zones if z.admits(vid, vt)},
                profile=str(vt.get("profile", next(iter(profiles)))),
                hired=bool(vt.get("hired", False)),
                breaks=None
                if rests is None
                else BreakRule(
                    float(rests["max_driving_min"]),
                    float(rests["duration_min"]),
                    None
                    if rests.get("split_min") is None
                    else (float(rests["split_min"][0]), float(rests["split_min"][1])),
                ),
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
        time_cost=str(data.get("time_cost", "operating")),
    )
    for vid, count, reload in trips:
        before = inst.n_nodes
        inst = add_reload_stops(inst, vid, count, reload)
        depot = next(vt for vt in inst.vehicle_types if vt.id == vid).start_depot
        home = replace(places[depot], role="reload")
        places += [home] * (inst.n_nodes - before)
    return GeoInstance(inst, tuple(places), str(data.get("currency", "")))


def load(
    path: str,
    *,
    osrm: str | None = None,
    osrm_profile: str = "driving",
    valhalla: str | None = None,
) -> GeoInstance:
    """Read a geo file; road matrices from Valhalla or OSRM if given, else offline."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if valhalla is not None and osrm is not None:
        raise ValueError("GEO_ONE_ROUTER")
    if valhalla is not None:
        source = valhalla_source(valhalla)
    elif osrm is not None:
        source = osrm_source(osrm, osrm_profile=osrm_profile)
    else:
        source = haversine_matrices
    return build(data, source=source)
