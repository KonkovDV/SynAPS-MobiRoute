# Сравнение с аналогами и мировой практикой

Язык: **RU** | [EN](#english-summary)

Возможности сверены по документации проектов 14.11.2026 (ссылки в конце).
«н/д» — функцию не нашли в просмотренной документации; это не значит, что её
нет. Замеры есть только против OR-Tools: остальные решатели на одних задачах
мы ещё не запускали, и оценок «лучше / хуже» для них здесь нет.

## Коротко

**Чем движок отличается**

1. **Каждый план проверяет независимый верификатор.** Он пересчитывает
   загрузку, расписание и стоимость и не берёт у решателя ничего. Если рейс
   невозможен, верификатор возвращает сертификат: какие ограничения
   конфликтуют и сколько минут не хватает.
2. **Эвристика сверяется с доказанным оптимумом.** Точные модели CP-SAT и MIP
   решают ту же модель. На 40 случайных задачах полной модели ALNS находит
   доказанный оптимум все 40 раз.
3. **Правило рабочего времени водителя — ограничение по времени за рулём**:
   перерыв не позже чем через 4,5 ч вождения, не больше 9 ч за смену. Каждый
   маршрутный лист показывает, как правило соблюдено.
4. **Одна модель для грузовой логистики**: окна, забор и доставка,
   разнородный парк из своих и наёмных машин, вектор ёмкости, несколько
   рейсов за смену, пробки по часам суток.
5. **Числа публикуются по каждому инстансу** и воспроизводятся одной
   командой.

**Профиль других инструментов**

* **PyVRP** — итерированный локальный поиск на C++ для классических CVRP и
  VRPTW; правил труда и отдыха в открытой версии нет.
* **VROOM** — быстрый движок на C++ со связкой с OSRM, Openrouteservice и
  Valhalla; задачи без нескольких рейсов и без доказательства оптимума.
* **OR-Tools** — универсальная библиотека с большим сообществом.
* **Timefold** — платформа планирования для Java, с коммерческой версией.
* **Яндекс Маршрутизация** — готовый сервис с картами, пробками и интерфейсом
  логиста; модель закрыта.

## Возможности

| | SynAPS-MobiRoute | OR-Tools Routing | VROOM | jsprit | PyVRP | Timefold Solver | Яндекс Маршрутизация |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Лицензия | MIT | Apache-2.0 | BSD-2-Clause | Apache-2.0 | MIT | Apache-2.0 (Community); Enterprise — коммерческая | коммерческий сервис |
| Ядро | Python + Rust | C++ | C++20 | Java | C++, API на Python | Java, Kotlin | облако, API |
| Окна времени | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ жёсткие и мягкие |
| Забор и доставка в одном рейсе | ✓ | ✓ | ✓ | ✓ | ✓ | н/д | н/д |
| Разнородный парк | ✓ свои и наёмные | ✓ | ✓ | ✓ | ✓ | н/д | ✓ типы транспорта |
| Несколько измерений груза | ✓ кг, м³, паллеты, … | ✓ | ✓ | ✓ | н/д | н/д | ✓ вес и габариты |
| Несколько рейсов за смену | ✓ | моделируется вручную | н/д | н/д | ✓ | н/д | ✓ |
| Перерыв водителя | ✓ по времени за рулём, 15 + 30 | ✓ интервалы перерывов | ✓ перерывы с окнами | н/д | только Enterprise | н/д | н/д |
| Зоны запрета для грузовиков | ✓ масса, ось, высота, тип; матрицы Valhalla | — | через профиль маршрутизатора | н/д | — | н/д | н/д |
| Пробки по времени суток | ✓ | н/д | н/д | ✓ | н/д | н/д | ✓ |
| Метод | ALNS + точные CP-SAT и MIP | локальный поиск; CP-SAT отдельно | эвристики | рандомизированный ruin & recreate | итерированный локальный поиск | метаэвристики | закрыт |
| Доказанный оптимум на той же модели | ✓ на малых задачах | — | — | — | — | — | н/д |
| Независимая проверка и сертификат «почему нельзя» | ✓ | н/д | н/д | н/д | н/д | н/д | н/д |
| Матрицы по координатам | ✓ офлайн и OSRM | на входе | ✓ OSRM, ORS, Valhalla | н/д | на входе | н/д | ✓ свои карты |

## Измерено: против OR-Tools при равном времени

18 задач (Solomon, Li & Lim, Sartori–Buriol с дорожными временами OSRM,
Cordeau, грузовые дни со смешанным парком), по 10 с на задачу, один поток.
Оба плана проверяет один и тот же верификатор. Порядок сравнения: обслуженные
заказы, затем число машин, затем стоимость.

| Итог | Задач |
| --- | ---: |
| ALNS лучше | 15 |
| Одинаково | 3 |
| OR-Tools лучше | 0 |

На грузовых днях со смешанным парком: 110 308 → 90 151 (−18,3%) при 12 → 10
машинах и 186 822 → 155 516 (−16,8%) при 19 → 17 машинах. Полная таблица —
[benchmarks/ortools-vs-alns.md](benchmarks/ortools-vs-alns.md),
воспроизведение — `python benchmark/ortools_vs_alns.py`.

## Мировая практика → что взято в движок

| Источник | Идея | В движке |
| --- | --- | --- |
| Savelsbergh 1992 | проверка вставки по прямому и обратному запасу времени, кратчайшая длительность рейса | ✓ вставка за O(1) |
| Ropke & Pisinger 2006 | ALNS: операторы разрушения и восстановления с адаптивными весами | ✓ |
| Christiaens & Vanden Berghe 2020 | SISR: удаление цепочек | ✓ |
| Nagata & Bräysy 2009 | guided ejection search для сокращения парка | ✓ |
| Vidal et al. 2013 | склейка временных сегментов: окна за O(1) в локальном поиске | ✓ |
| Ichoua, Gendreau & Potvin 2003 | скорости по периодам суток, свойство FIFO | ✓ |
| Goel 2009; Kok et al. 2010; Goel & Vidal 2014 | маршрутизация с правилами рабочего времени ЕС | ◐ один перерыв 45 мин; разделение 15 + 30 и недельные лимиты — следующий шаг |
| Furtado, Munari & Morabito 2017 | компактная MIP-модель для PDPTW / DARP | ✓ |
| Wouda, Lan & Kool 2024 (PyVRP) | несколько рейсов через точки повторной загрузки | ✓ та же идея: копии склада в маршруте |
| Vidal 2022 (HGS, SWAP*) | гибридный генетический поиск, окрестность SWAP* | — следующий шаг для чистых VRPTW |
| Pessoa et al. 2020 (VRPSolver) | branch-cut-and-price для точных решений | — точная ветка у нас на CP-SAT и MIP |
| Holland et al. 2017 (UPS ORION) | внедрение: водитель должен понимать и принимать маршрут | ✓ маршрутные листы, сертификаты с объяснением |
| Amazon Last Mile Routing Challenge 2021 | водители отклоняются от плана; учиться на фактических маршрутах | — нужны реальные треки |
| Kool et al. 2019; Zhou et al. 2024 (MVMoE) | нейросетевые решатели многих вариантов VRP | — классические методы остаются эталоном на богатых ограничениях; верификатор может проверять и такие планы |

## Когда что выбирать

* **Чистые CVRP / VRPTW, максимальная скорость на тысячах точек** — PyVRP или
  VROOM.
* **Готовый интерфейс логиста, карты, сопровождение** — коммерческий сервис.
* **Своя модель с правилами рабочего времени, несколькими рейсами и
  разнородным парком, где каждый план надо проверить и объяснить, а на малых
  задачах доказать оптимум** — этот движок.

## Развитие

* Запрет въезда грузовиков по времени суток (окна по типу машины).
* Многодневные рейсы: суточный и недельный отдых, недельные лимиты вождения.
* Разделённый перерыв и пробки в ядре Rust (сейчас — эталон на Python).

## Источники

Документация проектов (проверено 14.11.2026):
[OR-Tools Routing](https://developers.google.com/optimization/routing),
[OR-Tools: забор и доставка](https://developers.google.com/optimization/routing/pickup_delivery),
[VROOM](https://github.com/VROOM-Project/vroom),
[jsprit](https://github.com/graphhopper/jsprit),
[PyVRP](https://pyvrp.org/stable/) и [репозиторий PyVRP](https://github.com/PyVRP/PyVRP),
[Timefold Solver](https://github.com/TimefoldAI/timefold-solver),
[Яндекс Маршрутизация](https://yandex.ru/routing/).

Публикации:

* Christiaens, J., Vanden Berghe, G. (2020). Slack induction by string removals for vehicle routing problems. *Transportation Science* 54(2).
* Furtado, M. G. S., Munari, P., Morabito, R. (2017). Pickup and delivery problem with time windows: a new compact two-index formulation. *Operations Research Letters* 45(4).
* Goel, A. (2009). Vehicle scheduling and routing with drivers' working hours. *Transportation Science* 43(1).
* Goel, A., Vidal, T. (2014). Hours of service regulations in road freight transport: an optimization-based international assessment. *Transportation Science* 48(3).
* Holland, C., Levis, J., Nuggehalli, R., Santilli, B., Winters, J. (2017). UPS optimizes delivery routes. *Interfaces* 47(1).
* Ichoua, S., Gendreau, M., Potvin, J.-Y. (2003). Vehicle dispatching with time-dependent travel times. *European Journal of Operational Research* 144(2).
* Kok, A. L., Meyer, C. M., Kopfer, H., Schutten, J. M. J. (2010). A dynamic programming heuristic for the vehicle routing problem with time windows and European Community social legislation. *Transportation Science* 44(4).
* Kool, W., van Hoof, H., Welling, M. (2019). Attention, learn to solve routing problems! *ICLR*.
* Merchán, D., et al. (2024). 2021 Amazon Last Mile Routing Research Challenge: data set. *Transportation Science* 58(1).
* Nagata, Y., Bräysy, O. (2009). A powerful route minimization heuristic for the vehicle routing problem with time windows. *Operations Research Letters* 37(5).
* Pessoa, A., Sadykov, R., Uchoa, E., Vanderbeck, F. (2020). A generic exact solver for vehicle routing and related problems. *Mathematical Programming* 183.
* Ropke, S., Pisinger, D. (2006). An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows. *Transportation Science* 40(4).
* Savelsbergh, M. W. P. (1992). The vehicle routing problem with time windows: minimizing route duration. *ORSA Journal on Computing* 4(2).
* Uchoa, E., et al. (2017). New benchmark instances for the capacitated vehicle routing problem. *European Journal of Operational Research* 257(3).
* Vidal, T., Crainic, T. G., Gendreau, M., Prins, C. (2013). A hybrid genetic algorithm with adaptive diversity management for a large class of vehicle routing problems with time-windows. *Computers & Operations Research* 40(1).
* Vidal, T. (2022). Hybrid genetic search for the CVRP: open-source implementation and SWAP* neighborhood. *Computers & Operations Research* 140.
* Wouda, N. A., Lan, L., Kool, W. (2024). PyVRP: a high-performance VRP solver package. *INFORMS Journal on Computing* 36(4).
* Zhou, J., et al. (2024). MVMoE: multi-task vehicle routing solver with mixture-of-experts. *ICML*.

---

## English summary

Capabilities were checked against each project's documentation on
2026-11-14; "н/д" means "not found there", not "absent". Only OR-Tools was
measured head to head: on 18 instances at equal time (10 s, one thread,
one verifier) ALNS is better on 15, equal on 3 and worse on none (served
orders, then vehicles, then cost); on the mixed-fleet freight days it costs
16.8-18.3% less with two vehicles fewer. What sets the engine apart is
verification (an independent verifier with infeasibility certificates, and
exact CP-SAT and MIP models that prove the heuristic's optimum on small
instances: 40 of 40), the driving-time rule as a constraint on time at the
wheel with a check on every route sheet, and one model for time windows,
pickup and delivery, a mixed own-and-hired fleet, capacity vectors,
multi-trip days and rush hours. Other tools have their own profile: PyVRP
for classic CVRP/VRPTW, VROOM for speed and routing-engine integration,
OR-Tools for a broad ecosystem, Timefold for Java enterprise planning,
Yandex Routing as a finished service. The head-to-head harness for PyVRP, VROOM and
jsprit at equal time is `benchmark/solvers_study.py`.
Next: time-of-day truck bans, multi-day trips with daily and weekly rest,
split breaks and traffic in the Rust kernel.
