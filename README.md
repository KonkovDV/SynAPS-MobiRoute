# SynAPS-MobiRoute

Движок маршрутизации для смешанного парка: VRPTW, PDPTW и DARP с вектором
ёмкости (кг, м³, паллеты), требованиями к машине, сменами, своими и наёмными
машинами. ALNS на ядре Rust, точные модели CP-SAT и MIP, сравнение с OR-Tools,
диспетчеризация заявок в реальном времени — и независимая проверка каждого
плана.

Язык: **RU** | [EN](README.en.md) · Сайт: [konkovdv.github.io/SynAPS-MobiRoute](https://konkovdv.github.io/SynAPS-MobiRoute/)

[![CI](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml/badge.svg)](https://github.com/KonkovDV/SynAPS-MobiRoute/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/kernel-Rust%20%2B%20PyO3-orange.svg)](native/mobiroute_native)
[![OR-Tools](https://img.shields.io/badge/solvers-CP--SAT%20%C2%B7%20SCIP%20%C2%B7%20HiGHS%20%C2%B7%20OR--Tools%20Routing-4285F4.svg)](docs/benchmarks)
[![mypy strict](https://img.shields.io/badge/types-mypy%20strict-1D9BF0.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Любой план — от эвристики, точной модели или OR-Tools — проходит отдельный
верификатор: загрузка, расписание и стоимость пересчитываются заново, решателю
ничего не доверяется. Если рейс невозможен, вы получаете не «infeasible», а
**сертификат**: какие ограничения конфликтуют и **сколько минут не хватает**.

![Оптимальный план Cordeau a2-16, независимо проверенный](docs/img/a2-16-routes.svg)

## Результаты

| Что проверяем | Результат | Как воспроизвести |
| --- | --- | --- |
| 130 открытых эталонов: Solomon (VRPTW), Li & Lim и Sartori–Buriol (PDPTW, реальные дорожные времена OSRM), Cordeau (DARP) | все 130 планов проверены и обслуживают все заказы. Solomon: 54 из 56 — с числом машин лучшего известного решения, медиана разрыва **0.38%**, 21 совпадение. Sartori–Buriol: 22 из 25, медиана 0.92%. Cordeau: 19 из 48 — опубликованный оптимум, средний разрыв 0.50% | `python benchmark/vrp_benchmark.py` → [таблица](docs/benchmarks/vrp-public-benchmarks.md) |
| ALNS против доказанного оптимума | CP-SAT доказал оптимум на 40 из 40 случайных задач полной модели (2–3 типа машин, вектор ёмкости, навыки, лимит поездки, смены); ALNS находит его в **38 из 40** за 0.19 с (CP-SAT — 1.7 с), средний разрыв 0.13% | `python benchmark/exact_vs_alns.py` → [таблица](docs/benchmarks/exact-vs-alns.md) |
| OR-Tools Routing (PCI + GLS) при равном времени | 18 задач, по 10 с каждому, один верификатор: ALNS не хуже нигде. R101 — лучшее известное против +1.28%; bar-n100-1 (дороги OSRM) +0.96% против +12.2%; на RC101, ber-, nyc-, poa-n100-1 — на 1–2 машины меньше; на a2-16 OR-Tools теряет заказ; грузовые дни со смешанным парком дешевле на **19%** | `python benchmark/ortools_vs_alns.py` → [таблица](docs/benchmarks/ortools-vs-alns.md) |
| Заявки в реальном времени | ответ на заявку за **0.1 мс** (максимум 0.3 мс): вставка в непроеханную часть плана; ALNS раз в 30 минут поднимает долю принятых и снижает стоимость (завод, 140 перевозок: 84.3% → 85.0%). Полный пересчёт OR-Tools на каждую заявку (3 с) принимает 86.4% и дешевле ещё на 2.5%, но отвечает за 2.9 с — примерно в 30 000 раз дольше — и подаёт машину в среднем на 5 минут позже. Все итоговые планы проверены | `python benchmark/realtime_dispatch.py --with-ortools` → [таблица](docs/benchmarks/realtime-dispatch.md) |
| Профилирование → ядро на Rust | ALNS с ядром на Rust быстрее эталона на Python в **12–42 раза** (VRPTW ×12, PDPTW ×14, DARP ×42) — при **бит-в-бит одинаковом** результате; на дне с 8 типами машин ×4.4: узким местом стал подбор типов на Python | `python benchmark/measure_vrp_speed.py` → [таблица](docs/benchmarks/vrp-speed.md) |
| Выбор MIP/CP-решателя, Cordeau a2-16 | CP-SAT доказывает оптимум 294.25 за 0.6 с; SCIP — 26.2 с, HiGHS — 43.3 с; CBC за 60 с — разрыв 20%; LP-релаксация 85.27 (слабость big-M). ALNS находит тот же оптимум за 2.9 с; OR-Tools за 10 с теряет одну заявку из 16 | `python benchmark/solver_lab.py` → [таблица](docs/benchmarks/solver-lab-a2-16.md) |
| Качество кода | 507 тестов, `mypy --strict`, `ruff`, `clippy -D warnings`, Rust ↔ Python бит в бит | `pytest && ruff check . && mypy` |

Замеры — на одной машине (Linux x86_64, Python 3.13, один поток); это не SLA.

## Какие задачи решает

**Городская доставка со своим и наёмным парком.** Фургоны, грузовики, тягач;
у заказа вес, объём, паллеты, окно доставки, рефрижератор, гидроборт или
ДОПОГ. Решатель выпускает сначала свои машины и нанимает только тот класс,
которого не хватает.

**Внутризаводская логистика.** Перевозки паллет между цехами появляются в
течение смены. Каждая получает ответ за доли миллисекунды — вставку в
непроеханную часть плана или отказ с причиной (из прогона шаттла: «ближайшая
свободная машина доберётся до точки забора через 1.9 мин после закрытия
окна»). Раз в 30 минут живое состояние переоптимизируется.

**Шаттл по требованию.** Поездки между остановками: ожидание не больше 30
минут, ожидание плюс поездка — не больше 45; микроавтобусы на 8 мест.

**Пассажирская перевозка с особыми требованиями** (DARP): лимит времени в
пути, коляски, сопровождающие, водители с допуском — исходное ядро проекта
([docs/darp-kernel.md](docs/darp-kernel.md)).

## Как устроено

```mermaid
flowchart LR
  A[Заказы, парк, матрицы времени] --> B[Модель и валидация]
  B --> C{Решатели}
  C --> D[ALNS: regret-вставка за O1 · 5 операторов разрушения · отжиг · guided ejection]
  D <--> K[Ядро Rust VrpKernel — тот же результат, что эталон на Python]
  C --> E[Точная модель CP-SAT · MIP SCIP / HiGHS]
  C --> O[OR-Tools Routing — для сравнения]
  C --> R[Диспетчер реального времени]
  D --> V[Независимый верификатор]
  E --> V
  O --> V
  R --> V
  V -->|выполним| P[План, стоимость, карта SVG]
  V -->|невыполним| H[Сертификат: конфликт и дефицит в минутах]
```

| Метод | Когда | Доказывает оптимум |
| --- | --- | --- |
| Regret-k вставка + ALNS (random, worst, Shaw, SISR, route; отжиг) | основной режим | нет |
| Guided ejection (Nagata & Bräysy) | сократить число машин | нет |
| Вставка в живой план | новая заявка в течение дня | нет |
| CP-SAT, по циклу на машину | малые задачи с любыми ограничениями | да, для своей целочисленной модели |
| MIP Furtado–Munari–Morabito на SCIP / HiGHS / CBC | сравнение решателей, нижняя граница | да, по доказательству решателя |
| OR-Tools Routing (PCI + GLS) | эталон для сравнения | нет |
| Минимальное опоздание: бисекция по Беллману–Форду, LP | когда окна нельзя выполнить | да (LP) |

Проверка вставки за O(1): самое раннее и самое позднее начало обслуживания на
каждой остановке, загрузка по каждому измерению, а кратчайшая длительность
рейса после вставки — по формуле из префиксных и суффиксных экстремумов.
Подробно: [docs/mathematical-formulation.md](docs/mathematical-formulation.md).

## «Почему нельзя?» — сертификат

Грузовой день: перевозка от поставщика к клиенту.

```text
Рейс невозможен при любом расписании: не хватает 8.8 мин.
поставщик: начало не раньше 09:00 (погрузка 26 мин);
переезд поставщик → клиент: 162.8 мин;
клиент: начало разгрузки не позже 12:00.
```

Проверка вручную: 540 + 26 + 162.8 − 720 = 8.8. Сертификат — отрицательный цикл
в графе разностных ограничений; его вес и есть дефицит. Логист сразу видит, что
менять: окно клиента или время у поставщика.

![Когда обслуживается каждая заявка: окна, начала обслуживания, лимит поездки](docs/img/a2-16-timeline.svg)

## Быстрый старт

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

```bash
mobiroute vrp-solve --generate cargo --orders 120 --out-dir out-cargo --svg
mobiroute vrp-solve --instance benchmark/instances/sartori-buriol/n100/bar-n100-1.txt --time-limit 10 --out-dir out-sb --svg
mobiroute vrp-solve --generate cargo --orders 60 --solver ortools --time-limit 10 --out-dir out-ortools
mobiroute vrp-dispatch --day plant --policy insertion+alns --out-dir out-plant
mobiroute literature-benchmark --instance benchmark/instances/cordeau/a2-16.txt --out-dir out-a2 --svg
pytest            # быстрый набор; точные MIP-доказательства: pytest -m slow
```

```python
from mobiroute.vrp import AlnsConfig, load_benchmark, solve

inst, sha256 = load_benchmark("benchmark/instances/solomon/R101.txt")
result = solve(inst, AlnsConfig(time_limit=10, seed=1))
print(result.verdict.summary())
```

Без собранного ядра на Rust движок работает на эталонной реализации Python —
с тем же результатом, только медленнее.

## Документация

| Документ | О чём |
| --- | --- |
| [docs/cargo-vrp.md](docs/cargo-vrp.md) | грузовой VRP: модель, алгоритмы, сценарии, что дальше |
| [docs/mathematical-formulation.md](docs/mathematical-formulation.md) | постановка, вставка за O(1), разностные ограничения, LP опоздания, CP-SAT, MIP |
| [docs/architecture.md](docs/architecture.md) | модули, потоки данных, проектные решения |
| [docs/native-acceleration.md](docs/native-acceleration.md) | профилирование и ядра на Rust |
| [docs/benchmark-protocol.md](docs/benchmark-protocol.md) | правила публикации чисел |
| [docs/benchmarks/](docs/benchmarks) | таблицы всех экспериментов |
| [docs/darp-kernel.md](docs/darp-kernel.md) | пассажирское ядро DARP: правила, диспетчеризация, проверки |
| [docs/limitations.md](docs/limitations.md) | чего движок пока не умеет |
| [benchmark/instances/README.md](benchmark/instances/README.md) | происхождение эталонов и ссылки |

## Границы применимости

Открытые эталоны и синтетические дни; данных заказчика и пилота нет. Пока один
рейс на машину, без перерывов внутри маршрута и без пробок по времени суток;
эвристики оптимум не доказывают — разрыв к лучшим решениям опубликован по
каждому инстансу. Подробно: [docs/limitations.md](docs/limitations.md).

## Лицензия

MIT — см. [LICENSE](LICENSE). Цитирование — [CITATION.cff](CITATION.cff).
