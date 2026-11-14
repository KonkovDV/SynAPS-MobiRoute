"""Coordinates in, route sheets out.

Geographic input (offline great-circle matrices and the OSRM table
service), the dispatcher's schedule and the route sheets built from it.
Every sheet is re-checked against the route's constraint system arc by arc,
and the shortest schedule is held to the verifier's numbers on random
routes (property-based, Hypothesis).
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import math
import random
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.cli import main
from mobiroute.vrp import geo
from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import random_instance
from mobiroute.vrp.model import BreakRule, Instance, SpeedProfile
from mobiroute.vrp.schedule import TIME_EPS, compact_schedule, route_arcs, route_timing
from mobiroute.vrp.sheets import (
    _trips_ru,
    route_sheets,
    sheets_csv,
    sheets_markdown,
    sheets_svg,
)
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.traffic import arrive, with_traffic
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "chelny-day.geo.json"


def _doc() -> dict[str, Any]:
    """One depot and four orders 2-6 km around it: a drop, a pair, a collection, a drop."""
    return {
        "format": geo.FORMAT,
        "name": "tiny",
        "dimensions": ["kg", "m3"],
        "depots": [
            {"id": "D", "lat": 55.75, "lon": 52.40, "open": "06:00", "close": "22:00",
             "name": "depot"}
        ],
        "orders": [
            {"id": "A", "demand": [400, 1.0],
             "delivery": {"lat": 55.77, "lon": 52.43, "from": "08:00", "to": "12:00",
                          "service_min": 10}},
            {"id": "B", "demand": [300, 0.8],
             "pickup": {"lat": 55.73, "lon": 52.37, "from": "07:30", "to": "11:00",
                        "service_min": 15, "name": "supplier"},
             "delivery": {"lat": 55.76, "lon": 52.45, "from": "09:00", "to": "16:00",
                          "service_min": 10, "name": "customer"}},
            {"id": "C", "demand": [100, 0.3],
             "pickup": {"lat": 55.74, "lon": 52.47, "service_min": 5}},
            {"id": "E", "demand": [600, 1.5],
             "delivery": {"lat": 55.78, "lon": 52.36, "from": "13:00", "to": "17:00",
                          "service_min": 10}},
        ],
        "vehicle_types": [
            {"id": "van", "count": 1, "capacity": [1000, 4], "depot": "D",
             "shift": ["07:00", "19:00"], "cost_per_km": 20, "cost_per_hour": 600,
             "profile": "road"}
        ],
        "profiles": {"road": {"speed_kmh": 30, "detour": 1.3}},
    }  # fmt: skip


def _sheet_of(built: geo.GeoInstance, nodes: list[int]) -> Any:
    solution = Solution([Route(0, nodes)], set())
    verdict = verify(built.instance, solution)
    assert verdict.feasible, verdict.violations
    (sheet,) = route_sheets(built.instance, solution, verdict, built.places)
    return sheet


# -- clock and distances -------------------------------------------------------


def test_clock_and_minutes_round_trip() -> None:
    assert geo.minutes("07:30") == 450.0
    assert geo.minutes("24:00") == 1440.0
    assert geo.clock(450.0) == "07:30"
    assert geo.clock(449.6) == "07:30"
    assert geo.clock(1500.0) == "25:00"
    for bad in ("7.30", "12:75", "x:10", "-1:00"):
        with pytest.raises(ValueError, match="GEO_TIME_INVALID"):
            geo.minutes(bad)


def test_great_circle_distance_matches_known_values() -> None:
    moscow, spb = (55.7558, 37.6173), (59.9343, 30.3351)
    assert geo.haversine_km(moscow, spb) == pytest.approx(634, abs=3)
    assert geo.haversine_km(spb, moscow) == pytest.approx(geo.haversine_km(moscow, spb))
    assert geo.haversine_km(moscow, moscow) == 0.0
    # A degree of latitude is R * pi / 180 everywhere.
    assert geo.haversine_km((10.0, 20.0), (11.0, 20.0)) == pytest.approx(111.195, abs=1e-3)


def test_offline_matrices_apply_detour_and_speed() -> None:
    pts = [(55.75, 52.40), (55.76, 52.40)]
    mins, km = geo.haversine_matrices(pts, {"speed_kmh": 30, "detour": 1.5})
    direct = geo.haversine_km(*pts)
    assert km[0][0] == 0.0 and km[0][1] == pytest.approx(1.5 * direct)
    assert mins[1][0] == pytest.approx(1.5 * direct / 30 * 60)
    for bad in ({"speed_kmh": 0}, {"speed_kmh": 30, "detour": 0.9}):
        with pytest.raises(ValueError, match="GEO_PROFILE_INVALID"):
            geo.haversine_matrices(pts, bad)


# -- OSRM ------------------------------------------------------------------------


def _straight_line_osrm(calls: list[str]) -> Callable[[str, float], bytes]:
    """A fake OSRM ``table`` service: point ``k`` is ``k`` km and ``k`` minutes out."""

    def opener(url: str, timeout: float) -> bytes:
        calls.append(url)
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        assert query["annotations"] == ["duration,distance"]
        src = [int(x) for x in query["sources"][0].split(";")]
        dst = [int(x) for x in query["destinations"][0].split(";")]
        durations = [[60.0 * abs(a - b) for b in dst] for a in src]
        distances = [[1000.0 * abs(a - b) for b in dst] for a in src]
        body = {"code": "Ok", "durations": durations, "distances": distances}
        return json.dumps(body).encode()

    return opener


def test_osrm_source_queries_in_blocks_and_converts_units() -> None:
    points = [(55.75 + 0.01 * k, 52.40 + 0.02 * k) for k in range(5)]
    calls: list[str] = []
    source = geo.osrm_source("http://osrm.test/", block=2, opener=_straight_line_osrm(calls))
    mins, km = source(points, {"osrm_time_factor": 1.25})
    assert len(calls) == 9  # 3 x 3 blocks of at most two points
    path = urlsplit(calls[0]).path
    assert path.startswith("/table/v1/driving/")
    first = path.rsplit("/", 1)[1].split(";")[0]
    assert first == "52.400000,55.750000"  # OSRM wants lon,lat
    assert km[0][4] == pytest.approx(4.0) and km[3][1] == pytest.approx(2.0)
    assert mins[0][4] == pytest.approx(4.0 * 1.25)


def test_osrm_errors_name_the_problem() -> None:
    pts = [(55.75, 52.40), (55.76, 52.41)]

    def refuse(url: str, timeout: float) -> bytes:
        return json.dumps({"code": "InvalidQuery"}).encode()

    def island(url: str, timeout: float) -> bytes:
        grid = [[0, None], [None, 0]]
        return json.dumps({"code": "Ok", "durations": grid, "distances": grid}).encode()

    with pytest.raises(ValueError, match="GEO_OSRM_InvalidQuery"):
        geo.osrm_source("http://osrm.test", opener=refuse)(pts, {})
    with pytest.raises(ValueError, match="GEO_OSRM_NO_ROUTE:0->1"):
        geo.osrm_source("http://osrm.test", opener=island)(pts, {})


@pytest.fixture
def osrm_server() -> Iterator[tuple[str, list[str]]]:
    """A local HTTP server speaking the straight-line OSRM above."""
    calls: list[str] = []
    answer = _straight_line_osrm(calls)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = answer(f"http://local{self.path}", 1.0)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", calls
    finally:
        server.shutdown()
        server.server_close()


def test_load_reads_road_matrices_over_http(
    tmp_path: Path, osrm_server: tuple[str, list[str]]
) -> None:
    url, calls = osrm_server
    path = tmp_path / "day.geo.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    built = geo.load(str(path), osrm=url, osrm_profile="truck")
    assert calls and all("/table/v1/truck/" in c for c in calls)
    road = built.instance.profiles["road"]
    assert road.distance[0][5] == pytest.approx(5.0) and road.time[5][2] == pytest.approx(3.0)


# -- the document ----------------------------------------------------------------


def test_build_maps_orders_to_nodes_and_places() -> None:
    built = geo.build(_doc())
    inst = built.instance
    assert inst.n_nodes == len(built.places) == 6
    assert [p.role for p in built.places] == [
        "depot", "delivery", "pickup", "delivery", "pickup", "delivery"
    ]  # fmt: skip
    a, b, c, e = inst.requests
    assert (a.pickup, a.delivery) == (None, 1)
    assert (b.pickup, b.delivery) == (2, 3)
    assert (c.pickup, c.delivery) == (4, None)  # a collection to the depot
    assert e.demand == (600.0, 1.5)
    assert (inst.nodes[1].earliest, inst.nodes[1].latest) == (480.0, 720.0)
    assert inst.nodes[4].earliest == 0.0 and math.isinf(inst.nodes[4].latest)
    assert inst.nodes[2].service == 15.0
    vt = inst.vehicle_types[0]
    assert (vt.shift_start, vt.shift_end) == (420.0, 1140.0)
    assert vt.cost_per_time == pytest.approx(10.0)  # 600 an hour
    assert built.places[2].label == "supplier" and built.places[1].label == "A delivery"
    assert built.places[3].order == "B" and built.currency == ""
    # Plane coordinates in kilometres: 0.02 degrees of latitude north of the depot.
    assert inst.nodes[1].y - inst.nodes[0].y == pytest.approx(2.224, abs=1e-3)


def test_rests_trips_and_traffic_reach_the_model() -> None:
    doc = _doc()
    doc["currency"] = "RUB"
    doc["vehicle_types"][0] |= {
        "count": 2,
        "rests": {"max_driving_min": 240, "duration_min": 45},
        "trips": {"max": 3, "reload_min": 20},
    }
    built = geo.build(doc)
    inst = built.instance
    vt = inst.vehicle_types[0]
    assert vt.breaks == BreakRule(240.0, 45.0) and vt.max_trips == 3
    reloads = [k for k in range(inst.n_nodes) if inst.reload_type_of(k) == 0]
    assert len(reloads) == 4  # two units, two reloads each
    for k in reloads:
        assert built.places[k].role == "reload"
        assert (built.places[k].lat, built.places[k].lon) == (55.75, 52.40)
        assert inst.nodes[k].service == 20.0
    assert built.currency == "RUB"

    jam = _doc()
    jam["traffic"] = {"starts": ["00:00", "07:30", "10:00"], "factors": [1.0, 0.5, 1.0]}
    speed = geo.build(jam).instance.profiles["road"].speed
    assert speed == SpeedProfile((0.0, 450.0, 600.0), (1.0, 0.5, 1.0))


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(doc: dict[str, Any]) -> None:
        *head, last = path.split(".")
        node: Any = doc
        for key in head:
            node = node[int(key)] if key.isdigit() else node[key]
        if value is None:
            del node[last]
        else:
            node[last] = value

    return change


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (_set("format", "other"), "GEO_FORMAT"),
        (lambda d: d["orders"].append(dict(d["orders"][0])), "GEO_DUPLICATE_ORDER:A"),
        (lambda d: d["depots"].append(dict(d["depots"][0])), "GEO_DUPLICATE_DEPOT:D"),
        (_set("vehicle_types.0.depot", "X"), "GEO_UNKNOWN_DEPOT:van"),
        (_set("orders.0.delivery.lat", 95.0), "GEO_COORDINATES_INVALID:A.delivery"),
        (_set("orders.0.delivery.lon", None), "GEO_STOP_INVALID:A.delivery"),
        (_set("orders.0.demand", [1.0]), "GEO_DEMAND_DIMENSIONS:A"),
        (_set("orders.0.delivery.to", "25:99"), "GEO_TIME_INVALID"),
        (_set("profiles", {}), "GEO_PROFILES_MISSING"),
        (_set("vehicle_types.0.capacity", [1000]), "VRP_CAPACITY_INVALID"),
    ],
)
def test_build_rejects_bad_documents(change: Callable[[dict[str, Any]], None], code: str) -> None:
    doc = copy.deepcopy(_doc())
    change(doc)
    with pytest.raises(ValueError, match=code):
        geo.build(doc)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (_set("depots", None), "GEO_FIELD_MISSING:depots"),
        (_set("vehicle_types.0.capacity", None), "GEO_FIELD_MISSING:capacity"),
        (_set("profiles.road", {"detour": 1.2}), "GEO_FIELD_MISSING:speed_kmh"),
        (_set("vehicle_types.0.rests", {"duration_min": 45}), "GEO_FIELD_MISSING:max_driving"),
        (_set("orders", "x"), "GEO_FIELD_INVALID"),
        (_set("vehicle_types.0.shift", ["07:00"]), "GEO_FIELD_INVALID"),
        (_set("dimensions", 5), "GEO_FIELD_INVALID"),
        (_set("orders.0.delivery.from", 480), "GEO_TIME_INVALID"),
        (_set("orders.0.delivery.lat", True), "GEO_STOP_INVALID:A.delivery"),
    ],
)
def test_malformed_documents_end_in_a_code_not_a_traceback(
    change: Callable[[dict[str, Any]], None], code: str
) -> None:
    doc = copy.deepcopy(_doc())
    change(doc)
    with pytest.raises(ValueError, match=code):
        geo.build(doc)
    with pytest.raises(ValueError, match="GEO_FORMAT"):
        geo.build([])  # type: ignore[arg-type]


def test_osrm_accepts_only_http() -> None:
    for url in ("file:///etc/passwd?", "ftp://osrm.test", "osrm.test:5000"):
        with pytest.raises(ValueError, match="GEO_OSRM_URL_INVALID"):
            geo.osrm_source(url)
    geo.osrm_source("https://osrm.test")


def test_sheets_neutralise_formulas_and_table_breakers() -> None:
    doc = _doc()
    doc["orders"][0]["delivery"]["name"] = '=HYPERLINK("http://x")'
    doc["orders"][1]["pickup"]["name"] = "Склад | ворота 3\n<b>2 этаж</b>"
    built = geo.build(doc)
    sheet = _sheet_of(built, [1, 2, 3, 4, 5])
    rows = list(csv.DictReader(io.StringIO(sheets_csv([sheet], built.instance.dimensions))))
    assert rows[1]["place"] == '\'=HYPERLINK("http://x")'
    text = sheets_markdown([sheet], built.instance.dimensions)
    line = next(x for x in text.splitlines() if "ворота" in x)
    assert "Склад \\| ворота 3 &lt;b&gt;2 этаж&lt;/b&gt;" in line
    assert line.count(" | ") == text.splitlines()[6].count(" | ")


def test_example_day_is_synthetic_and_matches_its_generator() -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    names = [d["name"] for d in data["depots"]] + [
        o[role]["name"] for o in data["orders"] for role in ("pickup", "delivery") if role in o
    ]
    assert names and all("(условн.)" in n for n in names)
    spec = importlib.util.spec_from_file_location(
        "make_chelny_day", EXAMPLE.parent / "make_chelny_day.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.day(1, 45) == data


# -- the dispatcher's schedule -------------------------------------------------


def _with_rests(inst: Instance, drive: float, rest: float) -> Instance:
    types = tuple(replace(vt, breaks=BreakRule(drive, rest)) for vt in inst.vehicle_types)
    return replace(inst, vehicle_types=types)


def _random_sequence(inst: Instance, rng: random.Random, size: int) -> list[int]:
    seq: list[int] = []
    for r in rng.sample(range(inst.n_requests), min(size, inst.n_requests)):
        req = inst.requests[r]
        if req.is_pair:
            assert req.pickup is not None and req.delivery is not None
            i = rng.randint(0, len(seq))
            seq.insert(i, req.pickup)
            seq.insert(rng.randint(i + 1, len(seq)), req.delivery)
        else:
            seq.insert(rng.randint(0, len(seq)), req.nodes[0])
    return seq


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), size=st.integers(1, 6), rests=st.booleans())
def test_compact_schedule_is_admissible_shortest_and_returns_earliest(
    seed: int, size: int, rests: bool
) -> None:
    inst = random_instance(seed, n_requests=7, ride_share=0.4)
    if rests:
        inst = _with_rests(inst, 120.0, 30.0)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, size)
        for t in range(len(inst.vehicle_types)):
            timing = route_timing(inst, t, nodes)
            tight = compact_schedule(inst, t, nodes)
            assert tight.feasible == timing.feasible
            if not timing.feasible:
                continue
            z, arcs = route_arcs(inst, t, nodes, rest_gap=tight.rest_gap)
            b = [*tight.earliest, 0.0]
            assert all(b[a.head] - b[a.tail] <= a.weight + 1e-6 for a in arcs)
            assert b[0] >= timing.earliest[0] - 1e-9
            assert b[z - 1] == pytest.approx(timing.earliest[-1], abs=1e-6)
            assert b[z - 1] - b[0] == pytest.approx(timing.min_duration, abs=1e-6)


@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    factors=st.lists(st.floats(0.3, 1.5), min_size=1, max_size=5),
)
def test_compact_schedule_under_traffic_is_admissible_and_shortest(
    seed: int, factors: list[float]
) -> None:
    base = random_instance(seed, n_requests=7, ride_share=0.0, max_duration=False)
    speed = SpeedProfile(tuple(180.0 * k for k in range(len(factors))), tuple(factors))
    inst = with_traffic(base, speed)
    rng = random.Random(seed)
    for _ in range(6):
        nodes = _random_sequence(inst, rng, rng.randint(1, 6))
        for t, vt in enumerate(inst.vehicle_types):
            timing = route_timing(inst, t, nodes)
            if not timing.feasible:
                continue
            b = compact_schedule(inst, t, nodes).earliest
            seq = [vt.start_depot, *nodes, vt.end_depot]
            assert b[0] >= max(inst.nodes[seq[0]].earliest, vt.shift_start) - TIME_EPS
            assert b[-1] <= vt.shift_end + TIME_EPS
            for k, node in enumerate(seq):
                assert inst.nodes[node].earliest - TIME_EPS <= b[k]
                assert b[k] <= inst.nodes[node].latest + TIME_EPS
            for k in range(len(seq) - 1):
                a, c = seq[k], seq[k + 1]
                leave = b[k] + inst.nodes[a].service
                assert b[k + 1] >= arrive(speed, leave, inst.profiles[vt.profile].time[a][c]) - 1e-6
            assert b[-1] - b[0] == pytest.approx(timing.min_duration, abs=1e-6)


# -- route sheets ----------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(seed=st.integers(0, 10_000), drive=st.floats(40.0, 200.0), size=st.integers(2, 7))
def test_every_route_sheet_keeps_the_driving_time_rule(seed: int, drive: float, size: int) -> None:
    """A labour inspector's property: no sheet shows a stint over the limit."""
    inst = _with_rests(random_instance(seed, n_requests=8, ride_share=0.3), drive, 30.0)
    rng = random.Random(seed)
    for _ in range(5):
        nodes = _random_sequence(inst, rng, size)
        t = rng.randrange(len(inst.vehicle_types))
        served = {inst.request_of(n) for n in nodes}
        solution = Solution([Route(t, nodes)], set(range(inst.n_requests)) - served)
        verdict = verify(inst, solution)
        if not verdict.feasible:
            continue
        (sheet,) = route_sheets(inst, solution, verdict)
        assert sheet.compliant(), (sheet.longest_stint, sheet.stint_limit)
        assert sheet.longest_stint <= drive + 1e-6
        assert sheet.driving <= 2 * drive + 1e-6
        rests = [row for row in sheet.rows if row.kind == "rest"]
        assert len(rests) == (1 if sheet.driving > drive + 1e-6 else 0)


