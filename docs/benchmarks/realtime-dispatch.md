# Live dispatch on synthetic days

Orders become known at their release time and are answered immediately. Shuttle:
160 calls, 10 eight-seat buses, pickup within 30 min of the call, arrival within 45.
Plant: pallet moves between workshops, tow tractors, flatbeds with a crane and a
covered van; pickup within 40 min of release, delivery within 90, 12-hour shifts.
*Of carriable* leaves out orders no vehicle type can take; *-breaks* is the same
day with the drivers' break rule of Order No. 160.

| Day | Policy | Accepted | Of carriable | Call to pickup, mean / p95 (min) | Ride, mean (min) | Distance | Cost | Vehicles | Breaks | Decision, mean / p95 / max (ms) | Verified |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| shuttle-11-160 | insertion | 76.9% | 76.9% | 12.7 / 25.6 | 21.3 | 1419.2 | 1419 | 10 | 0 | 0.23 / 0.25 / 8.68 | yes |
| shuttle-11-160 | insertion+alns | 76.9% | 76.9% | 12.7 / 25.6 | 21.3 | 1419.2 | 1419 | 10 | 0 | 0.12 / 0.18 / 0.24 | yes |
| plant-5-140 | insertion | 85.7% | 88.9% | 20.2 / 38.1 | 23.5 | 645.7 | 58974 | 9 | 0 | 0.11 / 0.15 / 0.19 | yes |
| plant-5-140 | insertion+alns | 84.3% | 87.4% | 20.0 / 38.1 | 25.0 | 616.6 | 57529 | 9 | 0 | 0.13 / 0.19 / 0.33 | yes |
| plant-5-140 | ortools-resolve | 81.4% | 84.4% | 22.8 / 37.7 | 26.4 | 546.7 | 54210 | 9 | 0 | 2783.20 / 3109.97 / 3162.68 | yes |
| plant-5-140-breaks | insertion | 85.0% | 88.1% | 19.8 / 37.9 | 24.6 | 629.2 | 58677 | 9 | 3 | 0.19 / 0.27 / 0.35 | yes |
| plant-9-200 | insertion | 79.5% | 81.5% | 19.7 / 38.5 | 24.0 | 736.3 | 68045 | 9 | 0 | 0.14 / 0.20 / 0.24 | yes |
| plant-9-200 | insertion+alns | 79.5% | 81.5% | 21.0 / 38.6 | 25.0 | 732.3 | 67384 | 9 | 0 | 0.15 / 0.24 / 0.31 | yes |

Decision latency for `insertion+alns` excludes the background passes; their total time
is in the JSON (`reoptimize_seconds`). `ortools-resolve` re-solves the whole live state
with OR-Tools Routing for every order (3 s limit, no warm start) and
accepts the order only if every earlier promise is kept. Synthetic days: they exercise
the method, they describe no real operator.

## Reading the table

* Insertion answers 95% of orders within 0.27 ms on every day (background passes excluded); the slowest single answer took 8.68 ms. Wall-clock maxima of a Python process include rare runtime pauses (garbage collection), so the p95 is the figure to plan with.
* plant-5-140: 5 of 140 moves need the covered van but exceed its 4 pallets or 1500 kg, so no vehicle of the fleet can take them under any policy; against the other moves insertion accepts 88.9%.
* plant-5-140 under Order No. 160: the dispatcher plans 3 breaks and accepts 119 orders against 120 without the rule. No route has more than 4.5 h of driving before its break or after it (or in all, when it needs none); the verifier checks every route.
* plant-5-140: ALNS passes every 30 min change acceptance by -1.4 pp and cost by -2.4%; the passes take 3.3 s over the whole day.
* plant-5-140: re-solving with OR-Tools for every order accepts 81.4% against 84.3% and is 5.8% cheaper, but a decision takes 2.8 s instead of 0.13 ms and vehicles reach the pickup 2.8 min later on average: the re-solve minimises cost, not waiting.
* plant-9-200: ALNS passes every 30 min change acceptance by +0.0 pp and cost by -1.0%; the passes take 7.0 s over the whole day.
