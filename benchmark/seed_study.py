"""Seeds and statistics: how much does a result depend on luck?

A heuristic's number on one instance and one seed is a sample. This study
runs every Solomon type-2 instance (R2, RC2: two to four long routes, where
the search varies most) with five seeds, with and without the local search,
and reports per instance the mean and standard deviation of the gap at the
reference vehicle count, the best run, and how often the reference vehicle
count was reached. The two configurations are compared on paired runs
(same instance, same seed) by the Wilcoxon signed-rank test.

Usage:
  python benchmark/seed_study.py [--seeds 5] [--iterations 30000] [--workers 3]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOLOMON = ROOT / "benchmark" / "instances" / "solomon"
REFS = ROOT / "benchmark" / "references" / "solomon.json"


def wilcoxon(diffs: list[float]) -> dict[str, float]:
    """Two-sided Wilcoxon signed-rank test of ``diffs`` against zero.

    Zero differences are dropped (Wilcoxon's convention); tied magnitudes
    get average ranks. Exact null distribution for up to 25 untied
    differences, otherwise the normal approximation with tie and continuity
    corrections. Returns ``n``, ``w_plus``, ``w_minus``, ``z`` and ``p``.
    """
    d = [x for x in diffs if abs(x) > 1e-9]
    n = len(d)
    if n == 0:
        return {"n": 0, "w_plus": 0.0, "w_minus": 0.0, "z": 0.0, "p": 1.0}
    order = sorted(range(n), key=lambda k: abs(d[k]))
    ranks = [0.0] * n
    ties: list[int] = []
    k = 0
    while k < n:
        j = k
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[k]])) <= 1e-9:
            j += 1
        avg = (k + j + 2) / 2.0
        for x in range(k, j + 1):
            ranks[order[x]] = avg
        ties.append(j - k + 1)
        k = j + 1
    w_plus = sum(r for r, x in zip(ranks, d, strict=True) if x > 0)
    w_minus = sum(r for r, x in zip(ranks, d, strict=True) if x < 0)
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - sum(t**3 - t for t in ties) / 48.0
    z = 0.0 if var <= 0 else (w_plus - mean - math.copysign(0.5, w_plus - mean)) / math.sqrt(var)
    if n <= 25 and all(t == 1 for t in ties):
        # Exact: number of subsets of ranks 1..n per rank sum.
        top = n * (n + 1) // 2
        count = [0] * (top + 1)
        count[0] = 1
        for r in range(1, n + 1):
            for s in range(top, r - 1, -1):
                count[s] += count[s - r]
        low = round(min(w_plus, w_minus))
        p = min(1.0, 2.0 * sum(count[: low + 1]) / 2.0**n)
    else:
        p = math.erfc(abs(z) / math.sqrt(2.0))
    return {"n": n, "w_plus": w_plus, "w_minus": w_minus, "z": z, "p": p}


def run_one(task: dict[str, Any]) -> dict[str, Any]:
    from mobiroute.vrp.alns import AlnsConfig, solve
    from mobiroute.vrp.io import load_benchmark

    inst, _ = load_benchmark(str(SOLOMON / f"{task['name']}.txt"))
    res = solve(
        inst,
        AlnsConfig(iterations=task["iterations"], seed=task["seed"], local_search=task["ls"]),
    )
    v = res.verdict
    return {
        "name": task["name"],
        "seed": task["seed"],
        "ls": task["ls"],
        "vehicles": v.cost.vehicles,
        "distance": round(v.cost.distance, 4),
        "verified": v.feasible and not v.unassigned,
        "seconds": res.seconds,
    }


def summarize(rows: list[dict[str, Any]], refs: dict[str, Any]) -> dict[str, Any]:
    by: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault((r["name"], r["ls"]), []).append(r)
    per_instance = []
    for name in sorted({r["name"] for r in rows}):
        ref = refs[name]
        entry: dict[str, Any] = {"name": name, "ref_vehicles": ref["vehicles"]}
        for ls in (False, True):
            runs = by.get((name, ls), [])
            at_ref = [r for r in runs if r["vehicles"] == ref["vehicles"]]
            gaps = [100.0 * (r["distance"] / ref["cost"] - 1.0) for r in at_ref]
            tag = "ls" if ls else "plain"
            entry[f"{tag}_at_ref"] = f"{len(at_ref)}/{len(runs)}"
            entry[f"{tag}_mean"] = statistics.fmean(gaps) if gaps else None
            entry[f"{tag}_std"] = statistics.stdev(gaps) if len(gaps) > 1 else None
            entry[f"{tag}_best"] = min(gaps) if gaps else None
        per_instance.append(entry)
    pairs = []
    plain = {(r["name"], r["seed"]): r for r in rows if not r["ls"]}
    for r in rows:
        if not r["ls"]:
            continue
        other = plain.get((r["name"], r["seed"]))
        ref = refs[r["name"]]
        if (
            other is None
            or ref["vehicles"] not in (r["vehicles"],)
            or (other["vehicles"] != ref["vehicles"])
        ):
            continue
        pairs.append(100.0 * (r["distance"] - other["distance"]) / ref["cost"])
    test = wilcoxon(pairs)
    return {
        "instances": per_instance,
        "paired_runs": len(pairs),
        "median_change_pct": statistics.median(pairs) if pairs else None,
        "better": sum(1 for x in pairs if x < -1e-9),
        "worse": sum(1 for x in pairs if x > 1e-9),
        "wilcoxon": test,
    }


def render(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    def pct(x: float | None) -> str:
        return "—" if x is None else f"{x:.2f}%"

    t = summary["wilcoxon"]
    lines = [
        "# Seeds and statistics on Solomon's type-2 classes",
        "",
        f"{meta['instances']} instances (R2, RC2), seeds 1-{meta['seeds']}, "
        f"{meta['iterations']} ALNS iterations per run, Rust kernel. Gap: distance above the "
        "best known at the best-known vehicle count; runs with more vehicles are counted in "
        "*at ref.* but not in the gap statistics. *Plain*: ALNS alone; *LS*: with the "
        "relocate / swap / 2-opt* / 2-opt descent on every new best plan.",
        "",
        "| Instance | Vehicles (ref.) | Plain: at ref. | mean ± sd | best | LS: at ref. "
        "| mean ± sd | best |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for e in summary["instances"]:

        def ms(tag: str, e: dict[str, Any] = e) -> str:
            mean, sd = e[f"{tag}_mean"], e[f"{tag}_std"]
            if mean is None:
                return "—"
            return f"{mean:.2f}% ± {sd:.2f}" if sd is not None else f"{mean:.2f}%"

        lines.append(
            f"| {e['name']} | {e['ref_vehicles']} | {e['plain_at_ref']} | {ms('plain')} | "
            f"{pct(e['plain_best'])} | {e['ls_at_ref']} | {ms('ls')} | {pct(e['ls_best'])} |"
        )
    lines += [
        "",
        "## Paired comparison",
        "",
        f"Runs where both configurations reach the reference vehicle count: "
        f"**{summary['paired_runs']}**; the local search shortens the plan in "
        f"**{summary['better']}**, lengthens it in {summary['worse']}; median change "
        f"{pct(summary['median_change_pct'])} of the best-known distance.",
        "",
        f"Wilcoxon signed-rank test (two-sided): n = {t['n']}, W+ = {t['w_plus']:.1f}, "
        f"W- = {t['w_minus']:.1f}, z = {t['z']:.2f}, **p = {t['p']:.2g}**.",
        "",
        "Single-seed tables elsewhere in `docs/benchmarks/` are one draw from these "
        "distributions; this table says how wide they are.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--iterations", type=int, default=30000)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "seed_study.json")
    ap.add_argument("--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "seed-study.md")
    ap.add_argument("--from-json", type=Path, default=None)
    args = ap.parse_args()
    refs = json.loads(REFS.read_text())["instances"]
    if args.from_json is not None:
        saved = json.loads(args.from_json.read_text())
        args.markdown.write_text(render(summarize(saved["rows"], refs), saved["meta"]))
        return
    names = sorted(p.stem for p in SOLOMON.glob("*.txt") if p.stem.startswith(("R2", "RC2")))
    tasks = [
        {"name": n, "seed": s, "ls": ls, "iterations": args.iterations}
        for n in names
        for s in range(1, args.seeds + 1)
        for ls in (False, True)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, tasks))
    meta = {"instances": len(names), "seeds": args.seeds, "iterations": args.iterations}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2) + "\n")
    args.markdown.write_text(render(summarize(rows, refs), meta))


if __name__ == "__main__":
    main()