def test_sheet_leaves_late_rests_and_counts_load() -> None:
    doc = _doc()
    doc["profiles"]["road"]["speed_kmh"] = 15
    doc["vehicle_types"][0]["rests"] = {"max_driving_min": 90, "duration_min": 30}
    built = geo.build(doc)
    sheet = _sheet_of(built, [1, 2, 3, 4, 5])
    kinds = [row.kind for row in sheet.rows]
    assert kinds == [
        "depart", "delivery", "pickup", "rest", "delivery", "pickup", "delivery", "return"
    ]  # fmt: skip
    rest = sheet.rows[3]
    assert rest.end - rest.start == pytest.approx(30.0)
    # Lemma 1 admits the rest before the drive or on arrival; this route needs
    # the second: resting at the supplier would leave 109 min of driving after.
    assert rest.place == sheet.rows[4].place == "customer"
    assert rest.arrive == rest.start > sheet.rows[2].end
    assert sheet.rows[4].arrive == pytest.approx(rest.end)
    # Both drops ride from the depot; the collection rides back to it.
    assert sheet.rows[0].load == (1000.0, 2.5)
    assert [row.load[0] for row in sheet.rows[1:]] == [600, 900, 900, 600, 700, 100, 0]
    assert sheet.driving > 90.0 and sheet.trips == 1
    # The driving-time rule as an inspector reads it: each stint within 90 min,
    # the day within 180, the shift within the cap (none set here).
    assert 0 < sheet.longest_stint <= 90.0 < sheet.driving <= 180.0
    assert (sheet.stint_limit, sheet.driving_limit, sheet.shift_limit) == (90.0, 180.0, None)
    assert sheet.compliant()
    text = sheets_markdown([sheet], built.instance.dimensions)
    assert "Режим труда и отдыха соблюдён: непрерывно за рулём" in text
    late = replace(sheet, shift_limit=60.0)
    assert not late.compliant()
    assert "Driving-time rules VIOLATED" in sheets_markdown([late], ("kg", "m3"), lang="en")
    # No idle start: the van leaves later than the shift opens and does not wait.
    assert sheet.depart > 420.0 and sheet.waiting == pytest.approx(0.0, abs=1e-6)
    for row in sheet.rows:
        assert row.arrive <= row.start + 1e-9 and row.start <= row.end
        if row.window is not None:
            assert row.window[0] - 1e-9 <= row.start <= row.window[1] + 1e-9


