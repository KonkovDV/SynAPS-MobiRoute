# Live dispatch on synthetic days

Orders become known at their release time and are answered immediately. Shuttle:
160 calls, 10 eight-seat buses, pickup within 30 min of the call, arrival within 45.
Plant: pallet moves between workshops, tow tractors, flatbeds with a crane and a
covered van; pickup within 40 min of release, delivery within 90, 12-hour shifts.

| Day | Policy | Accepted | Call to pickup, mean / p95 (min) | Ride, mean (min) | Distance | Cost | Vehicles | Decision, mean / max (ms) | Verified |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| shuttle-11-160 | insertion | 76.2% | 11.9 / 24.1 | 21.3 | 1373.1 | 1373 | 10 | 0.08 / 0.20 | yes |
| shuttle-11-160 | insertion+alns | 76.2% | 11.9 / 24.1 | 21.3 | 1373.1 | 1373 | 10 | 0.08 / 0.32 | yes |
| plant-5-140 | insertion | 84.3% | 16.2 / 30.8 | 23.2 | 601.5 | 57492 | 9 | 0.07 / 0.12 | yes |
| plant-5-140 | insertion+alns | 85.0% | 15.6 / 30.6 | 22.3 | 599.7 | 57341 | 9 | 0.10 / 0.31 | yes |
| plant-5-140 | ortools-resolve | 86.4% | 20.9 / 38.7 | 24.4 | 566.8 | 55907 | 9 | 2894.70 / 3137.00 | yes |
| plant-9-200 | insertion | 78.5% | 17.2 / 32.1 | 22.7 | 734.8 | 67493 | 9 | 0.09 / 0.16 | yes |
| plant-9-200 | insertion+alns | 79.0% | 16.2 / 30.6 | 22.5 | 728.1 | 66502 | 9 | 0.11 / 0.26 | yes |

Decision latency for `insertion+alns` excludes the background passes; their total time
is in the JSON (`reoptimize_seconds`). `ortools-resolve` re-solves the whole live state
with OR-Tools Routing for every order (3 s limit, no warm start) and
accepts the order only if every earlier promise is kept. Synthetic days: they exercise
the method, they describe no real operator.

## Reading the table

* Insertion answers every order in at most 0.32 ms on every day, background passes excluded.
* plant-5-140: ALNS passes every 30 min change acceptance by +0.7 pp and cost by -0.3%; the passes take 3.2 s over the whole day.
* plant-5-140: re-solving with OR-Tools for every order accepts 86.4% against 85.0% and is 2.5% cheaper, but a decision takes 2.9 s instead of 0.10 ms and vehicles reach the pickup 5.3 min later on average: the re-solve minimises cost, not waiting.
* plant-9-200: ALNS passes every 30 min change acceptance by +0.5 pp and cost by -1.5%; the passes take 6.5 s over the whole day.
