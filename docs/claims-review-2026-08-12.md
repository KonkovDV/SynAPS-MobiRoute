# Claims review — 2026-08-12 (v0.2.0)

**Status sentence:** экспериментальный объяснимый оптимизационный контур доступного транспорта по требованию. Проверяется только на синтетических сценариях зон Москвы.

## Allowed claims

1. MobiRoute is an **experimental, explainable optimization kernel** for accessible
   on-demand transport (DARP / PDPTW family), not a passenger app, CRM, CAD/AVL, or billing suite.
2. On **synthetic** Moscow-**zone** scenarios it checks passenger–vehicle–driver compatibility,
   time windows (`appointment_end` latest dropoff; early lobby dropoff allowed), capacity, wheelchair type, pairing,
   depot start/end, and dynamic replan with reason codes.
3. Tiny CP-SAT is a **sequential** (non-pooling) model. `OPTIMAL` is allowed only when
   OR-Tools status is OPTIMAL **and** the independent notary + completeness check pass;
   otherwise `NOT_VERIFIED`. Fallback is never `OPTIMAL`.
4. Greedy insertion implements **PARTIAL pooling** (dynamic passenger/wheelchair load on a
   stop sequence). Insertion scoring is Rust `mobiroute_native` (required). Python SoA is
   an oracle only. It is not a proven shareability-network optimum.
5. SynAPS commit `5168fc7` is an audited **engineering reference**; FJSP and DARP are separated.
6. Real operational data, industrial integration, and user-effect require a separate pilot.

## Forbidden claims

| Claim | Status |
| --- | --- |
| Improved Moscow social taxi KPIs / «внедрено» / «улучшило социальное такси» | FORBIDDEN |
| Deployed at Мосавтосантранс | FORBIDDEN |
| GREEDY / NEAREST / FIFO / BEAM / online / disruption is OPTIMAL | FORBIDDEN |
| CP-SAT fallback is OPTIMAL | FORBIDDEN |
| Tiny CP-SAT is optimal for the **pooling** DARP | FORBIDDEN |
| Synthetic data = real Moscow trips or GPS | FORBIDDEN |
| Fair because one metric moved | FORBIDDEN |
| Certified 152-FZ / personal-data system | FORBIDDEN |
| Compatible with live Moscow APIs | FORBIDDEN (no integration test) |
| ALNS is OPTIMAL / LBBD / RHC implemented | FORBIDDEN (ALNS is a heuristic; LBBD/RHC PLANNED) |
| Unmeasured native ×N speedup | FORBIDDEN |
| Customer validation / production dispatch | FORBIDDEN |
| Mix with GridPlan, AeroBIM, SynAPS Energy in one Academy application | FORBIDDEN |

## Evidence ladder (v0.2.0)

| Layer | Evidence | Status |
| --- | --- | --- |
| algorithmic_capability | FIFO, nearest, greedy pooling insertion (Rust native scoring), beam, CPSAT-tiny sequential, ALNS destroy/repair, online insert, disruption | PARTIAL |
| synthetic_benchmark | examples + pytest (126 tests) + `mobiroute demo` + `mobiroute ops-benchmark` | IMPLEMENTED |
| open_data_benchmark | — | MISSING |
| customer_evidence | — | MISSING |
| production_evidence | — | MISSING |

## Solver honesty

| Solver | Status | OPTIMAL? |
| --- | --- | --- |
| FIFO | IMPLEMENTED (no pooling) | No |
| Nearest | IMPLEMENTED (no pooling) | No |
| Greedy insertion | PARTIAL pooling; Rust `mobiroute_native` REQUIRED | No (`HEURISTIC_FEASIBLE` / `PARTIAL`) |
| Beam | EXPERIMENTAL | No |
| CPSAT_TINY | EXPERIMENTAL sequential | Only OR-Tools OPTIMAL ∧ notary |
| CPSAT_FALLBACK_GREEDY | IMPLEMENTED | Never |
| Online insertion | PARTIAL (`P_k` versioning) | No |
| Disruption recovery | PARTIAL (seeded greedy; unrelated routes kept) | No |
| ALNS | IMPLEMENTED adaptive LNS (Shaw/worst/route/random + SA) | Never |
| LBBD / RHC | PLANNED | — |
