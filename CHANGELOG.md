# Changelog

## 0.7.0 — 2026-11-15

### Added
- Drivers' breaks in the live dispatcher. With a break rule on the vehicle
  types (`vrp-dispatch --rests` sets the one of Ministry of Transport Order
  No. 160: 45 minutes after 4.5 hours of driving, or 15 + 30), every answer
  to an order also places the break in the part of the route not yet driven.
  The count carries the driving already done and a first 15-minute part
  already taken. A whole break goes where both stints stay within the limit;
  a split one books its first part into a planned wait of at least 15
  minutes, set in advance as on a route sheet. A break once begun is never
  moved. An order that leaves the break no legal place is refused, and the
  reason says so. `dispatch.json` lists every break, and the report counts
  them. On the seed-5 plant day the dispatcher plans 3 breaks and accepts 119
  orders against 120 without the rule; every route passes the verifier. The
  ALNS pass sees only the open stops and would count that driving as zero, so
  a proposal is kept only when every new suffix still has a legal break
  (Lemma 1c), the verifier accepts the day and the verified cost falls. A
  break already begun is not an open gap. OR-Tools has no break variable
  (`REALTIME_ORTOLS_HAS_NO_BREAK_RULE`).
- The dispatcher's report counts the orders no vehicle type can carry
  (`uncarriable`) and gives acceptance against the rest
  (`acceptance_of_carriable`); `vrp-dispatch` prints both. On the seed-5
  plant day 5 of 140 moves need the covered van but exceed its 4 pallets or
  1500 kg, so 85.7% of all orders is 88.9% of those the fleet can carry.
- Exact re-sequencing of short routes in ALNS (`vrp.reseat`). On every new
  best plan each left-out order is tried in every route of an allowed type
  with at most 9 stops after the insertion: a depth-first search over the
  orders of the stops that keep each pickup before its delivery, pruned by
  windows, capacity and the cost already spent, with every complete order
  checked by `route_exact` (ride limits, shift cap, breaks). It reaches what
  one destroy-and-repair step cannot: the new pair goes in and a stop already
  on the route moves. On the 20 instances of the warm-start study ALNS now
  reaches the best plan on 17 instead of 16, worst gap 0.9% instead of
  16.02%; seed 2004 ends at the value CP-SAT proves. The step never acts on
  the 130 public instances with the published budgets (checked run by run),
  so their tables stand.
- Site: the dispatch replay switches to the same day under Order No. 160. A
  yellow ring marks a driver on a break, breaks appear in the feed, and the
  policy table has the row with the rule.

### Fixed
- The dispatcher counted the service time at a vehicle's current stop twice
  when it worked out when the vehicle could leave, and refused orders it
  could serve. The seed-5 plant day now accepts 120 orders instead of 118,
  seed 11 134 instead of 131. More orders go to vehicles that still have
  stops ahead (62 instead of 53 on seed 5), so the mean time to pickup rises
  from 16.2 to 20.2 minutes, inside the 40-minute window. A test pins the
  case.

### Changed
- The dispatch table has columns for acceptance of carriable orders and for
  breaks, and the plant day under Order No. 160. One untimed day runs before
  the timed ones: the first run in a fresh process paid for first-call setup.
- Recomputed: the dispatch table, the warm-start study and the exact-vs-ALNS
  study (the same values, new timings) and the site data. The rules study
  came out identical.

## 0.6.2 — 2026-11-15

### Fixed
- Three documents still described 0.5: time-dependent travel and split breaks
  "only on the Python reference". The Rust kernel has run both since 0.6, with
  the same plans. The profiling note, the rules table, the comparison and the
  cargo roadmap now say what the code does, and what is actually still in
  Python (vehicle-type assignment, route merges, the live dispatcher).
- The README and the site said 695 tests. The fast suite collects 717.
- The plant-day mileage figure was rounded to 79%; the measured value is 78.5%.
  The paragraph names seed 11, so it is not read as the seed-5 dispatch table.
- The site's "order, vehicle, driver" row now says where the driver lives:
  the passenger kernel checks the seated driver's qualification, the freight
  model checks vehicle skills and the driving-time rule.
- The Pages workflow pinned its three actions by commit, as the other
  workflows already do.
- `vrp-solve` exited 0 when every served route was legal, even if a
  mandatory order was left out. The exit is 0 only when the verdict is
  feasible and complete, and the summary says `INCOMPLETE`.
