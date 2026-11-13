"""Dependency-free SVG views of a verified literature plan.

Two figures a non-specialist can read without the code: where each vehicle
goes (route map, equal aspect ratio, shape encodes pickup / dropoff / depot)
and when (one row per request: its tight window, the service starts the
verifier computed, and the ride-time limit). Colors follow the entity (route),
never its rank; light and dark themes are both specified.
"""

from __future__ import annotations

from html import escape

from mobiroute.benchmarks.cordeau_exact import CordeauInstance, ExactVerdict

# Categorical slots validated for <= 3 simultaneous series (light / dark).
_SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")
_SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9")

_STYLE = """<style>
  .surface {{ fill: #fcfcfb; }}
  .ink {{ fill: #0b0b0b; }} .ink2 {{ fill: #52514e; }} .muted {{ fill: #898781; }}
  .grid {{ stroke: #e1e0d9; stroke-width: 1; }} .axis {{ stroke: #c3c2b7; stroke-width: 1; }}
  .window {{ fill: #898781; fill-opacity: 0.22; }}
  .limit {{ stroke: #898781; stroke-width: 1; stroke-dasharray: 3 3; }}
  .depot {{ fill: #0b0b0b; }}
  {light}
  @media (prefers-color-scheme: dark) {{
    .surface {{ fill: #1a1a19; }}
    .ink {{ fill: #f0efec; }} .ink2 {{ fill: #c3c2b7; }}
    .grid {{ stroke: #2c2c2a; }} .axis {{ stroke: #383835; }}
    .depot {{ fill: #f0efec; }}
    {dark}
  }}
  text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
</style>"""


def _series_css(count: int) -> str:
    light, dark = [], []
    for k in range(count):
        lc, dc = _SERIES_LIGHT[k % len(_SERIES_LIGHT)], _SERIES_DARK[k % len(_SERIES_DARK)]
        light.append(f".s{k} {{ stroke: {lc}; }} .f{k} {{ fill: {lc}; }}")
        dark.append(f".s{k} {{ stroke: {dc}; }} .f{k} {{ fill: {dc}; }}")
    return _STYLE.format(light=" ".join(light), dark=" ".join(dark))


def _node_label(instance: CordeauInstance, node: int) -> str:
    n = instance.n_requests
    if node in (0, instance.end_depot):
        return "depot"
    return f"pickup {node}" if node <= n else f"dropoff {node - n}"


