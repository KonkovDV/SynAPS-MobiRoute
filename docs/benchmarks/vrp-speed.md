# ALNS iteration cost: Python reference vs Rust kernel

400 iterations, seed 1, one thread, Linux x86_64, Python 3.13.18.
Both backends return the same plan; the column says so.

| Case | Python, ms / iteration | Rust, ms / iteration | Speed-up | Same plan |
| --- | ---: | ---: | ---: | :---: |
| VRPTW, Solomon R101 (100 customers) | 4.99 | 0.48 | 10.3x | yes |
| PDPTW, Sartori-Buriol bar-n100-1 (50 pairs, OSRM) | 3.79 | 0.22 | 17.4x | yes |
| DARP, Cordeau a4-48 (48 pairs, ride limits) | 109.77 | 2.25 | 48.8x | yes |
| Cargo day, 120 orders, 8 vehicle types, 3-D capacity | 9.07 | 1.68 | 5.4x | yes |
