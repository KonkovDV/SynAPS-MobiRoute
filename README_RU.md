# SynAPS-MobiRoute (RU)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)

Экспериментальное **объяснимое оптимизационное ядро** для планирования и
диспетчеризации доступного транспорта по требованию (социальное такси /
paratransit / DARP).

Это **не** замена операционной платформы оператора, call-центра, реестра льгот
или мобильного приложения пассажира.

Актуальная формулировка готовности и запрещённые заявления — в [`README.md`](README.md)
и [`docs/limitations.md`](docs/limitations.md) / [`docs/claims-review-2026-08-12.md`](docs/claims-review-2026-08-12.md).

Базовый движок-паттерн: [SynAPS](https://github.com/KonkovDV/SynAPS)
(commit `5168fc71005653945097e1f07ada1ce9cbc02eec`).

## Быстрый старт

```bash
python -m pip install -e ".[dev]"
mobiroute demo --out-dir benchmark/results/demo
pytest -q
```
