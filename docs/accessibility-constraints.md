# Accessibility constraints

Hard checks (optimizer may not violate for cost):

| Constraint | Field(s) |
| --- | --- |
| Wheelchair seat | `vehicle.wheelchair_capacity` vs load |
| Lift | `trip.needs_lift` → `vehicle.lift_available` |
| Ramp | `trip.needs_ramp` → ramp or lift |
| Boarding assistance | `driver.accessibility_training` |
| Companions | seats = 1 + `companion_count` |
| Service area | optional zone allow-list |
| Shift | pickup/dropoff within driver/vehicle shift |

Priority hierarchy is explicit in `domain/priorities.py` — not opaque weights.

Medical / child / palliative classes affect **priority and reporting**, not a
bypass of safety constraints.
