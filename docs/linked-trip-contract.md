# Linked-trip verification

Both reference fields apply when present; neither takes precedence over the other.

- `same_vehicle_as`: the referenced trip must be served on the same vehicle in the supplied plan. It does not impose pickup order. Equality-only cycles, including a self-reference, are not temporal cycles.
- `insert_immediately_after`: the referenced trip must be served on the same vehicle, and its dropoff must be followed by the child's pickup as the next service stop. An intervening VIA also breaks this adjacency.
- A served child with a missing or unserved parent is not verified. A rejected child does not force its parent to be rejected.

The independent notary checks every route. Its legacy `only_vehicles` argument no longer skips physical checks: a subset cannot establish whole-plan feasibility.

The policy module also supplies dependency ordering, ownership intersection and descendant/pruning helpers for constructive integration. Missing parents and incompatible anchors are not silently ignored; descendant traversal follows both fields without recursion. All-or-none passenger groups are `fulfillment_group_id` under `OperatorPolicy.chain_mode`, not these directional fields.

## Scope

The nine test methods cover dual references, adjacency/VIA, missing parents, equality cycles, descendant closure and partial-check false positives. Run `PYTHONPATH=src:tests python -m unittest test_linked_policy`.

This is the verification layer, not completion of link-preserving construction in every solver, seed and dispatch path. Native candidate refinement and constructive integration follow separately. Arbitrary supplied-plan validation, historical/frozen/onboard repair, quota metadata and output fingerprints remain separate contracts. No pilot-readiness or latency claim is made.
