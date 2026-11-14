"""Rich-VRP engine: readers, verifier, solvers and dispatch on small cases."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mobiroute.cli import main
from mobiroute.vrp.alns import AlnsConfig, search_objective, solve
from mobiroute.vrp.exact import solve_exact
from mobiroute.vrp.generators import cargo_day, plant_day, random_instance, shuttle_day
from mobiroute.vrp.io import (
    instance_from_json,
    instance_to_json,
    load_benchmark,
    parse_lilim,
    parse_solomon,
)
from mobiroute.vrp.lateness import min_max_lateness, min_total_lateness
from mobiroute.vrp.model import Instance, Node, Request, VehicleType, single_profile
from mobiroute.vrp.ortools_lane import solve_ortools
from mobiroute.vrp.realtime import Dispatcher, simulate
from mobiroute.vrp.schedule import route_timing
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]
INST = ROOT / "benchmark" / "instances"


@pytest.mark.parametrize(
    ("relpath", "requests", "nodes"),
    [
        ("solomon/C101.txt", 100, 101),
        ("solomon/RC208.txt", 100, 101),
        ("lilim/LC101.txt", 53, 107),
        ("sartori-buriol/n100/poa-n100-7.txt", 50, 101),
        ("cordeau/a2-16.txt", 16, 34),
        ("cordeau/b8-96.txt", 96, 194),
    ],
)
def test_benchmark_readers(relpath: str, requests: int, nodes: int) -> None:
    inst, digest = load_benchmark(INST / relpath)
    assert inst.n_requests == requests and inst.n_nodes == nodes
    assert digest == hashlib.sha256((INST / relpath).read_bytes()).hexdigest()


def test_every_vendored_file_matches_its_checksum() -> None:
    families = ["cordeau", "solomon", "lilim", "sartori-buriol/n100"]
    seen = 0
    for family in families:
        directory = INST / family
        for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
            digest, name = line.split(None, 1)
            assert hashlib.sha256((directory / name.strip()).read_bytes()).hexdigest() == digest
            seen += 1
    assert seen == 48 + 56 + 1 + 25


def test_references_cover_every_instance() -> None:
    refs = {
        "cordeau": json.loads((ROOT / "benchmark/references/cordeau.json").read_text()),
        "solomon": json.loads((ROOT / "benchmark/references/solomon.json").read_text()),
        "sartori-buriol/n100": json.loads(
            (ROOT / "benchmark/references/sartori-buriol-n100.json").read_text()
        ),
    }
    for family, doc in refs.items():
        names = {p.stem for p in (INST / family).glob("*.txt") if p.name != "SHA256SUMS.txt"}
        assert names == set(doc["instances"]), family


def test_readers_reject_malformed_files() -> None:
    with pytest.raises(ValueError, match="SOLOMON"):
        parse_solomon("C1\n\nVEHICLE\nNUMBER CAPACITY\n 25 200\nCUSTOMER\n 0 1 2 3\n")
    with pytest.raises(ValueError, match="LILIM_HEADER"):
        parse_lilim("25 200\n0 0 0 0 0 100 0 0 0\n", name="bad")
    with pytest.raises(ValueError, match="LILIM_PAIR_INVALID"):
        parse_lilim(
            "2 10 1\n0 0 0 0 0 100 0 0 0\n1 1 1 5 0 100 0 0 9\n2 2 2 -5 0 100 0 1 0\n", name="bad"
        )


def test_model_validation_codes() -> None:
    nodes = (Node(0, 0, 100), Node(1, 0, 100), Node(2, 0, 100))
    profile = single_profile(((0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0)))
    vt = VehicleType("v", (10.0,))
    ok = Instance("ok", nodes, (Request("a", 1, 2, (1.0,)),), (vt,), profile)
    assert ok.request_of(2) == 0 and ok.request_of(0) == -1
    with pytest.raises(ValueError, match="VRP_REQUEST_AT_DEPOT"):
        Instance("x", nodes, (Request("a", 0, 2, (1.0,)),), (vt,), profile)
    with pytest.raises(ValueError, match="VRP_NODE_SHARED"):
        Instance(
            "x", nodes, (Request("a", 1, 2, (1.0,)), Request("b", None, 2, (1.0,))), (vt,), profile
        )
    with pytest.raises(ValueError, match="VRP_DEMAND_INVALID"):
        Instance("x", nodes, (Request("a", 1, 2, (1.0, 2.0)),), (vt,), profile)
    with pytest.raises(ValueError, match="VRP_MAX_RIDE_NEEDS_A_PAIR"):
        Instance("x", nodes, (Request("a", None, 2, (1.0,), max_ride=5.0),), (vt,), profile)


def test_json_round_trip_keeps_the_instance() -> None:
    inst = cargo_day(3, n_orders=20)
    again = instance_from_json(instance_to_json(inst))
    assert again.nodes == inst.nodes and again.requests == inst.requests
    assert again.vehicle_types == inst.vehicle_types
    assert again.profiles["truck"].time == inst.profiles["truck"].time


def test_verifier_catches_tampered_plans() -> None:
    inst, _ = load_benchmark(INST / "lilim" / "LC101.txt")
    good = solve(inst, AlnsConfig(iterations=200, seed=1)).solution
    assert verify(inst, good).feasible
    route = good.routes[0]
    req = inst.requests[inst.request_of(route.nodes[0])]
    # Delivery before pickup.
    swapped = good.copy()
    nodes = swapped.routes[0].nodes
    a, b = nodes.index(req.pickup), nodes.index(req.delivery)
    nodes[a], nodes[b] = nodes[b], nodes[a]
    assert any(v.startswith("DELIVERY_BEFORE_PICKUP") for v in verify(inst, swapped).violations)
    # A request silently dropped from the books.
    lost = good.copy()
    lost.routes[0].nodes = [
        n for n in lost.routes[0].nodes if inst.request_of(n) != inst.request_of(route.nodes[0])
    ]
    assert any(v.startswith("UNACCOUNTED") for v in verify(inst, lost).violations)
    # A pair split across two vehicles.
    split = good.copy()
    split.routes[0].nodes.remove(req.delivery)
    split.routes[1].nodes.append(req.delivery)
    assert any(v.startswith("SPLIT_REQUEST") for v in verify(inst, split).violations)


def test_certificate_names_the_conflict_and_the_minutes() -> None:
    # Supplier opens at 540 with 26 min of loading, the drive takes 162.8 min,
    # the customer closes at 720: the earliest delivery is 728.8, 8.8 min late.
    nodes = (Node(0, 0, 1440), Node(1, 540, 780, 26.0, name="S"), Node(2, 480, 720, 26.0, name="C"))
    matrix = ((0.0, 60.0, 60.0), (60.0, 0.0, 162.8), (60.0, 162.8, 0.0))
    inst = Instance(
        "transfer",
        nodes,
        (Request("T", 1, 2, (1.0,)),),
        (VehicleType("truck", (10.0,)),),
        single_profile(matrix),
    )
    timing = route_timing(inst, 0, [1, 2])
    assert not timing.feasible and timing.infeasibility is not None
    assert timing.infeasibility.short_by == pytest.approx(8.8, abs=1e-6)
    assert set(timing.infeasibility.labels) == {"EARLIEST:1", "TRAVEL:1->2", "LATEST:2"}
    verdict = verify(inst, Solution([Route(0, [1, 2])], set()))
    assert not verdict.feasible and verdict.certificates[0][1].short_by == pytest.approx(8.8)
    assert min_max_lateness(inst, 0, [1, 2]) == pytest.approx(8.8, abs=1e-3)


def test_lateness_matches_the_certificate_and_lp_is_consistent() -> None:
    inst, _ = load_benchmark(INST / "solomon" / "C101.txt")
    route = max(
        solve(inst, AlnsConfig(iterations=200, seed=1)).solution.routes, key=lambda r: len(r.nodes)
    )
    broken = route.nodes[1:] + route.nodes[:1]
    timing = route_timing(inst, 0, broken)
    assert not timing.feasible and timing.infeasibility is not None
    delta = min_max_lateness(inst, 0, broken)
    assert delta is not None and delta == pytest.approx(timing.infeasibility.short_by, abs=1e-3)
    plan = min_total_lateness(inst, 0, broken)
    assert plan is not None and plan.worst == pytest.approx(delta, abs=1e-3)
    assert plan.total >= plan.worst - 1e-9
    assert min_max_lateness(inst, 0, route.nodes) == 0.0


def test_exact_model_and_alns_agree_on_small_rich_instances() -> None:
    for seed in (102, 105, 113):
        inst = random_instance(seed, n_requests=6, n_types=2, ride_share=0.4, penalty=1000.0)
        exact = solve_exact(inst, time_limit=30, workers=4)
        heur = solve(inst, AlnsConfig(iterations=800, seed=1))
        assert exact.status == "OPTIMAL" and exact.verdict.feasible and heur.verdict.feasible
        assert search_objective(inst, heur.solution) == pytest.approx(
            search_objective(inst, exact.solution), rel=1e-9
        )


def test_ortools_lane_returns_verified_plans() -> None:
    inst, _ = load_benchmark(INST / "solomon" / "C101.txt")
    run = solve_ortools(inst, time_limit=2.0)
    assert run.verdict.feasible and run.verdict.complete
    assert run.verdict.cost.vehicles == 10 and run.verdict.cost.distance == pytest.approx(
        828.94, abs=0.01
    )
    hf = solve_ortools(cargo_day(4, n_orders=25), time_limit=2.0)
    assert hf.verdict.feasible


@pytest.mark.parametrize(("name", "optimum"), [("b2-16", 309.41), ("a2-20", 344.83)])
def test_alns_reaches_published_optima(name: str, optimum: float) -> None:
    inst, _ = load_benchmark(INST / "cordeau" / f"{name}.txt")
    res = solve(inst, AlnsConfig(iterations=1500, seed=1))
    assert res.verdict.feasible and res.verdict.complete
    assert res.verdict.cost.distance == pytest.approx(optimum, abs=0.01)


def test_heterogeneous_fleet_prefers_own_vehicles() -> None:
    inst = cargo_day(7, n_orders=40)
    res = solve(inst, AlnsConfig(iterations=1500, seed=1))
    assert res.verdict.feasible and res.verdict.complete
    hired = sum(n for vid, n in res.verdict.cost.vehicles_by_type.items() if vid.endswith("hired"))
    assert hired == 0


def test_dispatch_keeps_every_promise() -> None:
    for inst in (shuttle_day(3, n_orders=60, n_buses=4), plant_day(2, n_moves=50)):
        rep = simulate(inst, "insertion")
        assert rep.verified, rep.violations
        assert all(d.latency_ms < 50 for d in rep.decisions)
        refused = [d for d in rep.decisions if not d.accepted]
        assert all(d.reason for d in refused)


def test_dispatch_snapshot_is_a_valid_static_instance() -> None:
    inst = plant_day(3, n_moves=60)
    disp = Dispatcher(inst)
    order = sorted(range(inst.n_requests), key=lambda r: inst.requests[r].release)
    for r in order[:30]:
        disp._insert(r, inst.requests[r].release)
    tau = inst.requests[order[30]].release
    snap, plan, _owners = disp.snapshot(tau)
    assert verify(snap, plan).feasible


def test_dispatch_rejects_ride_limits() -> None:
    inst, _ = load_benchmark(INST / "cordeau" / "a2-16.txt")
    with pytest.raises(ValueError, match="REALTIME_RIDE_LIMITS_AS_DEADLINES"):
        Dispatcher(inst)


def test_cli_vrp_commands(tmp_path: Path) -> None:
    code = main(
        [
            "vrp-solve",
            "--instance",
            str(INST / "lilim" / "LC101.txt"),
            "--iterations",
            "300",
            "--out-dir",
            str(tmp_path / "a"),
            "--svg",
        ]
    )
    assert code == 0
    verdict = json.loads((tmp_path / "a" / "verdict.json").read_text())
    assert verdict["feasible"] and verdict["vehicles"] == 10
    assert (tmp_path / "a" / "routes.svg").read_text().startswith("<svg")
    assert (
        main(
            [
                "vrp-solve",
                "--generate",
                "cargo",
                "--orders",
                "20",
                "--iterations",
                "200",
                "--out-dir",
                str(tmp_path / "b"),
            ]
        )
        == 0
    )
    assert main(["vrp-dispatch", "--day", "plant", "--out-dir", str(tmp_path / "c")]) == 0
    assert json.loads((tmp_path / "c" / "dispatch.json").read_text())["verified"]


def test_python_and_route_cost_bookkeeping_agree() -> None:
    inst = cargo_day(5, n_orders=30)
    res = solve(inst, AlnsConfig(iterations=300, seed=2))
    assert isinstance(res.solution, Solution)
    assert all(isinstance(r, Route) for r in res.solution.routes)
    assert res.objective == pytest.approx(search_objective(inst, res.solution))


def test_min_cost_assignment_matches_brute_force() -> None:
    import itertools
    import random as _random

    from mobiroute.vrp.fleet import min_cost_assignment

    rng = _random.Random(4)
    for _ in range(200):
        rows, cols = rng.randint(1, 5), rng.randint(1, 4)
        capacity = [rng.randint(0, 3) for _ in range(cols)]
        options = []
        for _r in range(rows):
            allowed = [k for k in range(cols) if rng.random() < 0.7]
            options.append({k: float(rng.randint(1, 50)) for k in allowed})
        best = None
        for combo in itertools.product(range(cols), repeat=rows):
            if any(k not in options[r] for r, k in enumerate(combo)):
                continue
            if any(combo.count(k) > capacity[k] for k in range(cols)):
                continue
            cost = sum(options[r][k] for r, k in enumerate(combo))
            best = cost if best is None else min(best, cost)
        got = min_cost_assignment(options, capacity)
        if best is None:
            assert got is None
        else:
            assert got is not None
            assert sum(options[r][k] for r, k in enumerate(got)) == pytest.approx(best)
            assert all(got.count(k) <= capacity[k] for k in range(cols))


def test_route_retyping_fixes_the_fleet_mix_trap() -> None:
    # Seed 1025: the optimum runs its longest route on the type with a fixed
    # fee and no time cost; insertion alone never opens that vehicle.
    inst = random_instance(1025, n_requests=8, n_types=3, ride_share=0.4, penalty=1000.0)
    res = solve(inst, AlnsConfig(iterations=2000, seed=1))
    assert res.verdict.feasible
    assert search_objective(inst, res.solution) == pytest.approx(756.3367, abs=1e-3)


@pytest.mark.parametrize(("seed", "optimum"), [(1023, 4046.03), (1037, 1975.91)])
def test_alns_reaches_optima_that_need_a_route_merge(seed: int, optimum: float) -> None:
    # The two instances ALNS missed before the merge operator: CP-SAT proves
    # these optima, and both put two small routes on one larger vehicle.
    inst = random_instance(seed, n_requests=8, n_types=3, ride_share=0.4, penalty=1000.0)
    res = solve(inst, AlnsConfig(iterations=2000, seed=1))
    assert res.verdict.feasible
    assert search_objective(inst, res.solution) == pytest.approx(optimum, abs=0.01)


def test_merge_operator_turns_the_local_optimum_into_the_optimum() -> None:
    from mobiroute.vrp.alns import Alns

    inst = random_instance(1037, n_requests=8, n_types=3, ride_share=0.4, penalty=1000.0)
    alns = Alns(inst, AlnsConfig(seed=1, backend="python"))
    assert alns.merger is not None
    ids = {vt.id: t for t, vt in enumerate(inst.vehicle_types)}
    # The plan ALNS stopped at without the operator: five routes.
    trapped = Solution(
        [
            Route(ids["type0"], [12, 13, 14, 15]),
            Route(ids["type1"], [7, 1, 8, 2]),
            Route(ids["type2"], [9, 10]),
            Route(ids["type0"], [3, 4]),
            Route(ids["type0"], [11]),
        ],
        {2},
    )
    assert verify(inst, trapped).feasible
    merged = alns.merger.improve(trapped)
    assert verify(inst, merged).feasible
    assert search_objective(inst, trapped) == pytest.approx(2068.35, abs=0.01)
    assert search_objective(inst, merged) == pytest.approx(1975.91, abs=0.01)
    assert sorted(len(r.nodes) for r in merged.routes if r.nodes) == [2, 3, 4, 4]


def test_ortools_lane_ignores_nodes_of_absent_orders() -> None:
    # A live snapshot keeps every node of the day but only a few open orders;
    # Routing must not be asked to visit the nodes of orders that do not exist.
    from dataclasses import replace

    day = plant_day(5)
    inst = replace(day, requests=day.requests[:3])
    run = solve_ortools(inst, time_limit=1.0)
    assert run.verdict.feasible and not run.solution.unassigned


@pytest.mark.parametrize("backend", ["CP-SAT", "SCIP", "HIGHS", "CBC"])
def test_set_partitioning_returns_a_verified_plan_no_worse(backend: str) -> None:
    from mobiroute.vrp.alns import Alns
    from mobiroute.vrp.setpart import SpBackend, solve_set_partitioning

    inst = cargo_day(5, n_orders=30)
    cfg = AlnsConfig(iterations=300, seed=2, setpart=True, sp_every=10**9, sp_final=False)
    alns = Alns(inst, cfg)
    res = alns.solve()
    assert alns.pool is not None and len(alns.pool) > 0
    chosen: SpBackend = backend  # type: ignore[assignment]
    sp = solve_set_partitioning(alns.pool, res.solution, backend=chosen, time_limit=5.0)
    assert sp.solution is not None, sp.status
    assert verify(inst, sp.solution).feasible
    assert search_objective(inst, sp.solution) <= search_objective(inst, res.solution) + 1e-6