- A fleet `count` of `2.7` or `true` in JSON or a geo file was truncated by
  `int()`. Both readers refuse it with `VRP_COUNT_INVALID`. The same holds
  for every other whole number in the JSON format (node ids, depots, reload
  stops, `max_trips`, pickup and delivery nodes) and for the geo `trips.max`:
  `2.7`, `true`, `"6"` and `2.0` are refused instead of becoming 2, 1, 6
  and 2. `trips.max` of 0 is `VRP_TRIPS_INVALID`.
- A large fleet grew the instance with its size: `trips` added
  `count * (max_trips - 1)` reload stops and every matrix grew with their
  square (20,000 vans with three trips asked for 40,000 stops), and the live
  dispatcher built one vehicle per unit. Both now stop at the number of
  orders, which no plan exceeds; the OR-Tools baseline already did.
- Without the Rust build, `mobiroute solve` with `fifo`, `greedy`, `beam`,
  `alns` or `rhc` and `mobiroute demo` ended in a Python traceback. The CLI
  prints one line with the build command and exits 2; the message names the
  heuristics that need the build and the two (`nearest`, `cpsat`) that do
  not. The README said the kernel was optional for the whole package; it is
  optional for the freight engine only.
- `docs/industrial-transport.md` explains the two orders of the seed-11
  plant day that both plans leave out: no vehicle type can carry them (the
  covered van holds 4 pallets and 1500 kg). The morning plan serves all 138
  feasible orders; a test pins the two ids.
- The geo format example showed driver rests and a speed profile in one
  file. That combination is refused; the example no longer contains it.

### Changed
- `vrp-solve` exit statuses: 0, the plan is verified and complete; 2, the
  input was refused or the plan breaks a rule; 3 (new), the plan is verified
  and written but mandatory orders have no vehicle. The CLI lists those
  orders and names the ones no vehicle type can carry, and `--help` states
  the three statuses.
- The fleet, route-sheet and price scripts load when their section comes
  near. The first screen fetches the page script and the verifier it replays.

## 0.6.1 — 2026-11-15

### Added
- Warm start and deterministic runs for the exact CP-SAT model, taken from
  the SynAPS scheduling core. `solve_exact(..., hint=plan)` starts the
  search from a known plan; `deterministic=True` stops on CP-SAT's
  deterministic time instead of the wall clock and runs the workers as one
  interleaved search, so the same input gives the same plan on any machine
  and under any load. The batch size of that search is set explicitly: with
  the default, OR-Tools 9.15 returned another plan on 2 of 8 identical runs.
- `vrp-solve --solver exact` starts CP-SAT from an ALNS plan, adds a cold
  run when the warm one proves nothing, and keeps the cheapest verified plan.
  `docs/benchmarks/warm-start.md` measures it on 20 instances of 14 orders,
  where ALNS alone stops short of the best plan on 4 (by up to 16%): the warm
  run is never worse than ALNS, and the two runs together reach the best
  plan on all 20, every run repeatable.
- `benchmark/instances/NOTICE.md`: authors, source and licence of every
  vendored benchmark set (MIT, Apache-2.0 with its full text, CC BY 4.0),
  which the MIT licence of this repository does not cover. Legal notes in
  both READMEs and in the site footer: an independent project built from
  public sources, no affiliation with the companies the documents mention,
  legal rules described as model constraints and not legal advice; the site
  sets no cookies and loads no third-party services.
- Supply-chain checks, as in the other SynAPS repositories: CodeQL for
  Python, JavaScript and Rust, OpenSSF Scorecard, Dependabot for pip, Cargo
  and Actions, a gitleaks scan of the whole history, and every third-party
  action pinned by SHA.
- `tests/test_claims.py`: published texts may not promise more than the
  evidence shows, the instance count on the site is recounted from the
  vendored files, the verifier may import nothing from the search (checked
  on the import graph), and no package in the dependency tree, runtime or
  development, is under GPL or AGPL.

### Fixed
- A JSON instance file with a missing or malformed field raised `KeyError`,
  `TypeError` or `OverflowError` from inside the loader; one mutated field in
  three escaped that way. Both loaders (`mobiroute.vrp.io` and the geo
  format) now end every broken file in a `ValueError` with a code
  (`VRP_JSON_FIELD_MISSING:<name>`, `VRP_JSON_FIELD_INVALID:<detail>`), and
  node references, optional numbers and skill lists are type-checked: a bare
  string is no longer split into one-letter skills.

