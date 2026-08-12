# Red Team: algebra, code, pipeline (2026-08-12)

**Claim level:** `synthetic_benchmark`. Not MAST GPS. Not a Moscow KPI. Greedy never `OPTIMAL`.

Method: independent notary vs every solver path, then adversarial combinations a dispatcher would not enumerate (sort-order starvation, empty-vehicle idle, stretcher cabin, vehicle overtime with a longer driver shift, frozen explained-reject, disruption churn).

Pytest after the residual close: see `tests/test_residuals.py`, `tests/test_alns.py`,
`tests/test_redteam_combat.py`. Package `mypy` on `src/mobiroute`.

## P0 / P1 closed in this pass

| ID | Hole | Why a human misses it | Fix |
| --- | --- | --- | --- |
| RT-01 | Notary accepted stretcher + ambulatory on the same load | Simulator forbids it; notary never had `STRETCHER_EXCLUSIVE` | Notary + tests |
| RT-02 | Notary ignored `vehicle.shift_end` when the driver shift was longer | Driver bound hid vehicle overtime | `VEHICLE_SHIFT_END` |
| RT-03 | Empty vehicle leaving the depot at `shift_start` counted curb idle against `max_wait` | Ops delayed pull-out was a workaround | Idle with load 0 is free (Python SoA + Rust + pydantic + notary reconstruct) |
| RT-04 | `same_vehicle_as` return sorted before outbound → `SAME_VEHICLE_UNAVAILABLE` | UUID / medical rank, not topology | `trip_sort_key` / `fifo_sort_key`: unpaired then paired |
| RT-05 | FIFO wait-return ignored `insert_immediately_after` (sequential append) | FIFO path skipped the insertion kernel | Paired trips use `try_insert_trip` even when `pooling=False` |
| RT-06 | FIFO subscription `NOT_VERIFIED` because one frozen trip was rejected but notary demanded must-serve | Frozen ≠ unaccounted | Notary `FROZEN_UNSERVED` only if missing from served **and** rejected |
| RT-07 | `recover_disruption` full re-greedy could move unrelated trips | Catalog said frozen immutable | Seed remaining routes from the baseline (except broken vehicle/driver; except traffic/appointment retime) |
| RT-08 | Beam dropped a failed final simulate but kept `served_requests` | `SERVED_BUT_UNASSIGNED` | Un-serve like greedy |
| RT-09 | Nearest final-fail left `reason_codes[tid]=ACCEPTED` | Completeness vs honesty | Overwrite reason |
| RT-10 | Notary mutated `route.ride_times` | Side effect during check | Read-only |
| RT-11 | Unknown `trip_id` / unknown zone crashed the notary | `trips[tid]` / `zones.index` | `UNKNOWN_TRIP`, `BLOCKED_LOCATION` |
| RT-12 | Duplicate `RoutePlan` for one vehicle | No unique-vehicle check | `DUPLICATE_VEHICLE_ROUTE` |
| RT-13 | `diagnose_rejection` labelled fleet-busy appointment trips `APPOINTMENT_CONFLICT` | Empty-vehicle insert actually works | If empty insert works → `TIME_WINDOW_CONFLICT` |
| RT-14 | Kernel `_compat` ignored `service_area`; native ABI had no area | Python filter only | Area on `VehicleKernel` + Rust `veh[11:]` |
| RT-15 | Unavailable intervals checked only at pickup boarding | Dropoff/travel during breakdown | Pickup **and** dropoff service overlap |
| RT-16 | CP-SAT omitted detour cap | Weaker model than greedy | `ride ≤ int(τ·detour)+1` |
| RT-17 | Explanation text said “min wait then duration” | Lex key is `(duration, wait, vid)` | Text aligned |
| RT-18 | Unified `max_wait` (passenger delay + onboard hold) | Same semantics in greedy, SoA, Rust, CP-SAT, notary | Passenger-late cap; empty idle still free |
| RT-19 | `appointment_start` cabin hold | Tests required dropoff ≥ start | Early lobby dropoff; `appointment_end` still hard |
| RT-20 | VIA + hour quota + FW travel + ALNS heuristic | Left as residuals | Ops `ops_via` / `ops_quota`; adaptive ALNS never OPTIMAL |
| RT-21 | Pickup dwell 3 min vs FTA/DREDF 5 min curb wait | Boarding field copied as dwell | \(\max(\mathrm{board},5)\) in greedy/SoA/Rust/CP-SAT/notary |
| RT-22 | Early-dropoff snap held other onboard passengers | Lobby wait looked like empty idle | Snap only if this trip is the last onboard; else infeasible |
| RT-23 | VIA detour used \(\tau(p,v)+\tau(v,d)\) without pharmacy dwell | Dwell looked like a geographic k-detour | Itinerary minutes include VIA service; integer `detour_limit` lockstep |
| RT-24 | `unavailable_intervals` checked only at boarding/alighting | Vehicle could travel or wait through a breakdown | Occupancy `[t_begin, leave)` + depot wait-out of shop windows |
| RT-25 | Online insert treated frozen as “same vehicle”, not same clock | Pooling retimed subscription pickups | Reject or append-only if frozen PU/DO times would move |
| RT-26 | Online insert ignored remaining hour quota | Second same-day trip reused the raw cap | Subtract baseline ride minutes; `QUOTA_EXCEEDED` |
| RT-27 | Notary allowed unexplained idle at VIA/dropoff | Solver never waits there without a window | `UNEXPLAINED_WAIT`; depot unavail wait aligned with simulator |
| RT-28 | Seeded disruption left one `QUOTA:` notary on `stress_200` | Cancel left wait-return orphans; seed kept over-cap clocks | Cancel cascade; seed peel; final quota lockstep |
| RT-29 | Online insert stashed the forked engine under the baseline `plan_id` | Two inserts from the same day plan reused a mutated fleet (`ASSIGNED_NOT_SERVED`) | Stash key is `event_id`; online gets a new `plan_id`; fleet re-synced before stash |
| RT-30 | `recover_disruption(..., emergency_trip=)` skipped the replan and inserted into the stale baseline | Combined cancel+emergency left cancelled trips on routes | Structural disruptions replan first, then online insert |
| RT-31 | `quota_caps` scanned every passenger for every request | Online insert paid ~0.3 s × 8; notary looked slow | Index remaining minutes by passenger id |
| RT-32 | Incremental `check_plan(only_vehicles=)` could bless `verified_feasible` without walking other routes | Speed path after native eval | Finalize still enriches the changed vehicle only; `check_plan` skips `check_route` on untouched vehicles but still walks assignments, drivers, quota, completeness. Combat test compares `verified_feasible` to a full notary |
| RT-33 | Full resim from depot on every `(i, j)` / VIA triple | Speed path paid O(m) prefix twice | Prefix cursor + incremental walk; lockstep vs Python SoA (`test_native_prefix_insert_matches_python_on_loaded_route`) |
| RT-34 | `fork()` cloned the 3200-trip table on every online insert | Copy-on-write was missing | `Arc` travel/table/detour; `append_trip` uses `make_mut` |
| RT-35 | +8 min traffic `eval_route` miss wiped the whole vehicle | Uniform delay usually breaks the tail, not the prefix | Peel last dropoff + wait-return children; reinsert dropped trips onto the same vehicle before global greedy |
| RT-36 | Two-phase duration prune (empties, then loaded with `current_dur > D`) | Duration is monotonic, but quota-ok \(D\) is known only after scoring | Tried; extra native round-trips lost ~1 s vs one 200-way Rayon `score_stored`. Not in the hot path |

