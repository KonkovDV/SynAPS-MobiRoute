# Solver lab: Cordeau a2-16

Instance SHA-256 `d25ab2609ad09a3ccbd533dbe8418e1ca6b65140114389d31aa8d6c111c0aa79`; published optimum 294.25 (Cordeau (2006), Operations Research 54(3):573-586, proven optimum; tabulated in Ho et al. (2018), Transp. Res. Part B 111:395-421).
Machine: Linux-6.18.44-fc-v445-x86_64-with-glibc2.39, Python 3.13.18, mobiroute 0.4.0. Wall-clock, single thread.

## Literature algebra (comparable)

| Solver | Status | Verified | Cost | Bound | Gap to published | Time, s |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| CP-SAT | OPTIMAL | yes | 294.25 | 294.25 | 0.00% (within rounding) | 0.6 |
| MIP · SCIP | OPTIMAL | yes | 294.25 | 294.25 | 0.00% (within rounding) | 26.2 |
| MIP · HIGHS | OPTIMAL | yes | 294.25 | 294.25 | 0.00% (within rounding) | 43.3 |
| MIP · CBC | FEASIBLE | yes | 353.84 | 225.89 | 20.25% | 59.3 |
| ALNS, rich-VRP engine (10k it) | HEURISTIC | yes | 294.25 | — | 0.00% (within rounding) | 2.9 |
| OR-Tools Routing PCI+GLS (10 s) | SUCCESS | feasible, 15/16 served | 258.13 | — | — | 10.0 |
| LP relaxation · GLOP | BOUND | — | — | 85.27 | — | 0.1 |

## Operator algebra (not comparable: integer minutes, 5-min curb, 30-min lobby)

| Solver | Status | Served | Notary | Kernel distance | Literature-feasible | With 30-min lobby | Time, s |
| --- | --- | --- | --- | ---: | --- | --- | ---: |
| Greedy insertion (Rust) | HEURISTIC_FEASIBLE | 16/16 | yes | 386.0 | no | yes | 0.01 |
| Beam search | HEURISTIC_FEASIBLE | 16/16 | yes | 368.0 | no | yes | 0.01 |
| ALNS | HEURISTIC_FEASIBLE | 16/16 | yes | 386.0 | no | yes | 0.05 |
| Rolling horizon | HEURISTIC_FEASIBLE | 16/16 | yes | 386.0 | no | yes | 0.01 |
| CP-SAT tiny (sequential) | OPTIMAL | 16/16 | yes | 377.0 | no | yes | 0.05 |
