"""SVG map of a rich-VRP plan (no dependencies, light and dark themes).

Equal scale on both axes; for latitude/longitude instances the x axis is
shrunk by ``cos(latitude)`` so distances look right. Filled circle = pickup,
ring = delivery, square = depot, one colour per route, legend by vehicle type.
"""

from __future__ import annotations

import math
from html import escape

from mobiroute.reporting.svg import _series_css
from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import Solution, evaluate


def routes_svg(inst: Instance, solution: Solution, *, title: str, size: int = 520) -> str:
    xs = [nd.x for nd in inst.nodes]
    ys = [nd.y for nd in inst.nodes]
    geo = (
        all(-180 <= x <= 180 for x in xs)
        and all(-90 <= y <= 90 for y in ys)
        and inst.source == "sartori-buriol"
    )
    shrink = math.cos(math.radians(sum(ys) / len(ys))) if geo else 1.0
    x0, y0 = min(xs), min(ys)
    span = max((max(xs) - x0) * shrink, max(ys) - y0) or 1.0
    left, top = 24, 70

    def px(x: float) -> float:
        return left + (x - x0) * shrink / span * size

    def py(y: float) -> float:
        return top + size - (y - y0) / span * size

    routes = [r for r in solution.routes if r.nodes]
    cost = evaluate(inst, solution)
    served = len(inst.requests) - len(solution.unassigned)
    width, height = left + size + 230, top + size + 30
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        _series_css(len(routes)),
        f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
        f'<text class="ink" x="{left}" y="30" font-size="17" font-weight="600">'
        f"{escape(title)}</text>",
        f'<text class="ink2" x="{left}" y="52" font-size="12.5">{cost.vehicles} vehicles · '
        f"distance {cost.distance:.1f} · {served}/{len(inst.requests)} orders · "
        "filled = pickup, ring = delivery, square = depot</text>",
    ]
    for k, route in enumerate(routes):
        vt = inst.vehicle_types[route.vehicle_type]
        seq = [vt.start_depot, *route.nodes, vt.end_depot]
        pts = " ".join(f"{px(inst.nodes[n].x):.1f},{py(inst.nodes[n].y):.1f}" for n in seq)
        out.append(
            f'<polyline class="s{k}" points="{pts}" fill="none" stroke-width="2" '
            f'stroke-linejoin="round" opacity="0.9"><title>{escape(vt.id)}: '
            f"{len(route.nodes)} stops</title></polyline>"
        )
        for n in route.nodes:
            if inst.request_of(n) < 0:
                continue  # a reload stop is drawn as its depot
            req = inst.requests[inst.request_of(n)]
            cx, cy = px(inst.nodes[n].x), py(inst.nodes[n].y)
            label = escape(f"{req.id} {'pickup' if n == req.pickup else 'delivery'}")
            if n == req.pickup:
                out.append(
                    f'<circle class="f{k}" cx="{cx:.1f}" cy="{cy:.1f}" r="3.6">'
                    f"<title>{label}</title></circle>"
                )
            else:
                out.append(
                    f'<circle class="s{k} surface" cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" '
                    f'stroke-width="1.8"><title>{label}</title></circle>'
                )
    for r in sorted(solution.unassigned):
        for n in inst.requests[r].nodes:
            cx, cy = px(inst.nodes[n].x), py(inst.nodes[n].y)
            out.append(
                f'<circle class="muted" cx="{cx:.1f}" cy="{cy:.1f}" r="3">'
                f"<title>{escape(inst.requests[r].id)}: unserved</title></circle>"
            )
    depots = {vt.start_depot for vt in inst.vehicle_types} | {
        vt.end_depot for vt in inst.vehicle_types
    }
    for d in sorted(depots):
        cx, cy = px(inst.nodes[d].x), py(inst.nodes[d].y)
        out.append(
            f'<rect class="depot" x="{cx - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10">'
            f"<title>{escape(inst.nodes[d].name or 'depot')}</title></rect>"
        )
    legend_x = left + size + 24
    out.append(
        f'<text class="ink" x="{legend_x}" y="{top + 4}" font-size="13" font-weight="600">'
        "Vehicles by type</text>"
    )
    for row, (vid, count) in enumerate(sorted(cost.vehicles_by_type.items())):
        out.append(
            f'<text class="ink2" x="{legend_x}" y="{top + 26 + 18 * row}" font-size="12.5">'
            f"{escape(vid)}: {count}</text>"
        )
    out.append("</svg>")
    return "\n".join(out)
