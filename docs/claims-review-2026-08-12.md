# Claims review (Stage 15) — 2026-08-12

## Allowed claims

1. MobiRoute is an **experimental, explainable optimization contour** for accessible
   on-demand transport planning (DARP/PDPTW family).
2. On **synthetic** Moscow-**zone** scenarios it checks passenger–vehicle–driver
   compatibility, time windows, capacity, accessibility, and dynamic replan.
3. SynAPS commit `5168fc7` is an audited **engineering reference**; manufacturing
   FJSP and DARP domains are separated.
4. Prototype demonstrates reproducible planning on synthetic instances with
   independent feasibility checks and reason codes.
5. Real operational data, industrial integration, and user-effect require a pilot.

## Forbidden claims (must remain false / unsaid)

| Claim | Status |
| --- | --- |
| Improved Moscow social taxi KPIs | FORBIDDEN |
| Deployed at Мосавтосантранс | FORBIDDEN |
| GREEDY / NEAREST / online insertion is OPTIMAL | FORBIDDEN |
| Synthetic data = Moscow trips | FORBIDDEN |
| Fair because one metric moved | FORBIDDEN |
| Certified personal-data system | FORBIDDEN |
| Compatible with live Moscow APIs | FORBIDDEN (no integration test) |
| ALNS / LBBD / RHC implemented | FORBIDDEN (PLANNED stubs only) |
| Customer validation complete | FORBIDDEN |

## Evidence ladder for v0.1

| Layer | Evidence |
| --- | --- |
| algorithmic_capability | FIFO / nearest / greedy pooling / beam / CPSAT-tiny + unit tests |
| synthetic_benchmark | examples + `mobiroute demo` + pytest |
| open_data_benchmark | MISSING |
| customer_evidence | MISSING |
| production_evidence | MISSING |

## Readiness

| Layer | Status |
| --- | --- |
| SynAPS core | IMPLEMENTED |
| MobiRoute domain | EXPERIMENTAL |
| DARP solvers | PARTIAL (greedy pooling + beam + CPSAT-tiny; ALNS/LBBD/RHC PLANNED) |
| Integration | MISSING |
| Customer | MISSING |
| Production | MISSING |
