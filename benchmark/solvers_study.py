"""Same instances, same clock: ALNS against PyVRP, VROOM and jsprit.

Every solver gets the same wall-clock budget on one thread and the same
instance data; every plan it returns is re-checked by this repository's
verifier on the instance's own distances, so a rounding trick or a missed
window shows up as "not verified" instead of a better number.

* PyVRP 0.14 (iterated local search, C++; Wouda, Lan & Kool 2024) and VROOM
  1.15 (C++, through pyvroom) take integer data: Solomon distances are scaled
  by 100, travel times rounded up (so their plans stay feasible in exact
  arithmetic), Gehring-Homberger data by 10 (exact under the DIMACS
  convention), X instances as they are (integers already).
* jsprit 2.0 (Java, ruin and recreate) takes the exact floating-point matrix
  through ``benchmark/jsprit/JspritRunner.java``; its time is measured inside
  the JVM, so start-up is not charged.
* ALNS: this repository, seed 1, with the Rust kernel when it is installed.

Objectives follow each benchmark's convention: Solomon ranks vehicles first,
then distance (solvers get a fixed vehicle cost of 10^5); Gehring-Homberger
(DIMACS) and X (CVRPLIB) rank distance only.

Usage:
  pip install pyvrp==0.14.1 pyvroom==1.15.2
  (cd benchmark/jsprit && mvn -q dependency:copy-dependencies -DoutputDirectory=lib \
     && javac -cp "lib/*" -d . JspritRunner.java)
  python benchmark/solvers_study.py [--set solomon|large|all] [--seconds 10] [--large-seconds 60]
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import Alns, AlnsConfig
from mobiroute.vrp.io import load_benchmark
from mobiroute.vrp.model import Instance
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "benchmark" / "instances"
JSPRIT = ROOT / "benchmark" / "jsprit"
BIG = 10**5  # vehicle fee that makes "fewer vehicles" dominate on Solomon

Routes = list[list[int]]


def cases(which: str) -> list[Path]:
    solomon = sorted((INST / "solomon").glob("*.txt"))
    large = sorted((INST / "gehring-homberger").glob("*.vrp")) + sorted(
        (INST / "uchoa-x").glob("*.vrp")
    )
    return {"solomon": solomon, "large": large, "all": solomon + large}[which]


def reference(path: Path) -> tuple[int | None, float | None]:
    """Best known (vehicles, distance) for the instance, if published here."""
    if path.parent.name == "solomon":
        data = json.loads((ROOT / "benchmark" / "references" / "solomon.json").read_text())
        ref = data["instances"].get(path.stem)
        return (ref["vehicles"], ref["cost"]) if ref else (None, None)
    sol = path.with_suffix(".sol")
    if sol.exists():
        lines = sol.read_text().splitlines()
        routes = sum(1 for ln in lines if ln.startswith("Route"))
        cost = next(float(ln.split()[1]) for ln in lines if ln.startswith("Cost"))
        return routes, cost
    return None, None


def scale_of(inst: Instance) -> int:
    return {"vrplib:dimacs": 10, "vrplib:round": 1}.get(inst.source, 100)


def int_data(inst: Instance) -> tuple[list[list[int]], list[list[int]], int]:
    """Integer distance and duration matrices (durations rounded up)."""
    k = scale_of(inst)
    dist = inst.profiles["default"].distance
    time_ = inst.profiles["default"].time
    d = [[round(v * k) for v in row] for row in dist]
    t = [[math.ceil(v * k - 1e-9) for v in row] for row in time_]
    return d, t, k


def fleet_fee(inst: Instance) -> float:
    return float(BIG) if inst.vehicle_penalty > 0 else 0.0


# -- solvers -------------------------------------------------------------------


def run_alns(inst: Instance, seconds: float) -> tuple[Routes, float]:
    started = time.perf_counter()
    res = Alns(inst, AlnsConfig(time_limit=seconds, iterations=10**9, seed=1)).solve()
    routes = [list(r.nodes) for r in res.solution.routes if r.nodes]
    return routes, time.perf_counter() - started


def run_pyvrp(inst: Instance, seconds: float) -> tuple[Routes, float]:
    pyvrp = importlib.import_module("pyvrp")
    stop = importlib.import_module("pyvrp.stop")
    d, t, k = int_data(inst)
    m = pyvrp.Model()
    locs = [m.add_location(node.x, node.y) for node in inst.nodes]
    depot = inst.nodes[0]
    m.add_depot(locs[0], tw_early=int(depot.earliest * k), tw_late=_late(depot.latest, k))
    for req in inst.requests:
        assert req.delivery is not None
        node = inst.nodes[req.delivery]
        m.add_client(
            locs[req.delivery],
            delivery=[int(req.demand[0])],
            service_duration=round(node.service * k),
            tw_early=round(node.earliest * k),
            tw_late=_late(node.latest, k),
        )
    vt = inst.vehicle_types[0]
    m.add_vehicle_type(
        num_available=vt.count,
        capacity=[int(vt.capacity[0])],
        fixed_cost=int(fleet_fee(inst) * k),
        tw_early=int(vt.shift_start * k),
        tw_late=_late(vt.shift_end, k),
    )
    for i, a in enumerate(locs):
        for j, b in enumerate(locs):
            if i != j:
                m.add_edge(a, b, distance=d[i][j], duration=t[i][j])
    started = time.perf_counter()
    res = m.solve(stop=stop.MaxRuntime(seconds), seed=1, display=False)
    elapsed = time.perf_counter() - started
    # Client activities carry the client index (0-based, in the order added).
    routes = [[act.idx + 1 for act in route if act.is_client()] for route in res.best.routes()]
    return routes, elapsed


def run_vroom(inst: Instance, seconds: float) -> tuple[Routes, float]:
    vroom = importlib.import_module("vroom")
    d, t, k = int_data(inst)
    problem = vroom.Input()
    problem.set_durations_matrix(profile="car", matrix_input=t)
    problem.set_costs_matrix(profile="car", matrix_input=d)
    vt = inst.vehicle_types[0]
    window = vroom.TimeWindow(int(vt.shift_start * k), _late(vt.shift_end, k, cap=2**31 - 1))
    fee = int(fleet_fee(inst) * k)
    for v in range(vt.count):
        problem.add_vehicle(
            vroom.Vehicle(
                id=v,
                start=0,
                end=0,
                capacity=[int(vt.capacity[0])],
                time_window=window,
                costs=vroom.VehicleCosts(fixed=fee),
            )
        )
    for req in inst.requests:
        assert req.delivery is not None
        node = inst.nodes[req.delivery]
        problem.add_job(
            vroom.Job(
                id=req.delivery,
                location=req.delivery,
                default_service=round(node.service * k),
                delivery=[int(req.demand[0])],
                time_windows=[
                    vroom.TimeWindow(round(node.earliest * k), _late(node.latest, k, cap=2**31 - 1))
                ],
            )
        )
    started = time.perf_counter()
    sol = problem.solve(exploration_level=5, nb_threads=1, timeout=timedelta(seconds=seconds))
    elapsed = time.perf_counter() - started
    frame = sol.routes
    routes: dict[int, list[int]] = {}
    for vid, kind, loc in zip(
        frame["vehicle_id"], frame["type"], frame["location_index"], strict=True
    ):
        if kind == "job":
            routes.setdefault(int(vid), []).append(int(loc))
    return list(routes.values()), elapsed


def run_jsprit(inst: Instance, seconds: float) -> tuple[Routes, float]:
    dist = inst.profiles["default"].distance
    vt = inst.vehicle_types[0]
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.txt", Path(tmp) / "out.txt"
        lines = [
            f"{inst.n_nodes} {int(vt.capacity[0])} {vt.count} {fleet_fee(inst)!r} {seconds!r} 1"
        ]
        demand = {req.delivery: req.demand[0] for req in inst.requests}
        for k, node in enumerate(inst.nodes):
            hi = node.latest if math.isfinite(node.latest) else 1e9
            lo = node.earliest if k else max(node.earliest, vt.shift_start)
            if k == 0:
                hi = min(hi, vt.shift_end if math.isfinite(vt.shift_end) else 1e9)
            lines.append(
                f"{node.x!r} {node.y!r} {demand.get(k, 0.0)!r} {lo!r} {hi!r} {node.service!r}"
            )
        lines += [" ".join(repr(v) for v in row) for row in dist]
        src.write_text("\n".join(lines) + "\n")
        subprocess.run(
            [
                "java",
                "-Xmx4g",
                "-cp",
                f"{JSPRIT / 'lib'}/*:{JSPRIT}",
                "JspritRunner",
                str(src),
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=seconds * 4 + 120,
        )
        routes: Routes = []
        elapsed = math.nan
        for line in out.read_text().splitlines():
            head, *rest = line.split()
            if head == "route":
                routes.append([int(x) for x in rest])
            elif head == "seconds":
                elapsed = float(rest[0])
    return routes, elapsed


def _late(value: float, k: int, cap: int = 2**62) -> int:
    return cap if not math.isfinite(value) else min(cap, round(value * k))


SOLVERS: dict[str, Callable[[Instance, float], tuple[Routes, float]]] = {
    "ALNS (this repo)": run_alns,
    "PyVRP 0.14.1": run_pyvrp,
    "VROOM 1.15.2": run_vroom,
    "jsprit 2.0.0": run_jsprit,
}


# -- study ---------------------------------------------------------------------


def study(paths: list[Path], seconds: float, large_seconds: float) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        inst, digest = load_benchmark(path)
        budget = large_seconds if inst.n_requests > 200 else seconds
        ref_v, ref_d = reference(path)
        for name, run in SOLVERS.items():
            try:
                routes, elapsed = run(inst, budget)
                served = {n for r in routes for n in r}
                missing = {r for r, req in enumerate(inst.requests) if req.delivery not in served}
                verdict = verify(inst, Solution([Route(0, r) for r in routes], missing))
                cost = verdict.cost
                row = {
                    "instance": inst.name,
                    "family": path.parent.name,
                    "sha256": digest,
                    "orders": inst.n_requests,
                    "solver": name,
                    "budget_s": budget,
                    "seconds": round(elapsed, 2),
                    "served": inst.n_requests - len(missing),
                    "vehicles": cost.vehicles,
                    "distance": round(cost.distance, 2),
                    "verified": verdict.feasible and not missing,
                    "ref_vehicles": ref_v,
                    "ref_distance": ref_d,
                    "error": None,
                }
            except Exception as exc:  # a solver failing is a result, not a crash
                row = {
                    "instance": inst.name,
                    "family": path.parent.name,
                    "sha256": digest,
                    "orders": inst.n_requests,
                    "solver": name,
                    "budget_s": budget,
                    "error": f"{type(exc).__name__}: {str(exc)[:120]}",
                }
            rows.append(row)
            print(json.dumps(row), flush=True)
    return rows


def _gap(row: dict[str, Any]) -> float | None:
    if row.get("error") or not row.get("verified") or row.get("ref_distance") is None:
        return None
    return 100.0 * (float(row["distance"]) / float(row["ref_distance"]) - 1.0)


def render(rows: list[dict[str, Any]], seconds: float, large_seconds: float) -> str:
    solvers = list(SOLVERS)
    lines = [
        "# Same instances, same clock: ALNS, PyVRP, VROOM, jsprit",
        "",
        f"One thread each, {seconds:g} s per Solomon instance and {large_seconds:g} s per "
        "1000-customer instance, seed 1. Every plan is re-checked by this repository's "
        "verifier on the instance's own distances; *verified* means feasible and complete. "
        "Solomon ranks vehicles first, then distance (best known: SINTEF TOP); "
        "Gehring-Homberger (DIMACS rounding) and X (CVRPLIB rounding) rank distance only "
        "(best known: CVRPLIB). Produced by `python benchmark/solvers_study.py`.",
        "",
        "## Summary",
        "",
        "| Family | Solver | Verified | At best-known vehicles | Mean gap, distance | Best of the four |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    families = sorted({r["family"] for r in rows})
    for fam in families:
        fam_rows = [r for r in rows if r["family"] == fam]
        instances = sorted({r["instance"] for r in fam_rows})
        wins: dict[str, int] = dict.fromkeys(solvers, 0)
        for name in instances:
            ok = [r for r in fam_rows if r["instance"] == name and r.get("verified")]
            if not ok:
                continue
            key = (
                (lambda r: (r["vehicles"], r["distance"]))
                if fam == "solomon"
                else (lambda r: (r["distance"],))
            )
            top = min(key(r) for r in ok)
            for r in ok:
                if key(r) == top:
                    wins[r["solver"]] += 1
        for s in solvers:
            mine = [r for r in fam_rows if r["solver"] == s]
            good = [r for r in mine if r.get("verified")]
            at_ref = sum(
                1
                for r in good
                if r.get("ref_vehicles") is not None and r["vehicles"] <= r["ref_vehicles"]
            )
            gaps = [g for g in (_gap(r) for r in good) if g is not None]
            mean = f"{sum(gaps) / len(gaps):+.2f}%" if gaps else "—"
            lines.append(
                f"| {fam} | {s} | {len(good)}/{len(mine)} | {at_ref} | {mean} | {wins[s]} |"
            )
    lines += [
        "",
        "Mean gap is over verified plans and against the best known distance; on Solomon "
        "a plan with more vehicles than the best known can show a negative distance gap, "
        "so read it with the vehicle column.",
        "",
        "## Every run",
        "",
        "| Instance | Solver | Served | Vehicles | Distance | Gap | Time, s | Verified |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        if r.get("error"):
            lines.append(
                f"| {r['instance']} | {r['solver']} | — | — | — | — | — | error: {r['error']} |"
            )
            continue
        g = _gap(r)
        lines.append(
            f"| {r['instance']} | {r['solver']} | {r['served']}/{r['orders']} | {r['vehicles']} | "
            f"{r['distance']:.2f} | {'—' if g is None else f'{g:+.2f}%'} | {r['seconds']:.1f} | "
            f"{'yes' if r['verified'] else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--set", choices=["solomon", "large", "all"], default="all")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--large-seconds", type=float, default=60.0)
    ap.add_argument(
        "--out", type=Path, default=ROOT / "benchmark" / "results" / "solvers_study.json"
    )
    ap.add_argument("--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "solvers.md")
    args = ap.parse_args()
    rows = study(cases(args.set), args.seconds, args.large_seconds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": rows}, indent=1) + "\n")
    args.markdown.write_text(render(rows, args.seconds, args.large_seconds))


if __name__ == "__main__":
    main()
