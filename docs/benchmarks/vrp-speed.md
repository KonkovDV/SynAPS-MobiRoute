# ALNS iteration cost: Python reference vs Rust kernel

400 iterations, seed 1, one thread, Linux x86_64, Python 3.13.18.
Both backends return the same plan; the column says so.

| Case | Python, ms / iteration | Rust, ms / iteration | Speed-up | Same plan |
| --- | ---: | ---: | ---: | :---: |
| VRPTW, Solomon R101 (100 customers) | 3.20 | 0.31 | 10.2x | yes |
| PDPTW, Sartori-Buriol bar-n100-1 (50 pairs, OSRM) | 2.34 | 0.17 | 13.6x | yes |
| DARP, Cordeau a4-48 (48 pairs, ride limits) | 96.86 | 2.28 | 42.4x | yes |
| Cargo day, 120 orders, 8 vehicle types, 3-D capacity | 7.47 | 1.37 | 5.4x | yes |
| Cargo day, 120 orders, rush hours (time-dependent travel) | 12.84 | 1.97 | 6.5x | yes |
| Store day, 60 stores, 2 trips, 15 + 30 min split breaks | 3.94 | 0.71 | 5.5x | yes |
