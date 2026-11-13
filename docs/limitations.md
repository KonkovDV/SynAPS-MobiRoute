# Limitations

What the code does not do yet, and what its numbers do not mean.

## Data

* Public benchmarks and synthetic days only. There is no customer data and no
  pilot, so nothing here is a claim about savings at an operator.
* Synthetic cargo, shuttle and plant days use straight-line distance times a
  detour factor and a fixed speed per profile. The model accepts any matrix:
  the Sartori–Buriol set already runs on real road times (OSRM), and a
  production setup would feed matrices from OSRM, Valhalla or GraphHopper.

## Rich VRP model

* One tour per vehicle: no multi-trip days (reloading at the depot).
* No breaks inside a route: a shift cap and windows, not the full working-
  and rest-time rules for drivers.
* Static travel times: no time-dependent speeds (rush hours).
* Cost per time is charged on driving and service, not on waiting.
* Every vehicle returns to its end depot; open routes need a zero-cost return.
* In the live dispatcher, ride limits have to be written as delivery
  deadlines, and vehicles idle where they finish instead of repositioning.

## Algorithms

* ALNS, regret insertion, guided ejection and the dispatcher are heuristics.
  Gaps to best-known solutions are reported per instance and vary between
  seeds; route elimination in particular is stochastic.
* The exact CP-SAT model proves optima on small instances (about ten orders).
  `OPTIMAL` refers to its integer model with travel rounded up to 0.01 min;
  the verifier re-prices the plan in real numbers.
* Insertion keeps a route's vehicle type; types are re-chosen only for finished
  routes. Merging two routes onto a different type in one move is not covered
  (both ALNS misses in the CP-SAT study are of this kind).
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
