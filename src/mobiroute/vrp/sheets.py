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
from itertools import pairwise

from mobiroute.vrp.geo import Place, clock
from mobiroute.vrp.insertion import Compiled, route_loads
from mobiroute.vrp.model import Instance
from mobiroute.vrp.schedule import compact_schedule
from mobiroute.vrp.solution import Solution, charged_time, route_cost
from mobiroute.vrp.verify import Verdict

#: Signs for ISO 4217 codes; any other label is printed as given.
CURRENCY_SIGNS = {"RUB": "₽", "EUR": "€", "USD": "$", "CNY": "¥"}

KINDS = {
    "depart": ("загрузка и выезд", "loading, departure"),
    "pickup": ("погрузка", "pickup"),
    "delivery": ("выгрузка", "delivery"),
    "reload": ("загрузка на складе", "reload"),
    "rest": ("перерыв", "break"),
    "rest_first": ("перерыв, 1-я часть", "break, first part"),
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
    #: Per trip, the depot goods in loading order: the last drop goes in first.
    loading: tuple[tuple[str, ...], ...] = ()
    #: Labour-rule check: the longest drive between breaks and the limits it
    #: is held to (``None`` where the vehicle type sets no such limit).
    longest_stint: float = 0.0
    stint_limit: float | None = None
    driving_limit: float | None = None
    shift_limit: float | None = None

    @property
    def shift(self) -> float:
        """On-duty time from departure to return, waiting included."""
        return self.back - self.depart

    def compliant(self) -> bool:
        """Every labour limit of the vehicle type holds on this sheet."""
        checks = (
            (self.longest_stint, self.stint_limit),
            (self.driving, self.driving_limit),
            (self.shift, self.shift_limit),
        )
        return all(limit is None or value <= limit + 1e-6 for value, limit in checks)


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
        gap = timing.rest_gap
        rest_first = gap is None or _rest_before_drive(inst, route.vehicle_type, seq, gap)
        first_gap = timing.first_gap
        rule = vt.breaks
        split = rule.split if rule is not None and first_gap is not None else None
        rest = 0.0 if rule is None else (rule.duration if split is None else split[1])
        first_len = 0.0 if split is None else split[0]
        arrivals, driving = arrival_times(
            inst,
            route.vehicle_type,
            seq,
            starts,
            gap,
            rest_first=rest_first,
            rest_len=rest,
            first_gap=first_gap,
            first_len=first_len,
        )
        loads = route_loads(c, route.nodes)
        rows: list[SheetRow] = []
        trip = 1
        last = len(seq) - 1
        for k, node in enumerate(seq):
            info = inst.nodes[node]
            label, lat, lon = where(node)
            arrive = arrivals[k]
            if gap is not None and not rest_first and k == gap + 1:
                # Lemma 1's other case: drive first, rest on arrival, then work.
                here = rows[-1].load
                rows.append(
                    SheetRow(
                        trip, "rest", "", label, lat, lon, None, arrive, arrive, arrive + rest, here
                    )
                )
                arrive += rest
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
                SheetRow(trip, kind, order, label, lat, lon, window, arrive, starts[k], end, load)
            )
            if k == first_gap:
                # The first part of a split break, before the drive: it does
                # not reset the driving counter, the second part does.
                rows.append(
                    SheetRow(
                        trip,
                        "rest_first",
                        "",
                        label,
                        lat,
                        lon,
                        None,
                        end,
                        end,
                        end + first_len,
                        load,
                    )
                )
            if k == gap and rest_first:
                pause_at = end + first_len if k == first_gap else end
                rows.append(
                    SheetRow(
                        trip,
                        "rest",
                        "",
                        label,
                        lat,
                        lon,
                        None,
                        pause_at,
                        pause_at,
                        pause_at + rest,
                        load,
                    )
                )
        # Cost as the plan was priced (free-flow times, or the shift with
        # time_cost == "duty"), so sheets add up to the verdict.
        distance, _free_flow, _service = route_cost(inst, route.vehicle_type, route.nodes)
        paid = charged_time(inst, route.vehicle_type, route.nodes)
        money = vt.fixed_cost + vt.cost_per_distance * distance + vt.cost_per_time * paid
        waiting = math.fsum(max(0.0, row.start - row.arrive) for row in rows)
        # Continuous driving between breaks: legs add up until a rest row.
        stint = longest = 0.0
        prev = rows[0]
        for row in rows[1:]:
            stint += max(0.0, row.arrive - prev.end)
            longest = max(longest, stint)
            if row.kind == "rest":
                stint = 0.0
            prev = row
        rule = vt.breaks
        # Depot goods go into the body in reverse order of their drops (LIFO).
        picked = {row.order for row in rows if row.kind == "pickup"}
        by_trip: dict[int, list[str]] = {}
        for row in rows:
            if row.kind == "delivery" and row.order not in picked:
                by_trip.setdefault(row.trip, []).append(row.order)
        loading = tuple(tuple(reversed(by_trip.get(t, []))) for t in range(1, trip + 1))
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
                loading=loading,
                longest_stint=longest,
                stint_limit=None if rule is None else rule.max_driving,
                driving_limit=None if rule is None else 2 * rule.max_driving,
                shift_limit=vt.max_duration,
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
    *,
    rest_first: bool = True,
    rest_len: float | None = None,
    first_gap: int | None = None,
    first_len: float = 0.0,
) -> tuple[list[float], float]:
    """Arrival at every stop of ``seq`` given its service starts, and driving minutes.

    The start depot's arrival is its departure. The rest, when the route has
    one, sits in gap ``rest_gap``: before the drive (``rest_first``) or on
    arrival at the next stop, before its work. Under traffic a leg takes
    what the speed profile gives at its departure.
    """
    from mobiroute.vrp.traffic import arrive

    vt = inst.vehicle_types[vehicle_type]
    profile = inst.profiles[vt.profile]
    rest = rest_len if rest_len is not None else (vt.breaks.duration if vt.breaks else 0.0)
    out = [starts[0]]
    legs: list[float] = []
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        pause = rest if k - 1 == rest_gap and rest_first else 0.0
        if k - 1 == first_gap:
            pause += first_len
        leave = starts[k - 1] + inst.nodes[a].service + pause
        free = profile.time[a][b]
        reach = leave + free if profile.speed is None else arrive(profile.speed, leave, free)
        legs.append(reach - leave)
        out.append(reach)
    return out, math.fsum(legs)


