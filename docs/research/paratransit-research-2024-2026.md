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
| Venue | *Transportation Research Part C*, 2024 |
| Problem | Online DARP with demand prediction **and** prediction-failure risk; spatial correlation |
| Transfer | ML only for travel/demand **priors**; hard constraints remain |
| Do not transfer | Forecasts as facts; ML as assignment authority |
| Method risk | Over-trusting forecasts → mandatory independent feasibility check |

### 7. Equity-aware Dial-a-Ride

| Field | Content |
| --- | --- |
| Status | Active family (multiple 2020–2026 works), not a single canonical paper |
| Transfer | Group acceptance rates, worst-group wait, lexicographic fairness for critical groups |
| Method risk | One index (including Jain) ≠ fairness proof |

### 8. Chance-constrained / robust DARP

| Field | Content |
| --- | --- |
| Transfer | Later stochastic time windows / travel-time robustness |
| v0.1 | OUT OF SCOPE beyond deterministic buffers |
| Method risk | Ambiguous “robust” claims without specified uncertainty set |

### 9. Dynamic insertion + rolling horizon

| Field | Content |
| --- | --- |
| Analog | e.g. ATMOS 2021 rolling-horizon event graph (Gaul et al., OASIcs); SynAPS RHC patterns |
| Transfer | Maps to MobiRoute online insertion now; RHC composition **PLANNED** |
| Method risk | Plan churn vs service quality; event MILP scale |

### 10. Continuous Dynamic Optimization in ADA paratransit

| Field | Content |
| --- | --- |
| Transfer | Continuous reopt under ADA-style constraints |
| Method risk | US ADA ≠ Russian social-taxi rules; do not copy eligibility law |

## Synthesis for MobiRoute portfolio

| Scale | Primary method | Status in v0.1.1 |
| --- | --- | --- |
| Tiny | CP-SAT exact / prove OPTIMAL when solver does | IMPLEMENTED |
| Medium | CP-SAT + Benders-style decomposition | PLANNED |
| Large | Greedy pooling insertion → beam → ALNS → RHC | PARTIAL (greedy pooling + beam; ALNS/RHC stubs) |
| Online | Insert into existing routes; frozen preservation; explainable reject | PARTIAL |

## Explicit non-claims

- No paper proves Moscow social-taxi improvement.  
- No public Moscow trip dataset for replication.  
- ML is never the assignment authority.