### Changed
- Drivers' working time is cited by Order of the Ministry of Transport of
  Russia No. 160 of 14.04.2026, in force from 1 September 2026 in place of
  Order No. 424 (the limits the engine plans with are the same).
  `docs/trucking-ru.md` is rewritten for a lawyer, a labour-law specialist
  and a logistician: working time and rest point by point, trip documents
  (waybill, electronic transport documents, medical and technical checks),
  road rules and the warehouse side, each with its status in the model.

## 0.6.0 — 2026-11-15

### Fixed
Found by trying to break the engine (`tests/test_vrp_robustness.py`):
- The model accepted `NaN` and infinity, which JSON readers parse: a `NaN`
  service time gave a plan the verifier passed with a cost of `nan`, an
  infinite one made every schedule look feasible. Amounts are now finite and
  not negative, clock times finite, and `+inf` remains only where it means
  "no limit".
- The verifier raised `IndexError` on a plan with an unknown vehicle type, a
  node that does not exist or an unknown request index, and priced a route
  with type `-1` as the last type. These are now violations; the cost covers
  the well-formed routes only. Hypothesis feeds it arbitrary plans.
- With a rest rule the reported shortest shift was that of the first
  admissible rest place, up to 45 minutes longer than the best place when a
  later gap hides the rest in waiting time. Duty-time prices, route sheets and
  the verdict used it. Every place (and pair of places for a split break) is
  now timed and the shortest kept (Lemma 1b of the formulation).
- The exact CP-SAT model and the OR-Tools baseline priced operating time on
  instances that pay the whole shift (`time_cost = "duty"`); both refuse such
  instances now instead of reporting a result for another objective.
- OR-Tools gave every order the must-serve penalty, on both nodes of a pair,
  and drove out to orders cheaper to refuse; the live re-solve policy could
  not tell the new order from old promises. An optional order costs its own
  penalty, once. The re-solve row of `docs/benchmarks/realtime-dispatch.md`
  is rerun: 81.4% of orders accepted (86.4% before), 4.6% cheaper than
  insertion with ALNS passes, 7 minutes later to the pickup.
- An OSRM table request carried every point of the day in its URL (about
  22 kB for a thousand stops); each block request carries its own points.

### Added
- Fleet indicators (`mobiroute.vrp.kpi`): loaded and empty kilometres, the
  mileage utilisation coefficient beta, the dynamic load utilisation gamma
  over loaded kilometres per load dimension, load-kilometres and time on
  duty split into driving, service, rest and waiting. `vrp-solve` writes
  `kpi.md` and a `kpi` block in `verdict.json`; route sheets name each
  vehicle's empty kilometres; the dispatcher's report adds empty running.
- `docs/industrial-transport.md`: in-plant and inter-plant transport,
  line feeding, staff shuttles; what the model covers and what it does not,
  with a live-versus-static comparison on the plant day.
- `vrp-dispatch --orders`; `vrp-solve --time-limit` without `--iterations`
  now runs for the whole budget instead of stopping at 5000 iterations.

### Changed
- The Rust kernel covers time-dependent travel and split breaks, which fell
  back to Python before: 6.5x and 5.5x faster per iteration on the measured
  days, the same plans bit for bit (`docs/benchmarks/vrp-speed.md`).
- The kernel unwinds on panic, so a bug fails one call with a Python
  exception instead of aborting the host process; the Bellman-Ford loop moved
  into its own frame to keep the DARP case as fast as before (faster, in
  fact: 2.45 against 2.63 ms an iteration on a4-48).
- Site: each data file is fetched once and a section loads when it comes
  near; off-screen sections skip layout. On a phone profile: 8 requests
  instead of 16, 200 instead of 331 kB at start, main-thread work down about
  40%, largest contentful paint 0.93 -> 0.81 s.
- Package and kernel 0.6.0; the kernel ABI check moves with them.

## 0.5.0 — 2026-11-14

