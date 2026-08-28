# Заявка: SynAPS-MobiRoute

Репозиторий: https://github.com/KonkovDV/SynAPS-MobiRoute
Версия пакета: **0.2.1**. Ветка: `main`.
SynAPS pin: [`54ebf9f32bc871cc27283331d7536c1068c7e606`](https://github.com/KonkovDV/SynAPS/commit/54ebf9f32bc871cc27283331d7536c1068c7e606).
Пин поднят по KI-N12 / ADR-0004 (fail-closed, calendar refuse, claims-lint). Бессрочный lag после 2026-09-09 не допускается.

Полный текст заявки в Академию инноваторов (поток, сроки, формулировка
разрешённого claim, TAM/SAM/SOM без выдуманной выручки):
[`docs/academy-innovators-application-ru.md`](docs/academy-innovators-application-ru.md).

Мотивационное письмо: [`docs/motivation-letter-ru.md`](docs/motivation-letter-ru.md).
Ограничения: [`docs/limitations.md`](docs/limitations.md).

## Что это

Объяснимое ядро планирования доступных перевозок по требованию (DARP / PDPTW).
Не пассажирское приложение, не CAD/AVL, не реестр льгот.

## Готовность

ISO 16290 TRL 4: синтетические сценарии зон Москвы, автотесты, независимый
notary. Пилота на живых поездках нет.

`optimal` — только если CP-SAT доказал OPTIMAL **и** notary пуст. Greedy / beam /
ALNS / RHC — эвристики.

## Заказчик цикла

В этом репозитории нет подписанного операторского контракта. Заявка в Академию
инноваторов — образовательный/акселераторный контур, не внедрение.

Не смешивать с GridPlan, кабельным доменом ядра или AeroBIM.
