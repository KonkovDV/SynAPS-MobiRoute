# Limitations and forbidden claims

## Not proven / PARTIAL in v0.2.1

- Improvement of Moscow social taxi KPIs
- Compatibility with Мосавтосантранс production APIs
- Optimality of greedy / beam / RHC / online insertion / disruption recovery
- Tiny CP-SAT as optimum of the **pooling** DARP (it is sequential)
- ALNS as OPTIMAL (adaptive LNS on greedy: Shaw / worst / route / random + SA)
- LBBD / Activated Benders — **out of scope** for v0.2.x (stub remains
  `NotImplementedError`; not a hidden solver)
- GPU insertion — **refused**: 13×13 zone tables, sequential/branchy insert
  with VIA/quota/unavail occupancy. The hot path stays CPU native. Do not
  claim a CUDA/OpenCL DARP engine.
- Third stop / hour quotas / live graph / ALNS OPTIMAL: `ops_via` and
  `ops_quota` exist; ALNS is never OPTIMAL (RT-20 residual)
- Stochastic travel times (deterministic buffers only)
- Fairness as a single score
- Personal-data certification / 152-FZ
- Vehicle shortage resolution
- Full passenger/driver mobile apps

Pooling in v0.2.1 is **classic pickup/dropoff insertion** with dynamic load, independently
feasibility-checked. It is not a proven optimal shareability network.

Insertion scoring for greedy / beam / ALNS / RHC / online is Rust `mobiroute_native`.
Python SoA is an oracle for lockstep tests, not a solver backend, and not a
license to claim OPTIMAL or an unmeasured ×N speedup. Generator `medium` is
60 vehicles / 1000 requests. The `stress_200` ~8.1 s full pipeline (day-ahead
plus disruptions and 8 inserts) is a sample on one machine, not a SLA.

## Forbidden statements

See `docs/claims-review-2026-08-12.md`.
Never mix MobiRoute with GridPlan / AeroBIM / SynAPS Energy in one Academy application.
Ops-suite service rates are synthetic policy scripts (seed 42), not Moscow social-taxi KPIs.
