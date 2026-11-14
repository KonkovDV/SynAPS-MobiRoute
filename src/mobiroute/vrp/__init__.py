"""Rich vehicle routing: heterogeneous fleet, capacity vector, time windows, pickup and delivery.

Typical use::

    from mobiroute.vrp import AlnsConfig, load_benchmark, solve, verify

    inst, sha256 = load_benchmark("benchmark/instances/solomon/R101.txt")
    result = solve(inst, AlnsConfig(time_limit=10, seed=1))
    print(result.verdict.summary())

From coordinates to route sheets::

    from mobiroute.vrp import AlnsConfig, geo, route_sheets, sheets_markdown, solve

    day = geo.load("examples/chelny-day.geo.json")  # osrm="http://localhost:5000"
    result = solve(day.instance, AlnsConfig(time_limit=10, seed=1))
    sheets = route_sheets(day.instance, result.solution, result.verdict, day.places)
    print(sheets_markdown(sheets, day.instance.dimensions, currency=day.currency))

Modules
-------
``model``        frozen instance data with validation; rests, reload stops, speed profiles
``io``           Solomon, Li & Lim, Sartori-Buriol, Cordeau readers; JSON format
``geo``          coordinates in: offline great-circle or OSRM road matrices
``schedule``     difference constraints, Bellman-Ford, certificates, the dispatcher's schedule
``traffic``      time-dependent travel (FIFO arrival function and its inverse)
``insertion``    O(1) insertion tests and regret-k repair (reference implementation)
``native``       the same repair in Rust (``mobiroute_native.VrpKernel``)
``alns``         adaptive large neighbourhood search with guided ejection
``fleet``        vehicle type per route as a transportation problem (min-cost flow)
``merge``        two routes onto one vehicle; trips chained through a reload
``local_search`` relocate, swap, 2-opt*, 2-opt with time-window segments
``setpart``      set partitioning over the route pool (CP-SAT, SCIP, HiGHS, CBC)
``prices``       LP duals of that model: the price of an order, the rent of a vehicle type
``exact``        CP-SAT model for proven optima on small instances
``ortools_baseline`` OR-Tools Routing baseline on the same model
``lateness``     minimal-lateness schedules (bisection and LP)
``realtime``     live dispatch simulator and policies
``verify``       independent verifier
``sheets``       route sheets (CSV, Markdown) from a verified plan
``generators``   synthetic cargo, DC, shuttle and plant days
``render``       SVG route maps
"""

from mobiroute.vrp import geo
from mobiroute.vrp.alns import AlnsConfig, SolveResult, search_objective, solve
from mobiroute.vrp.geo import GeoInstance, Place
from mobiroute.vrp.io import (
    instance_from_json,
    instance_to_json,
    load_benchmark,
    parse_cordeau_vrp,
    parse_lilim,
    parse_sartori_buriol,
    parse_solomon,
)
from mobiroute.vrp.model import Instance, Node, Profile, Request, VehicleType
from mobiroute.vrp.prices import Prices, prices_markdown, shadow_prices, solve_with_prices
from mobiroute.vrp.sheets import RouteSheet, route_sheets, sheets_csv, sheets_markdown
from mobiroute.vrp.solution import CostBreakdown, Route, Solution, evaluate
from mobiroute.vrp.verify import Verdict, verify

__all__ = [
    "AlnsConfig",
    "CostBreakdown",
    "GeoInstance",
    "Instance",
    "Node",
    "Place",
    "Prices",
    "Profile",
    "Request",
    "Route",
    "RouteSheet",
    "Solution",
    "SolveResult",
    "VehicleType",
    "Verdict",
    "evaluate",
    "geo",
    "instance_from_json",
    "instance_to_json",
    "load_benchmark",
    "parse_cordeau_vrp",
    "parse_lilim",
    "parse_sartori_buriol",
    "parse_solomon",
    "prices_markdown",
    "route_sheets",
    "search_objective",
    "shadow_prices",
    "sheets_csv",
    "sheets_markdown",
    "solve",
    "solve_with_prices",
    "verify",
]
