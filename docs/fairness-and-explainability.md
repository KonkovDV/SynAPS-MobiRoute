# Fairness and explainability

## Metrics (always multi-metric)

- Acceptance rate by zone / eligibility class  
- Medical on-time rate  
- Mean wait by group; wait dispersion; worst-group wait  
- Unexplained reject share (must be ~0)  
- Jain index on group acceptance (optional)  
- Maximum disparity  

Improving one metric does **not** prove fairness.

## Reason codes

`NO_COMPATIBLE_VEHICLE`, `NO_CAPACITY`, `NO_WHEELCHAIR_CAPACITY`, `NO_DRIVER`,
`TIME_WINDOW_CONFLICT`, `MAX_RIDE_TIME_CONFLICT`, `DEPOT_REACHABILITY_CONFLICT`,
`DISRUPTION`, `ELIGIBILITY_REVIEW_REQUIRED`, `MANUAL_REVIEW_REQUIRED`,
`CANCELLED`, `NO_SHOW`, `ACCEPTED`.

## Human-in-the-loop (design)

Operator sees proposal, constraints, alternatives; may accept/reject with
mandatory manual reason; audit trail retained. v0 encodes reason codes + diffs;
full UI is out of scope.
