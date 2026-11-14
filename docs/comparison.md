# Сравнение с другими решателями и литературой

Язык: **RU** | [EN](#english-summary)

Возможности сверены по документации проектов 14.11.2026 (ссылки в конце).
«н/д» — функцию не нашли в просмотренной документации; это не значит, что её
нет. Замеры при равном времени есть против OR-Tools, PyVRP, VROOM и jsprit;
для Timefold и Яндекс Маршрутизации оценок «лучше / хуже» здесь нет.

## В двух словах

От других инструментов этот движок отличается в основном проверкой. Любой
план пересчитывает отдельный верификатор, а если рейс невозможен, он
возвращает сертификат: какие ограничения конфликтуют и сколько минут не
хватает. На малых задачах та же модель решается точно в CP-SAT и MIP, так что
эвристику можно сверить с доказанным оптимумом: на 40 случайных задачах
полной модели ALNS нашёл его все 40 раз. Режим труда и отдыха здесь —
ограничение на время за рулём, а не на интервалы, и каждый маршрутный лист
показывает, как оно соблюдено. Окна, забор и доставка, свои и наёмные машины,
вектор ёмкости, несколько рейсов и пробки задаются в одной модели.

У остальных инструментов своя ниша. PyVRP — итерированный локальный поиск на
C++ для классических CVRP и VRPTW, без правил труда и отдыха в открытой
версии. VROOM — быстрый движок на C++ в связке с OSRM, Openrouteservice и
Valhalla, без нескольких рейсов и без доказательства оптимума. OR-Tools —
универсальная библиотека с большим сообществом. Timefold — платформа
планирования на Java с коммерческой версией. Яндекс Маршрутизация — готовый
сервис с картами, пробками и интерфейсом логиста, модель у него закрыта.

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
| Матрицы по координатам | ✓ офлайн, OSRM, Valhalla | на входе | ✓ OSRM, ORS, Valhalla | н/д | на входе | н/д | ✓ свои карты |

## Измерено: против OR-Tools при равном времени

18 задач (Solomon, Li & Lim, Sartori–Buriol с дорожными временами OSRM,
Cordeau, грузовые дни со смешанным парком), по 10 с на задачу, один поток.
Оба плана проверяет один и тот же верификатор. Порядок сравнения: обслуженные
заказы, затем число машин, затем стоимость.

| Итог | Задач |
| --- | ---: |
| ALNS лучше | 12 |
| Одинаково | 6 |
| OR-Tools лучше | 0 |

На грузовых днях со смешанным парком: 104 411 → 87 115 (−16,6%) при 11 → 10
машинах и 181 480 → 155 318 (−14,4%) при 19 → 16 машинах. Шесть ничьих — задачи,
где оба решателя приходят к оптимуму или лучшему известному решению (C101,
C201, LC101, a2-16, a4-24, b4-32). Полная таблица —
[benchmarks/ortools-vs-alns.md](benchmarks/ortools-vs-alns.md),
воспроизведение — `python benchmark/ortools_vs_alns.py`.

OR-Tools получает матрицы времени и стоимости на стороне C++
(`RegisterTransitMatrix`), а не через колбэки Python. С колбэками его время
уходило в интерпретатор, и счёт выглядел как 15 : 3 : 0; такое сравнение
измеряло привязку к Python, а не решатель.

## Измерено: против PyVRP, VROOM и jsprit

Те же задачи и то же время на один поток: 10 с на задачу Solomon (100
клиентов), 60 с на задачу в 1000 клиентов (Gehring–Homberger, Uchoa X).
Настройки поиска у всех по умолчанию. Каждый план перепроверяет верификатор
этого репозитория на исходных расстояниях задачи.

| | Этот движок | PyVRP 0.14 | VROOM 1.15 | jsprit 2.0 |
| --- | ---: | ---: | ---: | ---: |
| Solomon: планы проверены | 56 / 56 | 56 / 56 | 56 / 56 | 56 / 56 |
| Solomon: число машин лучшего известного решения | **56** | 50 | 32 | 30 |
| Solomon: лучший из четырёх (машины, затем расстояние) | **38** | 36 | 17 | 11 |
| Gehring–Homberger, 1000 клиентов: разрыв по расстоянию | +2,88% | **+1,18%** | +15,17% | +20,90% |
| Uchoa X, 500 и 1000 клиентов: разрыв по расстоянию | +2,40% | **+0,90%** | +3,47% | +19,03% |

Как читать. В эталоне Solomon сначала сравнивают число машин, потом
расстояние. Остальным решателям эта цель передана ценой машины 10⁵; у ALNS
для неё есть отдельная фаза (guided ejection), и это видно во второй строке.
Там, где считается только расстояние, впереди PyVRP: его итерированный
локальный поиск на C++ на тысяче клиентов сильнее. Этот движок
второй, впереди VROOM и jsprit. Замер шёл на общей четырёхъядерной машине,
поэтому повторный прогон сдвинет отдельные строки, но не картину. Полная
таблица — [benchmarks/solvers.md](benchmarks/solvers.md), воспроизведение —
`python benchmark/solvers_study.py`.

## Что взято из литературы и практики

| Источник | Идея | В движке |
| --- | --- | --- |
| Savelsbergh 1992 | проверка вставки по прямому и обратному запасу времени, кратчайшая длительность рейса | ✓ вставка за O(1) |
| Ropke & Pisinger 2006 | ALNS: операторы разрушения и восстановления с адаптивными весами | ✓ |
| Christiaens & Vanden Berghe 2020 | SISR: удаление цепочек | ✓ |
| Nagata & Bräysy 2009 | guided ejection search для сокращения парка | ✓ |
| Vidal et al. 2013 | склейка временных сегментов: окна за O(1) в локальном поиске | ✓ |
| Ichoua, Gendreau & Potvin 2003 | скорости по периодам суток, свойство FIFO | ✓ |
| Goel 2009; Kok et al. 2010; Goel & Vidal 2014 | маршрутизация с правилами рабочего времени ЕС | ◐ перерыв 45 мин, в том числе разделённый 15 + 30; суточный отдых и недельные лимиты — следующий шаг |
| Furtado, Munari & Morabito 2017 | компактная MIP-модель для PDPTW / DARP | ✓ |
| Wouda, Lan & Kool 2024 (PyVRP) | несколько рейсов через точки повторной загрузки | ✓ та же идея: копии склада в маршруте |
| Vidal 2022 (HGS, SWAP*) | гибридный генетический поиск, окрестность SWAP* | — следующий шаг для чистых VRPTW |
| Pessoa et al. 2020 (VRPSolver) | branch-cut-and-price для точных решений | ◐ из этой схемы взята ограниченная мастер-задача: LP по пулу маршрутов и его двойственные цены; подзадача ценообразования не решается, точная ветка — на CP-SAT и MIP |
| Holland et al. 2017 (UPS ORION) | внедрение: водитель должен понимать и принимать маршрут | ✓ маршрутные листы, сертификаты с объяснением |
| Amazon Last Mile Routing Challenge 2021 | водители отклоняются от плана; учиться на фактических маршрутах | — нужны реальные треки |
| Kool et al. 2019; Zhou et al. 2024 (MVMoE) | нейросетевые решатели многих вариантов VRP | — классические методы остаются эталоном на богатых ограничениях; верификатор может проверять и такие планы |

## Когда что выбирать

Для классических CVRP и VRPTW на тысячах точек, где важна прежде всего
скорость, лучше подойдут PyVRP или VROOM. Если нужен готовый интерфейс
логиста с картами и сопровождением, разумнее взять коммерческий сервис. Этот
движок имеет смысл, когда модель своя: правила рабочего времени, несколько
рейсов, разнородный парк, и каждый план нужно проверить и объяснить, а на
малых задачах ещё и доказать оптимум.

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
2026-11-14; "н/д" means "not found there", not "absent". Measured at equal
time, one thread, one verifier. Against OR-Tools Routing on 18 instances
(10 s): ALNS is better on 12, equal on 6 and worse on none (served orders,
then vehicles, then cost); on the mixed-fleet freight days it costs
14.4-16.6% less with one to three vehicles fewer. The baseline reads its
matrices in C++; with Python callbacks it lost wall clock to the
interpreter and the tally read 15 : 3 : 0. Against PyVRP 0.14, VROOM 1.15
and jsprit 2.0: on Solomon (vehicles first) this engine is at the best-known
vehicle count on all 56 instances (PyVRP 50, VROOM 32, jsprit 30); on
1000-customer instances ranked by distance PyVRP leads (+1.2% to the best
known), this engine is second (+2.9%), then VROOM (+15%) and jsprit (+21%).
The engine differs mostly in how plans are checked: an independent verifier
with infeasibility certificates, and exact CP-SAT and MIP models on the same
model, which found the heuristic at the proven optimum on 40 of 40 small
instances. The driving-time rule is a constraint on time at the wheel, shown
on every route sheet, and windows, pickup and delivery, a mixed own-and-hired
fleet, capacity vectors, several trips and rush hours share one model. The
other tools have their own niches: PyVRP for classic CVRP and VRPTW, VROOM
for speed and routing-engine integration, OR-Tools for a broad ecosystem,
Timefold for Java planning, Yandex Routing as a finished service. Tables:
`docs/benchmarks/ortools-vs-alns.md`, `docs/benchmarks/solvers.md`.
Next: time-of-day truck bans, multi-day trips with daily and weekly rest,
split breaks and traffic in the Rust kernel.
