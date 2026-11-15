# SynAPS-MobiRoute

A vehicle routing engine for mixed fleets. VRPTW, PDPTW and DARP share one
model: time windows at pickup and delivery, pickup-and-delivery pairs, loads
with weight, volume and pallets, own and hired vehicles of several types,
drivers' driving-time rules, several trips per shift and travel speeds that
change over the day.

It builds the plan for a day of transport — which vehicle carries each order,
in what order and when — and checks, apart from the search, that the plan
can be driven. The examples are a city freight day with own and hired
vehicles, workshops' requests for in-plant transport, and an employee
shuttle. The data are synthetic; the solvers are tested on public benchmarks.

The main method is ALNS. Its hot path (inserting orders and checking
schedules, rush hours and split breaks included) is written in Rust and
returns exactly the same plans as the reference implementation in Python.
Small instances are solved exactly with CP-SAT and MIP models (SCIP, HiGHS,
CBC), and OR-Tools Routing runs on the same model for comparison. Every plan,
wherever it comes from, is recomputed by a separate verifier. When a trip
cannot be scheduled, the verifier says which constraints conflict and how many
minutes are missing.

[Русская версия](README.md) · [Site with interactive examples](https://konkovdv.github.io/SynAPS-MobiRoute/)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/kernel-Rust%20%2B%20PyO3-orange.svg)](native/mobiroute_native)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/KonkovDV/SynAPS-MobiRoute/badge)](https://scorecard.dev/viewer/?uri=github.com/KonkovDV/SynAPS-MobiRoute)

![Verified optimal plan for the Cordeau a2-16 instance](docs/img/a2-16-routes.svg)

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

The freight engine (`vrp-solve`, `vrp-dispatch`) does not need the Rust
kernel: without it Python computes the same plans, only slower. The passenger
kernel needs it for the `fifo`, `greedy`, `beam`, `alns` and `rhc` heuristics
and for `demo`; without the build the CLI says in one line how to make it,
and `nearest` and `cpsat` run anyway.

```bash
# a freight day: 120 orders, own and hired vehicles, an SVG route map
mobiroute vrp-solve --generate cargo --orders 120 --out-dir out-cargo --svg

# a day given in coordinates -> route sheets (CSV, Markdown, a Gantt chart)
mobiroute vrp-solve --geo examples/chelny-day.geo.json --sheets --lang en --out-dir out-chelny

# Cordeau a2-16: the exact CP-SAT model and a check of the plan
mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out-a2 --svg

pytest          # fast test suite; exact MIP models: pytest -m slow
```

From Python:

```python
from mobiroute.vrp import AlnsConfig, load_benchmark, solve

inst, sha256 = load_benchmark("benchmark/instances/solomon/R101.txt")
result = solve(inst, AlnsConfig(time_limit=10, seed=1))
print(result.verdict.summary())
```

## Model

An order is a pickup-and-delivery pair, a delivery loaded at the depot or a
collection brought back to it. Demand is a vector of any length (kg, m³,
pallets) and vehicle requirements are skills: refrigeration, a tail lift, ADR.
A vehicle type sets the number of vehicles, capacity, depot, shift, speed
profile, hire fee and prices per kilometre and per hour. A hired type differs
from an own one only in price, so the solver hires vehicles of the class that
runs short on its own. The objective is money: hire fees, distance, time and
penalties for orders left out.

Operating rules are constraints of the model, not corrections applied after
solving:

- a 45-minute break after at most 4.5 hours of driving and at most 9 hours of
  driving per shift, including the break split into 15 and 30 minutes (EU
  Regulation 561/2006; Russian Ministry of Transport Order No. 160 of
  14.04.2026, points 8 and 11, which replaced Order No. 424 from
  1 September 2026);
- several trips per shift with a reload at the depot;
- speeds by time of day (the Ichoua, Gendreau and Potvin model, FIFO);
- zones closed to vehicles by gross weight, axle load, height or type;
- a ride-time limit for a pair and a shift length.

The formal model and proofs are in
[docs/mathematical-formulation.md](docs/mathematical-formulation.md); the
freight side in detail is in [docs/cargo-vrp.md](docs/cargo-vrp.md) (Russian,
with an English summary).

## Algorithms

| Method | Used for | Proves optimality |
| --- | --- | --- |
| Regret-k insertion with O(1) checks and ALNS: random, worst, Shaw, SISR and route removal, simulated annealing, adaptive weights | the main search | no |
| Guided ejection (Nagata, Bräysy 2009) | fewer vehicles | no |
| Vehicle types of finished routes as a transportation problem (min-cost flow) | mixed fleets | yes, for the given routes |
| Merging two routes onto a vehicle of another type, chaining trips through the depot | mixed fleets, several trips | no |
| Local search: relocate, swap, 2-opt*, 2-opt with time-window segments (Vidal et al. 2013) | every new best VRPTW plan | no |
| Exact re-sequencing of a short route (up to 9 stops): all stop orders, pruned by windows, capacity and cost | an order that one insertion cannot place because a stop on the route has to move too | yes, for one route when the search stays within 20,000 nodes |
| Set partitioning over the route pool (CP-SAT, SCIP, HiGHS, CBC) | recombining routes found so far | over the pool only |
| The dual of its LP relaxation (GLOP) | prices of orders, rents of vehicle types | for the LP |
| CP-SAT, one circuit per vehicle | small instances with any constraint of the model | yes |
| CP-SAT warm-started from the ALNS plan plus a cold run, both deterministic (a pattern from the SynAPS core) | `vrp-solve --solver exact`: a plan never worse than the heuristic one, the same on any machine | when time allows |
| Compact MIP of Furtado, Munari and Morabito (2017) on SCIP, HiGHS, CBC | lower bounds, comparing solvers | yes |
| OR-Tools Routing (PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH) | a baseline for comparison | no |
| Insertion into the part of a plan not yet driven, with the driver's break of Order No. 160 | orders arriving during the day | no |

A solver that does not support a rule of the instance (OR-Tools and the exact
model know nothing about breaks and trips, for example) refuses the instance
with an error code instead of returning a plan that silently breaks the rule.

## Results

| What was measured | Result | Table |
| --- | --- | --- |
| Cordeau a2-16, exact models | CP-SAT proves the published optimum 294.25 in under a second, SCIP in about 26 s, HiGHS in 40 s. CBC is still 20% off after 60 s. The LP relaxation of the compact model gives only 85.27: the big-M is weak. ALNS reaches the same optimum in about 3 s | [solver-lab-a2-16](docs/benchmarks/solver-lab-a2-16.md) |
| 130 public instances | every plan passed the verifier. Solomon: the best-known vehicle count on all 56 instances, median distance gap 0.50%, worst 7.0%. Cordeau: the published optimum on 19 of 48, mean gap 0.50% | [vrp-public-benchmarks](docs/benchmarks/vrp-public-benchmarks.md) |
| ALNS against proven optima | 40 random instances of the full model (2–3 vehicle types, capacity vector, skills, ride limits, shifts) with optima proven by CP-SAT: ALNS finds the optimum on all 40. Where leaving an order out pays, on 87 of 90 | [exact-vs-alns](docs/benchmarks/exact-vs-alns.md) |
| ALNS at 14 orders | 20 instances where some orders have to be refused: ALNS reaches the best plan on 17 of 20, worst gap 0.9% (16 of 20 and 16% before the exact re-sequencing of short routes). CP-SAT started from the ALNS plan is never worse than it, and with a cold run beside it finds the best plan on all 20; every run repeats bit for bit | [warm-start](docs/benchmarks/warm-start.md) |
| OR-Tools at equal time | 18 instances, 10 s each, both plans checked by the same verifier: ALNS is better on 12, equal on 6, worse on none. Mixed-fleet freight days come out 14–17% cheaper with one to three vehicles fewer | [ortools-vs-alns](docs/benchmarks/ortools-vs-alns.md) |
| PyVRP, VROOM, jsprit | Solomon, vehicles first: the best-known vehicle count on 56 of 56 instances, against 50 for PyVRP, 32 for VROOM and 30 for jsprit. On 1000 customers ranked by distance alone PyVRP is ahead: +1.2% to the best known against +2.9% for this engine | [solvers](docs/benchmarks/solvers.md) |
| Rust kernel | faster than the Python reference with bit-identical plans: 10× on VRPTW, 14× on PDPTW, 42× on DARP with ride limits. On a freight day with eight vehicle types it is 5.4×, with rush hours 6.5×, on a day with split breaks 5.5×: the operators still written in Python become the bottleneck there | [vrp-speed](docs/benchmarks/vrp-speed.md) |
| Profiling | on a 1000-customer instance, fixes guided by a `cProfile` table gave 2.9× more iterations a minute and cut the gap to the best known from 5.75% to 3.4% | [native-acceleration](docs/native-acceleration.md) |
| Orders during the day | 95% of new orders are answered within 0.3 ms. Under the 4.5 h / 45 min rule the dispatcher places the breaks itself: 3 breaks on the plant day, 119 orders accepted against 120 without the rule, every route verified | [realtime-dispatch](docs/benchmarks/realtime-dispatch.md) |
| Operating rules | a plan made without the 4.5 h / 45 min rule leaves 4–6 routes a day with no room for a break. Two trips cover 60 of 60 stores, one trip only 52–55. A plan made on free-flow speeds runs late on 8–13 routes in rush hour | [rules](docs/benchmarks/rules.md) |
| Spread over seeds | 19 Solomon R2 and RC2 instances, 5 seeds each; the effect of local search is significant by the Wilcoxon test, p = 0.006 | [seed-study](docs/benchmarks/seed-study.md) |

Measured on one machine: Linux x86_64, Python 3.13, one thread. Every table is
written by a script in `benchmark/` (commands in
[benchmark/README.md](benchmark/README.md)). With the same settings and seed a
rerun gives the same costs to the cent; timings depend on the machine.

## How it fits together

```mermaid
flowchart LR
  A[Orders and fleet: JSON, VRPLIB or coordinates] --> G[Matrices: offline, OSRM or Valhalla]
  G --> B[Model and input checks]
  B --> C{Solvers}
  C --> D[ALNS: regret insertion, removal, annealing, guided ejection]
  D <--> K[Rust kernel]
  D --> M[Route merges, local search, set partitioning]
  C --> E[Exact models: CP-SAT, MIP on SCIP and HiGHS]
  C --> O[OR-Tools Routing]
  C --> R[Dispatcher for orders during the day]
  D --> V[Verifier]
  E --> V
  O --> V
  R --> V
  V -->|feasible| P[Plan, cost, map, route sheets]
  V -->|infeasible| H[Certificate: conflict and missing minutes]
```

### Where things are

| What | Code |
| --- | --- |
| The model: orders, vehicle types, rules | [vrp/model.py](src/mobiroute/vrp/model.py) |
| Insertion with O(1) window, capacity and shift checks | [vrp/insertion.py](src/mobiroute/vrp/insertion.py), in Rust [vrp.rs](native/mobiroute_native/src/vrp.rs) |
| ALNS and guided ejection | [vrp/alns.py](src/mobiroute/vrp/alns.py) |
| Local search, route merges, vehicle types, exact re-sequencing of short routes | [vrp/local_search.py](src/mobiroute/vrp/local_search.py), [vrp/merge.py](src/mobiroute/vrp/merge.py), [vrp/fleet.py](src/mobiroute/vrp/fleet.py), [vrp/reseat.py](src/mobiroute/vrp/reseat.py) |
| Set partitioning and dual prices | [vrp/setpart.py](src/mobiroute/vrp/setpart.py), [vrp/prices.py](src/mobiroute/vrp/prices.py) |
| Exact CP-SAT and MIP models | [vrp/exact.py](src/mobiroute/vrp/exact.py), [benchmarks/cordeau_exact.py](src/mobiroute/benchmarks/cordeau_exact.py) |
| OR-Tools Routing on the same model | [vrp/ortools_baseline.py](src/mobiroute/vrp/ortools_baseline.py) |
| Verifier and the driver's schedule | [vrp/verify.py](src/mobiroute/vrp/verify.py), [vrp/schedule.py](src/mobiroute/vrp/schedule.py) |
| Breaks, trips, traffic | [vrp/schedule.py](src/mobiroute/vrp/schedule.py), [vrp/traffic.py](src/mobiroute/vrp/traffic.py) |
| Orders during the day, with drivers' breaks | [vrp/realtime.py](src/mobiroute/vrp/realtime.py) |
| Fleet indicators: empty kilometres, beta, gamma, time on duty | [vrp/kpi.py](src/mobiroute/vrp/kpi.py) |
| Input in coordinates, route sheets | [vrp/geo.py](src/mobiroute/vrp/geo.py), [vrp/sheets.py](src/mobiroute/vrp/sheets.py) |
| Benchmark scripts | [benchmark/](benchmark) |
| Tests | [tests/](tests) |

The project started as a planning kernel for transporting passengers with
reduced mobility (DARP with quotas, priorities and trained drivers). That
kernel is still in the repository and is described in
[docs/darp-kernel.md](docs/darp-kernel.md).

## Some mathematics

The objective is cost, not kilometres. Vehicle type $k$ has a hire fee $f_k$
(zero for an own vehicle), a price per kilometre $c^d_k$ and per hour
$c^t_k$; an order $r$ left out costs a penalty $\pi_r$:

```math
\min \sum_{\text{routes}} \Big( f_k + c^d_k \sum d_{ij} + c^t_k \big(\textstyle\sum t_{ij} + \sum s_i\big) \Big) \;+\; \sum_{r\ \text{unserved}} \pi_r
```

For a fixed order of stops the schedule is a system of difference
constraints on the service starts $B_i$:

```math
e_i \le B_i \le l_i, \qquad
B_{i+1} \ge B_i + s_i + t_{i,i+1}, \qquad
B_{d_r} - B_{p_r} - s_{p_r} \le L_r, \qquad
B_{\text{end}} - B_{\text{start}} \le T_k
```

The system is feasible if and only if its graph has no negative cycle.
Bellman–Ford finds such a cycle, and the cycle is the certificate: minus its
weight is the number of minutes missing. A driver's break lengthens one travel
constraint, so the system stays a difference system and certificates still
work with breaks.

Insertion is checked in constant time (Savelsbergh 1992). A forward and a
backward pass over the route

```math
\mathrm{begin}_k = \max\big(\mathrm{begin}_{k-1} + s_{k-1} + t_{k-1,k},\; e_k\big), \qquad
\mathrm{late}_k = \min\big(l_k,\; \mathrm{late}_{k+1} - s_k - t_{k,k+1}\big)
```

tell at once whether order $u$ fits between $v_i$ and $v_{i+1}$:
$b_u = \max(\mathrm{begin}_i + s_i + t_{iu},\, e_u) \le l_u$ and
$b_u + s_u + t_{u,i+1} \le \mathrm{late}_{i+1}$.

Once routes exist, the best vehicle type for each is a transportation problem:
the constraint matrix is totally unimodular, so a min-cost flow solves it
without a MIP. The routes the search has found can be recombined by set
partitioning over the pool $\Omega$:

```math
\min \sum_{\rho \in \Omega} c_\rho x_\rho + \sum_r \pi_r y_r
\quad \text{s.t.} \quad \sum_{\rho \ni r} x_\rho + y_r = 1 \;\; \forall r, \qquad
\sum_{\rho \in \Omega_k} x_\rho \le n_k, \qquad x \in \{0, 1\}^{\Omega}
```

The dual variables of its LP relaxation price every order and put a rent on
each vehicle type that ran out. These are prices of a restricted master
problem: exact for the pool, an estimate for the whole problem. Six lemmas
with proofs, including breaks, traffic and when a driver should leave, are in
[docs/mathematical-formulation.md](docs/mathematical-formulation.md).

## When a trip is impossible

![A negative cycle in the difference-constraint graph: 720 − 188.8 − 540 = −8.8 min](docs/img/certificate.en.svg)

An example from a freight day, a transfer from a supplier to a customer:

```text
The trip cannot be scheduled: short by 8.8 min.
supplier: start no earlier than 09:00 (loading 26 min);
drive supplier -> customer: 162.8 min;
customer: unloading must start by 12:00.
```

You can check it by hand: 540 + 26 + 162.8 − 720 = 8.8. The planner sees what
to change: the customer's window or the supplier's hours.

## From coordinates to route sheets

Orders and fleet can be given the way an ERP exports them: a depot with opening
hours, an order with an "08:00–11:00" window, weight, volume, pallets, vehicle
requirements, vehicle types with tariffs, a rest rule and a number of trips,
zones closed to trucks. The format is described in
[docs/cargo-vrp.md](docs/cargo-vrp.md#данные-из-координат-и-маршрутные-листы)
(Russian, with an English summary). Travel times and distances are computed
offline or requested from [OSRM](https://project-osrm.org/) or
[Valhalla](https://github.com/valhalla/valhalla) with a truck profile (weight,
height, axle load).

```bash
mobiroute vrp-solve --geo examples/chelny-day.geo.json --sheets --lang en --out-dir out-chelny
mobiroute vrp-solve --geo examples/chelny-day.geo.json --valhalla http://localhost:8002 --sheets --out-dir out-trucks
```

Every vehicle gets a route sheet: `route-sheets.md` for people,
`route-sheets.csv` for an ERP and `route-sheets.svg` with a Gantt chart of the
whole day. A vehicle leaves as late as its earliest possible return allows
instead of waiting an hour at the first customer's gate.

```text
## van #1 · own · 2 trips
Start 10:14, departure 10:34, return 13:34; 36.3 km, 10.8 of them empty; 73 min driving, 0 min waiting; cost 1,999 ₽
Driving-time rules met: longest drive between breaks 1:13 / 4:30; driving in the shift 1:13 / 9:00; shift 3:20 / 10:00.
Loading order at the depot, reverse of the drops: trip 1: Z011, Z020, Z014; trip 2: Z027, Z002.

| Trip | What               | Order | Where               | Window      | Arrive | Start |   End |     kg |
| ---: | ------------------ | ----- | ------------------- | ----------- | -----: | ----: | ----: | -----: |
|    1 | loading, departure |       | Склад (условн.)     |             |  10:14 | 10:14 | 10:34 | 1427.4 |
|    1 | delivery           | Z014  | Клиент 14 (условн.) | 08:00-11:00 |  10:37 | 10:37 | 10:55 |  645.8 |
|    1 | delivery           | Z020  | Клиент 20 (условн.) | 11:00-14:00 |  11:00 | 11:00 | 11:14 |  371.1 |
|    1 | delivery           | Z011  | Клиент 11 (условн.) | 08:00-18:00 |  11:16 | 11:16 | 11:30 |      0 |
|    2 | reload             |       | Склад (условн.)     | 07:00-20:00 |  11:36 | 11:36 | 12:01 | 1329.1 |
|    2 | delivery           | Z002  | Клиент 2 (условн.)  | 11:00-14:00 |  12:27 | 12:27 | 12:49 |  241.1 |
|    2 | delivery           | Z027  | Клиент 27 (условн.) | 08:00-18:00 |  13:04 | 13:04 | 13:18 |      0 |
|    2 | return             |       | Склад (условн.)     |             |  13:34 | 13:34 | 13:34 |      0 |
```

The example is a synthetic day in Naberezhnye Chelny: a depot, three
suppliers, 45 orders, own and hired vans and trucks. The points are random
inside the city's bounding box and the names are made up ("условн." means
"conventional"); a [generator](examples/make_chelny_day.py) writes the file.
ALNS covers the day with seven vehicles in a couple of seconds: all four own
vans run two trips, and one hired truck is needed.

A route sheet is the driver's trip plan, not the statutory waybill that
Russian law requires for every trip. The waybill with its medical and
technical checks and odometer readings lives in the accounting system; the
CSV loads into it as the assignment.

## Fleet indicators

Cost says what a day is worth, not how the vehicles worked. Next to the plan
the engine writes `kpi.md` and a `kpi` block in `verdict.json`: distance and
empty distance (legs with nothing on board), the mileage utilisation beta,
the dynamic load utilisation gamma over loaded kilometres for every load
dimension, and time on duty split into driving, work, rest and waiting. The
same Chelny day:

```text
Vehicles: 7 (1 hired); orders served 45, unserved 0.
Distance 333.9 km, of it empty 62.3 km; mileage utilisation 81.4%.
Load utilisation (dynamic, over loaded kilometres): kg 63.2%, m3 40.5%, pallets 71.4%.
On duty 38.2 h, driving 12.0 h, waiting 6.1 h.
```

The dispatcher's shift report counts empty running too: between workshops
those are the kilometres from one drop to the next pickup, the ones
dispatching is meant to cut. Formulas are in the
[formulation](docs/mathematical-formulation.md#10-fleet-indicators), in-plant
transport tasks in [docs/industrial-transport.md](docs/industrial-transport.md).

## Prices of orders

```bash
mobiroute vrp-solve --geo examples/chelny-day.geo.json --iterations 5000 --prices --out-dir out-chelny
```

The price of an order is its dual value: what serving it costs in this day,
counting the place it takes in an own vehicle when own vehicles are scarce.
The rent of a vehicle type says which own vehicles are short. It is a
marginal rate of the relaxation, not a forecast: on the Chelny day the rents
of own vans and trucks are 2,104 and 5,378, while solving the day again with
one more van saves 641 and with one more truck 2,160. Details are in the
[formulation](docs/mathematical-formulation.md#prices-the-dual-of-the-pools-lp).

## Tests and code quality

- The model is frozen dataclasses (`Instance`, `VehicleType`, `Request`), and
  an instance is validated when it is built. The search is made of small
  single-purpose classes: `Alns`, `LocalSearch`, `RouteMerger`,
  `TypeAssigner`, `Dispatcher`. A result is a plan (`Solution`) and the
  verifier's `Verdict`, which does not depend on the solver.
- 734 tests, 17 of them Hypothesis properties that check hundreds of random
  routes against the verifier. A separate set tries to break the engine: NaN
  and infinity in the input, a plan with a vehicle type or node that does
  not exist, arbitrary plans from another system, an input file with one
  broken field (every such file ends in an error code, not a traceback).
  Coverage is 92%.
- One test keeps the verifier from importing anything of the search: it may
  use the model, the schedule, the cost and travel times only. Another keeps
  claims stronger than the evidence (an optimum without a proof, savings
  without a carrier's data) out of the READMEs, the docs and the site, and
  recounts the benchmark instances the site names.
- The tests catch all 12 deliberately planted bugs (the verifier forgetting
  capacity, insertion allowing a minute of lateness, a rest missing from a
  route sheet, ...): `python benchmark/mutation_smoke.py`. A differential run,
  `python benchmark/fuzz_differential.py 4000`, compares the Rust kernel with
  the reference on 38 thousand insertions, feeds the verifier 80 thousand
  arbitrary plans and solves 400 random instances with every rule on both
  kernels, with no difference found.
- `mypy --strict`, `ruff`, `cargo clippy -D warnings` and `cargo fmt` in CI.
  Every pull request also gets CodeQL (Python, JavaScript, Rust), `pip-audit`
  and `cargo audit` and a gitleaks scan of the whole history, and a test
  reads the licences of the whole dependency tree and refuses GPL and AGPL.
  Third-party GitHub Actions are pinned by SHA, Dependabot proposes updates
  weekly, and OpenSSF Scorecard rates the supply chain.
- The Rust kernel follows the Python reference operation by operation. Tests
  require identical plans, down to whole ALNS trajectories, so the fast path
  cannot drift from the slow one.
- `python benchmark/profile_vrp.py` prints a `cProfile` table of one run on
  both backends. Every speed-up started from that table; the story is in
  [docs/native-acceleration.md](docs/native-acceleration.md).
- Input errors are codes (`GEO_UNKNOWN_DEPOT:van`, `VRP_CAPACITY_INVALID:van`):
  the CLI prints one line and exits with status 2. Whole-number fields (fleet
  size, depots, trip limit) are never rounded: `2.7` and `true` are errors.
  A panic in the Rust kernel becomes a Python exception, not a crash of the
  process.
- `vrp-solve` exit statuses: 0, the plan is verified and serves every
  mandatory order; 2, the input was refused or the plan breaks a rule; 3, the
  plan is verified and written, but mandatory orders are left without a
  vehicle. The CLI then lists them and names those no vehicle type can carry.

## Limitations

- The engine is tested on public benchmarks and synthetic days. There has been
  no carrier's data and no pilot.
- Offline matrices are straight-line distances times a detour factor; real
  roads need an OSRM or Valhalla server.
- The live dispatcher plans drivers' breaks from the driving already done.
  Re-optimisation starts from that same counter, so it does not propose an
  order of stops that only a fresh driver could drive, and a break already
  begun is not moved. OR-Tools does not run that day. A day with rush hours
  or several trips is refused with an error code, and a ride limit has to be
  written as a delivery deadline.
- There are no time-of-day truck bans and no multi-day trips with daily rest.

The full list and the plans are in [docs/limitations.md](docs/limitations.md).

## Documentation

| Document | About |
| --- | --- |
| [docs/cargo-vrp.md](docs/cargo-vrp.md) | freight VRP: model, algorithms, input in coordinates, route sheets, scenarios (Russian, English summary) |
| [docs/trucking-ru.md](docs/trucking-ru.md) | Russian freight practice and how each rule maps onto the model (Russian, English summary) |
| [docs/industrial-transport.md](docs/industrial-transport.md) | in-plant transport: moves between workshops on request, staff shuttles, line feeding; what the model covers (Russian) |
| [docs/mathematical-formulation.md](docs/mathematical-formulation.md) | the model, O(1) insertion, difference constraints, breaks, trips, traffic, lemmas with proofs |
| [docs/comparison.md](docs/comparison.md) | comparison with OR-Tools, VROOM, PyVRP, jsprit, Timefold and Yandex Routing (Russian, English summary) |
| [docs/architecture.md](docs/architecture.md) | modules, data flow, design decisions |
| [docs/native-acceleration.md](docs/native-acceleration.md) | profiling and the Rust kernels |
| [docs/benchmark-protocol.md](docs/benchmark-protocol.md) | how numbers are published |
| [docs/benchmarks/](docs/benchmarks) | tables of every experiment |
| [docs/darp-kernel.md](docs/darp-kernel.md) | the passenger DARP kernel |
| [docs/limitations.md](docs/limitations.md) | scope and plans |
| [benchmark/instances/README.md](benchmark/instances/README.md) | where the benchmark instances come from |
| [CHANGELOG.md](CHANGELOG.md) | what changed in each version |

## License and legal notes

The code is under the MIT licence, see [LICENSE](LICENSE). Written by Dmitrij
Konkov ([GitHub](https://github.com/KonkovDV)). How to cite:
[CITATION.cff](CITATION.cff).

- The benchmark instances in `benchmark/instances/` belong to their authors
  and are kept unchanged, so that every published result can be checked on
  the same files. The MIT licence does not cover them: the terms of each set
  and the licence texts of its source are in
  [benchmark/instances/NOTICE.md](benchmark/instances/NOTICE.md).
- OR-Tools, the MIP solvers and other dependencies are installed from their
  own sources under their own licences.
- Examples and generated days are synthetic: random points, made-up names.
  The repository holds no personal data and no data of any organisation.
- This is an independent project built from public sources. It is not
  affiliated with or endorsed by the organisations its documents mention
  (PJSC KAMAZ and PJSC NefAZ among them); company and product names belong
  to their owners and appear only as references to publications.
- The legal rules in [docs/trucking-ru.md](docs/trucking-ru.md) are described
  as model constraints as of November 2026, not as legal advice. The engine
  helps plan a trip; keeping to the drivers' working-time rules and releasing
  a vehicle onto the road remain the carrier's duty.
