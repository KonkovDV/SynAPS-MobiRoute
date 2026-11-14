"""What an order costs and what one more vehicle is worth: LP duality on the route pool.

The set-partitioning model of :mod:`mobiroute.vrp.setpart` picks routes
:math:`\\rho` from a pool :math:`P`. Its linear relaxation

.. math::

    \\min \\sum_{\\rho \\in P} c_\\rho x_\\rho + \\sum_r \\pi_r y_r
    \\quad \\text{s.t.} \\quad
    \\sum_{\\rho \\ni r} x_\\rho + y_r = 1 \\;(u_r), \\qquad
    \\sum_{\\rho \\in P_k} x_\\rho \\le n_k \\;(v_k \\le 0), \\qquad x, y \\ge 0

has the dual

.. math::

    \\max \\sum_r u_r + \\sum_k n_k v_k
    \\quad \\text{s.t.} \\quad
    \\sum_{r \\in \\rho} u_r + v_k \\le c_\\rho \\;\\; \\forall \\rho \\in P_k, \\qquad
    u_r \\le \\pi_r, \\qquad v_k \\le 0 .

:math:`u_r` is the price of order :math:`r`: no route of the pool is cheaper
than the prices of the orders it serves (plus the rent of its vehicle type),
and the routes of an optimal plan cost exactly that. :math:`-v_k` is the rent
of vehicle type :math:`k`: the most the LP value can fall with one more unit
of a type that ran out. By strong duality the prices add up to the value of the relaxation plus
the rents, so when the plan attains that value (:attr:`Prices.tight`) they
split its cost among the orders to the last kopeck.

Two things make the numbers usable rather than merely valid:

* the pool is enlarged by every route of the plan with one order taken out, so
  an optimal plan prices each order at no less than what dropping it would
  save (:attr:`OrderPrice.saving`): with :math:`\\rho` in the plan and
  :math:`\\rho \\setminus r` in the pool, complementary slackness gives
  :math:`u_r \\ge c_\\rho - c_{\\rho \\setminus r}`; and by every route of
  the plan on each other vehicle type that can run it, so a type that ran out
  shows its rent even in a thin pool;
* set-partitioning duals are far from unique (the LP is degenerate), and a
  simplex vertex typically charges a whole route to one of its orders. Among
  all optimal duals the one closest to the savings (smallest sum of absolute
  differences) is returned, by a second LP over the optimal face.

These are prices of a restricted master problem: exact for the pool, an
estimate for the full problem, whose pricing subproblem (an elementary
shortest path with all the rules of the model) is not solved here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from mobiroute.vrp.alns import Alns, AlnsConfig, SolveResult
from mobiroute.vrp.fleet import TypeAssigner, route_money
from mobiroute.vrp.insertion import Compiled, route_exact, tidy_reloads
from mobiroute.vrp.model import Instance
from mobiroute.vrp.setpart import RoutePool, _reload_classes
from mobiroute.vrp.sheets import _md
from mobiroute.vrp.solution import MUST_SERVE_PENALTY, Solution

#: Relative tolerance of "the plan attains the LP value".
TIGHT = 1e-7


@dataclass(frozen=True, slots=True)
class OrderPrice:
    request: str
    served: bool
    #: Dual price of the order in the pool's LP. An order that no route of the
    #: pool serves is priced at its penalty (``None`` if it must be served).
    price: float | None
    #: What the plan saves if this order is simply dropped from its route
    #: (``None``: unserved, or the shortened route is not feasible).
    saving: float | None


@dataclass(frozen=True, slots=True)
class Prices:
    status: str
    columns: int
    #: Search objective of the plan: route money, vehicle penalties, unserved penalties.
    plan_value: float
    #: Optimum of the LP relaxation over the pool (a lower bound for any plan made of it).
    lp_value: float | None
    orders: tuple[OrderPrice, ...]
    #: Rent per vehicle type: the LP's marginal value of one more unit, 0 unless
    #: the type ran out. A rate on the pool's routes, not a forecast for a
    #: whole vehicle: solve again with one more unit to get the amount.
    vehicles: tuple[tuple[str, float], ...]
    #: All scarcity rents together: fleet rows and shared reload stops.
    rents: float
    seconds: float

    @property
    def gap(self) -> float | None:
        """What recombining pool routes could still save, at most (``>= 0``)."""
        return None if self.lp_value is None else self.plan_value - self.lp_value

    @property
    def tight(self) -> bool:
        """The plan attains the LP value: prices minus rents add up to its cost."""
        gap = self.gap
        return gap is not None and gap <= TIGHT * max(1.0, abs(self.plan_value))


def removal_savings(c: Compiled, plan: Solution) -> dict[int, tuple[float | None, int, list[int]]]:
    """Per served order: ``(saving, vehicle type, route without the order)``.

    The saving is exact for the plan as it stands (the other stops keep their
    order); re-optimising after the removal could save more.
    """
    out: dict[int, tuple[float | None, int, list[int]]] = {}
    for route in plan.routes:
        if not route.nodes:
            continue
        t = route.vehicle_type
        money = route_money(c, t, route.nodes)
        for r in sorted(c.requests_of(route.nodes)):
            rest = tidy_reloads(c, [n for n in route.nodes if c.node_req[n] != r])
            if not c.requests_of(rest):
                out[r] = (money, t, [])
            elif route_exact(c, t, rest):
                out[r] = (money - route_money(c, t, rest), t, rest)
            else:  # matrices without the triangle inequality
                out[r] = (None, t, rest)
    return out


def shadow_prices(pool: RoutePool, plan: Solution) -> Prices:
    """Dual prices of orders and vehicle types for ``plan`` over ``pool``.

    The pool gains the plan's routes and each of them with one order removed
    (see the module docstring); it is otherwise left as the search built it.
    """
    from ortools.linear_solver import pywraplp

    started = time.perf_counter()
    c = pool.c
    pool.add(plan)
    savings = removal_savings(c, plan)
    for _saving, t, rest in savings.values():
        if rest:
            pool.add_route(t, rest)
    # The plan's routes on every other vehicle type that can run them: without
    # these columns a type that ran out would show no rent in a thin pool.
    assigner = TypeAssigner(c, lambda t, nodes: route_exact(c, t, nodes))
    for route in plan.routes:
        if route.nodes:
            for t in assigner.options(route):
                pool.add_route(t, route.nodes)
    plan_value = sum(route_money(c, r.vehicle_type, r.nodes) for r in plan.routes if r.nodes)
    plan_value += sum(c.penalty[r] for r in plan.unassigned)

    keys = sorted(pool.columns)
    n_req = len(c.penalty)
    covered = [False] * n_req
    per_type = [0] * c.n_types
    for t, requests in keys:
        per_type[t] += 1
        for r in requests:
            covered[r] = True
    classes, class_of = _reload_classes(c)
    uses: list[dict[int, int]] = [{} for _ in classes]
    for k, key in enumerate(keys):
        for n in pool.columns[key][1]:
            if c.reload_of[n] >= 0:
                cl = class_of[n]
                uses[cl][k] = uses[cl].get(k, 0) + 1
    shared = [cl for cl, u in enumerate(uses) if sum(u.values()) > len(classes[cl])]

    solver: Any = pywraplp.Solver.CreateSolver("GLOP")
    inf = solver.infinity()
    u: dict[int, Any] = {}
    for r in range(n_req):
        if not covered[r]:
            continue
        # As in the integer model: an order the plan serves and that must be
        # served has no "left out" variable, so its price has no upper bound.
        optional = c.penalty[r] < MUST_SERVE_PENALTY or r in plan.unassigned
        u[r] = solver.NumVar(-inf, c.penalty[r] if optional else inf, f"u{r}")
    v = {t: solver.NumVar(-inf, 0.0, f"v{t}") for t in range(c.n_types) if per_type[t] > c.count[t]}
    w = {cl: solver.NumVar(-inf, 0.0, f"w{cl}") for cl in shared}
    for k, (t, requests) in enumerate(keys):
        row = solver.Constraint(-inf, pool.columns[keys[k]][0])
        for r in requests:
            row.SetCoefficient(u[r], 1.0)
        if t in v:
            row.SetCoefficient(v[t], 1.0)
        for cl in shared:
            if k in uses[cl]:
                row.SetCoefficient(w[cl], float(uses[cl][k]))
    dual = solver.Objective()
    for var in u.values():
        dual.SetCoefficient(var, 1.0)
    for t, var in v.items():
        dual.SetCoefficient(var, float(c.count[t]))
    for cl, var in w.items():
        dual.SetCoefficient(var, float(len(classes[cl])))
    dual.SetMaximization()
    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return _no_prices(c, plan, savings, "LP_NOT_SOLVED", len(keys), plan_value, started)
    # An order no pool route serves is left out by every plan of the pool: its
    # penalty is a constant of the LP and, when finite, its price.
    lp_value = float(dual.Value()) + sum(c.penalty[r] for r in range(n_req) if not covered[r])
    dual_value = float(dual.Value())

    # Second LP: stay on the optimal face, move towards the removal savings.
    face = solver.Constraint(dual_value - TIGHT * max(1.0, abs(dual_value)), inf)
    for var in u.values():
        face.SetCoefficient(var, 1.0)
    for t, var in v.items():
        face.SetCoefficient(var, float(c.count[t]))
    for cl, var in w.items():
        face.SetCoefficient(var, float(len(classes[cl])))
    dual.Clear()
    for r, var in u.items():
        target = savings.get(r, (None, 0, []))[0]
        if target is None:
            continue
        away = solver.NumVar(0.0, inf, f"d{r}")
        above = solver.Constraint(-inf, target)  # u_r - away <= target
        above.SetCoefficient(var, 1.0)
        above.SetCoefficient(away, -1.0)
        below = solver.Constraint(target, inf)  # u_r + away >= target
        below.SetCoefficient(var, 1.0)
        below.SetCoefficient(away, 1.0)
        dual.SetCoefficient(away, 1.0)
    dual.SetMinimization()
    status = "OPTIMAL" if solver.Solve() == pywraplp.Solver.OPTIMAL else "LP_NOT_SOLVED"
    if status != "OPTIMAL":
        return _no_prices(c, plan, savings, status, len(keys), plan_value, started)

    served = c.requests_of(n for route in plan.routes for n in route.nodes)
    orders = tuple(
        OrderPrice(
            request=c.inst.requests[r].id,
            served=r in served,
            price=float(u[r].solution_value())
            if r in u
            else (c.penalty[r] if c.penalty[r] < MUST_SERVE_PENALTY else None),
            saving=savings[r][0] if r in savings else None,
        )
        for r in range(n_req)
    )
    rent = {t: -float(var.solution_value()) for t, var in v.items()}
    vehicles = tuple(
        (vt.id, max(0.0, rent.get(t, 0.0))) for t, vt in enumerate(c.inst.vehicle_types)
    )
    rents = sum(c.count[t] * value for t, value in rent.items())
    rents += sum(-len(classes[cl]) * float(var.solution_value()) for cl, var in w.items())
    return Prices(
        status=status,
        columns=len(keys),
        plan_value=plan_value,
        lp_value=lp_value,
        orders=orders,
        vehicles=vehicles,
        rents=rents,
        seconds=round(time.perf_counter() - started, 3),
    )


def solve_with_prices(
    inst: Instance, config: AlnsConfig | None = None
) -> tuple[SolveResult, Prices]:
    """ALNS with the route pool kept, then the prices of its best plan.

    The plan is the one :func:`mobiroute.vrp.alns.solve` returns for the same
    configuration: collecting the pool does not change the search.
    """
    search = Alns(inst, replace(config or AlnsConfig(), keep_pool=True))
    result = search.solve()
    assert search.pool is not None
    return result, shadow_prices(search.pool, result.solution)


def _no_prices(
    c: Compiled,
    plan: Solution,
    savings: dict[int, tuple[float | None, int, list[int]]],
    status: str,
    columns: int,
    plan_value: float,
    started: float,
) -> Prices:
    served = c.requests_of(n for route in plan.routes for n in route.nodes)
    orders = tuple(
        OrderPrice(req.id, r in served, None, savings[r][0] if r in savings else None)
        for r, req in enumerate(c.inst.requests)
    )
    vehicles = tuple((vt.id, 0.0) for vt in c.inst.vehicle_types)
    seconds = round(time.perf_counter() - started, 3)
    return Prices(status, columns, plan_value, None, orders, vehicles, 0.0, seconds)


def prices_dict(prices: Prices) -> dict[str, Any]:
    """JSON-ready form (``prices.json`` of ``vrp-solve --prices``)."""
    return {
        "format": "mobiroute.vrp.prices.v1",
        "status": prices.status,
        "columns": prices.columns,
        "plan_value": round(prices.plan_value, 4),
        "lp_value": None if prices.lp_value is None else round(prices.lp_value, 4),
        "gap": None if prices.gap is None else round(prices.gap, 4),
        "tight": prices.tight,
        "rents": round(prices.rents, 4),
        "vehicles": [{"type": vid, "rent": round(value, 4)} for vid, value in prices.vehicles],
        "orders": [
            {
                "request": o.request,
                "served": o.served,
                "price": None if o.price is None else round(o.price, 4),
                "saving": None if o.saving is None else round(o.saving, 4),
            }
            for o in prices.orders
        ],
    }


_TEXT = {
    "ru": {
        "title": "# Цены заказов и машин",
        "plan": "Стоимость плана",
        "lp": "LP-оценка по пулу из {n} маршрутов",
        "tight": "план достигает оценки: цены заказов минус рента в сумме дают стоимость плана",
        "loose": "перекомбинация маршрутов пула может дать ещё не больше {gap}",
        "rent": "Рента дефицитных машин (предельная LP-оценка ещё одной)",
        "none": "нет: машин каждого типа хватает",
        "head": "| Заказ | Цена | Экономия при отказе | Обслужен |",
        "yes": "да",
        "no": "нет",
        "note": (
            "Цена — двойственная оценка заказа в LP-релаксации разбиения множества по "
            "пулу маршрутов; экономия — на сколько дешевеет план, если заказ просто "
            "убрать из рейса."
        ),
    },
    "en": {
        "title": "# Prices of orders and vehicles",
        "plan": "Plan cost",
        "lp": "LP bound over a pool of {n} routes",
        "tight": "the plan attains the bound: order prices minus rents add up to its cost",
        "loose": "recombining pool routes can save at most {gap} more",
        "rent": "Rent of scarce vehicles (the LP's marginal value of one more)",
        "none": "none: no vehicle type ran out",
        "head": "| Order | Price | Saving if dropped | Served |",
        "yes": "yes",
        "no": "no",
        "note": (
            "The price is the order's dual value in the LP relaxation of set partitioning "
            "over the route pool; the saving is how much cheaper the plan gets if the "
            "order is simply taken out of its route."
        ),
    },
}


def _num(value: float | None, lang: str) -> str:
    if value is None:
        return "—"
    text = f"{value:,.2f}"
    return text.replace(",", " ").replace(".", ",") if lang == "ru" else text


def prices_markdown(prices: Prices, *, lang: str = "ru", currency: str = "") -> str:
    """Human-readable table, orders from the most expensive down."""
    tx = _TEXT[lang]
    unit = f" {currency}" if currency else ""
    lines = [tx["title"], "", f"{tx['plan']}: {_num(prices.plan_value, lang)}{unit}."]
    if prices.lp_value is not None:
        verdict = (
            tx["tight"] if prices.tight else tx["loose"].format(gap=_num(prices.gap, lang) + unit)
        )
        lines.append(
            f"{tx['lp'].format(n=prices.columns)}: {_num(prices.lp_value, lang)}{unit} — {verdict}."
        )
    scarce = [(vid, value) for vid, value in prices.vehicles if value > 1e-9]
    rent = (
        "; ".join(f"{vid}: {_num(value, lang)}{unit}" for vid, value in scarce)
        if scarce
        else tx["none"]
    )
    lines += [f"{tx['rent']}: {rent}.", "", tx["head"], "| --- | ---: | ---: | :---: |"]
    ranked = sorted(prices.orders, key=lambda o: (-(o.price or 0.0), o.request))
    for o in ranked:
        cell = _md(o.request)
        lines.append(
            f"| {cell} | {_num(o.price, lang)} | {_num(o.saving, lang)} "
            f"| {tx['yes'] if o.served else tx['no']} |"
        )
    lines += ["", tx["note"], ""]
    return "\n".join(lines)
