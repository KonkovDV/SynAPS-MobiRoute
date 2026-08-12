# MobiRoute implementation audit — 2026-08-12

**Product:** MobiRoute  
**Repository:** [KonkovDV/SynAPS-MobiRoute](https://github.com/KonkovDV/SynAPS-MobiRoute)  
**Audit date:** 2026-08-12  

**Current status (normative):**  
экспериментальный объяснимый оптимизационный контур доступного транспорта по требованию. Проверяется только на синтетических сценариях зон Москвы.

This is **not** a production dispatch product, passenger app, CRM, CAD/AVL, billing suite, or certified personal-data system.

Claim vocabulary used below: `IMPLEMENTED` | `PARTIAL` | `EXPERIMENTAL` | `PLANNED` | `MISSING` | `NOT_VERIFIED`.

---

## 1. MobiRoute commit (audit baseline)

| Field | Value |
| --- | --- |
| HEAD (pre-0.2.0 work) | `1a95b018e64bcf5fcaeff4d9949cb565b2a533bd` |
| Message | Add pooling insertion, frozen-safe online dispatch, and beam search. |
| Package version in tree at audit | **0.1.1** (`pyproject.toml`, `src/mobiroute/__init__.py`, `CITATION.cff`) |

Subsequent 0.2.0 work in this session is a **correctness** increment on that baseline, not a rewrite.

## 2. MobiRoute version

**0.1.1** at audit start. Intended post-audit release: **0.2.0** (route graph, driver assignment, CP-SAT notary, pooling tests).

## 3. Upstream SynAPS commit

Pinned in `src/mobiroute/__init__.py`:

`SYNAPS_COMMIT = 5168fc71005653945097e1f07ada1ce9cbc02eec` (`master`)

Role: engineering-pattern reference (deterministic solve, evidence, OR-Tools). **FJSP manufacturing models are not imported into the DARP domain.**

## 4. Test count (audit baseline)

`pytest --collect-only -q` on `1a95b01`:

| File | Tests |
| --- | --- |
| `tests/test_core.py` | 13 |
| `tests/test_adversarial.py` | 14 |
| **Total** | **27** |

No dedicated files yet for CP-SAT regression, driver assignment, pooling load, CLI exit codes, or fairness multi-metric policy.

## 5. Solver paths (actual)

| Path | Module | Status at 0.1.1 | May claim OPTIMAL? |
| --- | --- | --- | --- |
| FIFO | `solvers/greedy.py` `solve_fifo` | IMPLEMENTED (sequential PU–DO, **no pooling**) | No |
| Nearest feasible | `solvers/nearest.py` | IMPLEMENTED (sequential) | No |
| Greedy insertion | `solvers/greedy.py` `solve_greedy` | PARTIAL pooling (classic PD insertion) | No |
| Beam (width 3) | `solvers/beam.py` | EXPERIMENTAL heuristic over insertions | No |
| Tiny CP-SAT | `solvers/cpsat.py` | EXPERIMENTAL **sequential** pair model (not pooling DARP) | Only if OR-Tools `OPTIMAL` **and** independent notary; **not** honest at 0.1.1 (see defects) |
| CP-SAT fallback | same; `CPSAT_FALLBACK_GREEDY` if >40 trips or >12 vehicles | IMPLEMENTED | **Must not** be OPTIMAL |
| Online insertion | `dispatch/online_insertion.py` | PARTIAL (insert into existing routes; frozen guard) | No |
| Disruption recovery | same `recover_disruption` | PARTIAL (cancel, no-show, traffic, vehicle, driver → **full greedy re-solve**) | No |
| Incremental repair | `solvers/incremental_repair.py` | PARTIAL named wrapper | No |
| ALNS | `solvers/alns.py` | PLANNED (`NotImplementedError`) | — |
| LBBD / Benders | `solvers/benders.py` | PLANNED | — |
| RHC | `solvers/rolling_horizon.py` | PLANNED | — |

## 6. CLI commands (actual)

`src/mobiroute/cli.py`:

| Command | Flags | Exit |
| --- | --- | --- |
| `generate` | `--mode`, `--seed`, `--out` | 0 on write |
| `solve` | `--problem`, `--solver {fifo,greedy,nearest,cpsat,beam}`, `--out-dir`, `--time-limit` | 0 unless `ERROR` |
| `demo` | `--out-dir`, `--seed` | 0 |

No `benchmark` subcommand (benchmark is `python benchmark/run_benchmark.py`). Invalid generate `--mode` is not validated (KeyError).

## 7. JSON Schema (actual)

| File | Role |
| --- | --- |
| `schemas/mobiroute.problem.v1.json` | Day problem |
| `schemas/mobiroute.result.v1.json` | Planning result (`additionalProperties: true`) |
| `schemas/mobiroute.diff.v1.json` | Plan diff |
| `schemas/mobiroute.trip.v1.json` | Trip |

Result schema does **not** yet require `plan_id`, `driver_assignments`, load-after-stop, or explanations.

## 8. Generator modes (actual at 0.1.1)

`adapters/synthetic_data.py` `Mode`:

`tiny`, `small`, `medium`, `large`, `wheelchair_heavy`, `medical_priority`, `pooled_rides`, `disruption`, `infeasible`, `fairness_stress`, `peak_demand`

**Missing vs brief:** named `driver_unavailable`, `vehicle_breakdown` (disruption mode exists but does not disable a driver/vehicle).

Properties: UUID5 ids, SHA-256 fingerprint, stable sort, no `hash()`. Zones are synthetic Moscow **labels**, not OSM/addresses.

## 9. Factual limitations (0.1.1)

1. Tiny CP-SAT is a **sequential** assignment: if two trips share a vehicle, dropoff of one must finish before pickup of the next. It is **not** a pooling CP model.
2. Driver is chosen by `depot_id` map (`{depot_id: last driver}`) in CP-SAT; greedy falls back to `drivers[0]` if no depot match.
3. Two vehicles at the same depot can receive the **same** driver.
4. `appointment_start` is generated for medical trips but **not** enforced in CP-SAT or greedy simulation (only `appointment_end`).
5. Route plans are pickup/dropoff lists: **no** `DEPOT_START` / `DEPOT_END`, no `passenger_load_after_stop`, no per-passenger itinerary, no `deadhead_time`.
6. Online events are not versioned as `P_k` / `P_{k+1}` with `plan_id` / `event_id`.
7. Disruption recovery **re-solves greedy** rather than repairing `P_k`.
8. Fairness omits P95 wait/ride, wheelchair on-time, coverage, override disparity.
9. Explainability of **accepted** trips (alternatives considered/rejected) is a markdown summary, not a per-trip structure.
10. Reason enum lacks `APPOINTMENT_CONFLICT`, `DRIVER_SHIFT_CONFLICT`, `VEHICLE_UNAVAILABLE`.
11. Unassigned CP-SAT trips always get `TIME_WINDOW_CONFLICT`.
12. Greedy `+30` minute depot-return slack is not in the notary.
13. Wheelchair **type** vs vehicle is not modelled (only capacity ≥ 1).
14. No detour ratio beyond `max_ride_time`.
15. ALNS / LBBD / RHC are stubs.
16. No open-data, live Moscow API, 152-FZ, or customer validation.

## 10. README vs code mismatches (0.1.1)

| README / docs claim | Code fact |
| --- | --- |
| CP-SAT tiny may be OPTIMAL if OR-Tools OPTIMAL and notary passes | Notary is called, but the **model omits** driver uniqueness, `appointment_start`, max-wait as dropoff-window, depot stops, frozen must-serve, wheelchair type. An `OPTIMAL` label can be **mathematically optimal for a weaker model**. Independent check may still pass that weaker plan. |
| Greedy is pooling insertion | IMPLEMENTED as PD insertion; **not** proven by a load≥2 test (existing test only checks a flag). |
| Driver compatibility | PARTIAL: accessibility training in simulate; depot-first assignment; fallback to first driver. |
| Online insertion / disruption | Insert is PARTIAL; disruption is full re-solve. |
| Fairness metrics | Subset of the brief’s list. |
| Generator modes in later briefs | `driver_unavailable` / `vehicle_breakdown` names absent. |

## 11. Unproven / overstated statements

Treat as **FORBIDDEN** or **NOT_VERIFIED** unless a later notary+benchmark says otherwise:

- Any Moscow operational KPI, «внедрено», «улучшило социальное такси».
- OPTIMAL for FIFO / nearest / greedy / beam / online / fallback CP-SAT.
- OPTIMAL of tiny CP-SAT as optimum of the **pooling** DARP.
- ALNS / LBBD / RHC implemented.
- Fair because Jain or one rate moved.
- 152-FZ / certification / live API compatibility.
- Synthetic zones = real Moscow trips or GPS.
- Ridepooling planner as a complete product (pooling is PARTIAL).

## 12. Priority defects (fix order)

1. **P0** CP-SAT: driver as first-class assignment; no depot-only map; shift; qualifications; `appointment_start`/`end`; frozen; unavailable intervals; reason codes; OPTIMAL ⇒ notary+completeness else `NOT_VERIFIED`; fallback never OPTIMAL.
2. **P0** Route graph: depot start/end, loads after stop, itineraries, pairing on one route, non-negative load.
3. **P0** Drivers: `DriverAssignment`; one driver ↔ one active route; no `drivers[0]` fallback; occupied-driver set.
4. **P1** Pooling: dynamic passenger/wheelchair load tests; stretcher conflict; detour ratio; honest PARTIAL if CP-SAT remains sequential.
5. **P1** Online: `plan_id` / `base_plan_id` / `event_type`; appointment-changed; lex insertion; rejected trip never dropped.
6. **P1** Fairness + per-trip explanations + extra reason codes.
7. **P2** Privacy class names, retention/access-audit docs (no 152-FZ claim).
8. **P2** Benchmark matrix columns; research/academy/claims sync.

## Capability register (0.1.1)

| Capability | Status |
| --- | --- |
| Pydantic accessible DARP | IMPLEMENTED |
| Passengers, trips, vehicles, drivers | IMPLEMENTED |
| Wheelchair / lift / ramp flags | PARTIAL (no type compatibility matrix) |
| Medical priority sort | IMPLEMENTED |
| Time windows (pickup + appointment_end) | PARTIAL (`appointment_start` unused) |
| Synthetic Moscow zones | IMPLEMENTED |
| FIFO / nearest / greedy / tiny CP-SAT / online / cancel / no-show / disruption | PARTIAL (see solvers) |
| Fairness metrics | PARTIAL |
| Manual override journal | PARTIAL (reject does not rebuild route) |
| Privacy redaction | PARTIAL |
| Reason codes | PARTIAL (too coarse) |
| Independent feasibility checker | PARTIAL (missing driver double-book, appointment_start, depot, frozen) |
| Completeness checker | IMPLEMENTED |
| JSON Schema + CLI + synthetic benchmark + adversarial tests | IMPLEMENTED (narrow) |
| ALNS / LBBD / RHC | PLANNED |
| Production dispatch / live Moscow / open-data / customer / certified PDP / proven fairness / proven user effect | MISSING |

## Allowed one-sentence claim

MobiRoute — экспериментальный объяснимый оптимизационный контур для доступных перевозок по требованию. На синтетических сценариях он проверяет совместимость пассажира, автомобиля и водителя, временные окна, вместимость, accessibility-ограничения и динамическое перепланирование. Реальные данные, интеграция и пользовательский эффект требуют отдельного пилота.