def _rest_before_drive(inst: Instance, vehicle_type: int, seq: Sequence[int], gap: int) -> bool:
    """Whether the rest of gap ``gap`` may come before its drive (Lemma 1).

    Both stints around the rest must stay within the driving limit; the
    verifier accepted the gap, so if resting before the drive breaks that,
    resting after it does not.
    """
    vt = inst.vehicle_types[vehicle_type]
    assert vt.breaks is not None
    time = inst.profiles[vt.profile].time
    legs = [time[a][b] for a, b in pairwise(seq)]
    before = math.fsum(legs[:gap])
    limit = vt.breaks.max_driving + 1e-6
    return before <= limit and math.fsum(legs) - before <= limit


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
        leave = sheet.rows[0].end
        if ru:
            start = f"Начало {clock(sheet.depart)}, выезд" if leave > sheet.depart else "Выезд"
            summary = (
                f"{start} {clock(leave)}, возврат {clock(sheet.back)}; "
                f"{_dec(sheet.distance, ru)} км, за рулём {sheet.driving:.0f} мин, "
                f"ожидание {sheet.waiting:.0f} мин; стоимость {cost}{unit}"
            )
            header = "| Рейс | Что | Заказ | Где | Окно | Прибытие | Начало | Конец | "
            labour = _labour(sheet, ru=True)
        else:
            start = (
                f"Start {clock(sheet.depart)}, departure" if leave > sheet.depart else "Departure"
            )
            summary = (
                f"{start} {clock(leave)}, return {clock(sheet.back)}; "
                f"{sheet.distance:.1f} km, {sheet.driving:.0f} min driving, "
                f"{sheet.waiting:.0f} min waiting; cost {cost}{unit}"
            )
            header = "| Trip | What | Order | Where | Window | Arrive | Start | End | "
            labour = _labour(sheet, ru=False)
        lines += [
            f"## {_md(sheet.vehicle)} · {own} · {trips}",
            "",
            summary,
            "",
            *([labour, ""] if labour else []),
            *([_loading(sheet, ru=ru), ""] if any(sheet.loading) else []),
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
                *[_dec(q, ru, "g") for q in row.load],
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
        f"{len(sheets)} машин · {_dec(distance, True)} км · стоимость {money}{unit}"
        if ru
        else f"{len(sheets)} vehicles · {distance:.1f} km · cost {money}{unit}"
    )
    legend = (
        "линия — в пути · серый фон — ожидание · цвет — выгрузка (светлее — погрузка) · "
        "тёмное — загрузка на складе · жёлтое — перерыв"
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
            if row.arrive > prev.end + 1e-6:
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
                cls = {
                    "rest": "rest",
                    "rest_first": "rest",
                    "reload": "reload",
                    "pickup": f"f{r} pick",
                }.get(row.kind, f"f{r}")
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


def _dec(value: float, ru: bool, spec: str = ".1f") -> str:
    """A number for people: decimal comma in Russian (CSV keeps the point)."""
    text = format(value, spec)
    return text.replace(".", ",") if ru else text


def _loading(sheet: RouteSheet, *, ru: bool) -> str:
    """Loading order at the depot per trip, last drop first (LIFO)."""
    trips = [(t, orders) for t, orders in enumerate(sheet.loading, start=1) if orders]
    if ru:
        body = "; ".join(f"рейс {t}: " + ", ".join(o) for t, o in trips)
        return f"Порядок загрузки на складе, обратный порядку выгрузки: {body}."
    body = "; ".join(f"trip {t}: " + ", ".join(o) for t, o in trips)
    return f"Loading order at the depot, reverse of the drops: {body}."


def _hm(minutes: float) -> str:
    total = round(minutes)
    return f"{total // 60}:{total % 60:02d}"


def _labour(sheet: RouteSheet, *, ru: bool) -> str:
    """One line on the driving-time rules: value against limit for each."""
    parts = []
    if sheet.stint_limit is not None:
        name = "непрерывно за рулём" if ru else "longest drive between breaks"
        parts.append(f"{name} {_hm(sheet.longest_stint)} / {_hm(sheet.stint_limit)}")
    if sheet.driving_limit is not None:
        name = "за рулём за смену" if ru else "driving in the shift"
        parts.append(f"{name} {_hm(sheet.driving)} / {_hm(sheet.driving_limit)}")
    if sheet.shift_limit is not None:
        name = "смена" if ru else "shift"
        parts.append(f"{name} {_hm(sheet.shift)} / {_hm(sheet.shift_limit)}")
    if not parts:
        return ""
    if ru:
        head = "Режим труда и отдыха " + ("соблюдён" if sheet.compliant() else "НАРУШЕН")
    else:
        head = "Driving-time rules " + ("met" if sheet.compliant() else "VIOLATED")
    return f"{head}: " + "; ".join(parts) + "."


def _trips_ru(n: int) -> str:
    """Russian plural: 1 рейс, 2 рейса, 5 рейсов."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} рейс"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} рейса"
    return f"{n} рейсов"
