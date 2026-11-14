# Limitations

What the code does not do yet, and what its numbers do not mean.

## Data

* Public benchmarks and synthetic days only. There is no customer data and no
  pilot, so nothing here is a claim about savings at an operator.
* Synthetic cargo, shuttle and plant days use straight-line distance times a
  detour factor and a fixed speed per profile. The model accepts any matrix:
  the Sartori–Buriol set already runs on real road times (OSRM).
* Input in coordinates (`vrp.geo`): offline matrices are great-circle
  distance times a detour factor at a mean speed, symmetric and blind to
  one-way streets; OSRM matrices come from whatever profile the server runs
  (usually a car), and a truck is only slowed down by a factor. Truck
  restrictions (weight, height, bans) need a truck-aware engine such as
  Valhalla or GraphHopper behind the same matrix-source function. Matrices
  are fetched once per profile; there is no cache and no retry.
* The Naberezhnye Chelny example is synthetic: random points inside the
  city's bounding box, made-up names, no company's orders.

## Rich VRP model

* Driver rests: one rest per route, so at most twice the driving limit per
  day (the 9-hour daily limit for the 4.5 h rule); the rest is not split
  (15 + 30 min), and daily and weekly rest between shifts is out of scope.
* Multi-trip days need reload stops created up front
  (`model.add_reload_stops`); a stop is a copy of the depot, and reloading
  takes a fixed time whatever the load.
* Time-dependent travel: one speed profile per road profile (every arc slows
  down by the same factor); the search tests the shift cap soundly but not
  completely (it may reject a feasible route), time costs are charged on
  free-flow minutes, and it runs on the Python reference, not the Rust
  kernel. It is not combined with ride limits or rest rules.
* Cost per time is charged on driving and service, not on waiting.
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
