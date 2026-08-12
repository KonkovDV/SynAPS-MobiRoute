# SynAPS-MobiRoute (RU)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)

Экспериментальный объяснимый оптимизационный контур доступного транспорта по
требованию. Проверяется только на синтетических сценариях зон Москвы.

Это **не** замена операционной платформы оператора, call-центра, реестра льгот
или мобильного приложения пассажира.

Актуальная формулировка готовности и запрещённые заявления — в [`README.md`](README.md)
и [`docs/limitations.md`](docs/limitations.md) / [`docs/claims-review-2026-08-12.md`](docs/claims-review-2026-08-12.md).

Базовый движок-паттерн: [SynAPS](https://github.com/KonkovDV/SynAPS)
(commit `5168fc71005653945097e1f07ada1ce9cbc02eec`).

## Быстрый старт

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
mobiroute demo --out-dir benchmark/results/demo
mobiroute ops-benchmark --seed 42 --out-dir benchmark/results/ops-2026-08-12
pytest -q
```

Greedy / beam / ALNS требуют Rust-ядро `mobiroute_native`.
См. [`docs/native-acceleration.md`](docs/native-acceleration.md).
