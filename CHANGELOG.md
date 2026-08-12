# Changelog

## 0.1.1 — 2026-08-12

- Greedy **pooling insertion** (interleaved pickup/dropoff), not sequential PU–DO only.
- Online insertion into existing routes; reject if a frozen trip would move.
- Beam search heuristic; incremental-repair named lane.
- Driver accessibility training checked in simulation and feasibility.
- Deeper research cards (CP 2026, IJOC Benders, OR Spectrum 2026, IJCAI 2024).
- Still synthetic_benchmark only. ALNS/LBBD/RHC remain PLANNED.

## 0.1.0 — 2026-08-12

- Initial public engineering prototype.
- SynAPS audit, Moscow problem map, research and competitor notes.
- Domain models, schemas, FIFO / nearest / greedy / CP-SAT-tiny, online insertion,
  disruption recovery (cancel, no-show, traffic, breakdown), fairness metrics,
  privacy redaction, HITL override journal, CLI, synthetic Moscow-zone generator,
  adversarial tests.
- Community files: CI, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CITATION.cff.
- Claim level: `synthetic_benchmark` only.
