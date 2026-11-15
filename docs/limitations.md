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
  (art. 6-7) and of Russian Ministry of Transport Order No. 160 of 14.04.2026
  (points 8 and 11; in force from 1 September 2026, replacing Order No. 424 of
  16.10.2020 with the same limits), including the split into 15 + 30 min
  (`BreakRule.split`, in the Python reference and the Rust kernel). The shift cap counts from departure to return,
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
  completely (it may reject a feasible route), and time costs are charged on
  free-flow minutes. It runs in the Rust kernel too, with the same plans. It
  is not combined with ride limits or rest rules.
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
  the one that gives the shortest shift (the earliest such gap), not a
  driver's preference.
* Every vehicle returns to its end depot; open routes need a zero-cost return.
* The OR-Tools baseline and the exact CP-SAT model do not model rests,
  multi-trip days or time-dependent travel; they refuse such instances with an
  explicit error. They also refuse `time_cost = "duty"`: they price driving
  and service, and a result for another objective would be mislabelled.
* The live dispatcher plans the break rule when it answers an order: the
  break goes into the part of the route not yet driven, counting the driving
  already done, and a break once begun is never moved (Lemma 1c). ALNS
  re-optimisation sees only the open stops and would count that driving as
  zero, so a proposal is kept only when every new suffix still satisfies the
  lemma, the verifier accepts the day and the verified cost falls. OR-Tools
  has no break variable and that policy refuses the day. Multi-trip days and
  time-dependent travel are refused too. Ride limits have to be written as
  delivery deadlines, and vehicles idle where they finish instead of
  repositioning.

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
* ALNS can stall where serving one more order needs two moves at once (a new
  pair in, a stop already on the route moved). Since 0.7 an exact
  re-sequencing step covers that case for left-out orders on short routes (up
  to 9 stops after the insertion, at most 20,000 search nodes per route): on
  20 instances of 14 orders with refusals ALNS reaches the best plan on 17
  instead of 16, worst gap 0.9% instead of 16%
  ([benchmarks/warm-start.md](benchmarks/warm-start.md)). Longer routes keep
  the weakness. For instances that small, `vrp-solve --solver exact` closes
  the remaining gap; for large days the gap is unknown, as no proof is
  available there.
* Deterministic CP-SAT runs (the default of `--solver exact`) fix the batch
  size of the interleaved search and prove fewer optima in a given time than
  the same search with the batch size left to OR-Tools: on the study above 1
  cold and 2 warm runs of 20 end with a proof, against 5 of 20 in the 0.6.1
  run without a fixed batch size. That variant does not repeat itself (2 of 8
  identical runs differed), so reproducibility wins.
* The OR-Tools baseline is the common configuration (PCI + GLS, integer time grid,
  disjunctions), not a tuned setup; the comparison says how far the default
  gets in the same time, not what OR-Tools can do with tuning. Its matrices
  are registered on the C++ side, so the time limit is spent on the search.
* The comparison with PyVRP, VROOM and jsprit covers classic VRPTW and CVRP
  only (those solvers do not share the rich model), with default settings and
  wall-clock budgets on a shared machine. On Solomon the hierarchical
  objective reaches the other solvers as a fixed vehicle cost, which is not
  what they are built for; where distance alone ranks, PyVRP is ahead of
  this engine at 1000 customers (+1.2% against +2.9% to the best known).
* Orders that may be refused are dropped by a rule on the plan as it stands:
  single orders first, then whole routes of optional orders. A cluster inside
  a longer route that is unprofitable only as a group is not found; against
  CP-SAT the rule is optimal on 87 of 90 small instances, worst gap 13%.
* Prices and rents (`vrp.prices`) are duals of a restricted master problem:
  exact for the routes the search visited, an estimate for the full problem.
  No pricing subproblem is solved, so a route outside the pool can change
  them, and the LP value over the pool is not a lower bound for the problem.
  A rent is a marginal rate of the relaxation, not a forecast: on the Chelny
  day the rents of own vans and trucks are 2,104 and 5,378 while solving
  again with one more unit saves 641 and 2,160. Degenerate LPs have many
  optimal duals; the one closest to the removal savings is a convention,
  stated in the formulation, not the only valid price list.

## Paratransit kernel

* Synthetic Moscow-zone days; quota and priority rules are policy shapes, not
  legal eligibility; no integration with a live dispatch system.
* CP-SAT tiny is a sequential model (no pooling).
* A manual rejection removes that trip's clocks and marks the plan unverified
  (`verified_feasible` stays false). The call has no problem instance to
  re-check the remaining stops, so the old ride and quota totals are dropped
  rather than republished.

## Timings

One machine (Linux x86_64, Python 3.13), one thread unless stated. Samples,
not SLAs.
