# Заявка: SynAPS-MobiRoute

Репозиторий: https://github.com/KonkovDV/SynAPS-MobiRoute
Версия пакета: **0.2.2**. Ветка: `main`.
SynAPS pin: [`07f11ebb31357ff65c8c078f94207c965a255cc1`](https://github.com/KonkovDV/SynAPS/commit/07f11ebb31357ff65c8c078f94207c965a255cc1)
(SynAPS `main` на 2026-09-09). Регрессии ADR-0004 сохранены (fail-closed, calendar encode, claims-lint). KI-N12 остаётся закрытым. Дальнейший lag только с явным bump и регрессиями.

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
