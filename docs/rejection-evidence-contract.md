# Rejection evidence and benchmark gates

Status: IMPLEMENTED for `diagnose_rejection`; other reason-code producers retain their own scope.

The diagnostic consumes validated inputs. Concrete codes describe necessary-condition evidence: no compatible fleet/driver, unavailable compatible shifts, or a lower bound on the quota debit exceeding the remaining entitlement. That bound is the shortest path plus any VIA dwell, charged in the basis the active operator policy declares, so under `BILLABLE_SERVICE` it also carries the enforced curb wait and the alighting dwell. A specific vehicle cause is reported only when shared by all failing vehicles; heterogeneous causes use `NO_COMPATIBLE_VEHICLE`. Under `RIDE_DURATION`, zero quota alone does not prove an excess when the modeled ride is zero; under `BILLABLE_SERVICE` the service dwell the plan must hold is already an excess.

Neither a successful nor a failed greedy singleton simulation establishes why a global assignment was not found. It may examine only one driver or departure schedule. Appointment fields alone do not prove an appointment conflict. Unresolved cases return `MANUAL_REVIEW_REQUIRED`, not a fabricated time-window conflict. This code does not prove feasibility either, and does not authorize an automatic passenger refusal.

The existing reason-code vocabulary is preserved. Consumers must accept the conservative fallback and must not interpret any generic diagnostic as a complete DARP infeasibility certificate or legal eligibility decision.

Greedy leftover rebuild/peel and unresolved insertion use `diagnose_rejection`
for necessary-condition evidence (quota, fleet, driver). Wait-return is only the
label when that diagnostic is unresolved. Frozen-protect rollback and frozen
clock blocks that leave no feasible insertion use `MANUAL_REVIEW_REQUIRED` and
keep the detail that insertion would change frozen trips. Search producers must
not invent a time-window proof for an unresolved assignment. Leftover/peel
unserve rewrites per-trip explanations so a published `accepted=True` record
cannot outlive the served set.

## Cordeau a2-16

The native smoke gate now requires independent verification, nonzero service, complete/unique/disjoint served-rejected accounting and nonempty rejection reasons. The empty unaccounted result remains `NOT_VERIFIED`. Data hash and open-data provenance gates remain in place.

These are correctness checks, not a requirement to serve all 16 requests, a literature-BKS match, a solver quality comparison or a performance result. Rounded travel and additional MobiRoute constraints differ from the original benchmark. Comparative quality requires a separately specified common model, objectives and evaluation protocol.
