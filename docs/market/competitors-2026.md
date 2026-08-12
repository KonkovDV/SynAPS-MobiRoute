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

## Per-product notes (evidence discipline)

Do **not** treat a blank marketing page as “feature absent”. Use `NOT VERIFIED` / `NOT FOUND`.

| Product | Notes | Confirmed cases |
| --- | --- | --- |
| Ecolane | Vendor CAD/AVL + paratransit suite | CLAIMED BY VENDOR (US/CA agencies on vendor site) |
| TripSpark NovusDR | Demand-response / paratransit | CLAIMED BY VENDOR |
| RouteMatch | Historical brand; lineage with TripSpark/Trapeze | SECONDARY SOURCE — do not freeze 2026 feature list from old PDFs |
| Trapeze | Large transit ITS / paratransit modules | CLAIMED BY VENDOR |
| RideCo Paratransit | On-demand / microtransit vendor with paratransit offering | CLAIMED BY VENDOR |
| TripMaster | NEMT / broker scheduling family | CLAIMED BY VENDOR |
| NEMT platforms (generic) | Eligibility, billing, broker networks dominate | NOT VERIFIED as a class |
| Open DARP / PDPTW | OR-Tools routing, academic repos, Cordeau-style codes | VERIFIED algorithms exist; not ops platforms |
| RU social transport IT | Municipal stacks, 1C-adjacent dispatch, regional portals | NOT VERIFIED without named primary source |
| Moscow personalized / social taxi ops | Мосавтосантранс + apps + phone | VERIFIED operator; planning algorithm NOT FOUND publicly |
| «По пути» | Moscow DRT / ridepooling adjacent | VERIFIED as Moscow DRT product; **not** social-taxi eligibility |

## NEMT vs social taxi

Non-emergency medical transportation (NEMT) suites emphasize **payer eligibility and billing**. Moscow social taxi emphasizes **registry + accessible fleet + mixed individual/group trips**. MobiRoute models the **routing/dispatch kernel**, not claims adjudication.

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
