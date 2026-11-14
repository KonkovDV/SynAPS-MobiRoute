# Live dispatch on synthetic days

Orders become known at their release time and are answered immediately. Shuttle:
160 calls, 10 eight-seat buses, pickup within 30 min of the call, arrival within 45.
Plant: pallet moves between workshops, tow tractors, flatbeds with a crane and a
covered van; pickup within 40 min of release, delivery within 90, 12-hour shifts.

| Day | Policy | Accepted | Call to pickup, mean / p95 (min) | Ride, mean (min) | Distance | Cost | Vehicles | Decision, mean / p95 / max (ms) | Verified |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| shuttle-11-160 | insertion | 76.2% | 11.9 / 24.1 | 21.3 | 1373.1 | 1373 | 10 | 0.08 / 0.11 / 0.15 | yes |
| shuttle-11-160 | insertion+alns | 76.2% | 11.9 / 24.1 | 21.3 | 1373.1 | 1373 | 10 | 0.09 / 0.14 / 0.18 | yes |
| plant-5-140 | insertion | 84.3% | 16.2 / 30.8 | 23.2 | 601.5 | 57492 | 9 | 0.08 / 0.12 / 0.15 | yes |
| plant-5-140 | insertion+alns | 83.6% | 15.8 / 31.9 | 19.6 | 605.8 | 56799 | 9 | 0.11 / 0.17 / 0.68 | yes |
| plant-5-140 | ortools-resolve | 86.4% | 20.9 / 38.7 | 24.4 | 566.8 | 55907 | 9 | 2881.26 / 3088.57 / 3137.02 | yes |
| plant-9-200 | insertion | 78.5% | 17.2 / 32.1 | 22.7 | 734.8 | 67493 | 9 | 0.10 / 0.14 / 0.15 | yes |
| plant-9-200 | insertion+alns | 79.0% | 16.9 / 31.4 | 23.1 | 738.5 | 67247 | 9 | 0.12 / 0.21 / 0.29 | yes |

Decision latency for `insertion+alns` excludes the background passes; their total time
is in the JSON (`reoptimize_seconds`). `ortools-resolve` re-solves the whole live state
with OR-Tools Routing for every order (3 s limit, no warm start) and
accepts the order only if every earlier promise is kept. Synthetic days: they exercise
the method, they describe no real operator.

## Reading the table

* Insertion answers 95% of orders within 0.21 ms on every day (background passes excluded); the slowest single answer took 0.68 ms. Wall-clock maxima of a Python process include rare runtime pauses (garbage collection), so the p95 is the figure to plan with.
* plant-5-140: ALNS passes every 30 min change acceptance by -0.7 pp and cost by -1.2%; the passes take 3.1 s over the whole day.
* plant-5-140: re-solving with OR-Tools for every order accepts 86.4% against 83.6% and is 1.6% cheaper, but a decision takes 2.9 s instead of 0.11 ms and vehicles reach the pickup 5.2 min later on average: the re-solve minimises cost, not waiting.
* plant-9-200: ALNS passes every 30 min change acceptance by +0.5 pp and cost by -0.4%; the passes take 7.5 s over the whole day.
