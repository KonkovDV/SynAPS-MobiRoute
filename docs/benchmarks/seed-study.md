# Seeds and statistics on Solomon's type-2 classes

19 instances (R2, RC2), seeds 1-5, 30000 ALNS iterations per run, Rust kernel. Gap: distance above the best known at the best-known vehicle count; runs with more vehicles are counted in *at ref.* but not in the gap statistics. *Plain*: ALNS alone; *LS*: with the relocate / swap / 2-opt* / 2-opt descent on every new best plan.

| Instance | Vehicles (ref.) | Plain: at ref. | mean ± sd | best | LS: at ref. | mean ± sd | best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R201 | 4 | 5/5 | 0.24% ± 0.26 | 0.07% | 5/5 | 0.25% ± 0.34 | 0.05% |
| R202 | 3 | 5/5 | 5.08% ± 2.98 | 0.86% | 5/5 | 5.02% ± 2.72 | 0.76% |
| R203 | 3 | 5/5 | 1.55% ± 0.98 | 0.73% | 5/5 | 1.28% ± 0.54 | 0.73% |
| R204 | 2 | 5/5 | 3.88% ± 2.53 | 0.40% | 5/5 | 2.93% ± 1.59 | 1.13% |
| R205 | 3 | 5/5 | 2.47% ± 1.48 | 0.76% | 5/5 | 2.57% ± 2.26 | 0.00% |
| R206 | 3 | 5/5 | 1.54% ± 1.28 | 0.00% | 5/5 | 0.99% ± 1.09 | 0.00% |
| R207 | 2 | 5/5 | 5.40% ± 3.19 | 2.14% | 5/5 | 4.35% ± 2.02 | 1.91% |
| R208 | 2 | 5/5 | 1.11% ± 0.54 | 0.44% | 5/5 | 1.53% ± 0.63 | 0.84% |
| R209 | 3 | 5/5 | 3.03% ± 1.07 | 1.43% | 5/5 | 2.62% ± 0.55 | 2.04% |
| R210 | 3 | 5/5 | 1.00% ± 0.99 | 0.26% | 5/5 | 1.56% ± 1.07 | 0.40% |
| R211 | 2 | 5/5 | 6.54% ± 2.83 | 3.13% | 5/5 | 3.93% ± 1.91 | 1.98% |
| RC201 | 4 | 5/5 | 2.65% ± 1.87 | 0.66% | 5/5 | 1.86% ± 0.65 | 1.19% |
| RC202 | 3 | 5/5 | 8.26% ± 2.24 | 6.03% | 5/5 | 6.33% ± 1.57 | 4.98% |
| RC203 | 3 | 5/5 | 2.81% ± 0.47 | 2.11% | 5/5 | 2.78% ± 0.65 | 2.27% |
| RC204 | 3 | 5/5 | 4.00% ± 1.23 | 2.24% | 5/5 | 2.34% ± 1.72 | 0.06% |
| RC205 | 4 | 5/5 | 1.68% ± 1.37 | 0.67% | 5/5 | 1.65% ± 0.78 | 0.94% |
| RC206 | 3 | 5/5 | 1.70% ± 0.66 | 0.91% | 5/5 | 0.91% ± 0.22 | 0.64% |
| RC207 | 3 | 5/5 | 4.37% ± 1.98 | 2.28% | 5/5 | 2.80% ± 1.52 | 0.31% |
| RC208 | 3 | 5/5 | 1.93% ± 1.45 | 0.19% | 5/5 | 1.76% ± 1.80 | 0.19% |

## Paired comparison

Runs where both configurations reach the reference vehicle count: **95**; the local search shortens the plan in **61**, lengthens it in 31; median change -0.32% of the best-known distance.

Wilcoxon signed-rank test (two-sided): n = 92, W+ = 1429.5, W- = 2848.5, z = -2.76, **p = 0.0058**.

Single-seed tables elsewhere in `docs/benchmarks/` are one draw from these distributions; this table says how wide they are.
