# Plan diff contract

Status: IMPLEMENTED for `compute_diff`. Synthetic laboratory reporting, not frozen-promise preservation or operational authorization.

- `moved_trips` / `changed_vehicle_assignments` remain vehicle-reassignment only.
- `retimed_trips` are same-vehicle pickup/dropoff clock changes. Assignment churn (`changed_trips`) does not include them.
- `changed_driver_trips` reports driver identity changes even when the vehicle is unchanged.
- Frozen trips with the same vehicle are `unchanged_frozen_trips` only when clocks and driver also match. Otherwise they are `broken_frozen_trips`.
- `changed_routes` includes add-only, remove-only, composition-changed, retimed and driver-changed vehicles. `added_routes` / `removed_routes` / `retimed_routes` name those subsets.
- `plan_churn` keeps the previous assignment keys and adds `retimed_trips`, `changed_drivers`, `broken_frozen`, `temporal_churn` and `changed_routes`.
- Lists are sorted. JSON round-trip of a `PlanDiff` is deterministic on the same implementation.

This is a reporting contract. It does not prove that online insertion preserved passenger promises, and it does not authorize driver commands.

Regression: `python -m unittest tests.test_plan_diff`.