def route_map_svg(instance: CordeauInstance, verdict: ExactVerdict, *, title: str) -> str:
    """Routes on the instance plane; equal scale on both axes keeps geometry honest."""
    size, left, top = 440, 56, 76
    xs = [node.x for node in instance.nodes]
    ys = [node.y for node in instance.nodes]
    lo = min(min(xs), min(ys))
    span = max(max(xs), max(ys)) - lo or 1.0

    def px(x: float) -> float:
        return left + (x - lo) / span * size

    def py(y: float) -> float:
        return top + size - (y - lo) / span * size

    width, height = left + size + 250, top + size + 48
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        _series_css(len(verdict.routes)),
        f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
        f'<text class="ink" x="{left}" y="30" font-size="17" font-weight="600">'
        f"{escape(title)}</text>",
        f'<text class="ink2" x="{left}" y="52" font-size="12.5">Equal-scale plane · '
        f"filled = pickup, ring = dropoff, square = depot · hover a mark for details</text>",
    ]
    tick = 5.0 if span > 10 else 1.0
    value = (lo // tick) * tick
    while value <= lo + span + 1e-9:
        if value >= lo - 1e-9:
            out.append(
                f'<line class="grid" x1="{px(value):.1f}" y1="{top}" x2="{px(value):.1f}" '
                f'y2="{top + size}"/><line class="grid" x1="{left}" y1="{py(value):.1f}" '
                f'x2="{left + size}" y2="{py(value):.1f}"/>'
            )
        value += tick
    for r, route in enumerate(verdict.routes):
        points = " ".join(
            f"{px(instance.nodes[k].x):.1f},{py(instance.nodes[k].y):.1f}" for k in route.sequence
        )
        out.append(
            f'<polyline class="s{r}" fill="none" stroke-width="2" stroke-linejoin="round" '
            f'points="{points}"><title>Route {r + 1}: {len(route.sequence) - 2} stops, '
            f"cost {route.cost:.2f}</title></polyline>"
        )
    for r, route in enumerate(verdict.routes):
        for node, start in zip(route.sequence[1:-1], route.service_start[1:-1], strict=True):
            info = instance.nodes[node]
            tip = (
                f"{_node_label(instance, node)} · route {r + 1} · window "
                f"[{info.earliest}, {info.latest}] · service starts {start:.1f}"
            )
            cx, cy = px(info.x), py(info.y)
            if node <= instance.n_requests:
                out.append(
                    f'<circle class="f{r}" cx="{cx:.1f}" cy="{cy:.1f}" r="4.5">'
                    f"<title>{escape(tip)}</title></circle>"
                )
            else:
                out.append(
                    f'<circle class="s{r} surface" cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" '
                    f'stroke-width="2"><title>{escape(tip)}</title></circle>'
                )
    depot = instance.nodes[0]
    out.append(
        f'<rect class="depot" x="{px(depot.x) - 5:.1f}" y="{py(depot.y) - 5:.1f}" width="10" '
        f'height="10"><title>depot</title></rect>'
    )
    lx = left + size + 28
    out.append(
        f'<text class="ink" x="{lx}" y="{top + 8}" font-size="13" font-weight="600">Routes</text>'
    )
    for r, route in enumerate(verdict.routes):
        y = top + 34 + r * 40
        out.append(
            f'<line class="s{r}" x1="{lx}" y1="{y}" x2="{lx + 22}" y2="{y}" stroke-width="2"/>'
            f'<text class="ink" x="{lx + 30}" y="{y + 4}" font-size="12.5">Vehicle {r + 1}</text>'
            f'<text class="ink2" x="{lx + 30}" y="{y + 20}" font-size="11.5">'
            f"{len(route.sequence) - 2} stops · cost {route.cost:.2f}</text>"
        )
    y = top + 34 + len(verdict.routes) * 40 + 8
    out.append(
        f'<text class="ink2" x="{lx}" y="{y}" font-size="12">Total cost {verdict.cost:.2f}</text>'
        f'<text class="ink2" x="{lx}" y="{y + 18}" font-size="12">'
        f"{len(verdict.served_requests)}/{verdict.requests_total} requests served</text>"
        f'<text class="muted" x="{lx}" y="{y + 36}" font-size="11.5">'
        f"{'verified feasible' if verdict.feasible else 'NOT feasible'} "
        f"(difference constraints)</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


def timeline_svg(instance: CordeauInstance, verdict: ExactVerdict, *, title: str) -> str:
    """One row per request: tight window, service starts, ride-time limit."""
    n = instance.n_requests
    horizon = max(instance.nodes[instance.end_depot].latest, 1)
    route_of: dict[int, int] = {}
    starts: dict[int, float] = {}
    for r, route in enumerate(verdict.routes):
        for node, start in zip(route.sequence, route.service_start, strict=True):
            starts[node] = start
            if 1 <= node <= n:
                route_of[node] = r
    rows = sorted(route_of, key=lambda i: starts[i])
    left, top, plot, row_h = 92, 76, 720, 22
    width, height = left + plot + 40, top + row_h * max(len(rows), 1) + 70

    def tx(t: float) -> float:
        return left + min(max(t, 0.0), horizon) / horizon * plot

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        _series_css(len(verdict.routes)),
        f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
        f'<text class="ink" x="{left}" y="30" font-size="17" font-weight="600">'
        f"{escape(title)}</text>",
        f'<text class="ink2" x="{left}" y="52" font-size="12.5">Shaded: the request\'s tight '
        f"window · dot = pickup start, ring = dropoff start · dashed: "
        f"ride limit {instance.max_ride_time} min</text>",
    ]
    bottom = top + row_h * len(rows)
    step = 60 if horizon > 120 else 10
    for t in range(0, horizon + 1, step):
        out.append(
            f'<line class="grid" x1="{tx(t):.1f}" y1="{top - 6}" x2="{tx(t):.1f}" y2="{bottom}"/>'
            f'<text class="muted" x="{tx(t):.1f}" y="{bottom + 18}" font-size="11" '
            f'text-anchor="middle">{t}</text>'
        )
    out.append(
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{left + plot}" y2="{bottom}"/>'
        f'<text class="muted" x="{left + plot / 2:.1f}" y="{bottom + 38}" font-size="11.5" '
        f'text-anchor="middle">minutes since depot opening</text>'
    )
    for k, i in enumerate(rows):
        y = top + k * row_h + row_h / 2
        r = route_of[i]
        out.append(
            f'<text class="ink2" x="{left - 10}" y="{y + 4:.1f}" font-size="11.5" '
            f'text-anchor="end">request {i}</text>'
        )
        for node in (i, i + n):
            info = instance.nodes[node]
            if info.latest - info.earliest < horizon:
                out.append(
                    f'<rect class="window" x="{tx(info.earliest):.1f}" y="{y - 7:.1f}" '
                    f'width="{max(tx(info.latest) - tx(info.earliest), 2):.1f}" height="14" '
                    f'rx="3"><title>{_node_label(instance, node)} window '
                    f"[{info.earliest}, {info.latest}]</title></rect>"
                )
        pick, drop = starts[i], starts[i + n]
        limit = pick + instance.nodes[i].service + instance.max_ride_time
        ride = drop - pick - instance.nodes[i].service
        out.append(
            f'<line class="limit" x1="{tx(pick):.1f}" y1="{y:.1f}" x2="{tx(limit):.1f}" '
            f'y2="{y:.1f}"/>'
            f'<line class="s{r}" x1="{tx(pick):.1f}" y1="{y:.1f}" x2="{tx(drop):.1f}" '
            f'y2="{y:.1f}" stroke-width="2"><title>request {i} · vehicle {r + 1} · ride '
            f"{ride:.1f} of {instance.max_ride_time} min</title></line>"
            f'<circle class="f{r}" cx="{tx(pick):.1f}" cy="{y:.1f}" r="4"/>'
            f'<circle class="s{r} surface" cx="{tx(drop):.1f}" cy="{y:.1f}" r="4" '
            f'stroke-width="2"/>'
        )
    lx = left
    ly = bottom + 56
    for r in range(len(verdict.routes)):
        out.append(
            f'<line class="s{r}" x1="{lx + r * 120}" y1="{ly}" x2="{lx + r * 120 + 22}" '
            f'y2="{ly}" stroke-width="2"/><text class="ink" x="{lx + r * 120 + 30}" '
            f'y="{ly + 4}" font-size="12">Vehicle {r + 1}</text>'
        )
    out.append("</svg>")
    return "\n".join(out)
