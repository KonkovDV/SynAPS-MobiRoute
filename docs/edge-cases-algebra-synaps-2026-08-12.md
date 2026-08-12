# Edge cases, algebra, and SynAPS mapping (2026-08-12)

**Claim level:** `synthetic_benchmark` + code inspection of MobiRoute and pinned SynAPS `5168fc7`.  
**Not** real MAST GPS. **Not** Moscow KPI. **Not** “SynAPS already solves social taxi”.

Companion write-up of operator rules: [`ops-cases-and-benchmark-2026-08-12.md`](ops-cases-and-benchmark-2026-08-12.md).

## Real cases (what actually breaks a social-taxi day)

Sources: mgovos.ru how-to (2026-08-12); taxi.santrans.ru; public review of a Zvenigorod→Moscow missed pickup; RUSSPASS 2025-07-31 (phones in that article are **Mosgortrans-era / stale** after 23 Apr 2026); T-J 2026-01-28 (fleet scarcity; still cites Mosgortrans); 49 CFR 37.125 / 37.131 / 37.133; DREDF no-show guide; Metro St. Louis no-show policy effective 2026-05-01.

| # | What happens | Whose failure | Algebra (hard) | Code | Kernel? |
| --- | --- | --- | --- | --- | --- |
| 1 | Not in registry / wrong purpose | Intake | — | label only | No |
| 2 | Sedan booked, passenger cannot transfer | Compatibility | lift/ramp/type | `accessibility_compatible` | Yes |
| 3 | Scooter / power chair vs type mask | Compatibility | \(w_r \in W_v\) | default mask MANUAL/POWER; `ops_scooter` → `NO_COMPATIBLE_VEHICLE` | Yes |
| 4 | Two companions | Capacity | seats \(= 1 + c_r \le Q_v\) | `ops_companions` | Yes |
| 5 | Guide dog | — | does **not** consume a companion seat | not a field | Label only |
| 6 | Wait + return ≤ 60 min | Pairing + wait | same \(v\), dest wait cap | `same_vehicle_as` | Yes |
| 7 | Intermediate stop (clinic then pharmacy) | Sequence | VIA between PU and DO | `StopType.VIA`; `ops_via` 1/1 | Yes |
| 8 | Change destination after the trip started | Dynamics | freeze dest once `IN_PROGRESS` | status exists; no dest-change API | No |
| 9 | Stretcher / lying passenger | Exclusive load | if stretcher then load \(= 1\) | greedy + SoA `FLAG_STRETCHER`; `ops_stretcher` 1/2 | Yes |
| 10 | Untrained driver vs lift | Driver | assist ⇒ training | `ops_untrained_driver` → `NO_DRIVER` | Yes |
| 11 | Vehicle promised 11:30, never came (oblast) | Agency missed trip | not a passenger no-show | `VEHICLE_BREAKDOWN` recovery; `ops_agency_missed` | Partial (no callback/order-id) |
| 12 | Passenger no-show / late cancel / cancel-at-door | Dynamics | remove \(r\), free capacity | `NO_SHOW` / `CANCELLATION`; sanctions are CRM | Partial |
| 13 | Pattern of no-shows → suspend | Policy | 49 CFR 37.125 | not modelled | No |
| 14 | Medical vs dacha when one WAV | Lex objective | medical ≻ flexible | `trip_sort_key`; `ops_medical_vs_dacha` 1/2 | Yes |
| 15 | Recurring 20–28 previous month | Intake calendar | frozen \(r\) | `frozen=True`; month window is CRM | Partial |
| 16 | Hour quotas 80 / unlimited / 20 | Billing vs remaining minutes | door-to-door ride vs `quota_minutes_remaining` | remaining minutes in-kernel; annual 80h is CRM | Partial |
| 17 | Oblast 2× fare / 250 km sanatorium | Cost / horizon | travel \(\tau\) + shift | fare not kernel; `service_area` now hard | Partial |
| 18 | District-bound vehicle | Coverage | pickup, dropoff \(\in A_v\) | `accessibility_compatible` (fixed 2026-08-12) | Yes |
| 19 | Close 19:00, cannot return to depot | Shift | \(t_{\mathrm{end}} + \tau_{\mathrm{depot}} \le T_v\) | `ops_shift_close` 0/1 | Yes |
| 20 | Group bus / two wheelchairs | Capacity path | \(q(s), w(s)\) along sequence | `ops_group` pooling 6/6 vs FIFO 1/6 | Yes |
| 21 | Child restraint asked at booking | Equipment | — | not a field | No |
| 22 | Opaque refusal, no order number | Explain | \(\rho_r \ne \emptyset\) | reason codes; CRM ticket id out of scope | Partial |

