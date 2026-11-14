# Set partitioning over the route pool: CP-SAT and MIP solvers

Pool: distinct routes of the plans ALNS accepted in 5000 iterations (seed 1). Each backend: one thread unless stated, 10 s wall clock, zero optimality gap, the ALNS plan as a hint (not for HiGHS: OR-Tools crashes on a HiGHS hint). *LP*: the relaxation on GLOP, a lower bound for any plan made of pool routes. Objective as the search sees it (money plus vehicle and unserved penalties).

| Instance | Columns | ALNS plan | LP bound | Solver | Status | Objective | vs ALNS | Time, s | Verified |
| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | :---: |
| R101 | 997 | 1901655.35 | 1851706.41 | CP-SAT, default | FEASIBLE | 1901655.35 | +0.000% | 10.23 | yes |
| R101 | 997 | 1901655.35 | 1851706.41 | CP-SAT, linearization 2 | OPTIMAL | 1901652.93 | -0.000% | 0.18 | yes |
| R101 | 997 | 1901655.35 | 1851706.41 | CP-SAT, 8 workers | OPTIMAL | 1901652.93 | -0.000% | 0.39 | yes |
| R101 | 997 | 1901655.35 | 1851706.41 | SCIP | OPTIMAL | 1901652.93 | -0.000% | 0.16 | yes |
| R101 | 997 | 1901655.35 | 1851706.41 | HiGHS | OPTIMAL | 1901652.93 | -0.000% | 0.18 | yes |
| R101 | 997 | 1901655.35 | 1851706.41 | CBC | OPTIMAL | 1901652.93 | -0.000% | 0.31 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | CP-SAT, default | FEASIBLE | 1401749.04 | +0.000% | 10.01 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | CP-SAT, linearization 2 | OPTIMAL | 1401749.04 | +0.000% | 0.10 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | CP-SAT, 8 workers | OPTIMAL | 1401749.04 | +0.000% | 0.10 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | SCIP | OPTIMAL | 1401749.04 | +0.000% | 0.14 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | HiGHS | OPTIMAL | 1401749.04 | +0.000% | 0.11 | yes |
| RC101 | 666 | 1401749.04 | 1389563.66 | CBC | OPTIMAL | 1401749.04 | +0.000% | 0.17 | yes |
| C201 | 18 | 300591.56 | 300591.56 | CP-SAT, default | OPTIMAL | 300591.56 | +0.000% | 0.00 | yes |
| C201 | 18 | 300591.56 | 300591.56 | CP-SAT, linearization 2 | OPTIMAL | 300591.56 | +0.000% | 0.00 | yes |
| C201 | 18 | 300591.56 | 300591.56 | CP-SAT, 8 workers | OPTIMAL | 300591.56 | +0.000% | 0.01 | yes |
| C201 | 18 | 300591.56 | 300591.56 | SCIP | OPTIMAL | 300591.56 | +0.000% | 0.01 | yes |
| C201 | 18 | 300591.56 | 300591.56 | HiGHS | OPTIMAL | 300591.56 | +0.000% | 0.01 | yes |
| C201 | 18 | 300591.56 | 300591.56 | CBC | OPTIMAL | 300591.56 | +0.000% | 0.01 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | CP-SAT, default | OPTIMAL | 1000828.94 | +0.000% | 0.00 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | CP-SAT, linearization 2 | OPTIMAL | 1000828.94 | +0.000% | 0.00 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | CP-SAT, 8 workers | OPTIMAL | 1000828.94 | +0.000% | 0.01 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | SCIP | OPTIMAL | 1000828.94 | +0.000% | 0.01 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | HiGHS | OPTIMAL | 1000828.94 | +0.000% | 0.01 | yes |
| LC101 | 32 | 1000828.94 | 1000828.94 | CBC | OPTIMAL | 1000828.94 | +0.000% | 0.00 | yes |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | CP-SAT, default | FEASIBLE | 600758.00 | +0.000% | 10.03 | yes |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | CP-SAT, linearization 2 | FEASIBLE | 600758.00 | +0.000% | 10.03 | yes |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | CP-SAT, 8 workers | FEASIBLE | 600758.00 | +0.000% | 10.39 | yes |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | SCIP | FEASIBLE | 600758.00 | +0.000% | 10.06 | yes |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | HiGHS | CODE_99 | — | — | 10.09 | no |
| bar-n100-1 | 1383 | 600758.00 | 537904.58 | CBC | FEASIBLE | 600784.00 | +0.004% | 10.11 | yes |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | CP-SAT, default | FEASIBLE | 141564.84 | -0.014% | 10.12 | yes |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | CP-SAT, linearization 2 | FEASIBLE | 141560.51 | -0.017% | 10.12 | yes |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | CP-SAT, 8 workers | FEASIBLE | 141520.49 | -0.045% | 10.15 | yes |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | SCIP | FEASIBLE | 141564.84 | -0.014% | 10.18 | yes |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | HiGHS | CODE_99 | — | — | 10.36 | no |
| cargo-day-7-120 | 6339 | 141584.44 | 135759.66 | CBC | FEASIBLE | 173585.13 | +22.602% | 10.27 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | CP-SAT, default | FEASIBLE | 71758.51 | +0.000% | 10.02 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | CP-SAT, linearization 2 | OPTIMAL | 71554.05 | -0.285% | 6.43 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | CP-SAT, 8 workers | OPTIMAL | 71554.05 | -0.285% | 7.43 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | SCIP | OPTIMAL | 71554.05 | -0.285% | 7.54 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | HiGHS | OPTIMAL | 71554.05 | -0.285% | 7.15 | yes |
| dc-day-1-60-2trip | 855 | 71758.51 | 69835.23 | CBC | OPTIMAL | 71554.05 | -0.285% | 3.98 | yes |

Reading: when the LP bound equals the ALNS plan, no recombination of the pool can help and the solvers only have to prove it; when it is lower, the gap is the most a recombination could gain. `OPTIMAL` is a proof over the pool, not over all routes.

`CODE_n`: the backend returned no solution within the limit (OR-Tools status code n); HiGHS gets no hint, see above.
