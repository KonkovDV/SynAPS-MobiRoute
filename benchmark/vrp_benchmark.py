"""Run the rich-VRP engine on the vendored public benchmarks.

Every instance is read from its pinned bytes (SHA-256 checked against the
family's ``SHA256SUMS.txt``), solved with a fixed seed and iteration budget,
and re-checked by the independent verifier. A gap to the published value is
reported only for a verified plan that serves every order; under the
hierarchical objective it is reported only at the reference vehicle count,
otherwise the vehicle difference is reported instead.

Usage:
  python benchmark/vrp_benchmark.py                       # all families
  python benchmark/vrp_benchmark.py --families solomon --iterations 20000 --workers 4
  python benchmark/vrp_benchmark.py --only R101,C101      # a few instances
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INSTANCES = ROOT / "benchmark" / "instances"
REFERENCES = ROOT / "benchmark" / "references"

FAMILIES: dict[str, tuple[Path, str, bool]] = {
    # name: (directory, reference file, hierarchical objective)
    "solomon": (INSTANCES / "solomon", "solomon.json", True),
    "lilim": (INSTANCES / "lilim", "lilim.json", True),
    "sartori-buriol": (INSTANCES / "sartori-buriol" / "n100", "sartori-buriol-n100.json", True),
    "cordeau": (INSTANCES / "cordeau", "cordeau.json", False),
}


def _sums(directory: Path) -> dict[str, str]:
    out = {}
    for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            out[name.strip()] = digest
    return out


def _gap(cost: float, ref: float) -> float:
    """Percent above the reference; references carry 2 decimals, so +-0.005 is a match."""
    if abs(cost - ref) <= 0.005:
        return 0.0
    return round(100 * (cost - ref) / ref, 3)


def run_one(task: dict[str, Any]) -> dict[str, Any]:
    from mobiroute.vrp.alns import AlnsConfig, solve
    from mobiroute.vrp.io import load_benchmark

    path = Path(task["path"])
    inst, digest = load_benchmark(path)
    if digest != task["sha256"]:
        raise RuntimeError(f"instance bytes changed: {path}")
    began = time.perf_counter()
    res = solve(
        inst,
        AlnsConfig(
            iterations=task["iterations"],
            seed=task["seed"],
            time_limit=task["time_limit"],
            backend="auto",
        ),
    )
    wall = time.perf_counter() - began
    v = res.verdict
    ref = task["reference"]
    row: dict[str, Any] = {
        "family": task["family"],
        "instance": inst.name,
        "sha256": digest,
        "requests": inst.n_requests,
        "seed": task["seed"],
        "iterations": res.iterations,
        "seconds": round(wall, 2),
        "backend": res.backend,
        "feasible": v.feasible,
        "complete": v.complete,
        "vehicles": v.cost.vehicles,
        "cost": round(v.cost.distance, 4),
        "ref_vehicles": ref.get("vehicles"),
        "ref_cost": ref["cost"],
        "ref_kind": task["ref_kind"],
        "gap_pct": None,
        "vehicle_delta": None,
        "violations": list(v.violations[:5]),
    }
    if v.feasible and v.complete:
        if task["hierarchical"]:
            row["vehicle_delta"] = v.cost.vehicles - ref["vehicles"]
            if row["vehicle_delta"] == 0:
                row["gap_pct"] = _gap(v.cost.distance, ref["cost"])
        else:
            row["gap_pct"] = _gap(v.cost.distance, ref["cost"])
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family in sorted({r["family"] for r in rows}):
        fam = [r for r in rows if r["family"] == family]
        gaps = [r["gap_pct"] for r in fam if r["gap_pct"] is not None]
        deltas = [r["vehicle_delta"] for r in fam if r["vehicle_delta"] is not None]
        out[family] = {
            "instances": len(fam),
            "verified_complete": sum(r["feasible"] and r["complete"] for r in fam),
            "at_reference_fleet": sum(1 for d in deltas if d == 0) if deltas else None,
            "fewer_vehicles": sum(1 for d in deltas if d < 0) if deltas else None,
            "more_vehicles": sum(1 for d in deltas if d > 0) if deltas else None,
            "matched_reference": sum(1 for g in gaps if g <= 0.01),
            "mean_gap_pct": round(statistics.fmean(gaps), 3) if gaps else None,
            "median_gap_pct": round(statistics.median(gaps), 3) if gaps else None,
            "max_gap_pct": round(max(gaps), 3) if gaps else None,
            "mean_seconds": round(statistics.fmean(r["seconds"] for r in fam), 2),
        }
    return out


def markdown(rows: list[dict[str, Any]], summary: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        "# Rich-VRP engine on public benchmarks",
        "",
        f"Seed {meta['seed']}, {meta['iterations']} ALNS iterations per instance"
        + (f" (Cordeau: {meta['cordeau_iterations']})" if meta.get("cordeau_iterations") else "")
        + f", backend `{meta['backend']}`, {meta['platform']}, Python {meta['python']}.",
        "Every plan is re-checked by the independent verifier; gaps are quoted only for",
        "verified plans that serve every order, and under the hierarchical objective only",
        "at the reference vehicle count. Timings are single-threaded wall clock.",
        "",
        "## Summary",
        "",
        "| Family | Instances | Verified | At ref. fleet | Fewer veh. | More veh. | Matched ref. | Mean gap | Median gap | Max gap | Mean time |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value: Any, suffix: str = "") -> str:
        return "—" if value is None else f"{value}{suffix}"

    for family, s in summary.items():
        lines.append(
            f"| {family} | {s['instances']} | {s['verified_complete']} | {fmt(s['at_reference_fleet'])} "
            f"| {fmt(s['fewer_vehicles'])} | {fmt(s['more_vehicles'])} | {s['matched_reference']} "
            f"| {fmt(s['mean_gap_pct'], '%')} | {fmt(s['median_gap_pct'], '%')} "
            f"| {fmt(s['max_gap_pct'], '%')} | {s['mean_seconds']} s |"
        )
    lines += [
        "",
        "## Instances",
        "",
        "| Family | Instance | Orders | Vehicles (ref) | Cost (ref) | Gap | Time |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        ref_v = "" if r["ref_vehicles"] is None else f" ({r['ref_vehicles']})"
        gap = "—" if r["gap_pct"] is None else f"{r['gap_pct']:.2f}%"
        if r["vehicle_delta"]:
            gap = f"{r['vehicle_delta']:+d} veh."
        if not (r["feasible"] and r["complete"]):
            gap = "not verified"
        lines.append(
            f"| {r['family']} | {r['instance']} | {r['requests']} | {r['vehicles']}{ref_v} "
            f"| {r['cost']:.2f} ({r['ref_cost']:.2f}) | {gap} | {r['seconds']:.1f} s |"
        )
    lines += [
        "",
        "## Reading the table",
        "",
        "* One seed per instance, reported as it came. Solomon's type-2 classes (R2, RC2: two",
        "  to four long routes over wide windows) have the largest gaps and the largest spread",
        "  between seeds; RC202 lands anywhere between 3% and 12% depending on the seed and",
        "  the annealing settings.",
        "* `+1 veh.` means a verified, complete plan with one vehicle more than the reference;",
        "  under the hierarchical objective its distance is not comparable, so no gap is shown.",
        "* Cordeau has no vehicle-count objective: the gap is on total routing cost.",
        "",
        "References: " + "; ".join(f"{k}: {v}" for k, v in meta["sources"].items()),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--only", default="")
    ap.add_argument("--iterations", type=int, default=20000)
    ap.add_argument("--cordeau-iterations", type=int, default=5000)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "vrp")
    ap.add_argument("--markdown", type=Path, default=None)
    ap.add_argument("--from-json", type=Path, default=None, help="re-render a previous run")
    args = ap.parse_args()
    if args.from_json is not None:
        saved = json.loads(args.from_json.read_text())
        text = markdown(saved["rows"], saved["summary"], saved["meta"])
        (args.markdown or args.out / "vrp_benchmark.md").write_text(text)
        return

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    tasks: list[dict[str, Any]] = []
    sources: dict[str, str] = {}
    for family in [f.strip() for f in args.families.split(",") if f.strip()]:
        directory, ref_file, hierarchical = FAMILIES[family]
        refs = json.loads((REFERENCES / ref_file).read_text())
        sources[family] = refs["source"]
        sums = _sums(directory)
        for name, digest in sorted(sums.items()):
            stem = Path(name).stem
            if only and stem not in only:
                continue
            raw = (directory / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise SystemExit(f"checksum mismatch: {directory / name}")
            tasks.append(
                {
                    "family": family,
                    "path": str(directory / name),
                    "sha256": digest,
                    "reference": refs["instances"][stem],
                    "ref_kind": refs["kind"],
                    "hierarchical": hierarchical,
                    "iterations": args.cordeau_iterations
                    if family == "cordeau"
                    else args.iterations,
                    "time_limit": args.time_limit,
                    "seed": args.seed,
                }
            )
    began = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, tasks))
    summary = summarize(rows)
    meta = {
        "seed": args.seed,
        "iterations": args.iterations,
        "cordeau_iterations": args.cordeau_iterations if "cordeau" in args.families else None,
        "backend": rows[0]["backend"] if rows else "n/a",
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "wall_seconds": round(time.perf_counter() - began, 1),
        "workers": args.workers,
        "sources": sources,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "vrp_benchmark.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "rows": rows}, indent=2) + "\n"
    )
    text = markdown(rows, summary, meta)
    (args.out / "vrp_benchmark.md").write_text(text)
    if args.markdown is not None:
        args.markdown.write_text(text)
    for family, s in summary.items():
        print(family, json.dumps(s))
    print(f"wall {meta['wall_seconds']} s -> {args.out}")


if __name__ == "__main__":
    main()
