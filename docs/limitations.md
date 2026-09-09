# Limitations and forbidden claims

## Not proven / PARTIAL in v0.2.5

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
- Driver rest as labour-law certificate (ГОСТ 70314 / 580-ФЗ). The field is
  policy occupancy windows, same algebra as vehicle shop-out. Multi-day
  rostering is not modelled.

Kernel note (SynAPS ADR-0005, pin `07f11ebb`): `WorkCenter.calendar` is encoded
by CP-SAT/ALNS/LBBD (occupancy in one shift) and clipped on greedy-family
kernel configs. Auto-route stays `CALENDAR_AWARE`. The kernel night-window analog covered 0.75–0.88 of ops — that is
not a MobiRoute DARP KPI. Night/emergency vehicle unavailability in this
product is the domain's own tables, not a kernel shift calendar.

## Forbidden statements

Pooling in v0.2.5 is **classic pickup/dropoff insertion** with dynamic load, independently
feasibility-checked. It is not a proven optimal shareability network.

Insertion scoring for greedy / beam / ALNS / RHC / online is Rust `mobiroute_native`.
Python SoA is an oracle for lockstep tests, not a solver backend, and not a
license to claim OPTIMAL or an unmeasured ×N speedup. Generator `medium` is
60 vehicles / 1000 requests. The `stress_200` ~8.1 s full pipeline (day-ahead
plus disruptions and 8 inserts) is a sample on one machine, not a SLA.

See `docs/claims-review-2026-08-12.md`.
Never mix MobiRoute with GridPlan / AeroBIM / SynAPS Energy in one Academy application.
Ops-suite service rates are synthetic policy scripts (seed 42), not Moscow social-taxi KPIs.
