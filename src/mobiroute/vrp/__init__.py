"""Rich vehicle routing: heterogeneous fleet, capacity vector, time windows, pickup and delivery.

Typical use::

    from mobiroute.vrp import AlnsConfig, load_benchmark, solve, verify

    inst, sha256 = load_benchmark("benchmark/instances/solomon/R101.txt")
    result = solve(inst, AlnsConfig(time_limit=10, seed=1))
    print(result.verdict.summary())

Modules
-------
``model``        frozen instance data with validation
``io``           Solomon, Li & Lim, Sartori-Buriol, Cordeau readers; JSON format
``schedule``     difference constraints, Bellman-Ford, certificates
``insertion``    O(1) insertion tests and regret-k repair (reference implementation)
``native``       the same repair in Rust (``mobiroute_native.VrpKernel``)
``alns``         adaptive large neighbourhood search with guided ejection
``exact``        CP-SAT model for proven optima on small instances
``ortools_lane`` OR-Tools Routing baseline on the same model
``lateness``     minimal-lateness schedules (bisection and LP)
``realtime``     live dispatch simulator and policies
``verify``       independent verifier
``generators``   synthetic cargo, shuttle and plant days
``render``       SVG route maps
"""

from mobiroute.vrp.alns import AlnsConfig, SolveResult, search_objective, solve
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
from mobiroute.vrp.solution import CostBreakdown, Route, Solution, evaluate
from mobiroute.vrp.verify import Verdict, verify

__all__ = [
    "AlnsConfig",
    "CostBreakdown",
    "Instance",
    "Node",
    "Profile",
    "Request",
    "Route",
    "Solution",
    "SolveResult",
    "VehicleType",
    "Verdict",
    "evaluate",
    "instance_from_json",
    "instance_to_json",
    "load_benchmark",
    "parse_cordeau_vrp",
    "parse_lilim",
    "parse_sartori_buriol",
    "parse_solomon",
    "search_objective",
    "solve",
    "verify",
]
