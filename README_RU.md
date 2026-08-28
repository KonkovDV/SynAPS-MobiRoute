# SynAPS-MobiRoute (RU)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)

Экспериментальный объяснимый оптимизационный контур доступного транспорта по
требованию. Проверяется только на синтетических сценариях зон Москвы.

Это **не** замена операционной платформы оператора, call-центра, реестра льгот
или мобильного приложения пассажира.

Актуальная формулировка готовности и запрещённые заявления — в [`README.md`](README.md)
и [`docs/limitations.md`](docs/limitations.md) / [`docs/claims-review-2026-08-12.md`](docs/claims-review-2026-08-12.md).

| | |
| --- | --- |
| Version | **0.2.1** |
| Ветка | `main` |
| SynAPS pin | [`54ebf9f`](https://github.com/KonkovDV/SynAPS/commit/54ebf9f32bc871cc27283331d7536c1068c7e606) |
| Зрелость | ISO 16290 TRL 4 (синтетическая лаборатория). Не пилот оператора. |

Базовый движок-паттерн: [SynAPS](https://github.com/KonkovDV/SynAPS)
(commit `54ebf9f32bc871cc27283331d7536c1068c7e606`). Пин поднят по KI-N12 /
ADR-0004 (fail-closed покрытие, отказ календаря, claims-lint ядра). Бессрочный
lag после 2026-09-09 по-прежнему не допускается.

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

На этой машине синтетический `stress_200` (200 машин / 3200 заявок, seed 42):
ночной план около **5–6 с**. Если считать не только ночной план, а ещё поломки,
отмены, пересчёт после пробки и 8 срочных вставок, весь конвейер в том же
прогоне занял около **13–15 с**. Это замер, не SLA и не живая Москва.
