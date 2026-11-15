"""Operating indicators of a verified plan, as a transport department counts them.

Cost says what a day is worth; a fleet manager also asks how the vehicles
worked. For every route and for the whole plan:

* mileage, split into loaded and empty kilometres. A leg is empty when
  nothing is on board after its tail stop: the run back to the depot after
  the last drop, or the drive from one workshop to the next pickup. Empty
  running is the usual target of in-plant and contract transport;
* the mileage utilisation coefficient ``beta = loaded km / total km``
  (коэффициент использования пробега);
* the dynamic load utilisation per dimension, ``gamma = sum(q * d) /
  (Q * loaded km)`` over the loaded legs: the work done over the work the
  body could do while it carries something (динамический коэффициент
  использования грузоподъёмности, normalised by loaded kilometres as in the
  Russian textbook definition), with the load-kilometres ``sum(q * d)``
  behind it (tonne-km when the dimension is tonnes). Empty running is
  ``beta``'s business, so ``beta * gamma`` is the share of the possible
  work over the whole mileage;
* time on duty from the route sheet's departure to the return, split into
  driving, service, the driver's rest and waiting.

The numbers come from the same schedule as the route sheets
(:mod:`mobiroute.vrp.sheets`), so the indicators and the sheets describe
one day. Only a feasible plan has a schedule; an infeasible one has no
indicators.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from mobiroute.vrp.insertion import Compiled, route_loads
from mobiroute.vrp.model import Instance
from mobiroute.vrp.sheets import LOADED_EPS, RouteSheet, route_sheets
from mobiroute.vrp.solution import Solution
from mobiroute.vrp.verify import Verdict


def _ratio(num: float, den: float) -> float | None:
    return num / den if den > 0.0 else None


@dataclass(frozen=True, slots=True)
class RouteKpi:
    vehicle: str
    vehicle_type: str
    hired: bool
    orders: int
    trips: int
    distance: float
    loaded_distance: float
    #: Sum over legs of load times length, per dimension.
    load_distance: tuple[float, ...]
    #: Capacity times loaded kilometres, per dimension: the possible work.
    capacity_distance: tuple[float, ...]
    driving: float
    service: float
    rest: float
    waiting: float
    duty: float

    @property
    def empty_distance(self) -> float:
        return max(0.0, self.distance - self.loaded_distance)

    @property
    def mileage_utilisation(self) -> float | None:
        """``beta``: share of the kilometres driven with goods on board."""
        return _ratio(self.loaded_distance, self.distance)

    @property
    def load_utilisation(self) -> tuple[float | None, ...]:
        """``gamma`` per dimension: load-kilometres over capacity times loaded km."""
        return tuple(
            _ratio(q, cap)
            for q, cap in zip(self.load_distance, self.capacity_distance, strict=True)
        )


@dataclass(frozen=True, slots=True)
class PlanKpi:
    dimensions: tuple[str, ...]
    routes: tuple[RouteKpi, ...]
    served: int
    unserved: int
    cost: float

    def _sum(self, name: str) -> float:
        return math.fsum(getattr(r, name) for r in self.routes)

    @property
    def vehicles(self) -> int:
        return len(self.routes)

    @property
    def hired(self) -> int:
        return sum(1 for r in self.routes if r.hired)

    @property
    def distance(self) -> float:
        return self._sum("distance")

    @property
    def loaded_distance(self) -> float:
        return self._sum("loaded_distance")

    @property
    def empty_distance(self) -> float:
        return max(0.0, self.distance - self.loaded_distance)

    @property
    def mileage_utilisation(self) -> float | None:
        return _ratio(self.loaded_distance, self.distance)

    @property
    def load_distance(self) -> tuple[float, ...]:
        return tuple(
            math.fsum(r.load_distance[d] for r in self.routes) for d in range(len(self.dimensions))
        )

    @property
    def load_utilisation(self) -> tuple[float | None, ...]:
        cap = [
            math.fsum(r.capacity_distance[d] for r in self.routes)
            for d in range(len(self.dimensions))
        ]
        return tuple(_ratio(q, c) for q, c in zip(self.load_distance, cap, strict=True))

    @property
    def duty(self) -> float:
        return self._sum("duty")

    @property
    def driving(self) -> float:
        return self._sum("driving")

    @property
    def waiting(self) -> float:
        return self._sum("waiting")

    @property
    def cost_per_order(self) -> float | None:
        return _ratio(self.cost, float(self.served))

    @property
    def km_per_order(self) -> float | None:
        return _ratio(self.distance, float(self.served))

    def as_dict(self) -> dict[str, object]:
        """Totals and per-route rows for JSON reports (rounded for people)."""

        def r3(x: float | None) -> float | None:
            return None if x is None else round(x, 3)

        dims = self.dimensions
        return {
            "vehicles": self.vehicles,
            "hired": self.hired,
            "served": self.served,
            "unserved": self.unserved,
            "distance_km": r3(self.distance),
            "loaded_km": r3(self.loaded_distance),
            "empty_km": r3(self.empty_distance),
            "mileage_utilisation": r3(self.mileage_utilisation),
            "load_km": {d: r3(v) for d, v in zip(dims, self.load_distance, strict=True)},
            "load_utilisation": {
                d: r3(v) for d, v in zip(dims, self.load_utilisation, strict=True)
            },
            "duty_min": r3(self.duty),
            "driving_min": r3(self.driving),
            "waiting_min": r3(self.waiting),
            "cost": r3(self.cost),
            "cost_per_order": r3(self.cost_per_order),
            "km_per_order": r3(self.km_per_order),
            "routes": [
                {
                    "vehicle": r.vehicle,
                    "hired": r.hired,
                    "orders": r.orders,
                    "trips": r.trips,
                    "distance_km": r3(r.distance),
                    "empty_km": r3(r.empty_distance),
                    "mileage_utilisation": r3(r.mileage_utilisation),
                    "load_utilisation": {
                        d: r3(v) for d, v in zip(dims, r.load_utilisation, strict=True)
                    },
                    "duty_min": r3(r.duty),
                    "driving_min": r3(r.driving),
                    "service_min": r3(r.service),
                    "rest_min": r3(r.rest),
                    "waiting_min": r3(r.waiting),
                }
                for r in self.routes
            ],
        }


def plan_kpi(
    inst: Instance,
    solution: Solution,
    verdict: Verdict,
    sheets: Sequence[RouteSheet] | None = None,
) -> PlanKpi:
    """Indicators of a feasible plan (``ValueError`` for an infeasible one).

    ``sheets`` are the plan's route sheets if already built; they are made
    otherwise. Sheets and routes correspond in order (empty routes skipped).
    """
    if sheets is None:
        sheets = route_sheets(inst, solution, verdict)
    routes = [r for r in solution.routes if r.nodes]
    if len(sheets) != len(routes):
        raise ValueError("KPI_SHEETS_MISMATCH")
    c = Compiled(inst)
    dims = len(inst.dimensions)
    out: list[RouteKpi] = []
    for route, sheet in zip(routes, sheets, strict=True):
        vt = inst.vehicle_types[route.vehicle_type]
        dist = inst.profiles[vt.profile].distance
        seq = [vt.start_depot, *route.nodes, vt.end_depot]
        loads = route_loads(c, route.nodes)  # after positions 0..m: leg k carries loads[k]
        total = loaded = 0.0
        load_km = [0.0] * dims
        for k, (a, b) in enumerate(pairwise(seq)):
            km = dist[a][b]
            total += km
            on_board = loads[k]
            if any(q > LOADED_EPS for q in on_board):
                loaded += km
            for d in range(dims):
                load_km[d] += max(0.0, on_board[d]) * km
        rest = math.fsum(row.end - row.start for row in sheet.rows if row.kind.startswith("rest"))
        service = math.fsum(
            row.end - row.start for row in sheet.rows if not row.kind.startswith("rest")
        )
        out.append(
            RouteKpi(
                vehicle=sheet.vehicle,
                vehicle_type=vt.id,
                hired=vt.hired,
                orders=len(c.requests_of(route.nodes)),
                trips=sheet.trips,
                distance=total,
                loaded_distance=loaded,
                load_distance=tuple(load_km),
                capacity_distance=tuple(cap * loaded for cap in vt.capacity),
                driving=sheet.driving,
                service=service,
                rest=rest,
                waiting=sheet.waiting,
                duty=sheet.shift,
            )
        )
    return PlanKpi(
        dimensions=tuple(inst.dimensions),
        routes=tuple(out),
        served=len(verdict.served),
        unserved=len(verdict.unassigned),
        cost=verdict.cost.total,
    )


def kpi_markdown(kpi: PlanKpi, *, lang: str = "ru") -> str:
    """A one-page summary of the indicators, Russian by default."""
    ru = lang == "ru"

    def num(value: float, spec: str = ".1f") -> str:
        text = format(value, spec)
        return text.replace(".", ",") if ru else text

    def _pct(value: float | None) -> str:
        return "—" if value is None else num(100.0 * value) + "%"

    dims = kpi.dimensions
    gamma = ", ".join(f"{d} {_pct(g)}" for d, g in zip(dims, kpi.load_utilisation, strict=True))
    if ru:
        lines = [
            "# Показатели работы парка",
            "",
            f"Машин: {kpi.vehicles} (наёмных {kpi.hired}); заказов выполнено {kpi.served}, "
            f"не выполнено {kpi.unserved}.",
            "",
            f"Пробег {num(kpi.distance)} км, из них порожний {num(kpi.empty_distance)} км; "
            f"коэффициент использования пробега {_pct(kpi.mileage_utilisation)}.",
            "",
            f"Коэффициент использования грузоподъёмности (динамический, по гружёному "
            f"пробегу): {gamma}.",
            "",
            f"Время в наряде {num(kpi.duty / 60.0)} ч, за рулём {num(kpi.driving / 60.0)} ч, "
            f"ожидание {num(kpi.waiting / 60.0)} ч.",
            "",
            # beta and gamma: the textbook symbols of the two coefficients.
            "| Машина | Заказов | Рейсов | Пробег, км | Порожний, км | β | "
            + " | ".join(f"γ {d}" for d in dims)  # noqa: RUF001
            + " | Наряд, ч | Ожидание, мин |",
            "| --- | ---: | ---: | ---: | ---: | ---: | "
            + " | ".join("---:" for _ in dims)
            + " | ---: | ---: |",
        ]
    else:
        lines = [
            "# Fleet indicators",
            "",
            f"Vehicles: {kpi.vehicles} ({kpi.hired} hired); orders served {kpi.served}, "
            f"unserved {kpi.unserved}.",
            "",
            f"Distance {num(kpi.distance)} km, of it empty {num(kpi.empty_distance)} km; "
            f"mileage utilisation {_pct(kpi.mileage_utilisation)}.",
            "",
            f"Load utilisation (dynamic, over loaded kilometres): {gamma}.",
            "",
            f"On duty {num(kpi.duty / 60.0)} h, driving {num(kpi.driving / 60.0)} h, "
            f"waiting {num(kpi.waiting / 60.0)} h.",
            "",
            "| Vehicle | Orders | Trips | Distance, km | Empty, km | beta | "
            + " | ".join(f"gamma {d}" for d in dims)
            + " | On duty, h | Waiting, min |",
            "| --- | ---: | ---: | ---: | ---: | ---: | "
            + " | ".join("---:" for _ in dims)
            + " | ---: | ---: |",
        ]
    for r in kpi.routes:
        cells = [
            r.vehicle,
            str(r.orders),
            str(r.trips),
            num(r.distance),
            num(r.empty_distance),
            _pct(r.mileage_utilisation),
            *(_pct(g) for g in r.load_utilisation),
            num(r.duty / 60.0),
            num(r.waiting, ".0f"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


__all__ = ["PlanKpi", "RouteKpi", "kpi_markdown", "plan_kpi"]
