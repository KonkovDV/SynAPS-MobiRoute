# Linked-trip verification

Both reference fields apply when present; neither takes precedence over the other.

- `same_vehicle_as`: the referenced trip must be served on the same vehicle in the supplied plan. It does not impose pickup order. Equality-only cycles, including a self-reference, are not temporal cycles.
- `insert_immediately_after`: the referenced trip must be served on the same vehicle, and its dropoff must be followed by the child's pickup as the next service stop. An intervening VIA also breaks this adjacency.
- A served child with a missing or unserved parent is not verified. A rejected child does not force its parent to be rejected.

The independent notary checks every route. `check_plan` has no vehicle-subset
argument: a partial set cannot establish whole-plan feasibility.

The policy module also supplies dependency ordering, ownership intersection and descendant/pruning helpers for constructive integration. Missing parents and incompatible anchors are not silently ignored; descendant traversal follows both fields without recursion. Dispatch cancel/no-show cascade uses the same `dependent_ids` closure. All-or-none passenger groups are `fulfillment_group_id` under `OperatorPolicy.chain_mode`, not these directional fields.

## Scope

Ten test methods in two classes cover the policy helpers (dual references,
adjacency/VIA, missing parents, equality cycles, immediate-order precedence,
descendant closure and dispatch cancellation) and the notary (wrong vehicle,
broken adjacency, missing parent and partial-check false positives). Run
`PYTHONPATH=src:. python -m unittest tests.test_linked_policy`.

This is the verification layer, not completion of link-preserving construction in every solver, seed and dispatch path. Native candidate refinement and constructive integration follow separately. Arbitrary supplied-plan validation, historical/frozen/onboard repair, quota metadata and output fingerprints remain separate contracts. No pilot-readiness or latency claim is made.
