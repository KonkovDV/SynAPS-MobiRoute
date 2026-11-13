# OR-Tools Routing vs ALNS at equal time

Both solvers get 10 s of wall clock per instance on one core (Linux x86_64, Python 3.13.18). OR-Tools: PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH, integer time grid of 0.01 min rounded up, every order in a disjunction so a plan always comes back. ALNS: seed 1. Both plans are re-timed and re-priced by the independent verifier.

| Instance | Orders | Solver | Served | Vehicles | Distance | Cost | Gap to ref. | Verified |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | :---: |
| C101 | 100 | OR-Tools PCI+GLS | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| C101 | 100 | ALNS (this repo) | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| R101 | 100 | OR-Tools PCI+GLS | 100 | 19 | 1671.87 | 1671.87 | 1.28% | yes |
| R101 | 100 | ALNS (this repo) | 100 | 19 | 1650.80 | 1650.80 | 0.00% | yes |
| RC101 | 100 | OR-Tools PCI+GLS | 100 | 16 | 1682.13 | 1682.13 | — | yes |
| RC101 | 100 | ALNS (this repo) | 100 | 14 | 1725.00 | 1725.00 | 1.65% | yes |
| C201 | 100 | OR-Tools PCI+GLS | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| C201 | 100 | ALNS (this repo) | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| R201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1283.08 | 1283.08 | 2.45% | yes |
| R201 | 100 | ALNS (this repo) | 100 | 4 | 1261.36 | 1261.36 | 0.72% | yes |
| RC201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1516.79 | 1516.79 | 7.81% | yes |
| RC201 | 100 | ALNS (this repo) | 100 | 4 | 1433.97 | 1433.97 | 1.92% | yes |
| LC101 | 53 | OR-Tools PCI+GLS | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| LC101 | 53 | ALNS (this repo) | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| bar-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 6 | 821.00 | 821.00 | 12.16% | yes |
| bar-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 739.00 | 739.00 | 0.96% | yes |
| ber-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 14 | 1934.00 | 1934.00 | — | yes |
| ber-n100-1 | 50 | ALNS (this repo) | 50 | 13 | 1857.00 | 1857.00 | 0.16% | yes |
| nyc-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 7 | 642.00 | 642.00 | — | yes |
| nyc-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 639.00 | 639.00 | 0.79% | yes |
| poa-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 14 | 1724.00 | 1724.00 | — | yes |
| poa-n100-1 | 50 | ALNS (this repo) | 50 | 12 | 1619.00 | 1619.00 | 2.34% | yes |
| a2-16 | 16 | OR-Tools PCI+GLS | 15 | 2 | 258.13 | 258.13 | — | yes |
| a2-16 | 16 | ALNS (this repo) | 16 | 2 | 294.25 | 294.25 | 0.00% | yes |
| a4-24 | 24 | OR-Tools PCI+GLS | 24 | 4 | 382.16 | 382.16 | 1.90% | yes |
| a4-24 | 24 | ALNS (this repo) | 24 | 4 | 375.02 | 375.02 | 0.00% | yes |
| b4-32 | 32 | OR-Tools PCI+GLS | 32 | 4 | 502.33 | 502.33 | 1.52% | yes |
| b4-32 | 32 | ALNS (this repo) | 32 | 4 | 494.82 | 494.82 | 0.00% | yes |
| a6-48 | 48 | OR-Tools PCI+GLS | 48 | 5 | 643.08 | 643.08 | 6.45% | yes |
| a6-48 | 48 | ALNS (this repo) | 48 | 6 | 606.65 | 606.65 | 0.42% | yes |
| cargo-day-7-60 | 60 | OR-Tools PCI+GLS | 60 | 12 | 1719.19 | 110308.20 | — | yes |
| cargo-day-7-60 | 60 | ALNS (this repo) | 60 | 10 | 1465.32 | 89398.81 | — | yes |
| cargo-day-11-120 | 120 | OR-Tools PCI+GLS | 120 | 19 | 2634.76 | 189457.99 | — | yes |
| cargo-day-11-120 | 120 | ALNS (this repo) | 120 | 16 | 2211.88 | 154107.36 | — | yes |
| plant-5-140 | 140 | OR-Tools PCI+GLS | 128 | 9 | 570.89 | 56901.83 | — | yes |
| plant-5-140 | 140 | ALNS (this repo) | 131 | 9 | 485.22 | 52446.76 | — | yes |

Gap to reference is shown only for verified plans that serve every order, at the
reference vehicle count where the reference ranks vehicles first. Cargo and plant
days are synthetic and have no published reference; compare their cost columns.