## Algebra (deterministic core)

Sets: requests \(R\), vehicles \(V\), drivers \(D\), zones \(Z\), travel \(\tau(i,j)\).

Decisions: \(x_{rv}\in\{0,1\}\), sequence of stops, arrivals \(a_s\), reject \(y_r=1-\sum_v x_{rv}\) with reason \(\rho_r\).

Hard (normative list in `domain/constraints.py`): pairing, precedence, pickup/appointment windows, max ride/wait, passenger and wheelchair load along the path, type/lift/ramp, companion seats, **service area**, driver qualification and shift, no double-book, travel + dwell, depot start/return, no invalid pooling (including stretcher exclusive), cancelled excluded, frozen immutable, explainable reject, reproducible hashes.

Lexicographic (mirrors SynAPS coverage ≻ makespan ≻ scalar, with DARP metrics):

1. Safety / accessibility / medical feasibility  
2. Maximize served (medical on-time first)  
3. Wait, ride, lateness  
4. Fairness, deadhead, cost — never one index  

Tiny CP-SAT is a **sequential** pair model. Greedy insertion is the pooling heuristic. Neither may claim `OPTIMAL` unless OR-Tools OPTIMAL **and** the independent notary (`check_plan`) pass. Greedy never does.

## SynAPS → MobiRoute (pin `5168fc71005653945097e1f07ada1ce9cbc02eec`)

SynAPS is **MO-FJSP-SDST-ARC** (jobs, machines, sequence-dependent setup). It does not contain pickup–delivery pairing. Adapter `fjssp_compile = NOT_ENABLED`.

| SynAPS | What it actually is | MobiRoute analog | Status |
| --- | --- | --- | --- |
| `FeasibilityChecker` independent of solvers | Lane/SDST proof + greedy fallback | `validation/feasibility.py` notary | IMPLEMENTED (DARP rules) |
| `objective_sort_key`: coverage ≻ makespan ≻ scalar | P0-5/P0-6 SSOT | served ≻ wait/ride ≻ fairness/cost | Pattern transferred |
| Greedy ATCS dispatch | Constructive | Greedy PD insertion + SoA kernel | IMPLEMENTED |
| CP-SAT `OPTIMAL` only if proven | ADR determinism | Tiny sequential CP-SAT ∧ notary | EXPERIMENTAL |
| IncrementalRepair freeze neighbourhood | Disruption | `recover_disruption` + `frozen` | PARTIAL (full re-greedy) |
| ALNS | Adaptive LNS: Shaw / worst / route / random, SA | `solvers/alns.py` (SynAPS pattern, DARP operators) | IMPLEMENTED (never OPTIMAL) |
| LBBD / RHC | Implemented upstream | Stubs `NotImplementedError` | PLANNED |
| SDST changeover | Setup between ops on a lane | Boarding dwell + deadhead \(\tau\) | Analog only |
| Aux resources | Tools/fixtures | Lift, WAV seat, trained driver | Analog only |
| Compile DARP into FJSP | — | Forbidden | NOT_ENABLED |

## Measured edge scripts (greedy, seed 42, 2026-08-12)

| Script | Served | Reason | Note |
| --- | --- | --- | --- |
| `ops_stretcher` | 1/2 | TIME_WINDOW_CONFLICT on the ambulatory | Exclusive cabin; not OPTIMAL |
| `ops_scooter` | 0/1 | NO_COMPATIBLE_VEHICLE | Default WAV mask excludes scooter |
| `ops_medical_vs_dacha` | 1/2 | dacha rejected | One WAV seat; medical kept |
| `ops_service_area` | 0/1 | NO_COMPATIBLE_VEHICLE | Pickup/dropoff outside \(A_v\) |
| `ops_untrained_driver` | 0/1 | NO_DRIVER | Assist without training |
| `ops_agency_missed` | 1/1 then 0/1 after breakdown | VEHICLE_UNAVAILABLE | Agency miss ≠ passenger no-show |

Full 18-script suite: `mobiroute ops-benchmark --seed 42`. Pytest: **122**. Red Team of notary/solvers/pipeline: [`redteam-algebra-2026-08-12.md`](redteam-algebra-2026-08-12.md).

## Still missing (honest)

- Destination change after boarding.
- Guide dog as a non-seat passenger.
- Child restraint inventory.
- Annual 80h / fare ledger (CRM). Remaining minutes are in-kernel.
- Order-id / dispatcher callback (the Zvenigorod review).
- Live 5-minute no-show timer (planning dwell is \(\max(\mathrm{board},5)\); CRM sanctions are out of kernel).
- LBBD / RHC.
- Live Moscow roads (zones are labels; travel is Floyd–Warshall on the matrix).
