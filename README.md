# SynAPS-MobiRoute

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha%20prototype-orange.svg)](docs/claims-review-2026-08-12.md)

**Experimental, explainable optimization kernel** for accessible demand-responsive
transport (Dial-a-Ride / PDPTW with wheelchair, companion, medical priority,
fairness, and disruption recovery).

Language: **EN** | [RU](README_RU.md)

> MobiRoute is an **open, explainable and integrable optimization kernel** for
> accessible demand-responsive transport — **not** a passenger app, CRM, CAD/AVL,
> or billing suite.

**TRL honesty (2026-08-12):** engineering prototype. SynAPS scheduling patterns
are reused; the DARP domain is new and validated on **synthetic** Moscow-zone
instances only. No customer operational validation yet.

Pinned SynAPS reference commit: [`5168fc7`](https://github.com/KonkovDV/SynAPS/commit/5168fc71005653945097e1f07ada1ce9cbc02eec)
([upstream SynAPS](https://github.com/KonkovDV/SynAPS)).

## Allowed claim

> MobiRoute — experimental, explainable optimization contour for accessible
> on-demand transport planning. On synthetic scenarios it checks passenger–
> vehicle–driver compatibility, time windows, capacity, accessibility, and
> dynamic replan. Real operational data, industrial integration, and user
> impact require a separate pilot.

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
mobiroute generate --mode tiny --seed 42 --out examples/tiny_day.json
mobiroute solve --problem examples/tiny_day.json --solver greedy --out-dir benchmark/results/tiny_greedy
mobiroute demo --out-dir benchmark/results/demo
mobiroute ops-benchmark --seed 42 --out-dir benchmark/results/ops-2026-08-12
pytest -q
ruff check src tests benchmark
```

Greedy / beam / ALNS / online insertion **require** the Rust kernel
(`mobiroute_native`). Python SoA is an algebra oracle, not a solver backend.
See [`docs/native-acceleration.md`](docs/native-acceleration.md).
Do not quote an unverified ×N speedup.

## Solvers (portfolio)

| Solver | When | May claim OPTIMAL? |
| --- | --- | --- |
| FIFO | baseline, no pooling | No |
| Nearest feasible | baseline | No |
| Greedy insertion | small/medium; **pooling insertion** (Rust `mobiroute_native`) | No |
| Beam (width 3) | limited branching over insertions | No |
| CP-SAT tiny | ≤40 trips / ≤12 vehicles; **sequential pairs, not pooling** | Yes, only if OR-Tools proves OPTIMAL **and** independent feasibility+completeness pass; otherwise `NOT_VERIFIED` |
| CP-SAT fallback | larger instances → greedy | **Never** OPTIMAL (`HEURISTIC_FEASIBLE` / `PARTIAL`) |
| Online insertion / disruption | insert into existing routes | No |
| Incremental repair | named disruption replan | No |
| ALNS | adaptive LNS on greedy; Shaw/worst/route | **Never** OPTIMAL |
| LBBD / RHC | medium / rolling | **PLANNED** (stubs only) |

## Repository layout

See [`docs/architecture.md`](docs/architecture.md). Domain code lives under
`src/mobiroute/` and does **not** mix manufacturing FJSP models from SynAPS.

## Documentation

| Doc | Purpose |
| --- | --- |
| [`docs/implementation-audit-2026-08-12.md`](docs/implementation-audit-2026-08-12.md) | Code vs claims audit (0.1.1 baseline) |
| [`docs/native-acceleration.md`](docs/native-acceleration.md) | Optional PyO3 insertion kernel |
| [`docs/moscow-paratransit-problem-2026.md`](docs/moscow-paratransit-problem-2026.md) | Moscow social taxi problem map |
| [`docs/ops-cases-and-benchmark-2026-08-12.md`](docs/ops-cases-and-benchmark-2026-08-12.md) | Ops cases, world analogues, Academy 10th cohort, measured suite |
| [`docs/edge-cases-algebra-synaps-2026-08-12.md`](docs/edge-cases-algebra-synaps-2026-08-12.md) | Edge cases, DARP algebra, SynAPS pin mapping |
| [`docs/redteam-algebra-2026-08-12.md`](docs/redteam-algebra-2026-08-12.md) | Red Team: notary holes, sort-order traps, pipeline |
| [`docs/research/paratransit-research-2024-2026.md`](docs/research/paratransit-research-2024-2026.md) | Academic review |
| [`docs/market/competitors-2026.md`](docs/market/competitors-2026.md) | Market positioning |
| [`docs/mathematical-formulation.md`](docs/mathematical-formulation.md) | Formal DARP formulation |
| [`docs/privacy-and-security.md`](docs/privacy-and-security.md) | Privacy rules |
| [`docs/limitations.md`](docs/limitations.md) | Non-claims |
| [`docs/claims-review-2026-08-12.md`](docs/claims-review-2026-08-12.md) | Stage-15 honesty gate |
| [`docs/business-model.md`](docs/business-model.md) | Bottom-up TAM/SAM/SOM |
| [`docs/academy-innovators-application-ru.md`](docs/academy-innovators-application-ru.md) | Academy application (RU) |

## Contributing / security

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- [`SECURITY.md`](SECURITY.md)
- [`SUPPORT.md`](SUPPORT.md)
- [`CITATION.cff`](CITATION.cff)

## License

MIT — see [`LICENSE`](LICENSE).
