# Заявка: SynAPS-MobiRoute

Репозиторий: https://github.com/KonkovDV/SynAPS-MobiRoute
Версия пакета: **0.2.2**. Ветка: `main`.
SynAPS pin: [`6178c93b705ff58be21fa74a98651883a2da1169`](https://github.com/KonkovDV/SynAPS/commit/6178c93b705ff58be21fa74a98651883a2da1169).
Пин поднят по ADR-0004 (fail-closed, calendar encode, claims-lint). KI-N12 остаётся закрытым. Бессрочный lag после 2026-09-09 не допускается.

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