### Added
- Prices from LP duality (`mobiroute.vrp.prices`, `vrp-solve --prices`): the
  dual of the set-partitioning relaxation over the ALNS route pool prices
  every order and puts a rent on every vehicle type that ran out. The pool is
  enlarged by the plan's routes with one order taken out and on every other
  type that can run them, so an LP-optimal plan prices an order at no less
  than the saving of dropping it (Lemma 5); among the many optimal duals of
  the degenerate LP the one closest to those savings is returned by a second
  LP over the optimal face. `prices.json`, `prices.md` (RU, EN); on the site,
  a map of the Chelny day with orders sized by price and each rent next to
  the day solved again with one more vehicle.
- Orders that may be refused: an order with a finite `penalty` is left out
  when serving it costs more than refusing it, one order at a time and then
  whole routes of optional orders. Before, the repair served whatever fit:
  on 90 small instances with cheap refusals ALNS matched the CP-SAT optimum
  on 16 and cost twice the optimum on average; now it matches on 87, mean gap
  0.3% (`docs/benchmarks/exact-vs-alns.md`, second table).
- `benchmark/profile_vrp.py`: a `cProfile` ranking by own time of one ALNS run
  on the Python reference and on the Rust kernel
  (`docs/benchmarks/vrp-profile.md`), the table every optimisation in
  `docs/native-acceleration.md` started from.
- Split driver break 15 + 30 min (EU Regulation 561/2006 art. 7, Order
  No. 424): the second part where a whole break could go, the first in an
  earlier gap (Lemma 1a); exact in the verifier and the search check; route
  sheets show both parts and only the second resets the driving counter.
- `time_cost = "duty"`: the hourly rate pays the whole shift, waiting
  included (the shortest feasible duration), in the objective, the vehicle
  type choice, set partitioning and route sheets.
- Truck access zones (polygon or circle) with limits on gross weight, axle
  load and height and banned vehicle types, as road signs 3.4 and
  3.11–3.13 set them; truck-aware matrices from Valhalla
  (`vrp-solve --valhalla URL`).
- VRPLIB reader (CVRP, VRPTW; exact, DIMACS and CVRPLIB rounding) and the
  1000-customer Gehring–Homberger and Uchoa X instances with best-known
  solutions.
- `benchmark/solvers_study.py`: ALNS, PyVRP 0.14, VROOM 1.15 and jsprit 2.0
  on the same instances at equal time, one thread, every plan re-checked by
  the verifier (`docs/benchmarks/solvers.md`). Solomon, vehicles first, 10 s:
  ALNS at the best-known vehicle count on 56 of 56 (PyVRP 50, VROOM 32,
  jsprit 30). 1000 customers, distance only, 60 s: PyVRP leads at +1.2% to
  the best known, ALNS is second at +2.9%, VROOM +15%, jsprit +21%. The
  harness took `SHA256SUMS.txt` for an instance and crashed after its last
  run; it now skips the checksum file.
- `docs/trucking-ru.md`: Russian freight rules and practice mapped onto the
  model.
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
- A driving-time check on every route sheet, as an inspector reads it: the
  longest drive between breaks, driving in the shift and the shift length
  against their limits; a Hypothesis property holds every sheet of random
  feasible routes to them.
- Depot loading time before the first departure (`load_min`), counted in
  the shift and the windows; the loading order of each trip at the depot,
  last drop first; decimal commas in Russian sheets.
- `docs/comparison.md`: OR-Tools, VROOM, jsprit, PyVRP, Timefold and Yandex
  Routing checked against their documentation, the measured head-to-head
  with OR-Tools (better on 12 of 18 instances, worse on none), and the
  research behind the engine with what is taken and what is next.
- The driver's schedule (`schedule.compact_schedule`): the latest departure
  that still returns earliest, a shortest-duration schedule (Lemma 4 in the
  formulation, two Hypothesis properties).
- `examples/chelny-day.geo.json`, a synthetic day in Naberezhnye Chelny, and
  its generator.
- Site: a route-sheets section with the day's map, a Gantt chart of every
  vehicle, the sheet and load profile of the selected one, and a shift-start
  slider that plots the shift length $D(t_0) = \max(E - t_0, c)$ of Lemma 4;
  a comparison section; view transitions on theme and language switches,
  anchors clear of the sticky bar, balanced headings, and styles for
  increased contrast and forced colours.
- README (RU, EN): quick start, the model, the algorithms, measured results
  with links to their tables, a map of the code and the key formulas.
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

