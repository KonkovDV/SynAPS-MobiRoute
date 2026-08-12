# SynAPS-MobiRoute

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha%20prototype-orange.svg)](docs/claims-review-2026-08-12.md)

**Experimental, explainable optimization kernel** for accessible demand-responsive
transport (Dial-a-Ride / PDPTW with wheelchair, companion, medical priority,
fairness, and disruption recovery).

Language: **EN** | [RU](README_RU.md)

> MobiRoute is **not** a full social-taxi operations platform, passenger app,
> eligibility CRM, or certified personal-data system. It is an **integrable
> planning/dispatch core** designed to sit beside an operator stack.

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
mobiroute generate --mode tiny --seed 42 --out examples/tiny_day.json
mobiroute solve --problem examples/tiny_day.json --solver greedy --out-dir benchmark/results/tiny_greedy
mobiroute demo --out-dir benchmark/results/demo
pytest -q
ruff check src tests benchmark
```

## Solvers (portfolio)

| Solver | When | May claim OPTIMAL? |
| --- | --- | --- |
| FIFO | baseline, no pooling | No |
| Nearest feasible | baseline | No |
| Greedy insertion | small/medium; **pooling insertion** | No |
| Beam (width 3) | limited branching over insertions | No |
| CP-SAT tiny | ≤40 trips / ≤12 vehicles | Yes, only if OR-Tools proves OPTIMAL **and** independent feasibility passes |
| Online insertion / disruption | insert into existing routes | No |
| Incremental repair | named disruption replan | No |
| ALNS / LBBD / RHC | large / medium | **PLANNED** (stubs only) |

## Repository layout

See [`docs/architecture.md`](docs/architecture.md). Domain code lives under
`src/mobiroute/` and does **not** mix manufacturing FJSP models from SynAPS.

## Documentation

| Doc | Purpose |
| --- | --- |
| [`docs/synaps-audit-2026-08-12.md`](docs/synaps-audit-2026-08-12.md) | Upstream SynAPS audit |
| [`docs/moscow-paratransit-problem-2026.md`](docs/moscow-paratransit-problem-2026.md) | Moscow social taxi problem map |
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
