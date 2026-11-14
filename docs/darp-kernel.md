# Paratransit DARP kernel

The original operator kernel of the repository: accessible door-to-door
transport with passengers, companions, wheelchairs, drivers, hour quotas,
linked trips and live disruptions. It lives in `mobiroute.domain`,
`mobiroute.solvers`, `mobiroute.dispatch` and `mobiroute.validation`, works in
integer minutes on a zone matrix, and is exercised on synthetic Moscow-zone
days. The general cargo and passenger engine is in `mobiroute.vrp`
([cargo-vrp.md](cargo-vrp.md)).

## Model and hard constraints

| Area | Rule | Field(s) |
| --- | --- | --- |
| Pairing | pickup and dropoff on one vehicle, pickup first | stop sequence |
| Windows | pickup window; dropoff not before `appointment_start - 30`, not after `appointment_end` | `earliest_pickup`, `latest_pickup`, `appointment_*` |
| Waiting | passenger delay from earliest pickup at most `max_wait_time`; an onboard hold is capped the same way | `max_wait_time` |
| Ride | ride time (pickup departure to dropoff arrival) at most `max_ride_time` and `max_detour_ratio` x direct | `max_ride_time`, `max_detour_ratio` |
| Curb dwell | pickup service is `max(boarding, 5)` min; no extra dwell after it | `boarding_duration` |
| Capacity | seats = 1 + companions; wheelchair places separately | `passenger_capacity`, `wheelchair_capacity` |
| Accessibility | lift, ramp (or lift), wheelchair type, stretcher rides alone | `needs_lift`, `needs_ramp`, `compatible_wheelchair_types` |
| Driver | qualification, vehicle type, depot, shift, rest intervals; boarding assistance needs training | `Driver.*` |
| Vehicle | shift, depot return, service area, unavailable intervals | `Vehicle.*` |
| VIA stop | optional third stop, passenger stays on board; counts in detour | `via_zone`, `via_service_duration` |
| Quota | remaining entitlement in the policy's debit basis | `quota_minutes_remaining` |
| Links | `same_vehicle_as`, `insert_immediately_after`; all-or-none groups | linked-trip fields |

Pickup floor. With alight floor `a = max(0, appt - 30)`, ride cap
`L = min(max_ride, detour cap)` and curb service `s = max(board, 5)`, every
feasible schedule starts the pickup at or after `max(earliest, a - L - s)`
(Dumas, Desrosiers & Soumis 1991). Search, Python oracle and notary share
`pickup_service_floor`, so an early vehicle waits for it without losing any
schedule.

## Input validation

`validate_problem` returns a new canonical `DayProblem`; callers execute the
returned object, never the unchecked original. Minutes, capacities and seeds
are strict integers; NaN and infinity are rejected; IDs are nonblank and
unique per entity; depots, service areas and trip zones must exist in the
matrix; windows, shifts and intervals are ordered; all times fit `i32` for the
native kernel. A `TravelMatrix` is an immutable square snapshot with a zero
diagonal and `10**9` as the unreachable sentinel; Floyd-Warshall runs once per
snapshot. Malformed input raises `ValueError`; the CLI maps it to exit code 2.

## Solvers and the status they may publish

| Solver | Module | May publish `OPTIMAL` |
| --- | --- | --- |
| FIFO, nearest-feasible | `solvers/greedy.py`, `solvers/nearest.py` | no |
| Greedy pooling insertion (Rust `InsertionEngine`) | `solvers/greedy.py` | no |
| Beam over insertions | `solvers/beam.py` | no |
| ALNS (random, Shaw, worst, route; SA) | `solvers/alns.py` | no |
| Rolling horizon | `solvers/rolling_horizon.py` | no |
| CP-SAT tiny, sequential (no pooling), at most 40 requests / 12 vehicles | `solvers/cpsat.py` | only if OR-Tools proves it **and** the notary passes |

