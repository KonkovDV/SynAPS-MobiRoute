# Operating rules: driver rests and multi-trip vehicles

ALNS, 3000 iterations, seed 1, Rust kernel; every plan re-checked by the verifier. Synthetic days.

## Rests: 4.5 h of driving, then 45 minutes

City freight days, 120 orders, eight vehicle classes, 10-hour shifts. *Plain*: the plan made without the rule, then checked under it. *With rule*: the plan made with it.

| Day | Plain cost | Routes > 4.5 h driving | Routes with no room for a rest | Minutes short | With rule: cost | Rests taken | Cost of compliance | Verified |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| cargo-day-1-120 | 174447 | 11 | 4 | 94.5 | 183599 | 10 | +5.25% | yes |
| cargo-day-2-120 | 169257 | 12 | 5 | 102.4 | 172599 | 11 | +1.97% | yes |
| cargo-day-3-120 | 168005 | 10 | 6 | 208.9 | 174979 | 13 | +4.15% | yes |
| cargo-day-4-120 | 190307 | 10 | 5 | 165.3 | 200569 | 11 | +5.39% | yes |
| cargo-day-5-120 | 183851 | 11 | 4 | 112.2 | 193945 | 13 | +5.49% | yes |

A route that drives more than 4.5 hours is not wrong by itself: the driver can rest while waiting for a window. The verifier looks for such a place in every gap between two services; *no room* means none exists, and the certificate names the conflict.

## Trips: reload at the DC between waves

60 stores, half with a 07:00-10:00 slot and half with 13:00-16:00, 1-4 pallets each; own fleet 6 vans and 3 trucks, up to 8 hired vans and 4 hired trucks; reload 30 min; rest rule on.

| Day | Trips allowed | Served | Vehicles | Hired | Reloads | Cost | Verified |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| dc-day-1 | 1 | 55/60 | 21 | 12 | 0 | 86390 | yes |
| dc-day-1 | 2 | 60/60 | 13 | 4 | 9 | 71516 | yes |
| dc-day-1 | 3 | 60/60 | 13 | 4 | 13 | 73893 | yes |
| dc-day-2 | 1 | 55/60 | 21 | 12 | 0 | 88853 | yes |
| dc-day-2 | 2 | 60/60 | 13 | 4 | 8 | 71831 | yes |
| dc-day-2 | 3 | 60/60 | 12 | 3 | 12 | 70552 | yes |
| dc-day-3 | 1 | 54/60 | 21 | 12 | 0 | 84186 | yes |
| dc-day-3 | 2 | 60/60 | 13 | 4 | 9 | 70178 | yes |
| dc-day-3 | 3 | 60/60 | 13 | 4 | 10 | 71486 | yes |
| dc-day-4 | 1 | 55/60 | 21 | 12 | 0 | 83853 | yes |
| dc-day-4 | 2 | 60/60 | 13 | 4 | 8 | 69483 | yes |
| dc-day-4 | 3 | 60/60 | 12 | 3 | 15 | 70784 | yes |
| dc-day-5 | 1 | 52/60 | 21 | 12 | 0 | 87944 | yes |
| dc-day-5 | 2 | 60/60 | 15 | 6 | 9 | 84969 | yes |
| dc-day-5 | 3 | 60/60 | 13 | 4 | 12 | 78341 | yes |

With one trip per vehicle the day cannot be covered even with every hired vehicle; a second trip per own vehicle covers it. Cost is money only (fees and running cost), so a plan that leaves stores out looks cheaper than it is.

## Rush hours: speeds by time of day

The freight days with 55% of free-flow speed 07:30-10:00 and 60% 17:00-19:30 (Ichoua-Gendreau-Potvin model, FIFO). *Free-flow plan*: made on static times, then driven in traffic as early as possible. *Aware*: made with the speed profile.

| Day | Free-flow cost | Routes failing in traffic | Stops late | Minutes late | Aware: cost | Vehicles (free-flow / aware) | Cost of traffic | Verified |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| cargo-day-1-120 | 174447 | 9 | 10 | 249.0 | 174959 | 19 / 18 | +0.29% | yes |
| cargo-day-2-120 | 169257 | 8 | 8 | 150.8 | 169237 | 18 / 18 | -0.01% | yes |
| cargo-day-3-120 | 168005 | 11 | 10 | 252.3 | 185543 | 17 / 18 | +10.44% | yes |
| cargo-day-4-120 | 190307 | 12 | 10 | 112.5 | 206155 | 17 / 20 | +8.33% | yes |
| cargo-day-5-120 | 183851 | 13 | 16 | 318.0 | 204087 | 18 / 20 | +11.01% | yes |

Time costs are charged on free-flow minutes in both plans, so the cost column shows what the routing change costs, not the extra hours spent in traffic. The time-aware search runs on the Python reference (the Rust kernel covers static travel times).
