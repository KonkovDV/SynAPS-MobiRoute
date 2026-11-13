# SynAPS-MobiRoute

Ядро планирования маршрутов **DARP / PDPTW** с доказуемыми результатами: заказы
«подача → высадка» с временными окнами, лимитом времени в пути, гетерогенным
парком и совместимостью «заказ — машина — водитель».

Язык: **RU** | [EN](README.en.md) · Сайт: [konkovdv.github.io/SynAPS-MobiRoute](https://konkovdv.github.io/SynAPS-MobiRoute/)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/kernel-Rust%20%2B%20PyO3-orange.svg)](native/mobiroute_native)
[![OR-Tools](https://img.shields.io/badge/solvers-CP--SAT%20%C2%B7%20SCIP%20%C2%B7%20HiGHS%20%C2%B7%20CBC-4285F4.svg)](docs/benchmarks/solver-lab-a2-16.md)
[![mypy strict](https://img.shields.io/badge/types-mypy%20strict-1D9BF0.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CITATION.cff](https://img.shields.io/badge/cite-CITATION.cff-orange.svg)](CITATION.cff)

Любой опубликованный план проходит **независимую проверку**: временные
ограничения маршрута сводятся к системе разностных неравенств и проверяются
алгоритмом Беллмана–Форда, отдельно от решателя. Если маршрут невыполним, вы
получаете не «infeasible», а **сертификат**: какие ограничения конфликтуют и
**сколько минут не хватает**.

![Оптимальный план Cordeau a2-16, независимо проверенный](docs/img/a2-16-routes.svg)

## Результаты, которые можно воспроизвести

| Что проверяем | Результат | Команда |
| --- | --- | --- |
| Точная модель на эталоне Cordeau (2006) a2-16 | стоимость **294.25** = опубликованный доказанный оптимум; CP-SAT **0.5 с** | `mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out` |
| Выбор MIP/CP-решателя на той же задаче | SCIP 24.5 с и HiGHS 37.3 с — тот же оптимум; CBC за 60 с — разрыв 20%; LP-релаксация 85.27 (слабость big-M: разрыв 71%) | `python benchmark/solver_lab.py` → [таблица](docs/benchmarks/solver-lab-a2-16.md) |
| Скорость на большом синтетическом дне | 200 машин / 3200 заявок: жадная вставка **2.8 с** (было 47.9 с до профилирования); 180 / 2000: **1.6 с** | `python benchmark/run_stress_day.py` |
| Независимый нотариус и красная команда | план со «спрятанным» ожиданием пассажира, подделанные часы, перегруз — отклоняются | `pytest` |
| Качество кода | более 460 тестов, `mypy --strict`, `ruff`, `clippy`, паритет Rust ↔ Python-оракул | `pytest && ruff check . && mypy` |

Замеры — на машине автора (Linux x86_64, Python 3.13, один поток); это не SLA.
Метод и сырые данные — в [docs/benchmarks](docs/benchmarks/solver-lab-a2-16.md).

## Какую задачу решает

Диспетчер или логист планирует сотни заказов, у каждого — жёсткие окна, лимит
времени в пути, требования к машине (подъёмник, тип кузова, вместимость) и к
водителю (допуск, смена, перерыв). Типичные проблемы:

- **решатель молча отказывает** в выполнимых заказах. Здесь такой дефект нашёл
  аудит: расписание «как можно раньше» отклоняло 7 из 16 заявок эталона a2-16,
  каждую даже поодиночке; после исправления — 16 из 16;
- **«оптимально» без доказательства**: статус ставится, но план никто не
  перепроверяет;
- **«невыполнимо» без объяснения**: непонятно, что менять — окно, машину или
  обещание клиенту;
- **медленное перепланирование** при отменах, пробках и поломках.

## Как решает

```mermaid
flowchart LR
  A[Заказы, парк, водители, матрица времени] --> B[Валидация входа]
  B --> C{Портфель решателей}
  C --> D[Жадная вставка на Rust · beam · ALNS · RHC]
  C --> E[Точные модели: CP-SAT и MIP SCIP · HiGHS · CBC]
  D --> F[Независимый нотариус]
  E --> F
  F -->|выполнимо| G[План, отчёт, SVG, отпечатки входа и конфигурации]
  F -->|невыполнимо| H[Сертификат: конфликт ограничений и дефицит в минутах]
```

| Решатель | Когда | Может заявить OPTIMAL |
| --- | --- | --- |
| Жадная вставка (ядро на Rust, PyO3) | основной режим, тысячи заказов | нет |
| Beam search | ограниченный перебор вставок | нет |
| ALNS (Shaw / worst / route / random, имитация отжига) | улучшение плана | нет |
| Rolling horizon | день окнами по времени | нет |
| CP-SAT tiny (операторская алгебра) | до 40 заказов | только если OR-Tools доказал **и** нотариус пуст |
| Точная CP-SAT (литературная алгебра) | эталоны Cordeau | да — для своей целочисленной модели; стоимость пересчитывается в вещественных числах |
| MIP SCIP / HiGHS / CBC (двухиндексная формулировка Furtado–Munari–Morabito 2017) | сравнение решателей, нижние границы | да — по доказательству решателя |
| Онлайн-вставка и восстановление | срочный заказ, отмена, неявка, пробка, поломка | нет |

## «Почему нельзя?» — пример сертификата

Переносим одну высадку в конец маршрута оптимального плана a2-16:

```text
Маршрут 2 невыполним при любом расписании: не хватает 358.68 мин.
заявка 12 в пути не дольше 30 мин; подача 12 — начало не позже 29;
высадка 1 — начало не раньше 402; высадка 1 -> высадка 12: обслуживание 3 + переезд 15.68 мин.
```

Проверка вручную: 402 + 3 + 15.68 − (29 + 3 + 30) = 358.68. Сертификат — это
отрицательный цикл в графе ограничений: никакое изменение времени в этой
последовательности остановок его не закроет.

![Когда обслуживается каждая заявка: окна, начала обслуживания, лимит поездки](docs/img/a2-16-timeline.svg)

## Быстрый старт

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

```bash
mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out --svg
mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out-mip --solver mip --backend SCIP
mobiroute academic-benchmark --instance benchmark/instances/cordeau/a2-16.txt --solver alns --out-dir out-kernel
mobiroute generate --mode medium --seed 42 --out day.json
mobiroute solve --problem day.json --solver greedy --out-dir out-day
pytest            # быстрый набор; точные MIP-доказательства: pytest -m slow
```

## Две алгебры — и почему их нельзя смешивать

- **Литературная** (Cordeau 2006): вещественные расстояния, опубликованные
  времена обслуживания, жёсткие окна. Только здесь публикуется разрыв к
  опубликованному оптимуму — и только для байт-в-байт того же файла (SHA-256).
- **Операторская**: целые минуты, ожидание у подъезда 5 мин, высадка за 30 мин
  до записи. Её планы с литературой не сравниваются, и это проверено машинно:
  маршруты ядра становятся допустимыми в литературной алгебре ровно при
  открытии окон высадки на 30 мин раньше.

## Перенос на грузовую логистику

Алгебра расписания та же (пары «забор — доставка», окна, перерывы водителя,
вставка, нотариус); меняются единицы: вектор ёмкости (кг, м³, паллеты),
стоимость по типу ТС, правила смены водителя. Этапы и критерии приёмки:
[docs/cargo-vrp-porting-plan.md](docs/cargo-vrp-porting-plan.md).

## Границы применимости

Синтетические сценарии зон Москвы и открытый эталон Cordeau. Нет данных
оператора, нет пилота, нет утверждений об экономии (уровень готовности
технологии 4 — лабораторная проверка). Подробно: [docs/limitations.md](docs/limitations.md).

## Документация

| Документ | О чём |
| --- | --- |
| [docs/mathematical-formulation.md](docs/mathematical-formulation.md) | формальная постановка, ограничения, целевые функции |
| [docs/architecture.md](docs/architecture.md) | модули, потоки данных, контракты |
| [docs/benchmark-protocol.md](docs/benchmark-protocol.md) | правила публикации чисел и разрыва к литературе |
| [docs/benchmarks/solver-lab-a2-16.md](docs/benchmarks/solver-lab-a2-16.md) | сравнение решателей на a2-16 |
| [docs/native-acceleration.md](docs/native-acceleration.md) | ядро на Rust, профилирование |
| [docs/cargo-vrp-porting-plan.md](docs/cargo-vrp-porting-plan.md) | перенос на грузовой VRP |
| [docs/research/darp-sota-2025-2026.md](docs/research/darp-sota-2025-2026.md) | обзор литературы по DARP |
| [CHANGELOG.md](CHANGELOG.md) | история изменений |

## Лицензия

MIT — см. [LICENSE](LICENSE). Цитирование — [CITATION.cff](CITATION.cff).
