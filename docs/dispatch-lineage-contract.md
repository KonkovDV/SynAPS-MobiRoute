# Dispatch result lineage

Status: IMPLEMENTED for online insertion and disruption recovery. Synthetic laboratory contract, not operational authorization or production certification.

- Acceptance, rejection and frozen rollback all use the full-plan notary against the updated problem. A baseline verification flag is not evidence for a new result.
- Returned routes are detached from the supplied baseline. Metrics and explanations are regenerated, including newly rejected requests and unchanged routes.
- Input fingerprints are recomputed with the shared planning-input fingerprint adapter. The execution config includes online freeze protection; derived `verified_feasible` and `proven_optimal` flags are excluded from its hash.
- Identity has one signer. Solvers leave `input_hash` unsigned and only
  `finalize_result` publishes `fingerprint_problem`. A solver that re-stamps an
  already published plan (RHC, ALNS) republishes `plan_id` through the shared
  `plan_identity` helper, so the identity fingerprints the configuration that is
  actually published instead of the greedy pass that built the routes.
- Refusal evidence is search-side and per vehicle. The seated driver of a
  committed route is re-checked against the new request, and the rejection
  detail names the refusing vehicles (deduplicated, truncated). It records where
  insertion failed on this baseline, not a proof that no plan exists. Codes and
  labels are defined in `docs/rejection-evidence-contract.md`.
- Event IDs use canonical structured payloads, not request IDs alone. Appointment values and all combined disruption operations contribute. Combined operations are labelled `DISRUPTION`.
- Child IDs use the `mobiroute:plan:v2` namespace and cover lineage, inputs, execution config, status, served/rejected records, route evidence and running package/SynAPS versions. Exact JSON replay on the same implementation is deterministic. IDs intentionally differ from the previous scheme.
- Imported baselines without a plan ID receive a content-derived parent reference. IDs are identifiers, not signatures, permissions or reusable native-cache keys.

An invalid baseline is not silently repaired or certified. Where a result can be constructed, failed verification yields `NOT_VERIFIED`; malformed inputs may raise instead. No driver command or passenger refusal is authorized by this contract.

This does not establish global DARP optimality, complete mandatory-return chains, legal pooling permission, billing-time semantics or passenger outcomes. Temporal churn is defined in `docs/plan-diff-contract.md`.

Regression: `python -m unittest tests.test_online_result_lineage tests.test_identity_ownership` with the real native extension built. Includes accepted/rejected replay, forged verification, changed travel inputs, detached results, payload collisions, fault-injected frozen rollback, one-signer `input_hash` and per-solver replay determinism.
