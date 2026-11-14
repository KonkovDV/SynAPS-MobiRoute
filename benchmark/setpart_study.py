"""Which solver for set partitioning? CP-SAT against MIP on the same route pools.

ALNS builds a pool of distinct routes on each instance (every accepted plan
contributes its routes). The same set-partitioning model over that pool
(:mod:`mobiroute.vrp.setpart`) is then solved by CP-SAT and by SCIP, HiGHS
and CBC through OR-Tools, each on one thread with the same wall-clock limit
and a zero optimality gap (CP-SAT also with its LP kept whole, linearization
level 2, and with its default eight-worker portfolio), and its LP relaxation is solved by GLOP: the LP value bounds
every recombination of the pool from below. Every plan is re-checked by the
verifier.

The point is the method of choosing a solver on one's own model class, not a
ranking of solvers in general: the instances, pool sizes and limits here
are small.

Usage:
  python benchmark/setpart_study.py [--iterations 5000] [--time-limit 10]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from mobiroute.vrp.alns import Alns, AlnsConfig, search_objective
from mobiroute.vrp.generators import cargo_day, dc_day
from mobiroute.vrp.io import load_benchmark
from mobiroute.vrp.model import Instance
from mobiroute.vrp.setpart import RoutePool, SpBackend, _reload_classes, solve_set_partitioning
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, Solution
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "benchmark" / "instances"
#: (label, backend, threads, CP-SAT linearization level)
BACKENDS: tuple[tuple[str, SpBackend, int, int], ...] = (
    ("CP-SAT, default", "CP-SAT", 1, 1),
    ("CP-SAT, linearization 2", "CP-SAT", 1, 2),
    ("CP-SAT, 8 workers", "CP-SAT", 8, 1),
    ("SCIP", "SCIP", 1, 2),
    ("HiGHS", "HIGHS", 1, 2),
    ("CBC", "CBC", 1, 2),
)


def cases() -> list[Instance]:
    out = []
    for rel in ("solomon/R101.txt", "solomon/RC101.txt", "solomon/C201.txt", "lilim/LC101.txt"):
        out.append(load_benchmark(str(INST / rel))[0])
    out.append(load_benchmark(str(INST / "sartori-buriol/n100/bar-n100-1.txt"))[0])
    out.append(cargo_day(7, n_orders=120))
    out.append(dc_day(1, trips=2))
    return out


def lp_bound(pool: RoutePool, incumbent: Solution) -> tuple[float | None, float]:
    """LP relaxation of the set-partitioning model (GLOP), same rows as the MIP."""
    from ortools.linear_solver import pywraplp

    c = pool.c
    started = time.perf_counter()
    solver = pywraplp.Solver.CreateSolver("GLOP")
    keys = sorted(pool.columns)
    x = [solver.NumVar(0.0, 1.0, f"x{k}") for k in range(len(keys))]
    cover: list[list[int]] = [[] for _ in range(len(c.penalty))]
    by_type: list[list[int]] = [[] for _ in range(c.n_types)]
    classes, class_of = _reload_classes(c)
    uses: list[dict[int, int]] = [{} for _ in classes]
    for k, key in enumerate(keys):
        by_type[key[0]].append(k)
        for r in key[1]:
            cover[r].append(k)
        for n in pool.columns[key][1]:
            if c.reload_of[n] >= 0:
                uses[class_of[n]][k] = uses[class_of[n]].get(k, 0) + 1
    y = {}
    for r, cols in enumerate(cover):
        if cols and c.penalty[r] >= MUST_SERVE_PENALTY and r not in incumbent.unassigned:
            solver.Add(sum(x[k] for k in cols) == 1)
            continue
        y[r] = solver.NumVar(0.0, 1.0, f"y{r}")
        solver.Add(sum(x[k] for k in cols) + y[r] == 1)
    for t, cols in enumerate(by_type):
        if cols:
            solver.Add(sum(x[k] for k in cols) <= c.count[t])
    for cl, used in enumerate(uses):
        if used:
            solver.Add(sum(n * x[k] for k, n in used.items()) <= len(classes[cl]))
    solver.Minimize(
        sum(pool.columns[key][0] * x[k] for k, key in enumerate(keys))
        + sum(c.penalty[r] * var for r, var in y.items())
    )
    ok = solver.Solve() == pywraplp.Solver.OPTIMAL
    return (solver.Objective().Value() if ok else None), time.perf_counter() - started


def study(iterations: int, time_limit: float) -> list[dict[str, Any]]:
    rows = []
    for inst in cases():
        cfg = AlnsConfig(
            iterations=iterations, seed=1, setpart=True, sp_every=10**9, sp_final=False
        )
        alns = Alns(inst, cfg)
        res = alns.solve()
        assert alns.pool is not None
        pool = alns.pool
        base = search_objective(inst, res.solution)
        bound, lp_seconds = lp_bound(pool, res.solution)
        for label, backend, threads, level in BACKENDS:
            sp = solve_set_partitioning(
                pool,
                res.solution,
                backend=backend,
                time_limit=time_limit,
                deterministic=False,
                workers=threads,
                linearization=level,
            )
            ok = sp.solution is not None and verify(inst, sp.solution).feasible
            value = None if sp.solution is None else search_objective(inst, sp.solution)
            rows.append(
                {
                    "instance": inst.name,
                    "columns": sp.columns,
                    "alns": round(base, 4),
                    "lp_bound": None if bound is None else round(bound, 4),
                    "lp_seconds": round(lp_seconds, 3),
                    "backend": label,
                    "status": sp.status,
                    "objective": None if value is None else round(value, 4),
                    "verified": ok,
                    "seconds": round(sp.seconds, 3),
                }
            )
            print(rows[-1], flush=True)
    return rows


def render(rows: list[dict[str, Any]], iterations: int, time_limit: float) -> str:
    lines = [
        "# Set partitioning over the route pool: CP-SAT and MIP solvers",
        "",
        f"Pool: distinct routes of the plans ALNS accepted in {iterations} iterations "
        f"(seed 1). Each backend: one thread unless stated, {time_limit:g} s wall clock, zero "
        "optimality gap, the ALNS plan as a hint (not for HiGHS: OR-Tools crashes on a HiGHS "
        "hint). *LP*: the relaxation on GLOP, a lower bound for any plan made of pool routes. "
        "Objective as the search sees it (money plus vehicle and unserved penalties).",
        "",
        "| Instance | Columns | ALNS plan | LP bound | Solver | Status | Objective | vs ALNS "
        "| Time, s | Verified |",
        "| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        obj = "—" if r["objective"] is None else f"{r['objective']:.2f}"
        lp = "—" if r["lp_bound"] is None else f"{r['lp_bound']:.2f}"
        delta = "—" if r["objective"] is None else f"{100 * (r['objective'] / r['alns'] - 1):+.3f}%"
        lines.append(
            f"| {r['instance']} | {r['columns']} | {r['alns']:.2f} | {lp} | {r['backend']} | "
            f"{r['status']} | {obj} | {delta} | {r['seconds']:.2f} | "
            f"{'yes' if r['verified'] else 'no'} |"
        )
    lines += [
        "",
        "Reading: when the LP bound equals the ALNS plan, no recombination of the pool can "
        "help and the solvers only have to prove it; when it is lower, the gap is the most "
        "a recombination could gain. `OPTIMAL` is a proof over the pool, not over all routes.",
        "",
    ]
    if any(str(r["status"]).startswith("CODE_") for r in rows):
        lines += [
            "`CODE_n`: the backend returned no solution within the limit (OR-Tools status "
            "code n); HiGHS gets no hint, see above.",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--iterations", type=int, default=5000)
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument(
        "--out", type=Path, default=ROOT / "benchmark" / "results" / "setpart_study.json"
    )
    ap.add_argument(
        "--markdown", type=Path, default=ROOT / "docs" / "benchmarks" / "setpart-solvers.md"
    )
    args = ap.parse_args()
    rows = study(args.iterations, args.time_limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    args.markdown.write_text(render(rows, args.iterations, args.time_limit))


if __name__ == "__main__":
    main()
