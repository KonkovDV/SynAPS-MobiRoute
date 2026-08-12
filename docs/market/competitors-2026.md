# Competitors and adjacent products (2026-08-12)

**Positioning:** MobiRoute is an **open, explainable optimization kernel** for
accessible DARP planning/dispatch — **not** a full CAD/AVL + eligibility CRM
replacement.

Evidence tags: `VERIFIED` | `CLAIMED BY VENDOR` | `SECONDARY SOURCE` |
`NOT FOUND` | `NOT VERIFIED`.

## Comparison matrix (capability presence)

| Capability | Ecolane | TripSpark NovusDR | RouteMatch | Trapeze | RideCo Paratransit | TripMaster | Open DARP solvers | RU social / MoD | «По пути» |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Booking | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT FOUND | CLAIMED BY VENDOR | CLAIMED BY VENDOR |
| Eligibility | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT FOUND | CLAIMED BY VENDOR | NOT FOUND |
| Planning | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | VERIFIED (academic codes) | NOT VERIFIED | PARTIAL (DRT) |
| Dispatch | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | PARTIAL | NOT VERIFIED | CLAIMED BY VENDOR |
| Dynamic insertion | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT VERIFIED | NOT VERIFIED | CLAIMED BY VENDOR | NOT VERIFIED | VERIFIED (papers) | NOT VERIFIED | NOT VERIFIED |
| GPS/AVL | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT FOUND | NOT VERIFIED | CLAIMED BY VENDOR |
| Mobile apps | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT FOUND | CLAIMED BY VENDOR | CLAIMED BY VENDOR |
| Wheelchair constraints | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | PARTIAL | NOT VERIFIED | NOT FOUND |
| Pooling | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | VERIFIED | NOT VERIFIED | CLAIMED BY VENDOR |
| Billing | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT FOUND | NOT VERIFIED | CLAIMED BY VENDOR |
| Reporting | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | PARTIAL | NOT VERIFIED | NOT VERIFIED |
| Explainability | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | PARTIAL | NOT FOUND | NOT FOUND |
| Fairness metrics | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | PARTIAL (research) | NOT FOUND | NOT FOUND |
| On-prem | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | NOT VERIFIED | CLAIMED BY VENDOR | VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Cloud | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | CLAIMED BY VENDOR | N/A | NOT VERIFIED | CLAIMED BY VENDOR |
| RU localization | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | N/A | CLAIMED BY VENDOR | VERIFIED (Moscow) |
| Source code | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | VERIFIED (OSS/academic) | NOT FOUND | NOT FOUND |

Notes:

- **RouteMatch** historically absorbed into TripSpark/Trapeze lineage — treat
  brand pages carefully; do not assert missing features without primary source.
- **«По пути»** is adjacent demand-responsive transit, not social-taxi eligibility
  service — useful as DRT UX reference only.
- Open solvers (OR-Tools routing, academic DARP repos) provide algorithms, not
  ops platforms.

## MobiRoute differentiation (honest)

| Dimension | Commercial suites | MobiRoute target |
| --- | --- | --- |
| Scope | Full stack ops | Optimization kernel + adapters |
| Explainability | Often opaque | Mandatory reason codes + plan diffs |
| Fairness | Rarely audited openly | Explicit group metrics |
| Open source | Closed | Open prototype |
| Russia on-prem / isolated | Vendor-dependent | Designed for on-prem integration |

## Forbidden positioning

- “Drop-in replacement for Ecolane / Trapeze / Мосавтосантранс stack.”  
- “Already deployed in Moscow.”  
- “Better than vendor X” without controlled benchmark.