## Measured after the fix (seed 42, this machine)

| Script | Greedy | FIFO | Note |
| --- | --- | --- | --- |
| `ops_wait_return` | 3/3 `HEURISTIC_FEASIBLE` | **3/3** (was 2/3 `SAME_VEHICLE_UNAVAILABLE`) | Topology + paired insert |
| `ops_subscription_vs_nextday` | 6/6 | **2/6 `PARTIAL` verified** (was `NOT_VERIFIED`) | Sequential cannot pool; frozen reject is explained |
| `ops_wav_shortage` | 2/5 | — | Rejects now `TIME_WINDOW_CONFLICT` (WAV exists; window/fleet) |
| `ops_clinic_peak` | 9/10 | — | One reject `TIME_WINDOW_CONFLICT` |
| Empty vehicle, `earliest=300`, `max_wait=20` | **served** | — | Was false `TIME_WINDOW_CONFLICT` |
| Clinic breakdown of a used vehicle | moved = trips on that vehicle | — | Unrelated assignment kept |

Ops greedy served counts for the original sixteen scripts are unchanged vs the earlier ops table (empty-idle and passenger-late cap did not change delayed-pull-out instances; ops windows are 30 min with `max_wait=60`). New scripts: `ops_via` 1/1, `ops_quota` 1/2 `QUOTA_EXCEEDED`. Greedy never `OPTIMAL`.

## Residual (honest, not closed)

| Residual | Why it stays |
| --- | --- |
| Live Moscow roads / GPS | Zone matrix + Floyd–Warshall only |
| LBBD / RHC | Still `NotImplementedError` |
| Native and Python SoA must stay in lockstep | Rebuild `mobiroute_native` after kernel ABI changes; CI pytest builds the wheel |
| Gschwind–Drexl amortized O(1) insertion test | VIA, stretcher, unavail occupancy, and appointment lobby snap break the auxiliary-data contract; prefix+incremental walk is the honest analogue |
| 2–3 s `stress_200` pipeline | Day-ahead is ~4 s of sequential lex inserts (3000×200). Traffic +8 keeps a short feasible tail; leftovers still re-greedy. Measured **8.1 s**, not 2–3 s. See `docs/native-acceleration.md` |
| GPU / CUDA scoring of this insert kernel | 13×13 zone matrix; hot path is sequential and branchy. cuOpt-style GPU nets help independent neighborhood moves, not this constructive lex insert |
| Jain index on tiny served sets | `fair_by_single_metric` remains false |
| Manual override does not retime the residual route | Status `MANUAL_REVIEW_REQUIRED`, notary false — intentional HITL |
| Annual 80h / fare / registry | Billing CRM; kernel only sees remaining minutes |

## Pipeline (from / to)

`generate_day` / `generate_ops_day` → greedy / FIFO / nearest / beam / tiny CP-SAT → `finalize_result` (`enrich` + completeness + `check_plan` notary) → online insert / `recover_disruption` (seeded) → reports (`claim_level=synthetic_benchmark`).

Hard constraint catalog: `DEPOT_RETURN_BY_SHIFT_END`, `SERVICE_AREA`, `STRETCHER_EXCLUSIVE` (replacing the lie `DEPOT_RETURN_OPTIONAL` for v0.2).
