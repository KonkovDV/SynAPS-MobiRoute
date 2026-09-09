# Operator policy contract

Status: IMPLEMENTED as a laboratory profile on `DayProblem`. Not operator approval, legal pooling permission, billing, CAD/AVL, or automatic passenger refusal.

- Policy identity (`policy_id`, `policy_version`, `provenance`, `approved_by`) is versioned separately from solver capability. The laboratory default provenance is `laboratory:implicit_default` with `approved_by is None`.
- Blank provenance/ids are rejected. Fingerprints include the policy, `pooling_opt_in` and `fulfillment_group_id`; existing input hashes intentionally change.
- `pooling_mode`: `FORBIDDEN` forbids simultaneous onboard sharing (the notary
  walks pickup/dropoff occupancy, not "two trips used the van today"); `OPT_IN`
  requires every simultaneously shared passenger to opt in; `ALLOWED` is the
  explicit laboratory evaluation default. Collective transport does not invent
  another jurisdiction's mixing rule.
- `chain_mode`: directional `same_vehicle_as` / `insert_immediately_after` stay link verification. `fulfillment_group_id` with `MANDATORY` is all-or-none for active members, excluding cancelled/no-show.
- Time accounting distinguishes onboard `ride_duration` (pickup departure →
  dropoff arrival), `quota_debit` (policy basis) and `billable_service`. Billable
  service is the dwell the plan must hold: `max(boarding_duration, CURB_WAIT)`
  + ride + alighting, so a declared boarding below the enforced curb wait cannot
  understate an entitlement. Quota checks use the debit basis, not a cached ride
  summary; insertion, CP-SAT, the quota lower bound in `diagnose_rejection` and
  the notary read the same basis.
- Dispatch `COMMIT` and `SHADOW` both set `operational_authorization=False`. Shadow mode is evaluation-only. This kernel does not emit driver commands or treat search failure as an operator refusal.

Solvers, online insertion, disruption recovery and the independent notary read the same profile. Regulatory interpretation and commercial/pilot outcomes require separate evidence. `CURB_WAIT` is an FTA/DREDF analogue in this kernel, not a Moscow tariff rule.

Regression: `python -m unittest tests.test_operator_policy tests.test_quota_debit_basis`. Native-backed shadow/recovery methods skip when `mobiroute_native` is absent.