def test_sheet_numbers_trips_at_the_reload_stop() -> None:
    doc = _doc()
    doc["currency"] = "RUB"
    doc["vehicle_types"][0] |= {"capacity": [700, 4], "trips": {"max": 2, "reload_min": 20}}
    built = geo.build(doc)
    reload = next(k for k in range(built.instance.n_nodes) if built.places[k].role == "reload")
    nodes = [1, 2, 3, 4, reload, 5]  # E (600 kg) cannot ride with A (400 kg) in a 700 kg van
    sheet = _sheet_of(built, nodes)
    assert sheet.trips == 2
    assert [row.trip for row in sheet.rows] == [1, 1, 1, 1, 1, 2, 2, 2]
    reload_row = sheet.rows[5]
    assert reload_row.kind == "reload" and reload_row.load == (600.0, 1.5)
    assert reload_row.end - reload_row.start == pytest.approx(20.0)
    assert sheet.rows[4].load == (100.0, 0.3)  # the collection, unloaded at the reload

    text = sheets_markdown([sheet], built.instance.dimensions, currency=built.currency)
    assert text.startswith("# Маршрутные листы")
    assert "## van #1 · своя · 2 рейса" in text and "₽" in text
    assert "| 2 | перезагрузка |" in text
    english = sheets_markdown([sheet], built.instance.dimensions, lang="en", currency="EUR")
    assert "## van #1 · own · 2 trips" in english and "€" in english

    rows = list(csv.DictReader(io.StringIO(sheets_csv([sheet], built.instance.dimensions))))
    assert len(rows) == len(sheet.rows)
    assert list(rows[0])[-2:] == ["load_kg", "load_m3"]
    assert [r["kind"] for r in rows][:3] == ["depart", "delivery", "pickup"]
    assert rows[1]["order"] == "A" and rows[1]["window_from"] == "08:00"
    assert rows[1]["lat"] == "55.770000" and rows[5]["trip"] == "2"
    assert rows[4]["window_from"] == rows[4]["window_to"] == ""  # no window at all


