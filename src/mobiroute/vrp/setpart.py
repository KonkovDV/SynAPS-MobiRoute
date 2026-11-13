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
from mobiroute.vrp.solution import Route, Solution

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
) -> SpResult:
    """Best plan made of pool routes (see module docstring).

    ``deterministic`` gives CP-SAT a deterministic-time budget instead of a
    wall-clock one, so the same pool always gives the same plan.
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
    hint: set[int] = set()
    if incumbent is not None:
        lookup = {key: k for k, key in enumerate(keys)}
        for route in incumbent.routes:
            if route.nodes:
                key = (route.vehicle_type, tuple(sorted(c.requests_of(route.nodes))))
                if key in lookup:
                    hint.add(lookup[key])
    if backend == "CP-SAT":
        chosen, status = _solve_cpsat(c, cover, by_type, costs, hint, time_limit, deterministic)
    else:
        chosen, status = _solve_mip(c, cover, by_type, costs, hint, time_limit, backend)
    seconds = time.perf_counter() - started
    if chosen is None:
        return SpResult(None, None, status, seconds, len(keys), backend)
    routes = []
    served: set[int] = set()
    for k in chosen:
        t, requests = keys[k]
        routes.append(Route(t, list(pool.columns[keys[k]][1])))
        served.update(requests)
    unassigned = set(range(len(c.penalty))) - served
    sol = Solution(routes, unassigned)
    value = sum(costs[k] for k in chosen) + sum(c.penalty[r] for r in unassigned)
    return SpResult(sol, value, status, seconds, len(keys), backend)


def _solve_cpsat(
    c: Compiled,
    cover: list[list[int]],
    by_type: list[list[int]],
    costs: list[float],
    hint: set[int],
    time_limit: float,
    deterministic: bool,
) -> tuple[list[int] | None, str]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x = [model.new_bool_var(f"x{k}") for k in range(len(costs))]
    y: dict[int, Any] = {}
    for r, cols in enumerate(cover):
        if cols:
            y[r] = model.new_bool_var(f"y{r}")
            model.add(sum(x[k] for k in cols) + y[r] == 1)
    for t, cols in enumerate(by_type):
        if cols and len(cols) > c.count[t]:
            model.add(sum(x[k] for k in cols) <= c.count[t])
    model.minimize(
        sum(round(SCALE * costs[k]) * x[k] for k in range(len(costs)))
        + sum(round(SCALE * c.penalty[r]) * var for r, var in y.items())
    )
    for k, var in enumerate(x):
        model.add_hint(var, k in hint)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
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
    by_type: list[list[int]],
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
        if cols:
            y[r] = solver.BoolVar(f"y{r}")
            solver.Add(sum(x[k] for k in cols) + y[r] == 1)
    for t, cols in enumerate(by_type):
        if cols and len(cols) > c.count[t]:
            solver.Add(sum(x[k] for k in cols) <= c.count[t])
    solver.Minimize(
        sum(costs[k] * x[k] for k in range(len(costs)))
        + sum(c.penalty[r] * var for r, var in y.items())
    )
    if hint:
        solver.SetHint(x, [1.0 if k in hint else 0.0 for k in range(len(x))])
    solver.SetTimeLimit(int(time_limit * 1000))
    code = solver.Solve()
    names = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }
    status = names.get(code, str(code))
    if code not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return None, status
    return [k for k, var in enumerate(x) if var.solution_value() > 0.5], status
