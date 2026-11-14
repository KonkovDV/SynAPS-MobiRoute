# OR-Tools Routing vs ALNS at equal time

Both solvers get 10 s of wall clock per instance on one core (Linux x86_64, Python 3.13.18). OR-Tools: PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH, integer time grid of 0.01 min rounded up, every order in a disjunction so a plan always comes back. ALNS: seed 1. Both plans are re-timed and re-priced by the independent verifier.

| Instance | Orders | Solver | Served | Vehicles | Distance | Cost | Gap to ref. | Verified |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | :---: |
| C101 | 100 | OR-Tools PCI+GLS | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| C101 | 100 | ALNS (this repo) | 100 | 10 | 828.94 | 828.94 | 0.00% | yes |
| R101 | 100 | OR-Tools PCI+GLS | 100 | 19 | 1653.53 | 1653.53 | 0.17% | yes |
| R101 | 100 | ALNS (this repo) | 100 | 19 | 1650.80 | 1650.80 | 0.00% | yes |
| RC101 | 100 | OR-Tools PCI+GLS | 100 | 16 | 1669.37 | 1669.37 | — | yes |
| RC101 | 100 | ALNS (this repo) | 100 | 14 | 1696.95 | 1696.95 | 0.00% | yes |
| C201 | 100 | OR-Tools PCI+GLS | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| C201 | 100 | ALNS (this repo) | 100 | 3 | 591.56 | 591.56 | 0.00% | yes |
| R201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1279.07 | 1279.07 | 2.13% | yes |
| R201 | 100 | ALNS (this repo) | 100 | 4 | 1253.23 | 1253.23 | 0.07% | yes |
| RC201 | 100 | OR-Tools PCI+GLS | 100 | 4 | 1482.45 | 1482.45 | 5.37% | yes |
| RC201 | 100 | ALNS (this repo) | 100 | 4 | 1442.82 | 1442.82 | 2.55% | yes |
| LC101 | 53 | OR-Tools PCI+GLS | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| LC101 | 53 | ALNS (this repo) | 53 | 10 | 828.94 | 828.94 | 0.00% | yes |
| bar-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 6 | 774.00 | 774.00 | 5.74% | yes |
| bar-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 736.00 | 736.00 | 0.55% | yes |
| ber-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 14 | 1880.00 | 1880.00 | — | yes |
| ber-n100-1 | 50 | ALNS (this repo) | 50 | 13 | 1857.00 | 1857.00 | 0.16% | yes |
| nyc-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 6 | 649.00 | 649.00 | 2.37% | yes |
| nyc-n100-1 | 50 | ALNS (this repo) | 50 | 6 | 638.00 | 638.00 | 0.63% | yes |
| poa-n100-1 | 50 | OR-Tools PCI+GLS | 50 | 13 | 1692.00 | 1692.00 | — | yes |
| poa-n100-1 | 50 | ALNS (this repo) | 50 | 12 | 1621.00 | 1621.00 | 2.47% | yes |
| a2-16 | 16 | OR-Tools PCI+GLS | 16 | 2 | 294.25 | 294.25 | 0.00% | yes |
| a2-16 | 16 | ALNS (this repo) | 16 | 2 | 294.25 | 294.25 | 0.00% | yes |
| a4-24 | 24 | OR-Tools PCI+GLS | 24 | 4 | 375.02 | 375.02 | 0.00% | yes |
| a4-24 | 24 | ALNS (this repo) | 24 | 4 | 375.02 | 375.02 | 0.00% | yes |
| b4-32 | 32 | OR-Tools PCI+GLS | 32 | 4 | 494.82 | 494.82 | 0.00% | yes |
| b4-32 | 32 | ALNS (this repo) | 32 | 4 | 494.82 | 494.82 | 0.00% | yes |
| a6-48 | 48 | OR-Tools PCI+GLS | 48 | 6 | 622.92 | 622.92 | 3.11% | yes |
| a6-48 | 48 | ALNS (this repo) | 48 | 6 | 604.48 | 604.48 | 0.06% | yes |
| cargo-day-7-60 | 60 | OR-Tools PCI+GLS | 60 | 11 | 1698.78 | 104411.08 | — | yes |
| cargo-day-7-60 | 60 | ALNS (this repo) | 60 | 10 | 1589.50 | 87114.66 | — | yes |
| cargo-day-11-120 | 120 | OR-Tools PCI+GLS | 120 | 19 | 2480.07 | 181479.65 | — | yes |
| cargo-day-11-120 | 120 | ALNS (this repo) | 120 | 16 | 2243.30 | 155318.33 | — | yes |
| plant-5-140 | 140 | OR-Tools PCI+GLS | 130 | 9 | 567.55 | 56615.21 | — | yes |
| plant-5-140 | 140 | ALNS (this repo) | 131 | 9 | 489.92 | 52772.71 | — | yes |

Gap to reference is shown only for verified plans that serve every order, at the
reference vehicle count where the reference ranks vehicles first. Cargo and plant
days are synthetic and have no published reference; compare their cost columns.
