# Changelog

## 0.5.0 — 2026-11-14

### Added
- Input in coordinates (`mobiroute.vrp.geo`, format `mobiroute.vrp.geo.v1`):
  depots with opening hours, orders with `"HH:MM"` windows, pickups at a
  supplier or loads at the depot, collections, demand vectors, skills,
  vehicle types with shifts, prices per km and per hour, rest rules and
  trips, rush-hour profiles. Road matrices offline (great circle times a
  detour factor) or from the OSRM `table` service in blocks of 100 points;
  every malformed document ends in a code (`GEO_FIELD_MISSING:capacity`,
  `GEO_UNKNOWN_DEPOT:van`, `GEO_OSRM_NO_ROUTE:i->j`), never a traceback.
- Route sheets (`mobiroute.vrp.sheets`): one per vehicle with arrival, start
  and end of work, load per dimension and trip, reloads and the driver's
  rest; CSV for an ERP, Markdown in Russian or English and an SVG Gantt
  chart of the day. `vrp-solve --geo FILE [--osrm URL] --sheets [--lang en]`.
  The Russian output says "маршрутный лист" (a trip plan), not "путевой лист":
  the statutory waybill has required details the engine does not produce.
- The driver's schedule (`schedule.compact_schedule`): the latest departure
  that still returns earliest, a shortest-duration schedule (Lemma 4 in the
  formulation, two Hypothesis properties).
- `examples/chelny-day.geo.json`, a synthetic day in Naberezhnye Chelny, and
  its generator.
- Site: a route-sheets section with the day's map, a Gantt chart of every
  vehicle, the sheet and load profile of the selected one, and a departure
  slider that plots the shift length $D(t_0) = \max(E - t_0, c)$ of Lemma 4.
- README (RU, EN): a table from the tasks of the role to code and
  measurements, and the key formulas on one screen.
- Driver rests (`BreakRule`, 4.5 h of driving / 45 min by default, daily
  driving within twice the limit): the rest's place is chosen per route; a
  fixed place keeps the schedule a system of difference constraints, so the
  verifier still returns certificates (`TRAVEL+REST`, `DRIVING`).
- Multi-trip days: reload stops inside a route (`add_reload_stops`),
  capacity per trip, windows, shift cap and rests per day; trips are chained
  by the merge operator, which can move a hired vehicle's route onto an own
  vehicle's second trip.
- Time-dependent travel (`SpeedProfile`, Ichoua-Gendreau-Potvin model,
  FIFO): exact window tests with the arrival function and its inverse, exact
  shortest duration in the verifier, a sound shift-cap test in the search.
- Merge operator: two routes onto one vehicle, possibly of another type.
  Both instances ALNS missed in the CP-SAT study are now solved optimally.
- Local search for VRPTW (relocate, swap, 2-opt*, 2-opt) with time-window
  segment concatenation on granular neighbourhoods, on every new best plan.
- Set partitioning over the route pool (CP-SAT, SCIP, HiGHS, CBC), optional.
  CP-SAT runs with `linearization_level = 2`: on one worker it then proves a
  Solomon pool optimum in 0.13 s instead of not at all in 10 s.
- Studies: `rules_study.py` (rests, trips, rush hours), `seed_study.py`
  (five seeds on Solomon R2/RC2 with a Wilcoxon signed-rank test),
  `setpart_study.py` (solver choice for set partitioning).
- `dc_day` generator: store deliveries from a DC in two waves.
- Property-based tests (Hypothesis) hold the search's checks to the verifier.

### Security
- CSV cells that start like a spreadsheet formula are quoted (OWASP CSV
  injection); Markdown cells escape `|`, line breaks and HTML; the site
  escapes data it writes as HTML; `--osrm` accepts only http(s) URLs.

### Changed
- Kernel and ABI 0.5: rests and reload stops in Rust, bit-identical to the
  Python reference; a kernel of another version is ignored, not trusted.
- CLI input errors go to stderr (still one line, exit status 2).
- `mobiroute.vrp` exports `geo`, `route_sheets`, `sheets_csv` and
  `sheets_markdown`; CI lints the examples and smoke-tests a geo day.
- The OR-Tools lane, the exact model and the dispatcher refuse instances
  with rests, reload stops or speed profiles with an explicit error.
- The live-dispatch table reports the 95th percentile of decision time next
  to the mean and the maximum (a single maximum can be a runtime pause).

### Results
- ALNS reaches the CP-SAT optimum on 40 of 40 random instances (was 38).
- Solomon: all 56 instances at the best-known vehicle count (was 54); worst
  gap 7.0% (was 11.4%, RC202 now 6.1%).
- Rest rule: plans made without it leave 4-6 routes a day with no room for
  a rest; compliant plans cost 2.0-5.5% more.
- Two trips per vehicle cover a 60-store, two-wave day with 12-15
  vehicles; one trip leaves 5-8 stores unserved with 21.
- Rush hours: free-flow plans fail on 8-13 routes a day; traffic-aware
  plans hold at 0-11% more.

## 0.4.0 — 2026-11-13

### Added
- `mobiroute.vrp`, a rich VRP engine for heterogeneous fleets: capacity vectors
  (kg, m³, pallets), fixed and variable costs, own and hired units, skills,
  travel profiles per vehicle type, shift caps; pickup-and-delivery pairs,
  depot deliveries and collections, ride limits.
- Constant-time insertion tests from forward/backward slack and a closed-form
  shortest route duration; ride limits checked exactly with Bellman-Ford on
  the cheapest candidates. Tested against brute force judged by the verifier.
