# ruff: noqa: RUF001
"""README figures: key results, the infeasibility certificate, Lemma 4.

Dependency-free SVG with light and dark themes. Numbers come from
benchmark/results/*.json where a result file exists.

    python benchmark/make_readme_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"

STYLE = """<style>
  .surface { fill: #fcfcfb; } .ink { fill: #0b0b0b; } .ink2 { fill: #52514e; }
  .muted { fill: #898781; } .line { stroke: #c3c2b7; } .grid { stroke: #e1e0d9; }
  .accent { fill: #2a78d6; } .saccent { stroke: #2a78d6; } .bad { fill: #d03b3b; }
  .sbad { stroke: #d03b3b; } .node { fill: #fcfcfb; stroke: #52514e; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; } .ink { fill: #f0efec; } .ink2 { fill: #c3c2b7; }
    .line { stroke: #383835; } .grid { stroke: #2c2c2a; }
    .accent { fill: #3987e5; } .saccent { stroke: #3987e5; }
    .node { fill: #1a1a19; stroke: #c3c2b7; }
  }
  text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
</style>"""

ARROW = (
    '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
    'markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" '
    'class="muted"/></marker><marker id="b" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path '
    'd="M0,0L10,5L0,10z" class="bad"/></marker></defs>'
)


def svg(width: int, height: int, label: str, body: list[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{label}">',
            STYLE,
            ARROW,
            f'<rect class="surface" width="{width}" height="{height}" rx="10"/>',
            *body,
            "</svg>\n",
        ]
    )


def _results() -> dict[str, str]:
    bench = json.loads((ROOT / "benchmark/results/vrp/vrp_benchmark.json").read_text())
    sol = [r for r in bench["rows"] if r["family"] == "solomon"]
    at_ref = sum(r["vehicles"] <= r["ref_vehicles"] for r in sol)
    exact = json.loads((ROOT / "benchmark/results/exact_vs_alns.json").read_text())["rows"]
    proven = sum(abs(r["gap_pct"]) < 1e-9 for r in exact)
    return {
        "solomon": f"{at_ref} / {len(sol)}",
        "exact": f"{proven} / {len(exact)}",
    }


def kpi(lang: str) -> str:
    r = _results()
    tiles = {
        "ru": [
            (r["solomon"], "Solomon: число машин", "лучшего известного решения"),
            (r["exact"], "оптимумов CP-SAT", "найдено эвристикой"),
            ("15 · 3 · 0", "против OR-Tools, 10 с:", "лучше · наравне · хуже"),
            ("−18%", "стоимость грузового дня", "и на две машины меньше"),
            ("×49", "ядро Rust против Python", "при том же плане"),
            ("0,1 мс", "ответ диспетчера", "на новую заявку"),
        ],
        "en": [
            (r["solomon"], "Solomon instances at", "the best-known fleet size"),
            (r["exact"], "CP-SAT optima", "found by the heuristic"),
            ("15 · 3 · 0", "vs OR-Tools, 10 s:", "better · equal · worse"),
            ("−18%", "cost of a cargo day,", "two vehicles fewer"),
            ("×49", "Rust kernel vs Python,", "identical plan"),
            ("0.1 ms", "dispatcher response", "to a new order"),
        ],
    }[lang]
    w, h, cols = 960, 250, 3
    tw, th = 296, 96
    body = []
    for i, (value, l1, l2) in enumerate(tiles):
        x = 24 + (i % cols) * (tw + 12)
        y = 24 + (i // cols) * (th + 12)
        body += [
            f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="8" fill="none" '
            f'class="line" stroke-width="1"/>',
            f'<rect x="{x}" y="{y + 18}" width="3" height="{th - 36}" rx="1.5" class="accent"/>',
            f'<text class="ink" x="{x + 20}" y="{y + 50}" font-size="30" '
            f'font-weight="600">{value}</text>',
            f'<text class="ink2" x="{x + 20}" y="{y + 70}" font-size="13">{l1}</text>',
            f'<text class="ink2" x="{x + 20}" y="{y + 86}" font-size="13">{l2}</text>',
        ]
    title = "Ключевые результаты" if lang == "ru" else "Key results"
    return svg(w, h, title, body)


def certificate(lang: str) -> str:
    ru = lang == "ru"
    z, c, p = (110, 190), (420, 70), (420, 310)
    names = (
        ("0", "начало отсчёта" if ru else "time origin", z),
        ("c", "клиент" if ru else "customer", c),
        ("p", "поставщик" if ru else "supplier", p),
    )
    arcs = [
        (z, c, "+720", "B_c ≤ 12:00"),
        (
            c,
            p,
            "−188,8" if ru else "−188.8",
            "B_c ≥ B_p + 26 + 162,8" if ru else "B_c ≥ B_p + 26 + 162.8",
        ),
        (p, z, "−540", "B_p ≥ 09:00"),
    ]
    body = []
    for (x1, y1), (x2, y2), weight, rule in arcs:
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / n, dy / n
        a, b = (x1 + ux * 34, y1 + uy * 34), (x2 - ux * 34, y2 - uy * 34)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ox = 18 if (x1 + x2) / 2 > 300 else -26
        my += 0 if ox > 0 else (-26 if dy > 0 else 50)
        anchor = "start" if ox > 0 else "end"
        body += [
            f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
            f'class="sbad" stroke-width="2" marker-end="url(#b)"/>',
            f'<text class="ink" x="{mx + ox:.1f}" y="{my - 4:.1f}" font-size="16" '
            f'font-weight="600" text-anchor="{anchor}">{weight}</text>',
            f'<text class="ink2" x="{mx + ox:.1f}" y="{my + 14:.1f}" font-size="12" '
            f'text-anchor="{anchor}">{rule}</text>',
        ]
    for key, name, (x, y) in names:
        body += [
            f'<circle cx="{x}" cy="{y}" r="30" class="node" stroke-width="2"/>',
            f'<text class="ink" x="{x}" y="{y + 6}" font-size="18" font-weight="600" '
            f'text-anchor="middle">{key}</text>',
            f'<text class="ink2" x="{x}" y="{y + 50}" font-size="12.5" '
            f'text-anchor="middle">{name}</text>',
        ]
    head = "Отрицательный цикл = сертификат" if ru else "Negative cycle = certificate"
    total = "720 − 188,8 − 540 = −8,8 мин" if ru else "720 − 188.8 − 540 = −8.8 min"
    note = (
        (
            "Вес цикла меньше нуля: рейс невозможен",
            "при любом расписании, не хватает 8,8 мин.",
            "Каждая дуга — одно правило: B_v − B_u ≤ w.",
        )
        if ru
        else (
            "The cycle weight is negative: no schedule",
            "exists, 8.8 minutes are missing.",
            "Each arc is one rule: B_v − B_u ≤ w.",
        )
    )
    body += [
        f'<text class="ink" x="600" y="110" font-size="17" font-weight="600">{head}</text>',
        f'<text class="bad" x="600" y="150" font-size="24" font-weight="600">{total}</text>',
        f'<text class="ink2" x="600" y="185" font-size="13">{note[0]}</text>',
        f'<text class="ink2" x="600" y="203" font-size="13">{note[1]}</text>',
        f'<text class="muted" x="600" y="235" font-size="13">{note[2]}</text>',
    ]
    return svg(960, 380, head, body)


def lemma4(lang: str) -> str:
    ru = lang == "ru"
    # Van #1 of the Chelny example: earliest return E = 13:34, shortest shift c = 3:20.
    e_min, c_min, lo, hi = 13 * 60 + 34, 200, 7 * 60, 11 * 60 + 30
    x0, x1, y0, y1 = 80, 600, 300, 50
    dmax = e_min - lo

    def px(t: float) -> float:
        return x0 + (t - lo) / (hi - lo) * (x1 - x0)

    def py(d: float) -> float:
        return y0 - d / dmax * (y0 - y1)

    star = e_min - c_min
    body = []
    for hh in range(7, 12):
        x = px(hh * 60)
        body += [
            f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y0}" class="grid"/>',
            f'<text class="muted" x="{x:.1f}" y="{y0 + 20}" font-size="12" '
            f'text-anchor="middle">{hh:02d}:00</text>',
        ]
    for hrs in range(0, 7, 2):
        y = py(hrs * 60)
        body += [
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>',
            f'<text class="muted" x="{x0 - 10}" y="{y + 4:.1f}" font-size="12" '
            f'text-anchor="end">{hrs} {"ч" if ru else "h"}</text>',
        ]
    pts = f"{px(lo):.1f},{py(e_min - lo):.1f} {px(star):.1f},{py(c_min):.1f} {px(hi):.1f},{py(c_min):.1f}"
    body += [
        f'<polyline points="{pts}" fill="none" class="saccent" stroke-width="2.5" '
        f'stroke-linejoin="round"/>',
        f'<circle cx="{px(star):.1f}" cy="{py(c_min):.1f}" r="6" class="accent" '
        f'stroke="#fcfcfb" stroke-width="2"/>',
        f'<text class="ink" x="{px(star):.1f}" y="{py(c_min) - 16:.1f}" font-size="13" '
        f'font-weight="600" text-anchor="middle">t₀* = E − c = 10:14</text>',
        f'<text class="ink2" x="{px(8 * 60):.1f}" y="{py(6.2 * 60):.1f}" font-size="12.5">'
        + ("D = E − t₀: стоим у ворот" if ru else "D = E − t₀: waiting at gates")
        + "</text>",
        f'<text class="ink2" x="{px(10.6 * 60):.1f}" y="{py(c_min) + 22:.1f}" font-size="12.5">'
        + ("D = c, но возврат позже" if ru else "D = c, later return")
        + "</text>",
    ]
    title = (
        "Лемма 4: длительность смены D(t₀) = max(E − t₀, c)"
        if ru
        else "Lemma 4: shift duration D(t₀) = max(E − t₀, c)"
    )
    sub = (
        "Фургон №1, день в Челнах: E = 13:34, c = 3:20 · ось x — начало смены"
        if ru
        else "Van #1, Chelny day: E = 13:34, c = 3:20 · x axis: shift start"
    )
    head = [
        f'<text class="ink" x="660" y="80" font-size="16" font-weight="600">{title.split(":")[0]}</text>',
        f'<text class="ink2" x="660" y="104" font-size="13">{title.split(": ", 1)[1]}</text>',
        f'<text class="ink2" x="660" y="140" font-size="12.5">{sub.split(" · ")[0]}</text>',
        f'<text class="muted" x="660" y="160" font-size="12.5">{sub.split(" · ")[1]}</text>',
        '<text class="ink2" x="660" y="200" font-size="12.5">'
        + (
            "Начало в t₀* даёт сразу кратчайшую"
            if ru
            else "Starting at t₀* gives both the shortest"
        )
        + "</text>",
        '<text class="ink2" x="660" y="218" font-size="12.5">'
        + ("смену и самое раннее возвращение." if ru else "shift and the earliest return.")
        + "</text>",
    ]
    return svg(960, 340, title, body + head)


def main() -> None:
    for lang, suffix in (("ru", ""), ("en", ".en")):
        (IMG / f"key-results{suffix}.svg").write_text(kpi(lang), encoding="utf-8")
        (IMG / f"certificate{suffix}.svg").write_text(certificate(lang), encoding="utf-8")
        (IMG / f"lemma4{suffix}.svg").write_text(lemma4(lang), encoding="utf-8")


if __name__ == "__main__":
    main()
