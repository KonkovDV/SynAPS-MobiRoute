# SynAPS Audit for MobiRoute (2026-08-12)

**Claim level:** evidence from local SynAPS checkout + package metadata.  
**SynAPS HEAD audited:** `5168fc71005653945097e1f07ada1ce9cbc02eec`  
**Branch:** `master`  
**Remote reference:** https://github.com/KonkovDV/SynAPS  
**Package version (pyproject):** `0.1.0`  
**Python runtime used for probe:** 3.13.7 (requires-python `>=3.12`)  
**OR-Tools:** `9.15.6755`  
**Pydantic:** `2.11.7`  
**HiGHS / highspy:** `1.13.1` (via `importlib.metadata.version("highspy")`)

Statuses: `IMPLEMENTED` | `PARTIAL` | `EXPERIMENTAL` | `PLANNED` | `MISSING` | `NOT_VERIFIED`.

## 1. What SynAPS is

SynAPS is a **deterministic-first scheduling engine** for **MO-FJSP-SDST-ARC**
(multi-objective flexible job-shop with sequence-dependent setups and auxiliary
resources). README explicitly scopes production planning — **not** dial-a-ride /
PDPTW. Upstream honesty: no live-factory validation claimed.

## 2. Portfolio solvers (registry)

From `synaps/solvers/registry.py` (names are **IMPLEMENTED** as registered configs):

| Config family | Status | Notes for MobiRoute |
| --- | --- | --- |
| GREED / GREED-K1-3 | IMPLEMENTED | ATCS dispatch — reuse as pattern for insertion heuristics |
| BEAM-3 / BEAM-5 | IMPLEMENTED | Limited beam constructive |
| CPSAT-10/30/120 | IMPLEMENTED | Exact CP-SAT; dual bounds / OPTIMAL when proven; strict determinism ADR |
| CPSAT-PARETO / EPS-* | IMPLEMENTED | Multi-objective slices |
| LBBD-5/10 (+ HD) | IMPLEMENTED | Logic-based Benders; HiGHS via lazy import |
| ALNS-300/500/1000 | IMPLEMENTED | Large-neighborhood metaheuristic |
| RHC-ALNS / RHC-CPSAT / RHC-GREEDY* / COVER variants | IMPLEMENTED | Rolling-horizon composition |
| IncrementalRepair | IMPLEMENTED | Disruption repair with freeze neighbourhood |

## 3. Component audit

| Component | Path | Status | Reuse for MobiRoute |
| --- | --- | --- | --- |
| Domain model (Order/Op/WC/SDST/Aux) | `synaps/model.py` | IMPLEMENTED | **Adapter only** — do not overload with trips |
| Objective algebra | `synaps/objective.py` | IMPLEMENTED | Pattern: coverage ≻ makespan ≻ scalar; need DARP metrics |
| FeasibilityChecker | `synaps/solvers/feasibility_checker.py` | IMPLEMENTED | Pattern for independent notary; DARP needs new checker |
| CP-SAT | `synaps/solvers/cpsat_solver.py` | IMPLEMENTED | Inspiration for tiny DARP CP; different variables |
| LBBD | `synaps/solvers/lbbd_*.py`, `_lbbd_cuts.py` | IMPLEMENTED | Later vehicle/time decomposition for day-ahead |
| ALNS | `synaps/solvers/alns_solver.py` | IMPLEMENTED | Destroy/repair pattern for large DARP |
| RHC | `synaps/solvers/rhc/` | IMPLEMENTED | Rolling horizon for continuous dispatch |
| IncrementalRepair | `synaps/solvers/incremental_repair.py` | IMPLEMENTED | Map to online insertion / disruption |
| Router / portfolio | `synaps/solvers/router.py`, `portfolio.py` | IMPLEMENTED | Reuse routing policy ideas |
| Contracts / schemas | `synaps/contracts.py`, `schema/contracts/` | IMPLEMENTED | New mobiroute schemas required (separate) |
| Benchmark harness | `synaps/benchmarks/`, `benchmark/` | IMPLEMENTED | Pattern for evidence tables |
| Control-plane BFF | `control-plane/` | IMPLEMENTED (upstream) | Out of MobiRoute v0 scope |
| Determinism ADR | `docs/adr/0001-strict-determinism-single-thread.md` | IMPLEMENTED | **Must keep** |
| ML advisory | `synaps/ml_advisory.py` | EXPERIMENTAL | Advisory only — never assignment authority |
| Proof logging VeriPB | ADR 0002 | PLANNED / EXPERIMENTAL | Do not claim in MobiRoute v0 |
| Travel / road network | — | MISSING | Need travel-time adapter |
| Pickup–delivery pairing | — | MISSING | Core DARP constraint |
| Wheelchair / lift capacity | — | MISSING | Accessibility layer |
| Fairness metrics | — | MISSING | Social service layer |
| Privacy / PII controls | — | MISSING | Required before any real data |

## 4. Constraints SynAPS already enforces (machine scheduling)

IMPLEMENTED (hard via FeasibilityChecker / solvers): release dates, precedence
chains, machine/lane capacity, SDST gaps, horizon, aux pools, completeness,
UNKNOWN entity refs.

**Not present:** pairing pickup/dropoff, max ride time, appointment windows,
wheelchair seats, driver accessibility qualifications, equity objectives.

## 5. What to reuse unchanged

- Deterministic seeds / fingerprint discipline / single-thread CP-SAT.
- Portfolio idea: tiny→CP-SAT, large→ALNS/RHC, disruption→repair.
- Independent feasibility gate before claiming `FEASIBLE`/`OPTIMAL`.
- Lexicographic / multi-level objectives.
- Pin SynAPS by **commit SHA** in MobiRoute (`SYNAPS_COMMIT`).

## 6. What requires a new transport layer

Entire DARP/PDPTW domain: passengers, vehicles, drivers, stops, routes,
pooling, online insertion, reason codes, fairness, privacy redaction.
SynAPS stays an **optional engineering reference / future compile backend**;
MobiRoute must not pollute FJSP models.

## 7. Forbidden claims (inherited honesty)

- Do not call GREED/ALNS/RHC “optimal”.
- Do not claim SynAPS already solves social taxi.
- Do not claim industrial Moscow deployment.
- Do not claim personal-data certification without evidence.
- Do not claim live-operator validation without a pilot protocol.

## 8. Adapter strategy (chosen)

Separate repo `SynAPS-MobiRoute` with:

1. Native DARP models + own feasibility notary (**IMPLEMENTED** in v0.1).
2. `synaps_adapter.py` documents pin; FJSP compile **NOT_ENABLED**.
3. Pin: `SYNAPS_COMMIT=5168fc71005653945097e1f07ada1ce9cbc02eec`.

## 9. Readiness snapshot

| Layer | Status |
| --- | --- |
| SynAPS core readiness | IMPLEMENTED (scheduling kernel) |
| MobiRoute domain readiness | EXPERIMENTAL (v0.1 prototype) |
| DARP solver readiness | PARTIAL (FIFO/greedy/CPSAT-tiny; ALNS/LBBD/RHC PLANNED) |
| Integration readiness | MISSING |
| Customer readiness | MISSING |
| Production readiness | MISSING |