- ALNS with random, worst, related, string (SISR) and route removal, regret
  repair with noise, adaptive weights, simulated annealing, and guided
  ejection search to eliminate vehicles.
- `VrpKernel` in Rust: regret repair, insertion tests, exact route timing and
  the ejection step. Bit-identical to the Python reference, including whole
  ALNS trajectories (`tests/test_vrp_native.py`).
- Exact CP-SAT model of the full model (one circuit per vehicle unit) and a
  study of ALNS against its proven optima (38 of 40 matched).
- Vehicle types of finished routes are re-chosen exactly as a transportation
  problem (min-cost flow by successive shortest paths): insertion alone never
  opens a type whose fee is paid up front, which cost up to 19.6%.
- OR-Tools Routing lane (PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH) on
  the same model and verifier, and an equal-time comparison. The routing model
  holds only depots and order nodes: Routing treats every node it knows as a
  mandatory visit, which made live snapshots unsolvable.
- Minimal-lateness schedules: bisection on Bellman-Ford and an LP on GLOP.
- Live dispatch simulator: freeze what is driven, insert each order on
  arrival, re-optimise the live state written as a static instance; KPIs and
  an OR-Tools re-solve-per-order policy for comparison.
- Generators for a city freight day, an in-plant transport shift and an
  on-demand shuttle; SVG route maps; CLI `vrp-solve` and `vrp-dispatch`.
- Vendored benchmarks with SHA-256 sums and reference tables: 56 Solomon,
  Li & Lim LC101, 25 Sartori-Buriol (real road times), all 48 Cordeau.
- Benchmark runners writing `docs/benchmarks/*.md`.
- Site: mixed-fleet explorer, live dispatch replay, benchmark heat strip,
  OR-Tools and Rust comparisons; earlier: animated a2-16 replay, before/after
  of the scheduling fix, solver race and an in-browser route notary.

### Changed
- Documentation rewritten around the engine; fourteen contract and policy
  notes merged into `docs/darp-kernel.md`; dated audits, business and market
  notes, the pilot outline and the evidence-bundle spec removed.
- The solver lab reports how many requests each plan serves. OR-Tools leaves
  one a2-16 request out in 10 s; such a plan is cheaper than the optimum and
  is now labelled incomplete instead of "not verified".
- Site counters follow the measured data, a social preview card is published,
  and the meta descriptions match the engine.
- CI type-checks the benchmark scripts with `mypy --strict` and checks Rust
  formatting.
- Native crate and ABI 0.4.

## 0.3.0 — 2026-11-13

### Fixed
- Appointment pickups wait for the tightened window floor
  `max(earliest, alight − min(max_ride, detour cap) − curb)` in the Rust kernel,
  the Python oracle, the route simulator and the notary. Before, every simulator
  scheduled pickups as early as possible: Cordeau a2-16 lost 7 of 16 requests
  (each refused even alone). Now greedy, beam, ALNS and RHC serve 16 of 16 and
  the tiny CP-SAT plan verifies as OPTIMAL.
- The notary refuses pickup dwell beyond the curb wait (`UNEXPLAINED_DWELL`):
  a passenger held onboard at the curb no longer escapes the ride clock and quota.
- `nearest` and `beam` respect the passenger-day quota (they published plans the
  notary rejected on `ops_quota`).
- `generate --mode large` asked for a depot outside the zone matrix.
- `academic-benchmark` attached the a2-16 reference to any file; it now binds to
  the vendored SHA-256 and reads the instance bytes once.
- CLI input errors print one line and exit 2 instead of a traceback.

### Added
- Literature-exact Cordeau lane: strict parser, exact CP-SAT model, compact
  two-index MIP (Furtado, Munari & Morabito 2017) on SCIP, HiGHS and CBC, LP
  relaxation bound, and an independent difference-constraint verifier
  (Bellman–Ford). a2-16 reproduces the published optimum 294.25.
- Why-not certificates: an infeasible route returns its negative cycle with the
  missing minutes and an English and a Russian explanation.
- `literature-benchmark` (with `--solver mip`, `--backend`, `--svg`),
  `benchmark/solver_lab.py`, SVG route map and timeline, a GitHub Pages site.
- Native ABI gate: the Python package refuses a `mobiroute_native` wheel from
  another minor line. `clippy -D warnings` in CI; dependency audit workflow.

### Performance
- Profile-guided fixes (pooling verdict, driver index, travel lookup, Shaw
  relatedness, native coercion). Results are identical on 217 mode × solver
  runs. stress_200 day-ahead greedy 47.9 s → 2.8 s; full disruption pipeline
  67.6 s → 13.1 s; medium ALNS 10.1 s → 2.6 s (author's machine, single thread).

### Removed
- Dependabot config and application documents for an accelerator programme.

## Earlier versions

- **0.2.x (Aug–Sep 2026).** Paratransit kernel hardening: explicit driver
  assignment; greedy pooling insertion with dynamic loads; the Rust
  `InsertionEngine` for insertion scoring (persistent fleet, prefix-state
  walk, copy-on-write fork); tiny CP-SAT that may publish `OPTIMAL` only with
  the notary's agreement; operator policy (pooling modes, chains, quota
  bases); one-signer plan identity and lineage for online and recovery lanes;
  plan diff with retiming and driver changes; refusal evidence; Cordeau a2-16
  vendored behind a hash gate; the open-data claim gate; the `stress_200` day.
- **0.1.x (Aug 2026).** Domain model and schemas, FIFO and greedy baselines,
  the feasibility notary, online insertion and disruption recovery, the
  synthetic Moscow-zone generator, fairness and privacy helpers.
