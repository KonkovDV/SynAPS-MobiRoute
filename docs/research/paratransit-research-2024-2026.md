# Paratransit / DARP research review (2024–2026)

**Research date:** 2026-08-12.  
**Method:** primary DOIs / LIPIcs / INFORMS / IJCAI / Springer where reachable.  
Statuses for transfer: transferable pattern vs data-locked.

## Paper cards

### 1. Paratransit Optimization with Constraint Programming (Savannah, GA)

| Field | Content |
| --- | --- |
| Citation | Jagrowski, Dalmeijer, Ye, Van Hentenryck. CP 2026. LIPIcs Vol. 379, 31:1–31:16 |
| DOI | [10.4230/LIPIcs.CP.2026.31](https://doi.org/10.4230/LIPIcs.CP.2026.31) |
| Problem | Joint **route planning and shift scheduling** for paratransit |
| Data | Savannah / Chatham Area Transit operator case |
| Constraints | Time windows, capacity, pairing (DARP family); shift start flexibility |
| Algorithm | Constraint Programming; compared with AI-accelerated column generation |
| Instance size | Operator day-ahead case (not a public Moscow set) |
| Metrics | Requests served vs current practice; ~+5% served when shifts need not start on the hour |
| Deployment | Case study — **not** Moscow |
| Transfer | CP modelling of routes+shifts → MobiRoute CPSAT-tiny / medium |
| Do not transfer | Savannah service-rate gains as Moscow effect |
| Method risk | Operator-specific rules; CP scaling limits |

### 2. Activated Benders Decomposition for Day-Ahead Paratransit

| Field | Content |
| --- | --- |
| Citation | Cummings, Jacquillat, Vaze. *INFORMS Journal on Computing* 38(1):126–149 (2026 issue; online 6 Mar 2025) |
| DOI | [10.1287/ijoc.2023.0311](https://doi.org/10.1287/ijoc.2023.0311) |
| Code | [github.com/INFORMSJoC/2023.0311](https://github.com/INFORMSJoC/2023.0311) — verify LICENSE before reuse |
| Problem | SIPPAR: stochastic itinerary planning with advance requests; cancellations and driver no-shows |
| Data | Major paratransit platform (authors); not open Moscow data |
| Constraints | Shareability network; two-stage disruption recourse |
| Algorithm | Activated Benders; restricted subproblems; locally Pareto-optimal cuts |
| Instance size | Authors report scaling to real-world platform instances |
| Metrics | Cost, robustness/slack, computational time vs benchmarks |
| Deployment | Industry data study — not a public replica |
| Transfer | Day-ahead robustness + Benders pattern for medium instances (**PLANNED** in MobiRoute) |
| Do not transfer | Without travel-time and disruption distributions |
| Method risk | Stochastic second stage needs scenarios; cut validity if adapted poorly |

### 3. Efficient insertion and reoptimization (dynamic DARP)

| Field | Content |
| --- | --- |
| Citation | Pfeiffer, Schulz. *OR Spectrum*, published 2026-02-02 |
| DOI | [10.1007/s00291-026-00847-0](https://doi.org/10.1007/s00291-026-00847-0) |
| Problem | Stochastic-dynamic **customer-oriented** ridepooling DARP |
| Data | Computational study, **2700 instances** (synthetic / study-generated, not Moscow) |
| Constraints | Wait/travel attractiveness; delivery time windows; reinsertion of accepted customers |
| Algorithm | Fast insertion + reoptimization; precomputation, clustering, sampling, parallelization |
| Metrics | Acceptance probability vs detour; current vs future customer “potential”; fleet size for a target service level |
| Deployment | Computational — not an operational Moscow pilot |
| Transfer | Online insertion + min-churn reopt → MobiRoute continuous dispatch |
| Do not transfer | Commercial ridepooling acceptance curves as social-taxi policy |
| Method risk | Customer-oriented objectives ≠ medical/accessibility lexicographic hierarchy |

### 4. Deploying Mobility-On-Demand for All (paratransit)

| Field | Content |
| --- | --- |
| Citation | Pavia et al. IJCAI 2024, pp. 7430–7437 |
| DOI | [10.24963/ijcai.2024/822](https://doi.org/10.24963/ijcai.2024/822) |
| Problem | Paratransit VRP with wheelchair / accessibility nuances; public-agency collaboration (southern USA) |
| Data | Real agency data + **pilot deployment in the city** (CARTA line of work) |
| Algorithm | Open-source routing adapted to paratransit constraints |
| Metrics | Authors claim outperformance vs agency incumbent methods (agency-specific) |
| Deployment | Real pilot — **not** Moscow |
| Transfer | Equity + MoD design; wheelchair-aware VRP framing |
| Do not transfer | Pilot KPI deltas as Moscow effect |
| Method risk | US ADA / agency rules ≠ Russian social-taxi law |

### 5. SmartTransit.AI (dynamic paratransit + microtransit)

| Field | Content |
| --- | --- |
| Citation | Pavia et al. IJCAI 2024 Demo Track, pp. 8767–8770 |
| DOI | [10.24963/ijcai.2024/1028](https://doi.org/10.24963/ijcai.2024/1028) |
| Problem | Modular cloud software: dispatcher dashboard + driver/user apps + pluggable routing |
| Data | Demonstration in Chattanooga, TN; related Clifton Hills microtransit pilot (Jun–Jul 2024, vendor site) |
| Algorithm | Agency-configurable ridepooling solvers behind REST API |
| Deployment | Demo / pilot system — full ops stack, not a kernel-only paper |
| Transfer | Architecture of dynamic paratransit + microtransit **around** a solver |
| Do not transfer | Product UI claims; MobiRoute is not a passenger app |
| Method risk | Cloud modular suite ≠ on-prem isolated social-service contour |

### 6. Prediction-failure-risk-aware online DARP (spatial correlation)

| Field | Content |
| --- | --- |
| Citation | Wu, Zou, Liu. *Transportation Research Part C* 169 (2024) 104801 |
| DOI | [10.1016/j.trc.2024.104801](https://doi.org/10.1016/j.trc.2024.104801) |
| Problem | Online DARP as MDP; request selection/cancellation; **prediction-failure risk** and spatial OD correlation |
| Data | Computational study with predicted + actual demand mix (not Moscow) |
| Constraints | Online scheduling; cancellations; correlated sparse OD demand |
| Algorithm | Approximate dynamic programming + scenario approach; deep quantile regression; Gaussian copula; prediction-error correction |
| Transfer | ML only for travel/demand **priors**; hard constraints and independent notary remain |
| Do not transfer | Forecasts as facts; ADP policy as assignment authority; copula as a Moscow demand model |
| Method risk | Over-trusting forecasts; value-function bias in rolling ADP |

### 7. Equity-aware Dial-a-Ride

| Field | Content |
| --- | --- |
| Status | Active family (multiple 2020–2026 works), not a single canonical paper |
| Transfer | Group acceptance rates, worst-group wait, lexicographic fairness for critical groups |
| Method risk | One index (including Jain) ≠ fairness proof |

### 8. Chance-constrained / robust DARP

| Field | Content |
| --- | --- |
| Status | Active family (chance-constrained TW, robust travel times) |
| Transfer | Later stochastic time windows / travel-time robustness |
| v0.2 | OUT OF SCOPE beyond deterministic buffers and occupancy lockstep |
| Method risk | Ambiguous “robust” claims without a specified uncertainty set |

### 9. Dynamic insertion + rolling horizon

| Field | Content |
| --- | --- |
| Analog | Gaul et al. ATMOS / OASIcs rolling-horizon event graph; SynAPS RHC window+overlap |
| Transfer | MobiRoute **RHC**: greedy insertion per time window with seeded previous routes; leftovers retry |
| Do not transfer | Event-MILP optimality or SynAPS FJSP RHC coverage claims |
| Method risk | Plan churn vs service quality; window size is a heuristic parameter |

### 10. Continuous Dynamic Optimization in ADA paratransit

| Field | Content |
| --- | --- |
| Citation | Rodman & Blume. TCRP Synthesis 168, TRB / National Academies, 2023 |
| URL | [NAP 26907](https://nap.nationalacademies.org/catalog/26907) |
| Problem | Practice synthesis: vendor CDO re-optimizes ADA paratransit during the service day |
| Data | Survey/interviews of 11 US agencies (March–June 2022) |
| Metrics | Agencies that shared before/after data reported productivity and OTP changes — **not transferable as Moscow KPIs** |
| Transfer | Event-driven replan + frozen pickup windows; human override remains |
| Do not transfer | US ADA law, vendor CDO product, published % as MobiRoute effect |
| Method risk | Self-reported agency metrics; vendor-specific CDO; ADA ≠ Russian social-taxi rules |

## Policy analogues (not Moscow law) — confirmed 2026-08-12

| Topic | Primary | Use in MobiRoute | Forbidden transfer |
| --- | --- | --- | --- |
| Next-day vs 24 h-before-clock | 49 CFR 37.131(b); FTA ADA circular webinar | `channel=NEXT_DAY` vs Moscow 24 h/3 d intake | Treat Moscow as ADA |
| Pickup negotiation ≤ 1 h | 49 CFR 37.131(b)(2) | Window encoding | Copy US denial statute |
| Pickup window ≤ 30 min; ~5 min driver wait after window start | DREDF OTP guide | 30 min span; planning dwell \(\max(\mathrm{board},5)\); live no-show timer is CRM | Call it Moscow OTP |
| Appointment drop-off −30/0 | DREDF OTP | earliest alight \(start-30\); `appointment_end` hard; no cabin-until-slot | Copy agency % |
| Will-call / open return is premium | ADA practice | Explicit wait-return, 60 min Moscow cap | Promise will-call as a right |
| Subscription ≤ 50% of capacity unless excess | 49 CFR 37.133 | Frozen vs leftover next-day **label** | Enforce 50% as RF law |
| Capacity constraint = pattern of denials / lateness / long rides | 49 CFR 37.131(f) | Non-empty reason codes | “We solved ADA capacity” |
| Wheelchair dwell longer than ambulatory | STM Montréal dwell (TRR 2020) | wheelchair 8; ambulatory \(\max(3,5)=5\) | Copy STM as MAST |
| Productivity / OTP reporting | TCRP Synthesis 168 | Served, P95, coverage | Copy published % to Moscow |

Ops encoding and measured numbers: [`docs/ops-cases-and-benchmark-2026-08-12.md`](../ops-cases-and-benchmark-2026-08-12.md).

## Synthesis for MobiRoute portfolio (v0.2.1)

| Scale | Primary method | Status |
| --- | --- | --- |
| Tiny | Sequential CP-SAT; OPTIMAL only if OR-Tools OPTIMAL and notary | EXPERIMENTAL |
| Medium | Greedy pooling insertion / beam; Benders **PLANNED** | PARTIAL |
| Large | Greedy → beam → ALNS heuristic → RHC windows | PARTIAL (heuristics; LBBD stub) |
| Online | Insert into existing routes; `plan_id` / `event_type`; frozen preservation | PARTIAL |

### Mapping: paper → MobiRoute (2026-08-12)

| Work | In MobiRoute | Missing | Can add | Needs customer data | Benchmark | Allowed claim |
| --- | --- | --- | --- | --- | --- | --- |
| CP 2026 Savannah paratransit | Tiny sequential CP-SAT + shifts as windows | Joint shift design, operator rules | Medium CP / column generation | Yes for KPI transfer | Synthetic zones only | Pattern transfer, not Savannah % |
| Activated Benders 2026 | Stub `benders.py` | LBBD, stochastic 2nd stage | After tiny CP-SAT stable | Disruption distributions | Author instances ≠ Moscow | PLANNED only |
| OR Spectrum 2026 dynamic insertion | Greedy/online PD insertion | Sampling, clustering, parallel reopt | Insertion speed-ups | No for algorithm; yes for SL | 2700-instance paper ≠ ours | Insertion exists; not their curves |
| SmartTransit.AI | Kernel-only JSON contracts | Apps, CAD/AVL, cloud suite | Integration adapters | Agency ops | Demo city ≠ Moscow | Not a passenger app |
| Dynamic insertion + RHC | Rolling-horizon greedy windows + online insert | Exact event MILP | Window size / overlap | Yes for KPI | Synthetic zones | Heuristic composition, never OPTIMAL |
| Equity-aware DARP | Multi-metric fairness, Jain, P95, coverage | Proven equity, override disparity | Lex fairness after hard constraints | Group labels | Synthetic stress mode | Never “fair” from one metric |
| Robust / chance-constrained DARP | Deterministic buffers | Uncertainty sets, CVaR | Later | Travel-time samples | — | OUT OF SCOPE v0.2 |
| Dynamic ridepooling | PARTIAL load-based insertion | Shareability network | Detour-aware ALNS (heuristic exists) | Demand | pooled_rides mode | Not a ridepooling product |
| Disruption recovery | Cancel / no-show / traffic / vehicle / driver | Recourse optimality | Incremental repair | Ops logs | disruption / breakdown modes | Heuristic replan only |
| Omega 2026 TD-DARP ALNS | Adaptive LNS: Shaw/worst/route/random + SA; greedy repair | Time-dependent \(\tau\), regret-k, zero-split, tabu | After live travel | Yes for KPI | Omega instances ≠ Moscow | Heuristic pattern only |

### 11. ALNS for DARP (pattern transfer, not a new paper)

| Field | Content |
| --- | --- |
| Citations | Ropke & Pisinger, *Transportation Science* 2006 (ALNS); Shaw 1998 relatedness; Hu, Wang, Hao, Chen, Li, Jin, *Omega* 2026, [10.1016/j.omega.2026.103577](https://doi.org/10.1016/j.omega.2026.103577) (TD-DARP ALNS: random / Shaw / worst / route / zero-split; greedy + regret repair; SA) |
| Transfer | Destroy operators + roulette weights + SA on equal-served duration. Repair stays greedy reinsert (native-scored). SynAPS `alns_solver.py` is the engineering pattern (not FJSP). |
| Do not transfer | Time-dependent travel, regret-k, zero-split, tabu polish, MAB/UCB1, CP-SAT repair, Omega benchmark % |
| Method risk | Heuristic only — never `OPTIMAL` |

Do not copy published percentages without identical methodology and data.


## Explicit non-claims

- No paper proves Moscow social-taxi improvement.  
- No public Moscow trip dataset for replication.  
- ML is never the assignment authority.