def test_sheets_add_up_to_the_verdict() -> None:
    built = geo.build(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    inst = built.instance
    result = solve(inst, AlnsConfig(iterations=300, seed=1))
    assert result.verdict.feasible and not result.verdict.unassigned
    sheets = route_sheets(inst, result.solution, result.verdict, built.places)
    assert len(sheets) == result.verdict.cost.vehicles
    assert sum(s.cost for s in sheets) == pytest.approx(result.verdict.cost.total)
    assert sum(s.distance for s in sheets) == pytest.approx(result.verdict.cost.distance)
    loads = [q for s in sheets for row in s.rows for q in row.load]
    assert min(loads) >= 0.0 and all(q == round(q, 6) for q in loads)  # no float dust
    stops = [(row.order, row.kind) for s in sheets for row in s.rows if row.order]
    assert len(stops) == len(set(stops)) == sum(len(r.nodes) for r in inst.requests)
    assert len({s.vehicle for s in sheets}) == len(sheets)


def test_gantt_chart_draws_every_vehicle_and_every_stop() -> None:
    import xml.etree.ElementTree as ET

    doc = _doc()
    doc["currency"] = "RUB"
    doc["vehicle_types"][0] |= {"capacity": [700, 4], "trips": {"max": 2, "reload_min": 20}}
    built = geo.build(doc)
    reload = next(k for k in range(built.instance.n_nodes) if built.places[k].role == "reload")
    sheet = _sheet_of(built, [1, 2, 3, 4, reload, 5])
    svg = sheets_svg([sheet, sheet], title="tiny: маршрутные листы", currency="RUB")
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    bars = [el for el in root.iter(f"{ns}rect") if el.find(f"{ns}title") is not None]
    busy = [row for row in sheet.rows if row.end > row.start]
    assert len(bars) == 2 * len(busy)
    assert sum("reload" in (el.get("class") or "") for el in bars) == 2
    texts = "".join(el.text or "" for el in root.iter(f"{ns}text"))
    assert texts.count("van #1") == 2 and "₽" in texts and "2 рейса" in texts
    english = sheets_svg([sheet], title="tiny", lang="en")
    assert "2 trips" in english and "driving" in english
    with pytest.raises(ValueError, match="SHEETS_EMPTY"):
        sheets_svg([], title="none")


def test_sheets_refuse_what_they_cannot_describe() -> None:
    built = geo.build(_doc())
    inst = built.instance
    late = Solution([Route(0, [5, 1, 2, 3, 4])], set())  # E at 13:00 before A by 12:00
    verdict = verify(inst, late)
    assert not verdict.feasible
    with pytest.raises(ValueError, match="SHEETS_NEED_A_FEASIBLE_PLAN"):
        route_sheets(inst, late, verdict)
    fine = Solution([Route(0, [1, 2, 3, 4, 5])], set())
    with pytest.raises(ValueError, match="SHEETS_PLACES_MISMATCH"):
        route_sheets(inst, fine, verify(inst, fine), built.places[:-1])
    (plain,) = route_sheets(inst, fine, verify(inst, fine))
    assert plain.rows[1].lat is None and plain.rows[1].place == "#1"


@pytest.mark.parametrize(
    ("n", "text"),
    [(1, "1 рейс"), (2, "2 рейса"), (4, "4 рейса"), (5, "5 рейсов"), (11, "11 рейсов"),
     (12, "12 рейсов"), (21, "21 рейс"), (22, "22 рейса"), (111, "111 рейсов")],
)  # fmt: skip
def test_russian_plural_of_trips(n: int, text: str) -> None:
    assert _trips_ru(n) == text


# -- command line ----------------------------------------------------------------


def test_cli_solves_a_geo_day_into_route_sheets(tmp_path: Path) -> None:
    code = main(
        ["vrp-solve", "--geo", str(EXAMPLE), "--iterations", "200", "--sheets", "--svg",
         "--out-dir", str(tmp_path)]
    )  # fmt: skip
    assert code == 0
    text = (tmp_path / "route-sheets.md").read_text(encoding="utf-8")
    assert text.startswith("# Маршрутные листы") and "₽" in text
    rows = list(csv.DictReader(io.StringIO((tmp_path / "route-sheets.csv").read_text("utf-8"))))
    assert len({r["order"] for r in rows if r["kind"] == "delivery"}) == 45
    assert (tmp_path / "routes.svg").exists() and (tmp_path / "solution.json").exists()
    assert (tmp_path / "route-sheets.svg").read_text("utf-8").startswith("<svg")

    code = main(
        ["vrp-solve", "--geo", str(EXAMPLE), "--iterations", "50", "--sheets", "--lang", "en",
         "--out-dir", str(tmp_path / "en")]
    )  # fmt: skip
    assert code == 0
    assert (tmp_path / "en" / "route-sheets.md").read_text("utf-8").startswith("# Route sheets")


def test_cli_reports_a_bad_geo_file_in_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.geo.json"
    bad.write_text(json.dumps({"format": "nope"}), encoding="utf-8")
    assert main(["vrp-solve", "--geo", str(bad), "--out-dir", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "GEO_FORMAT" in err and "Traceback" not in err
