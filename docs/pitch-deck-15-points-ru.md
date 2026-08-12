# Питчдек — 15 обязательных пунктов (RU)

**Поток:** Академия инноваторов, 10-й набор, заявка до **14 сентября 2026**.  
**Пакет:** карточка + эта презентация + команда + мотивационное письмо.

1. **Название** — MobiRoute (репозиторий SynAPS-MobiRoute).  
2. **Описание** — открытое объяснимое оптимизационное ядро для доступных перевозок по требованию (DARP / paratransit). Не приложение пассажира, не CRM льгот, не CAD/AVL, не биллинг.  
3. **Стадия** — Alpha / экспериментальный прототип; synthetic Moscow-zone benchmark; без customer validation.  
4. **Отрасль** — социальный и доступный транспорт, paratransit, заказные медицинские поездки (NEMT-adjacent).  
5. **Технологии** — Python, Pydantic, OR-Tools CP-SAT (tiny sequential), JSON Schema, детерминированные хеши, независимый feasibility checker.  
6. **РИД** — MIT open-source kernel; данные заказчика остаются у заказчика.  
7. **Контакты** — https://github.com/KonkovDV/SynAPS-MobiRoute (телефон и ФИО в открытый репозиторий не кладутся).  
8. **Изображение продукта** — схема: intake JSON → MobiRoute (compatibility, windows, capacity, driver, pooling insertion / tiny CP-SAT) → plan + diff + reason codes + fairness report → диспетчер.  
9. **Решаемая задача** — назначение ТС и водителя, маршрут с depot/pickup/dropoff, окна, коляски, отказ с кодом, перепланирование.  
10. **Выгода** — прозрачные отказы, воспроизводимость, метрики fairness, интеграция в существующий контур (гипотеза пилота, не измеренный KPI Москвы).  
11. **Бизнес-модель** — on-prem license + integration + support + analytics.  
12. **TAM/SAM/SOM** — bottom-up: операторы соцперевозок / DRT / NEMT; SAM — РФ и on-prem рынки; SOM — 1 город, 1 парк, 1 контракт. Без выдуманной выручки.  
13. **Конкуренты** — Ecolane, TripSpark, RouteMatch, Trapeze, RideCo, TripMaster, SmartTransit.AI, RU stacks, «По пути»; MobiRoute = kernel.  
14. **Команда** — OR + transport planning + software (ФИО уточняются при подаче).  
15. **Запрос на пилот / инвестиции** — shadow-пилот с оператором; трекер 10-го потока (встречи не пропускать); помощь Академии в запуске пилота с городом; не заявление о готовой эксплуатации и не KPI Москвы.

Разрешённая формулировка — в `docs/academy-innovators-application-ru.md` и `docs/claims-review-2026-08-12.md`.
