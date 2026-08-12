# Fairness and explainability

## Policy (lexicographic)

1. Safety / accessibility / medical hard constraints before cost.
2. Medical urgency above a standard trip.
3. Accessibility above extra kilometres.
4. Confirmed appointment window above route convenience.
5. Fairness is analysed **after** hard constraints.
6. An operator may change a result only with a non-empty reason code.

## Metrics (always multi-metric)

- Service rate by zone and eligibility class
- Medical on-time rate; wheelchair on-time rate
- Average / P95 waiting; worst-group waiting
- Average / P95 ride time
- Rejected rate; maximum disparity; Jain index
- Service coverage; unexplained reject share
- `fair_by_single_metric` is always `false`

Improving one metric does **not** prove fairness.

## Reason codes

`NO_COMPATIBLE_VEHICLE`, `NO_CAPACITY`, `NO_WHEELCHAIR_CAPACITY`, `NO_DRIVER`,
`TIME_WINDOW_CONFLICT`, `APPOINTMENT_CONFLICT`, `MAX_RIDE_TIME_CONFLICT`,
`DEPOT_REACHABILITY_CONFLICT`, `DRIVER_SHIFT_CONFLICT`, `VEHICLE_UNAVAILABLE`,
`DISRUPTION`, `ELIGIBILITY_REVIEW_REQUIRED`, `MANUAL_REVIEW_REQUIRED`,
`CANCELLED`, `NO_SHOW`, `ACCEPTED`.

Empty rejection reasons are a notary violation.

## Explanations

Each served trip records vehicle, driver, pickup/dropoff times, active constraints,
why this route, and alternatives considered/rejected. Each rejected trip keeps a
non-empty reason code.

## Human-in-the-loop

Operator override requires a non-empty free-text reason; the journal is the audit
trail. Full dispatcher UI is out of scope.
