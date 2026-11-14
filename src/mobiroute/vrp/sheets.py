"""Route sheets: what each driver does, stop by stop.

A verified plan becomes one sheet per vehicle: departure, every stop with
its window, the planned arrival, start and end of work and the load on
board after it (per dimension, per trip), reload stops, the driver's rest
and the return; with the day's distance, driving, waiting and cost.

The times are :func:`mobiroute.vrp.schedule.compact_schedule`: the vehicle
leaves as late as its earliest possible return allows, so a sheet does not
open with an hour of waiting at the first window. That schedule is a
solution of the same constraint system the verifier checks (the tests
re-check every sheet against it, arc by arc).

Three renderings: CSV, one row per event, for an accounting or dispatch
system; Markdown, one table per vehicle, in Russian or English; and an SVG
Gantt chart of the whole day (driving, waiting, service, reloads, rests).
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from mobiroute.vrp.geo import Place, clock
from mobiroute.vrp.insertion import Compiled, route_loads
from mobiroute.vrp.model import Instance
from mobiroute.vrp.schedule import compact_schedule
from mobiroute.vrp.solution import Solution, route_cost
from mobiroute.vrp.verify import Verdict

#: Signs for ISO 4217 codes; any other label is printed as given.
CURRENCY_SIGNS = {"RUB": "₽", "EUR": "€", "USD": "$", "CNY": "¥"}

KINDS = {
    "depart": ("выезд", "departure"),
    "pickup": ("погрузка", "pickup"),
    "delivery": ("выгрузка", "delivery"),
    "reload": ("перезагрузка", "reload"),
    "rest": ("перерыв", "rest"),
    "return": ("возврат", "return"),
}


@dataclass(frozen=True, slots=True)
class SheetRow:
    """One event of a route sheet; times in minutes after midnight."""

    trip: int
    kind: str
    order: str
    place: str
    lat: float | None
    lon: float | None
    window: tuple[float, float] | None
    arrive: float
    start: float
    end: float
    #: Load on board after the event, per dimension.
    load: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RouteSheet:
    vehicle: str
    vehicle_type: str
    hired: bool
    trips: int
    depart: float
    back: float
    distance: float
    driving: float
    waiting: float
    cost: float
    rows: tuple[SheetRow, ...]


def route_sheets(
    inst: Instance,
    solution: Solution,
    verdict: Verdict,
    places: Sequence[Place] | None = None,
) -> list[RouteSheet]:
    """One sheet per used vehicle of a verified plan.

    ``places`` (from :mod:`mobiroute.vrp.geo`) adds names and coordinates;
    without it a stop is named after its node.
    """
    if not verdict.feasible:
        raise ValueError("SHEETS_NEED_A_FEASIBLE_PLAN")
    if places is not None and len(places) != inst.n_nodes:
        raise ValueError("SHEETS_PLACES_MISMATCH")
    c = Compiled(inst)
    zeros = tuple(0.0 for _ in inst.dimensions)

    def where(node: int) -> tuple[str, float | None, float | None]:
        if places is not None:
            place = places[node]
            return place.label, place.lat, place.lon
        return inst.nodes[node].name or f"#{node}", None, None

    numbers: dict[str, int] = {}
    sheets: list[RouteSheet] = []
    for route in solution.routes:
        if not route.nodes:
            continue
        vt = inst.vehicle_types[route.vehicle_type]
        numbers[vt.id] = numbers.get(vt.id, 0) + 1
        timing = compact_schedule(inst, route.vehicle_type, route.nodes)
        if not timing.feasible:
            raise ValueError("SHEETS_ROUTES_MISMATCH")
        seq = [vt.start_depot, *route.nodes, vt.end_depot]
        starts = timing.earliest
        arrivals, driving = arrival_times(inst, route.vehicle_type, seq, starts, timing.rest_gap)
        loads = route_loads(c, route.nodes)
        rest = vt.breaks.duration if vt.breaks is not None else 0.0
        rows: list[SheetRow] = []
        trip = 1
        last = len(seq) - 1
        for k, node in enumerate(seq):
            info = inst.nodes[node]
            label, lat, lon = where(node)
            window: tuple[float, float] | None = (info.earliest, info.latest)
            order = ""
            if k == 0:
                kind, window = "depart", None
            elif k == last:
                kind, window = "return", None
            elif inst.reload_type_of(node) >= 0:
                kind = "reload"
                trip += 1
            else:
                req = inst.requests[inst.request_of(node)]
                kind = "pickup" if node == req.pickup else "delivery"
                order = req.id
            load = zeros if k == last else _tidy(loads[k])
            end = starts[k] + (info.service if k < last else 0.0)
            rows.append(
                SheetRow(
                    trip, kind, order, label, lat, lon, window, arrivals[k], starts[k], end, load
                )
            )
            if k == timing.rest_gap:
                rows.append(
                    SheetRow(trip, "rest", "", label, lat, lon, None, end, end, end + rest, load)
                )
        # Cost as the plan was priced (free-flow times), so sheets add up to the verdict.
        distance, free_flow, service = route_cost(inst, route.vehicle_type, route.nodes)
        money = (
            vt.fixed_cost
            + vt.cost_per_distance * distance
            + vt.cost_per_time * (free_flow + service)
        )
        waiting = math.fsum(max(0.0, row.start - row.arrive) for row in rows)
        sheets.append(
            RouteSheet(
                vehicle=f"{vt.id} #{numbers[vt.id]}",
                vehicle_type=vt.id,
                hired=vt.hired,
                trips=1 + sum(1 for n in route.nodes if inst.reload_type_of(n) >= 0),
                depart=starts[0],
                back=starts[-1],
                distance=distance,
                driving=driving,
                waiting=waiting,
                cost=money,
                rows=tuple(rows),
            )
        )
    if len(sheets) != len(verdict.routes):
        raise ValueError("SHEETS_ROUTES_MISMATCH")
    return sheets


def arrival_times(
    inst: Instance,
    vehicle_type: int,
    seq: Sequence[int],
    starts: Sequence[float],
    rest_gap: int | None,
) -> tuple[list[float], float]:
    """Arrival at every stop of ``seq`` given its service starts, and driving minutes.

    The start depot's arrival is its departure; the rest, when the route
    has one, is taken before driving on from stop ``rest_gap``. Under
    traffic a leg takes what the speed profile gives at its departure.
    """
    from mobiroute.vrp.traffic import arrive

    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    rest = vt.breaks.duration if vt.breaks is not None else 0.0
    out = [starts[0]]
    legs: list[float] = []
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        leave = starts[k - 1] + inst.nodes[a].service + (rest if k - 1 == rest_gap else 0.0)
        free = profile.time[a][b]
        reach = leave + free if profile.speed is None else arrive(profile.speed, leave, free)
        legs.append(reach - leave)
        out.append(reach)
    return out, math.fsum(legs)


def _cell(text: str) -> str:
    """A text cell that a spreadsheet will not run as a formula (OWASP CSV injection)."""
    return f"'{text}" if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


def _md(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    flat = " ".join(text.split())
    return escape(flat, quote=False).replace("|", "\\|")


def _tidy(values: Sequence[float]) -> tuple[float, ...]:
    """Loads without float dust: ``-6.8e-13`` kg is an empty body."""
    return tuple(round(q, 6) + 0.0 for q in values)


def _window(window: tuple[float, float] | None) -> tuple[str, str]:
    if window is None:
        return "", ""
    lo, hi = window
    return (clock(lo) if lo > 0 else ""), (clock(hi) if math.isfinite(hi) else "")


def sheets_csv(sheets: Sequence[RouteSheet], dimensions: Sequence[str]) -> str:
    """One row per event; times ``HH:MM``, loads per dimension."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        [
            "vehicle",
            "vehicle_type",
            "hired",
            "trip",
            "seq",
            "kind",
            "order",
            "place",
            "lat",
            "lon",
            "window_from",
            "window_to",
            "arrive",
            "start",
            "end",
            *[f"load_{d}" for d in dimensions],
        ]
    )
    for sheet in sheets:
        for seq, row in enumerate(sheet.rows):
            lo, hi = _window(row.window)
            writer.writerow(
                [
                    _cell(sheet.vehicle),
                    _cell(sheet.vehicle_type),
                    int(sheet.hired),
                    row.trip,
                    seq,
                    row.kind,
                    _cell(row.order),
                    _cell(row.place),
                    "" if row.lat is None else f"{row.lat:.6f}",
                    "" if row.lon is None else f"{row.lon:.6f}",
                    lo,
                    hi,
                    clock(row.arrive),
                    clock(row.start),
                    clock(row.end),
                    *[f"{q:g}" for q in row.load],
                ]
            )
    return out.getvalue()


