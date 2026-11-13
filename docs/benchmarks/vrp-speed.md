# ALNS iteration cost: Python reference vs Rust kernel

400 iterations, seed 1, one thread, Linux x86_64, Python 3.13.18.
Both backends return the same plan; the column says so.

| Case | Python, ms / iteration | Rust, ms / iteration | Speed-up | Same plan |
| --- | ---: | ---: | ---: | :---: |
| VRPTW, Solomon R101 (100 customers) | 4.22 | 0.35 | 12.1x | yes |
| PDPTW, Sartori-Buriol bar-n100-1 (50 pairs, OSRM) | 3.19 | 0.23 | 13.7x | yes |
| DARP, Cordeau a4-48 (48 pairs, ride limits) | 140.29 | 3.33 | 42.1x | yes |
| Cargo day, 120 orders, 8 vehicle types, 3-D capacity | 9.10 | 2.07 | 4.4x | yes |
