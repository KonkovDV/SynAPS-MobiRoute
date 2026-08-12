# Paratransit / DARP research review (2024–2026)

**Research date:** 2026-08-12.  
**Method:** primary DOIs / LIPIcs / INFORMS / conference proceedings where reachable.

## Paper cards

### 1. Paratransit Optimization with Constraint Programming (Savannah, GA)

| Field | Content |
| --- | --- |
| Citation | Jagrowski, Dalmeijer, Ye, Van Hentenryck. CP 2026. LIPIcs Vol. 379, 31:1–31:16 |
| DOI | [10.4230/LIPIcs.CP.2026.31](https://doi.org/10.4230/LIPIcs.CP.2026.31) |
| Problem | Joint route planning **and** shift scheduling for paratransit |
| Data | Savannah / Chatham Area Transit case study (operator data) |
| Algorithm | Constraint Programming; compared to AI-accelerated column generation |
| Metrics | Requests served vs current practice; flexibility of non-hourly shifts (~+5% served in study) |
| Deployment | Case study — **not** Moscow |
| Transfer | CP modelling of routes+shifts → MobiRoute CPSAT-tiny / medium |
| Do not transfer | Savannah service-rate gains as Moscow effect |
| Method risk | Operator-specific rules; CP scaling limits |

### 2. Activated Benders Decomposition for Day-Ahead Paratransit

| Field | Content |
| --- | --- |
| Citation | Cummings, Jacquillat, Vaze. INFORMS Journal on Computing 38(1):126–149 (2026 issue; online 6 Mar 2025) |
| DOI | [10.1287/ijoc.2023.0311](https://doi.org/10.1287/ijoc.2023.0311) |
| Code | [github.com/INFORMSJoC/2023.0311](https://github.com/INFORMSJoC/2023.0311) — verify LICENSE before reuse |
| Problem | SIPPAR: stochastic itinerary planning with advance requests; cancellations & driver no-shows |
| Algorithm | Activated Benders; restricted subproblems; Pareto-optimal cuts; shareability network |
| Data | Major paratransit platform (authors); not open Moscow data |
| Transfer | Day-ahead robustness + Benders pattern for medium instances |
| Do not transfer | Without travel-time + disruption distributions |
| Method risk | Stochastic second stage needs disruption scenarios; cut validity if adapted poorly |

### 3. Efficient insertion and reoptimization (dynamic DARP)

| Field | Content |
| --- | --- |
| Venue | OR Spectrum, 2026 |
| DOI | [10.1007/s00291-026-00847-0](https://doi.org/10.1007/s00291-026-00847-0) |
| Problem | Customer-oriented **dynamic** dial-a-ride |
| Algorithm | Insertion + reoptimization |
| Transfer | Online insertion + min-churn reopt → continuous dispatch |
| Method risk | Customer-oriented objectives ≠ social priority hierarchy; confirm instance sizes from full text before claiming scale |

### 4. Deploying Mobility-On-Demand for All (paratransit)

| Field | Content |
| --- | --- |
| Venue | IJCAI 2024 |
| DOI | [10.24963/ijcai.2024/822](https://doi.org/10.24963/ijcai.2024/822) |
| Problem | Optimize paratransit / MoD for accessibility (CARTA-related line of work) |
| Transfer | Equity + MoD design ideas; fairness framing |
| Method risk | Demo cities ≠ Moscow fleet / law |

### 5. SmartTransit.AI (dynamic paratransit + microtransit)

| Field | Content |
| --- | --- |
| Venue | IJCAI 2024 system/demo family |
| Problem | Dynamic paratransit + microtransit application |
| Transfer | Architecture of dynamic + microtransit hybrid ops |
| Do not transfer | Product claims without integration evidence |

### 6. Prediction-failure-risk-aware online DARP (spatial correlation)

| Field | Content |
| --- | --- |
| Venue | Transportation Research Part C, 2024 |
| Problem | Online scheduling with prediction failure risk + spatial demand correlation |
| Transfer | ML only for travel/demand **priors**; hard constraints remain |
| Method risk | Over-trusting forecasts → mandatory feasibility check |

### 7. Equity-aware Dial-a-Ride

| Field | Content |
| --- | --- |
| Status | ACTIVE RESEARCH FAMILY (multiple 2020–2026 works) |
| Transfer | Group acceptance rates, worst-group wait, lex fairness |
| Method risk | Single index ≠ fairness proof |

### 8. Chance-constrained / robust DARP

| Field | Content |
| --- | --- |
| Transfer | Later stochastic TW / travel-time robustness |
| v0 | OUT OF SCOPE beyond deterministic buffers |

### 9. Dynamic insertion + rolling horizon

| Field | Content |
| --- | --- |
| Transfer | Maps to MobiRoute online insertion + future RHC (SynAPS RHC patterns) |
| Method risk | Plan churn vs service quality trade-off |

### 10. Continuous Dynamic Optimization in ADA paratransit

| Field | Content |
| --- | --- |
| Transfer | Continuous reopt under ADA-style constraints |
| Method risk | US ADA ≠ Russian social-taxi rules |

## Synthesis for MobiRoute portfolio

| Scale | Primary method | Status in v0.1 |
| --- | --- | --- |
| Tiny | CP-SAT exact / prove OPTIMAL when solver does | IMPLEMENTED |
| Medium | CP-SAT + Benders-style decomposition | PLANNED |
| Large | Greedy insertion → ALNS → RHC | PARTIAL (greedy only) |
| Online | Frozen stops + feasible insertion + explainable reject | PARTIAL |

## Explicit non-claims

- No paper proves Moscow social-taxi improvement.  
- No public Moscow trip dataset for replication.  
- ML is never the assignment authority.