Above the CP-SAT size gate, or without OR-Tools, the lane returns the greedy
plan relabelled `CPSAT_FALLBACK_GREEDY` with its own `config_hash`; it is never
`OPTIMAL`.

## Notary

`validation/feasibility.check_plan` re-simulates every route from the problem,
not from solver bookkeeping: travel, windows, waits, curb dwell, ride and
detour, capacities, accessibility, drivers, shifts, rest, VIA order, linked
trips, pooling policy, quotas and the served/rejected accounting. There is no
partial check: a subset of routes cannot certify a plan.

## Online dispatch and disruptions

`dispatch/online_insertion.py` inserts an urgent request into the published
plan; `recover_disruption` handles cancellation, no-show, traffic delay and a
vehicle or driver dropping out.

* Frozen trips (already promised) keep vehicle, driver and pickup/dropoff
  clocks; an insertion that would move them is refused.
* Every result is re-verified by the notary against the updated problem.
* Identity: only `finalize_result` publishes `input_hash`; every lane that
  republishes a plan (RHC, ALNS, repair, fallback, manual override) signs its
  own `config_hash` and `plan_id`; a baseline without a plan id is referenced
  as `unsigned:<content hash>`.
* `compute_diff` reports moved, retimed, driver-changed, added and removed
  trips, broken and unchanged frozen trips and `plan_churn`.
* A refusal lists per-vehicle evidence (`NO_COMPATIBLE_VEHICLE`,
  `NO_QUALIFIED_DRIVER`, `INSERT_INFEASIBLE`, `POOLING_BLOCKED`, ...), at most
  eight vehicles plus the count omitted. `diagnose_rejection` reports a
  specific cause only when it is a necessary condition (no compatible fleet or
  driver, quota below the shortest ride); otherwise `MANUAL_REVIEW_REQUIRED`.

## Operator policy

`OperatorPolicy` is versioned separately from solver code:

* `pooling_mode`: `FORBIDDEN` (no simultaneous sharing), `OPT_IN` (every
  co-rider opted in), `ALLOWED`;
* `chain_mode`: `fulfillment_group_id` groups served all-or-none when
  `MANDATORY`;
* `quota_debit_basis`: `RIDE_DURATION` or `BILLABLE_SERVICE`
  (`max(board, 5) + ride + alight`).

## Fairness and explanations

Every served trip records vehicle, driver, times, active constraints and the
alternatives considered and rejected; every rejected trip has a non-empty
reason code (an empty one is a notary violation). Fairness is always reported
as several metrics: service rate by zone and eligibility class, medical and
wheelchair on-time rates, mean and P95 wait and ride, worst-group wait, Jain
index, maximum disparity, unexplained-reject share.

## Privacy

Open data is synthetic. Passenger ids are pseudonymous and separate from trip
ids; `redact_problem_for_open` strips coordinates and refuses non-synthetic
input; `log_safe` masks e-mail and phone patterns in logs. No real names,
phones, addresses, medical data or GPS tracks are committed.

## Native kernel state

The Rust `InsertionEngine` keeps a persistent fleet within one solve and is
forked copy-on-write for online insertion. Kernels are never cached across
solves by `plan_id` or `input_hash`; online insertion rebuilds from the
validated problem.

## Speed

`stress_200` (200 vehicles, 3200 requests, seed 42, Linux x86_64, Python 3.13,
one thread): day-ahead greedy 2.8 s (47.9 s before profiling: 56% of the time
went into rebuilding a request map inside `pooling_stops_violate`), full
pipeline with disruptions and 8 urgent inserts 13.1 s. See
[native-acceleration.md](native-acceleration.md).

## Tests

`tests/test_core.py`, `test_adversarial.py`, `test_redteam*.py` (forged
clocks, hidden onboard dwell, overloads), `test_online_*`, `test_plan_diff.py`,
`test_rejection_evidence.py`, `test_operator_policy.py`, `test_linked_policy.py`,
`test_quota_*`, `test_privacy_boundary.py`, `test_insertion_kernel.py`
(Rust vs Python oracle lockstep).