### Performance
- Profiled on a 1000-customer instance (X-n1001-k43, 60 s, one thread):
  8,577 → 24,748 iterations a minute, gap to the best known 5.75% → 3.4%.
  A granular mode from 400 requests (worst removal from the arcs around a
  stop, local search from the changed routes only); a memoized objective;
  Shaw removal and served-request lookup without full scans; in Rust,
  regret-k by linear selection of the k smallest costs and insertion bounds
  without a vector per evaluation. Rust and Python stay bit-identical, and
  instances under 400 requests keep their published trajectories.

### Fixed
- A multi-trip day lost its rush hours: `add_reload_stops` rebuilt every
  road profile without its speed profile, so a geo file with both `trips`
  and `traffic` was planned and verified on free-flow times. The profile is
  now kept, with a regression test through the verifier.
- The OR-Tools baseline fed Routing its matrices through Python callbacks. The
  search spent its wall-clock budget in the interpreter, which handicapped
  the baseline of every equal-time comparison (and made one test fail under
  the coverage tracer, as CI runs it). Matrices are now registered on the
  C++ side; the baseline reaches the C101 optimum in half the time, and the
  comparison tables are rerun: ALNS is better on 12 of 18 instances and equal
  on 6 (was 15 and 3 against the slow baseline), and OR-Tools no longer drops
  an order of Cordeau a2-16.
- Route sheets put the driver's rest before the drive of its gap even where
  Lemma 1 admits it only after the drive, on arrival at the next stop; such
  sheets showed a stint over the limit (the verifier's schedule was right).

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
- The OR-Tools baseline, the exact model and the dispatcher refuse instances
  with rests, reload stops or speed profiles with an explicit error.
- One name for one thing: the paratransit kernel's feasibility check is the
  verifier, as in `mobiroute.vrp`. Benchmark evidence fields
  `notary_feasible` and `notary_violations` are now `verifier_feasible` and
  `verifier_violations`; the gap blocker `ALGEBRA_NOT_COMPARABLE` is
  `MODEL_NOT_COMPARABLE`; `vrp.ortools_lane` is `vrp.ortools_baseline`, and
  its error codes start with `ORTOOLS_`. Test modules got descriptive names.
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
- OR-Tools Routing baseline (PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH) on
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
  of the scheduling fix, solver race and an in-browser route verifier.

### Changed
- Documentation rewritten around the engine; the notes on the paratransit
  kernel merged into `docs/darp-kernel.md`.
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
  the Python oracle, the route simulator and the verifier. Before, every simulator
  scheduled pickups as early as possible: Cordeau a2-16 lost 7 of 16 requests
  (each refused even alone). Now greedy, beam, ALNS and RHC serve 16 of 16 and
  the tiny CP-SAT plan verifies as OPTIMAL.
- The verifier refuses pickup dwell beyond the curb wait (`UNEXPLAINED_DWELL`):
  a passenger held onboard at the curb no longer escapes the ride clock and quota.
- `nearest` and `beam` respect the passenger-day quota (they published plans the
  verifier rejected on `ops_quota`).
- `generate --mode large` asked for a depot outside the zone matrix.
- `academic-benchmark` attached the a2-16 reference to any file; it now binds to
  the vendored SHA-256 and reads the instance bytes once.
- CLI input errors print one line and exit 2 instead of a traceback.

### Added
- Cordeau (2006) exactly as published: strict parser, exact CP-SAT model, compact
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
- The automatic dependency-update config; a weekly dependency audit
  replaces it.

## Earlier versions

- **0.2.x (Aug–Sep 2026).** Paratransit kernel hardening: explicit driver
  assignment; greedy pooling insertion with dynamic loads; the Rust
  `InsertionEngine` for insertion scoring (persistent fleet, prefix-state
  walk, copy-on-write fork); tiny CP-SAT that reports `OPTIMAL` only when the
  verifier accepts the plan; operator policy (pooling modes, linked trips,
  quota bases); plan identifiers with parent links for online and recovery
  plans; plan diff with retiming and driver changes; reasons for refused
  trips; Cordeau a2-16 pinned by its SHA-256; a check that keeps a literature
  gap out of reports for runs that are not comparable; the `stress_200` day.
- **0.1.x (Aug 2026).** Domain model and schemas, FIFO and greedy baselines,
  the feasibility verifier, online insertion and disruption recovery, the
  synthetic Moscow-zone generator, fairness and privacy helpers.
