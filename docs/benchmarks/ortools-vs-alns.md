# OR-Tools Routing vs ALNS at equal time

Both solvers get 10 s of wall clock per instance on one core (Linux x86_64, Python 3.13.18). OR-Tools: PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH, integer time grid of 0.01 min rounded up, every order in a disjunction so a plan always comes back. ALNS: seed 1. Both plans are re-timed and re-priced by the independent verifier.

| Instance | Orders | Solver | Served | Vehicles | Distance | Cost | Gap to ref. | Verified |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | :---: |
| C101 | 100 | OR-Tools PCI+GLS | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| C101 | 100 | ALNS (this repo) | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| R101 | 100 | OR-Tools PCI+GLS | 100 | 19 | 1653.53 | 1653.53 | 0.17% | yes |
| R101 | 100 | ALNS (this repo) | 100 | 19 | 1651.10 | 1651.10 | 0.02% | yes |
| RC101 | 100 | OR-Tools PCI+GLS | 100 | 16 | 1669.37 | 1669.37 | — | yes |
| RC101 | 100 | ALNS (this repo) | 100 | 14 | 1698.82 | 1698.82 | 0.11% | yes |
| C201 | 100 | OR-Tools PCI+GLS | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| C201 | 100 | ALNS (this repo) | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| R201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1283.08 | 1283.08 | 2.45% | yes |
| R201 | 100 | ALNS (this repo) | 100 | 4 | 1253.02 | 1253.02 | 0.05% | yes |
| RC201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1516.79 | 1516.79 | 7.81% | yes |
| RC201 | 100 | ALNS (this repo) | 100 | 4 | 1417.99 | 1417.99 | 0.79% | yes |
| LC101 | 53 | OR-Tools PCI+GLS | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| LC101 | 53 | ALNS (this repo) | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| bar-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 6 | 795.00 | 795.00 | 8.61% | yes |
| bar-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 733.00 | 733.00 | 0.14% | yes |
| ber-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 14 | 1934.00 | 1934.00 | — | yes |
| ber-n100-1 | 50 | ALNS (this repo) | 50 | 13 | 1887.00 | 1887.00 | 1.78% | yes |
| nyc-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 7 | 641.00 | 641.00 | — | yes |
| nyc-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 636.00 | 636.00 | 0.32% | yes |
| poa-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 14 | 1724.00 | 1724.00 | — | yes |
| poa-n100-1 | 50 | ALNS (this repo) | 50 | 12 | 1613.00 | 1613.00 | 1.96% | yes |
| a2-16 | 16 | OR-Tools PCI+GLS | 15 | 2 | 258.13 | 258.13 | — | yes |
| a2-16 | 16 | ALNS (this repo) | 16 | 2 | 294.25 | 294.25 | 0.00% | yes |
| a4-24 | 24 | OR-Tools PCI+GLS | 24 | 4 | 382.16 | 382.16 | 1.90% | yes |
| a4-24 | 24 | ALNS (this repo) | 24 | 4 | 375.02 | 375.02 | 0.00% | yes |
| b4-32 | 32 | OR-Tools PCI+GLS | 32 | 4 | 502.33 | 502.33 | 1.52% | yes |
| b4-32 | 32 | ALNS (this repo) | 32 | 4 | 494.82 | 494.82 | 0.00% | yes |
| a6-48 | 48 | OR-Tools PCI+GLS | 48 | 5 | 642.46 | 642.46 | 6.35% | yes |
| a6-48 | 48 | ALNS (this repo) | 48 | 5 | 613.61 | 613.61 | 1.57% | yes |
| cargo-day-7-60 | 60 | OR-Tools PCI+GLS | 60 | 12 | 1719.19 | 110308.20 | — | yes |
| cargo-day-7-60 | 60 | ALNS (this repo) | 60 | 10 | 1474.48 | 90151.26 | — | yes |
| cargo-day-11-120 | 120 | OR-Tools PCI+GLS | 120 | 19 | 2615.45 | 186822.36 | — | yes |
| cargo-day-11-120 | 120 | ALNS (this repo) | 120 | 17 | 2193.58 | 155515.62 | — | yes |
| plant-5-140 | 140 | OR-Tools PCI+GLS | 128 | 9 | 561.15 | 56440.65 | — | yes |
| plant-5-140 | 140 | ALNS (this repo) | 131 | 9 | 491.76 | 52705.04 | — | yes |

Gap to reference is shown only for verified plans that serve every order, at the
reference vehicle count where the reference ranks vehicles first. Cargo and plant
days are synthetic and have no published reference; compare their cost columns.