def sheets_markdown(
    sheets: Sequence[RouteSheet],
    dimensions: Sequence[str],
    *,
    lang: str = "ru",
    currency: str = "",
) -> str:
    """One table per vehicle (Russian by default)."""
    ru = lang == "ru"
    k = 0 if ru else 1
    sign = CURRENCY_SIGNS.get(currency, currency)
    unit = f" {sign}" if sign else ""
    lines = ["# Маршрутные листы" if ru else "# Route sheets", ""]
    for sheet in sheets:
        own = ("наёмная" if ru else "hired") if sheet.hired else ("своя" if ru else "own")
        trips = _trips_ru(sheet.trips) if ru else f"{sheet.trips} trip{'s' * (sheet.trips > 1)}"
        cost = f"{sheet.cost:,.0f}".replace(",", " ") if ru else f"{sheet.cost:,.0f}"
        if ru:
            summary = (
                f"Выезд {clock(sheet.depart)}, возврат {clock(sheet.back)}; "
                f"{sheet.distance:.1f} км, за рулём {sheet.driving:.0f} мин, "
                f"ожидание {sheet.waiting:.0f} мин; стоимость {cost}{unit}"
            )
            header = "| Рейс | Что | Заказ | Где | Окно | Прибытие | Начало | Конец | "
        else:
            summary = (
                f"Departure {clock(sheet.depart)}, return {clock(sheet.back)}; "
                f"{sheet.distance:.1f} km, {sheet.driving:.0f} min driving, "
                f"{sheet.waiting:.0f} min waiting; cost {cost}{unit}"
            )
            header = "| Trip | What | Order | Where | Window | Arrive | Start | End | "
        lines += [
            f"## {_md(sheet.vehicle)} · {own} · {trips}",
            "",
            summary,
            "",
            header + " | ".join(dimensions) + " |",
            "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | "
            + " | ".join("---:" for _ in dimensions)
            + " |",
        ]
        for row in sheet.rows:
            lo, hi = _window(row.window)
            window = f"{lo}-{hi}" if lo or hi else ""
            cells = [
                str(row.trip),
                KINDS[row.kind][k],
                _md(row.order),
                _md(row.place),
                window,
                clock(row.arrive),
                clock(row.start),
                clock(row.end),
                *[f"{q:g}" for q in row.load],
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


_GANTT_STYLE = """<style>
  .drive { stroke: #898781; stroke-width: 2.5; stroke-linecap: round; }
  .wait { fill: #898781; fill-opacity: 0.16; }
  .rest { fill: #eda100; } .reload { fill: #52514e; } .pick { fill-opacity: 0.5; }
  .hour { stroke: #e1e0d9; stroke-width: 1; }
  @media (prefers-color-scheme: dark) {
    .drive { stroke: #898781; } .wait { fill-opacity: 0.22; }
    .rest { fill: #c98500; } .reload { fill: #c3c2b7; } .hour { stroke: #2c2c2a; }
  }
</style>"""


def sheets_svg(
    sheets: Sequence[RouteSheet], *, title: str, lang: str = "ru", currency: str = ""
) -> str:
    """Gantt chart of the day: one row per vehicle, hover a bar for the stop."""
    from mobiroute.reporting.svg import _series_css

    ru = lang == "ru"
    k = 0 if ru else 1
    if not sheets:
        raise ValueError("SHEETS_EMPTY")
    first = math.floor(min(s.depart for s in sheets) / 60) * 60
    last = math.ceil(max(s.back for s in sheets) / 60) * 60
    left, top, row_h, width = 168, 92, 34, 1000
    plot = width - left - 24
    height = top + row_h * len(sheets) + 40

    def x(t: float) -> float:
        return left + (t - first) / max(last - first, 1) * plot

    sign = CURRENCY_SIGNS.get(currency, currency)
    unit = f" {sign}" if sign else ""
    cost = sum(s.cost for s in sheets)
    distance = sum(s.distance for s in sheets)
    money = f"{cost:,.0f}".replace(",", " " if ru else ",")
    head = (
        f"{len(sheets)} машин · {distance:.1f} км · стоимость {money}{unit}"
        if ru
        else f"{len(sheets)} vehicles · {distance:.1f} km · cost {money}{unit}"
    )
    legend = (
        "линия — в пути · серый фон — ожидание · цвет — выгрузка (светлее — погрузка) · "
        "тёмное — перезагрузка · жёлтое — перерыв"
        if ru
        else "line: driving · grey: waiting · colour: delivery (lighter: pickup) · "
        "dark: reload · amber: rest"
    )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        _series_css(len(sheets)),
        _GANTT_STYLE,
        f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
        f'<text class="ink" x="24" y="32" font-size="17" font-weight="600">{escape(title)}</text>',
        f'<text class="ink2" x="24" y="54" font-size="12.5">{escape(head)}</text>',
        f'<text class="muted" x="24" y="74" font-size="12">{escape(legend)}</text>',
    ]
    for t in range(first, last + 1, 60):
        out.append(
            f'<line class="hour" x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" '
            f'y2="{height - 34}"/>'
        )
        out.append(
            f'<text class="muted" x="{x(t):.1f}" y="{height - 16}" font-size="11.5" '
            f'text-anchor="middle">{clock(t)}</text>'
        )
    for r, sheet in enumerate(sheets):
        y = top + r * row_h + row_h / 2
        own = ("наёмная" if ru else "hired") if sheet.hired else ("своя" if ru else "own")
        trips = _trips_ru(sheet.trips) if ru else f"{sheet.trips} trip{'s' * (sheet.trips > 1)}"
        out.append(
            f'<text class="ink" x="24" y="{y - 2:.1f}" font-size="13" font-weight="600">'
            f"{escape(sheet.vehicle)}</text>"
        )
        out.append(
            f'<text class="muted" x="24" y="{y + 12:.1f}" font-size="11">{own} · {trips}</text>'
        )
        prev = sheet.rows[0]
        for row in sheet.rows[1:]:
            if row.kind != "rest" and row.arrive > prev.end + 1e-6:
                out.append(
                    f'<line class="drive" x1="{x(prev.end):.1f}" y1="{y:.1f}" '
                    f'x2="{x(row.arrive):.1f}" y2="{y:.1f}"/>'
                )
            if row.start > row.arrive + 0.5:
                out.append(
                    f'<rect class="wait" x="{x(row.arrive):.1f}" y="{y - 8:.1f}" '
                    f'width="{x(row.start) - x(row.arrive):.1f}" height="16" rx="2"/>'
                )
            if row.end > row.start + 1e-6:
                cls = {"rest": "rest", "reload": "reload", "pickup": f"f{r} pick"}.get(
                    row.kind, f"f{r}"
                )
                tip = f"{KINDS[row.kind][k]} {row.order} {row.place} {clock(row.start)}-"
                tip += clock(row.end)
                out.append(
                    f'<rect class="{cls}" x="{x(row.start):.1f}" y="{y - 8:.1f}" '
                    f'width="{max(x(row.end) - x(row.start), 1.5):.1f}" height="16" rx="2">'
                    f"<title>{escape(' '.join(tip.split()))}</title></rect>"
                )
            prev = row
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _trips_ru(n: int) -> str:
    """Russian plural: 1 рейс, 2 рейса, 5 рейсов."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} рейс"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} рейса"
    return f"{n} рейсов"
