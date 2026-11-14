# Scope and roadmap

What the engine covers, what it leaves to adjacent systems (the accounting
system, the operator's router), how to read its numbers, and what comes
next.

## Data

* Public benchmarks and synthetic days only. There is no customer data and no
  pilot, so nothing here is a claim about savings at an operator.
* Synthetic cargo, shuttle and plant days use straight-line distance times a
  detour factor and a fixed speed per profile. The model accepts any matrix:
  the Sartori–Buriol set already runs on real road times (OSRM).
* Input in coordinates (`vrp.geo`): offline matrices are great-circle
  distance times a detour factor at a mean speed, symmetric and blind to
  one-way streets; OSRM matrices come from whatever profile the server runs
  (usually a car), and a truck is only slowed down by a factor. With a
  Valhalla server (`--valhalla URL`) a profile gets truck-aware matrices
  (weight, axle load, height, hazmat). Matrices are fetched once per
  profile; there is no cache and no retry.
* Access zones close stops to vehicle types by gross weight, axle load,
  height or type for the whole day; a ban by time of day (trucks barred
  from a centre at rush hour) needs time windows per vehicle type, which
  the model does not have. Seasonal axle limits are set by hand as zone
  limits or Valhalla options.
* The Naberezhnye Chelny example is synthetic: random points inside the
  city's bounding box, made-up names, no company's orders.

## Rich VRP model

* Driver rules. Implemented: a break of at least $b$ minutes after at most
  $D$ minutes of driving and at most $2D$ minutes of driving a day; with
  $D$ = 4.5 h and $b$ = 45 min this is the rule of EU Regulation 561/2006
  (art. 6-7) and of Russian Ministry of Transport Order No. 424 of
  16.10.2020, including the split into 15 + 30 min (`BreakRule.split`, on
  the Python reference). The shift cap counts from departure to return,
  waiting included, as working time does. Not modelled: daily driving
  extended to 10 h twice a week (art. 6 of the EU regulation); weekly and fortnightly driving limits; the meal break of the
  Labour Code (art. 108), which is not working time; daily and weekly rest
  between shifts; tachograph data. The rest is one contiguous block in one
  gap between two stops, before or after that gap's drive (whichever keeps
  both stints within the limit). It may use idle time of the gap only if the
  driver is free to rest there (queueing at a gate is not a break). These are
  engineering constraints, not legal advice: check a configuration against
  the regulations in force and the company's local acts.
* Route sheets are trip plans ("маршрутный лист" in the Russian output), not
  the statutory waybill ("путевой лист", Road Transport Charter, art. 6;
  required details by Order No. 390 of 28.09.2022). Vehicle and driver data,
  odometer readings and the medical and technical pre-trip checks stay in
  the accounting system.
* Multi-trip days need reload stops created up front
  (`model.add_reload_stops`); a stop is a copy of the depot, and reloading
  takes a fixed time whatever the load.
* Time-dependent travel: one speed profile per road profile (every arc slows
  down by the same factor); the search tests the shift cap soundly but not
  completely (it may reject a feasible route), time costs are charged on
  free-flow minutes, and it runs on the Python reference, not the Rust
  kernel. It is not combined with ride limits or rest rules.
* By default cost per time is charged on driving and service, not on
  waiting. `time_cost = "duty"` charges the whole shift instead (the
  shortest feasible duration, waiting included) in the objective, the
  choice of vehicle types, set partitioning and route sheets; the regret
  repair, in Python and in Rust, still ranks insertions by the fast
  operating-time delta, so a plan's waiting is cut by acceptance and the
  other operators rather than at insertion.
* The loading order on a sheet is the reverse of the drops per trip; it does
  not check stowage, axle loads or load securing.
* Route sheets: the schedule is the shortest one that returns earliest (no
  traffic) or the shortest one (traffic); a dispatcher who prefers an early
  start or a fixed departure has to shift it by hand, and the rest's place is
  the first admissible gap the verifier finds, not a driver's preference.
* Every vehicle returns to its end depot; open routes need a zero-cost return.
* The OR-Tools lane, the exact CP-SAT model and the live dispatcher do not
  model rests, multi-trip days or time-dependent travel; they refuse such
  instances with an explicit error. In the dispatcher, ride limits have to be
  written as delivery deadlines, and vehicles idle where they finish instead
  of repositioning.

## Algorithms

* ALNS, regret insertion, guided ejection, the merge operator, the local
  search and the dispatcher are heuristics. Gaps to best-known solutions vary
  between seeds; the spread on Solomon's type-2 classes is measured in
  [benchmarks/seed-study.md](benchmarks/seed-study.md).
* The local search applies to instances whose orders are all deliveries from
  the depot (VRPTW) without reload stops, rest rules or traffic.
* Set partitioning over the route pool is off by default: on long-route
  instances the pool rarely holds routes that partition the orders anew.
* The exact CP-SAT model proves optima on small instances (about ten orders).
  `OPTIMAL` refers to its integer model with travel rounded up to 0.01 min;
  the verifier re-prices the plan in real numbers.
* The OR-Tools lane is the common configuration (PCI + GLS, integer time grid,
  disjunctions), not a tuned setup; the comparison says how far the default
  gets in the same time, not what OR-Tools can do with tuning.

## Paratransit kernel

* Synthetic Moscow-zone days; quota and priority rules are policy shapes, not
  legal eligibility; no integration with a live dispatch system.
* CP-SAT tiny is a sequential model (no pooling).

## Timings

One machine (Linux x86_64, Python 3.13), one thread unless stated. Samples,
not SLAs.
