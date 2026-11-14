"""Route pool and set partitioning: the matheuristic half of the search.

ALNS visits many plans whose routes are good while the plans themselves
are not: a route found early may fit perfectly with routes found much later.
Keeping every distinct route of the accepted plans and solving

.. math::

    \\min \\sum_{\\rho \\in P} c_\\rho x_\\rho + \\sum_{r} \\pi_r y_r
    \\quad \\text{s.t.} \\quad
    \\sum_{\\rho \\ni r} x_\\rho + y_r = 1 \\;\\; \\forall r, \\qquad
    \\sum_{\\rho \\in P_k} x_\\rho \\le n_k \\;\\; \\forall k, \\qquad
    x, y \\in \\{0, 1\\}

recombines them into the best plan the pool allows (Rochat & Taillard 1995;
Subramanian, Uchoa & Ochi 2013). ``c_rho`` is the route's money plus the
vehicle penalty, ``pi_r`` the price of leaving order ``r`` out, ``P_k`` the
routes of vehicle type ``k``. Every column is a route that was feasible when
it was found, so any solution of the model is a feasible plan; the
incumbent is in the pool, so the model is never worse than it.

The pool keeps, for each vehicle type and set of orders, the cheapest stop
sequence seen. The model is solved by CP-SAT (default; one worker and a
deterministic time budget, so runs repeat exactly) or by a MIP solver
through OR-Tools (SCIP, HiGHS, CBC) for comparison.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from mobiroute.vrp.fleet import route_money
from mobiroute.vrp.insertion import Compiled
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, Route, Solution

SpBackend = Literal["CP-SAT", "SCIP", "HIGHS", "CBC"]
#: CP-SAT needs integer costs: money is scaled to thousandths.
SCALE = 1000.0


class RoutePool:
    """Distinct routes seen by the search, cheapest sequence per order set."""

    def __init__(self, c: Compiled, *, max_columns: int = 60_000) -> None:
        self.c = c
        self.max_columns = max_columns
        #: (type, sorted requests) -> (money, nodes)
        self.columns: dict[tuple[int, tuple[int, ...]], tuple[float, tuple[int, ...]]] = {}
        self._seen: set[tuple[int, tuple[int, ...]]] = set()

    def __len__(self) -> int:
        return len(self.columns)

    def add_route(self, t: int, nodes: list[int]) -> None:
        seq = (t, tuple(nodes))
        if not nodes or seq in self._seen:
            return
        self._seen.add(seq)
        c = self.c
        key = (t, tuple(sorted(c.requests_of(nodes))))
        money = route_money(c, t, nodes)
        old = self.columns.get(key)
        if old is None or money < old[0] - 1e-9:
            if old is None and len(self.columns) >= self.max_columns:
                return
            self.columns[key] = (money, seq[1])

    def add(self, sol: Solution) -> None:
        for route in sol.routes:
            self.add_route(route.vehicle_type, route.nodes)
        if len(self._seen) > 4 * self.max_columns:
            self._seen.clear()


@dataclass(frozen=True, slots=True)
class SpResult:
    solution: Solution | None
    objective: float | None
    status: str
    seconds: float
    columns: int
    backend: str


def solve_set_partitioning(
    pool: RoutePool,
    incumbent: Solution | None = None,
    *,
    backend: SpBackend = "CP-SAT",
    time_limit: float = 5.0,
    deterministic: bool = True,
    workers: int = 1,
    linearization: int = 2,
) -> SpResult:
    """Best plan made of pool routes (see module docstring).

    ``deterministic`` gives CP-SAT a deterministic-time budget instead of a
    wall-clock one, so the same pool always gives the same plan.
    ``linearization`` is CP-SAT's ``linearization_level``: at 2 it keeps the
    LP relaxation of the whole model, which is what proves set-partitioning
    optima (on one worker, level 1 left the R101 pool unproven after 10 s,
    level 2 proves it in 0.13 s; see ``benchmark/setpart_study.py``).
    """
    c = pool.c
    if incumbent is not None:
        pool.add(incumbent)
    keys = sorted(pool.columns)
    started = time.perf_counter()
    if not keys:
        return SpResult(None, None, "EMPTY", 0.0, 0, backend)
    cover: list[list[int]] = [[] for _ in range(len(c.penalty))]
    by_type: list[list[int]] = [[] for _ in range(c.n_types)]
    costs: list[float] = []
    for k, key in enumerate(keys):
        t, requests = key
        costs.append(pool.columns[key][0])
        by_type[t].append(k)
        for r in requests:
            cover[r].append(k)
    classes, class_of = _reload_classes(c)
    uses: list[dict[int, int]] = [{} for _ in classes]
    for k, key in enumerate(keys):
        for n in pool.columns[key][1]:
            if c.reload_of[n] >= 0:
                cl = class_of[n]
                uses[cl][k] = uses[cl].get(k, 0) + 1
    # Chosen routes may not use more copies of a reload stop than exist.
    shared = [
        (sorted(u.items()), len(classes[cl]))
        for cl, u in enumerate(uses)
        if sum(u.values()) > len(classes[cl])
    ]
    # An order the incumbent serves gets no "left out" variable: the incumbent
    # shows that covering all of them at once is possible, so the optimum is
    # unchanged, and the model loses the huge must-serve penalties that make
    # its LP badly scaled. Orders the incumbent leaves out keep the variable.
    optional = [
        not cover[r]
        or c.penalty[r] < MUST_SERVE_PENALTY
        or incumbent is None
        or r in incumbent.unassigned
        for r in range(len(cover))
    ]
    hint: set[int] = set()
    if incumbent is not None:
        lookup = {key: k for k, key in enumerate(keys)}
        for route in incumbent.routes:
            if route.nodes:
                key = (route.vehicle_type, tuple(sorted(c.requests_of(route.nodes))))
                if key in lookup:
                    hint.add(lookup[key])
    if backend == "CP-SAT":
        chosen, status = _solve_cpsat(
            c,
            cover,
            optional,
            by_type,
            shared,
            costs,
            hint,
            time_limit,
            deterministic,
            workers,
            linearization,
        )
    else:
        chosen, status = _solve_mip(
            c, cover, optional, by_type, shared, costs, hint, time_limit, backend
        )
    seconds = time.perf_counter() - started
    if chosen is None:
        return SpResult(None, None, status, seconds, len(keys), backend)
    routes = []
    served: set[int] = set()
    spare = [list(members) for members in classes]
    for k in chosen:
        t, requests = keys[k]
        # Give every chosen route its own copies of the reload stops it uses.
        nodes = [
            spare[class_of[n]].pop(0) if c.reload_of[n] >= 0 else n
            for n in pool.columns[keys[k]][1]
        ]
        routes.append(Route(t, nodes))
        served.update(requests)
    unassigned = set(range(len(c.penalty))) - served
    sol = Solution(routes, unassigned)
    value = sum(costs[k] for k in chosen) + sum(c.penalty[r] for r in unassigned)
    return SpResult(sol, value, status, seconds, len(keys), backend)


def _solve_cpsat(
    c: Compiled,
    cover: list[list[int]],
    optional: list[bool],
    by_type: list[list[int]],
    shared: list[tuple[list[tuple[int, int]], int]],
    costs: list[float],
    hint: set[int],
    time_limit: float,
    deterministic: bool,
    workers: int,
    linearization: int,
) -> tuple[list[int] | None, str]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x = [model.new_bool_var(f"x{k}") for k in range(len(costs))]
    y: dict[int, Any] = {}
    for r, cols in enumerate(cover):
        if not cols:
            continue
        if optional[r]:
            y[r] = model.new_bool_var(f"y{r}")
            model.add(sum(x[k] for k in cols) + y[r] == 1)
        else:
            model.add(sum(x[k] for k in cols) == 1)
    for t, cols in enumerate(by_type):
        if cols and len(cols) > c.count[t]:
            model.add(sum(x[k] for k in cols) <= c.count[t])
    for used, size in shared:
        model.add(sum(n * x[k] for k, n in used) <= size)
    model.minimize(
        sum(round(SCALE * costs[k]) * x[k] for k in range(len(costs)))
        + sum(round(SCALE * c.penalty[r]) * var for r, var in y.items())
    )
    for k, var in enumerate(x):
        model.add_hint(var, k in hint)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.linearization_level = linearization
    if deterministic:
        # About one deterministic unit per wall-clock second on one core.
        solver.parameters.max_deterministic_time = time_limit
    else:
        solver.parameters.max_time_in_seconds = time_limit
    code = solver.solve(model)
    status = solver.status_name(code)
    if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    return [k for k, var in enumerate(x) if solver.value(var)], status


def _solve_mip(
    c: Compiled,
    cover: list[list[int]],
    optional: list[bool],
    by_type: list[list[int]],
    shared: list[tuple[list[tuple[int, int]], int]],
    costs: list[float],
    hint: set[int],
    time_limit: float,
    backend: str,
) -> tuple[list[int] | None, str]:
    from ortools.linear_solver import pywraplp

    solver = pywraplp.Solver.CreateSolver(backend)
    if solver is None:
        return None, f"{backend}_UNAVAILABLE"
    solver.SetNumThreads(1)
    x = [solver.BoolVar(f"x{k}") for k in range(len(costs))]
    y: dict[int, Any] = {}
    for r, cols in enumerate(cover):
        if not cols:
            continue
        if optional[r]:
            y[r] = solver.BoolVar(f"y{r}")
            solver.Add(sum(x[k] for k in cols) + y[r] == 1)
        else:
            solver.Add(sum(x[k] for k in cols) == 1)
    for t, cols in enumerate(by_type):
        if cols and len(cols) > c.count[t]:
            solver.Add(sum(x[k] for k in cols) <= c.count[t])
    for used, size in shared:
        solver.Add(sum(n * x[k] for k, n in used) <= size)
    solver.Minimize(
        sum(costs[k] * x[k] for k in range(len(costs)))
        + sum(c.penalty[r] * var for r, var in y.items())
    )
    # OR-Tools 9.15 crashes when HiGHS is given a hint, so HiGHS starts cold.
    if hint and backend != "HIGHS":
        solver.SetHint(x, [1.0 if k in hint else 0.0 for k in range(len(x))])
    solver.SetTimeLimit(int(time_limit * 1000))
    # Prove optimality, not the default 0.01% relative gap: with a vehicle
    # penalty in the costs that tolerance hides real differences.
    params = pywraplp.MPSolverParameters()
    params.SetDoubleParam(pywraplp.MPSolverParameters.RELATIVE_MIP_GAP, 0.0)
    code = solver.Solve(params)
    names = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }
    status = names.get(code, f"CODE_{code}")
    if code not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return None, status
    return [k for k, var in enumerate(x) if var.solution_value() > 0.5], status


def _reload_classes(c: Compiled) -> tuple[list[list[int]], dict[int, int]]:
    """Reload stops grouped into interchangeable copies.

    Two stops of one vehicle type are copies when they share opening hours,
    service time and every travel time and cost to and from them
    (:func:`~mobiroute.vrp.model.add_reload_stops` makes such copies); any
    copy can then stand for any other in a route.
    """
    groups: dict[tuple[object, ...], list[int]] = {}
    for n in range(c.n):
        if c.reload_of[n] < 0:
            continue
        key: tuple[object, ...] = (
            c.reload_of[n],
            c.e[n],
            c.l[n],
            c.s[n],
            tuple(m[n] for m in c.time),
            tuple(tuple(row[n] for row in m) for m in c.time),
            tuple(m[n] for m in c.cost),
            tuple(tuple(row[n] for row in m) for m in c.cost),
        )
        groups.setdefault(key, []).append(n)
    classes = list(groups.values())
    return classes, {n: cl for cl, members in enumerate(classes) for n in members}
