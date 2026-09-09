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
| Version | **0.2.5** |
| Ветка | `main` |
| SynAPS pin | [`07f11ebb`](https://github.com/KonkovDV/SynAPS/commit/07f11ebb31357ff65c8c078f94207c965a255cc1) |
| Зрелость | ISO 16290 TRL 4 (синтетическая лаборатория). Не пилот оператора. |

Базовый движок-паттерн: [SynAPS](https://github.com/KonkovDV/SynAPS)
(commit `07f11ebb31357ff65c8c078f94207c965a255cc1`, SynAPS `main` на 2026-09-09).
Пин закрывает lag по ADR-0004 (fail-closed покрытие, кодирование календаря
CP-SAT/ALNS/LBBD, claims-lint ядра). KI-N12 остаётся закрытым. Дальнейший lag
только с явным bump и регрессиями.

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
ночной план около **4.0–4.1 с**. Если считать не только ночной план, а ещё поломки,
отмены, пересчёт после пробки и 8 срочных вставок, весь конвейер в том же
прогоне занял около **8.1 с**. Это замер, не SLA и не живая Москва.
