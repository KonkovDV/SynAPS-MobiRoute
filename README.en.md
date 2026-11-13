# SynAPS-MobiRoute

A routing engine for mixed fleets: VRPTW, PDPTW and DARP with a capacity vector
(kg, m³, pallets), vehicle requirements, shifts, own and hired vehicles. ALNS
on a Rust kernel, exact CP-SAT and MIP models, a head-to-head with OR-Tools,
live order dispatch — and an independent check of every plan.

Language: [RU](README.md) | **EN** · Site: [konkovdv.github.io/SynAPS-MobiRoute](https://konkovdv.github.io/SynAPS-MobiRoute/)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/kernel-Rust%20%2B%20PyO3-orange.svg)](native/mobiroute_native)
[![OR-Tools](https://img.shields.io/badge/solvers-CP--SAT%20%C2%B7%20SCIP%20%C2%B7%20HiGHS%20%C2%B7%20OR--Tools%20Routing-4285F4.svg)](docs/benchmarks)
[![mypy strict](https://img.shields.io/badge/types-mypy%20strict-1D9BF0.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Every plan — from a heuristic, an exact model or OR-Tools — goes through a
separate verifier that recomputes loads, timing and cost and trusts nothing a
solver reports. When a trip cannot be scheduled you get a **certificate**
instead of "infeasible": which constraints conflict and **how many minutes are
missing**.

![Verified optimal plan for Cordeau a2-16](docs/img/a2-16-routes.svg)

## Results

| Claim | Result | Reproduce |
| --- | --- | --- |
| 130 public instances: Solomon (VRPTW), Li & Lim and Sartori–Buriol (PDPTW, real OSRM road times), Cordeau (DARP) | all 130 plans verified, every order served. Solomon: 54 of 56 at the best-known vehicle count, median gap **0.38%**, 21 matches. Sartori–Buriol: 22 of 25, median 0.92%. Cordeau: 19 of 48 at the published optimum, mean gap 0.50% | `python benchmark/vrp_benchmark.py` → [table](docs/benchmarks/vrp-public-benchmarks.md) |
| ALNS against proven optima | CP-SAT proved the optimum of 40 of 40 random instances of the full model (2–3 vehicle types, capacity vector, skills, ride limits, shifts); ALNS finds it on **38 of 40** in 0.19 s (CP-SAT 1.7 s), mean gap 0.13% | `python benchmark/exact_vs_alns.py` → [table](docs/benchmarks/exact-vs-alns.md) |
| OR-Tools Routing (PCI + GLS) at equal time | 18 instances, 10 s each, one verifier: ALNS is never worse. R101 at the best known vs +1.28%; bar-n100-1 (OSRM roads) +0.96% vs +12.2%; one or two vehicles fewer on RC101 and ber-, nyc-, poa-n100-1; on a2-16 OR-Tools drops an order; mixed-fleet cargo days **19%** cheaper | `python benchmark/ortools_vs_alns.py` → [table](docs/benchmarks/ortools-vs-alns.md) |
| Orders in real time | an answer in **0.1 ms** (max 0.3 ms): insertion into the part of a plan not yet driven; an ALNS pass every 30 minutes raises acceptance and lowers cost (plant, 140 moves: 84.3% → 85.0%). Re-solving everything with OR-Tools for every order (3 s) accepts 86.4% and is 2.5% cheaper, but answers in 2.9 s — about 30,000× slower — and its vehicles arrive 5 minutes later on average. Every final plan verified | `python benchmark/realtime_dispatch.py --with-ortools` → [table](docs/benchmarks/realtime-dispatch.md) |
| Profiling → Rust kernel | ALNS on the Rust kernel runs **12–42×** faster than the Python reference (VRPTW ×12, PDPTW ×14, DARP ×42) with **bit-identical** plans; ×4.4 on the 8-type cargo day, where vehicle-type selection in Python became the bottleneck | `python benchmark/measure_vrp_speed.py` → [table](docs/benchmarks/vrp-speed.md) |
| MIP vs CP on Cordeau a2-16 | CP-SAT proves the optimum 294.25 in 0.6 s; SCIP 26.2 s, HiGHS 43.3 s; CBC keeps a 20% gap at 60 s; LP relaxation 85.27 (weak big-M). ALNS reaches the same optimum in 2.9 s; OR-Tools leaves 1 of 16 requests out in 10 s | `python benchmark/solver_lab.py` → [table](docs/benchmarks/solver-lab-a2-16.md) |
| Engineering | 507 tests, `mypy --strict`, `ruff`, `clippy -D warnings`, Rust ↔ Python bit for bit | `pytest && ruff check . && mypy` |

Measured on one machine (Linux x86_64, Python 3.13, single thread); not an SLA.

## What it solves

**City distribution with own and hired vehicles.** Vans, trucks, a tractor;
orders with weight, volume, pallets, a delivery window, refrigeration, a tail
lift or ADR. The solver sends out its own vehicles first and hires only the
class that runs short.

**In-plant logistics.** Pallet moves between workshops appear during a shift.
Each gets an answer in a fraction of a millisecond: an insertion into the part
of a plan not yet driven, or a refusal with the reason (from the shuttle run:
"the nearest free vehicle reaches the pickup 1.9 min after its window
closes"). Every 30 minutes the live state is re-optimised.

**On-demand shuttle.** Rides between stops: wait at most 30 minutes, wait plus
ride at most 45; eight-seat minibuses.

**Passenger transport with special needs** (DARP): ride limits, wheelchairs,
companions, qualified drivers — the original kernel of the project
([docs/darp-kernel.md](docs/darp-kernel.md)).

## How it works

```mermaid
flowchart LR
  A[Orders, fleet, travel matrices] --> B[Model and validation]
  B --> C{Solvers}
  C --> D[ALNS: O1 regret insertion · 5 ruin operators · annealing · guided ejection]
  D <--> K[Rust VrpKernel — same output as the Python reference]
  C --> E[Exact CP-SAT · MIP on SCIP / HiGHS]
  C --> O[OR-Tools Routing — for comparison]
  C --> R[Live dispatcher]
  D --> V[Independent verifier]
  E --> V
  O --> V
  R --> V
  V -->|feasible| P[Plan, cost, SVG map]
  V -->|infeasible| H[Certificate: conflict and missing minutes]
```

| Method | When | Proves optimality |
| --- | --- | --- |
| Regret-k insertion + ALNS (random, worst, Shaw, SISR, route; annealing) | default | no |
| Guided ejection (Nagata & Bräysy) | cut the fleet | no |
| Insertion into the live plan | new order during the day | no |
| CP-SAT, one circuit per vehicle | small instances, any constraint | yes, for its integer model |
| Furtado–Munari–Morabito MIP on SCIP / HiGHS / CBC | solver comparison, lower bound | yes, by the backend's proof |
| OR-Tools Routing (PCI + GLS) | baseline | no |
| Minimal lateness: bisection on Bellman–Ford, LP | when windows cannot all be met | yes (LP) |

Constant-time insertion tests: earliest and latest service start at every
stop, loads per dimension, and a closed-form shortest route duration from
prefix and suffix extrema. Details:
[docs/mathematical-formulation.md](docs/mathematical-formulation.md).

## "Why not?" — a certificate

A freight day, a transfer from a supplier to a customer:

```text
The trip cannot be scheduled: short by 8.8 min.
supplier: start no earlier than 09:00 (loading 26 min);
drive supplier -> customer: 162.8 min;
customer: unloading must start by 12:00.
```

By hand: 540 + 26 + 162.8 − 720 = 8.8. The certificate is a negative cycle of
the difference-constraint graph; its weight is the deficit, and the planner
sees what to change: the customer's window or the supplier's hours.

![When each request is served: windows, service starts, ride limit](docs/img/a2-16-timeline.svg)

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

```bash
mobiroute vrp-solve --generate cargo --orders 120 --out-dir out-cargo --svg
mobiroute vrp-solve --instance benchmark/instances/sartori-buriol/n100/bar-n100-1.txt --time-limit 10 --out-dir out-sb --svg
mobiroute vrp-solve --generate cargo --orders 60 --solver ortools --time-limit 10 --out-dir out-ortools
mobiroute vrp-dispatch --day plant --policy insertion+alns --out-dir out-plant
mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out-a2 --svg
pytest            # fast suite; exact MIP proofs: pytest -m slow
```

```python
from mobiroute.vrp import AlnsConfig, load_benchmark, solve

inst, sha256 = load_benchmark("benchmark/instances/solomon/R101.txt")
result = solve(inst, AlnsConfig(time_limit=10, seed=1))
print(result.verdict.summary())
```

Without the compiled Rust kernel the engine runs on its Python reference
implementation, with the same results, only slower.

## Documentation

| Document | About |
| --- | --- |
| [docs/cargo-vrp.md](docs/cargo-vrp.md) | cargo VRP: model, algorithms, scenarios, next steps (RU, EN summary) |
| [docs/mathematical-formulation.md](docs/mathematical-formulation.md) | model, O(1) insertion, difference constraints, lateness LP, CP-SAT, MIP |
| [docs/architecture.md](docs/architecture.md) | modules, data flow, design decisions |
| [docs/native-acceleration.md](docs/native-acceleration.md) | profiling and the Rust kernels |
| [docs/benchmark-protocol.md](docs/benchmark-protocol.md) | rules for published numbers |
| [docs/benchmarks/](docs/benchmarks) | tables of every experiment |
| [docs/darp-kernel.md](docs/darp-kernel.md) | paratransit DARP kernel: rules, dispatch, checks |
| [docs/limitations.md](docs/limitations.md) | what the engine does not do yet |
| [benchmark/instances/README.md](benchmark/instances/README.md) | provenance and citations of the instances |

## Limits

Public benchmarks and synthetic days; no customer data and no pilot. One trip
per vehicle for now, no breaks inside a route, no time-of-day traffic;
heuristics prove no optimum, and the gap to the best known solution is
published per instance. Details: [docs/limitations.md](docs/limitations.md).

## License

MIT — see [LICENSE](LICENSE). Citation: [CITATION.cff](CITATION.cff).
