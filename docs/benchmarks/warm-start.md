# Warm start: CP-SAT from the ALNS plan

20 random instances of the full model with 14 orders (the generator of the exact-vs-ALNS study), two or three vehicle types, ride limits on 40% of pairs, every order optional at a price of 1000. ALNS runs 2000 iterations (seed 1). CP-SAT runs twice with `deterministic=True`, eight workers and a 20 s limit (10 s of deterministic time): cold, and with the ALNS plan as a hint. *Best* is the lowest verified objective of the three; objectives include the price of refused orders.

* CP-SAT proves the optimum: cold 1 / 20, warm 2 / 20
* ALNS at the best value: 17 / 20; mean gap 0.08%, worst 0.9%
* warm CP-SAT at the best value: 18 / 20, never worse than ALNS: True
* cold CP-SAT worse than ALNS (or no plan): 9 / 20
* both runs, cheaper verified plan kept (what `vrp-solve --solver exact` does): at the best value 20 / 20
* mean time: cold 6.3 s, warm 8.24 s; every run ended by the deterministic stop or a proof: True

| Seed | Types | ALNS | Left out | Cold CP-SAT | Status | Warm CP-SAT | Status | Left out | Warm time |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |
| 2000 | 2 | 2285.51 | 0 | 2950.29 | FEASIBLE | 2285.51 | FEASIBLE | 0 | 9.27 s |
| 2001 | 3 | 4004.59 | 3 | 3979.82 | FEASIBLE | 4004.59 | FEASIBLE | 3 | 7.60 s |
| 2002 | 2 | 4041.18 | 3 | 4082.40 | FEASIBLE | 4041.18 | FEASIBLE | 3 | 6.66 s |
| 2003 | 3 | 3002.74 | 1 | 2975.87 | FEASIBLE | 2975.87 | FEASIBLE | 1 | 10.12 s |
| 2004 | 2 | 5353.99 | 4 | 5353.99 | FEASIBLE | 5353.99 | FEASIBLE | 4 | 6.38 s |
| 2005 | 3 | 1177.73 | 0 | 1869.84 | FEASIBLE | 1177.73 | FEASIBLE | 0 | 9.66 s |
| 2006 | 2 | 5776.22 | 5 | 5776.22 | FEASIBLE | 5776.22 | FEASIBLE | 5 | 5.89 s |
| 2007 | 3 | 2477.32 | 1 | 2477.32 | FEASIBLE | 2477.32 | FEASIBLE | 1 | 9.17 s |
| 2008 | 2 | 5231.68 | 4 | 5231.68 | FEASIBLE | 5231.68 | OPTIMAL | 4 | 8.50 s |
| 2009 | 3 | 3183.86 | 1 | 3180.11 | FEASIBLE | 3183.86 | FEASIBLE | 1 | 8.43 s |
| 2010 | 2 | 2087.52 | 1 | 2930.22 | FEASIBLE | 2087.52 | FEASIBLE | 1 | 6.55 s |
| 2011 | 3 | 1513.07 | 0 | 1642.55 | FEASIBLE | 1513.07 | FEASIBLE | 0 | 9.30 s |
| 2012 | 2 | 7499.87 | 7 | 7499.87 | OPTIMAL | 7499.87 | OPTIMAL | 7 | 3.52 s |
| 2013 | 3 | 2850.69 | 1 | 3757.97 | FEASIBLE | 2850.69 | FEASIBLE | 1 | 10.85 s |
| 2014 | 2 | 4493.93 | 3 | 4493.93 | FEASIBLE | 4493.93 | FEASIBLE | 3 | 6.93 s |
| 2015 | 3 | 2470.82 | 1 | 2470.82 | FEASIBLE | 2470.82 | FEASIBLE | 1 | 8.92 s |
| 2016 | 2 | 6928.89 | 6 | 6928.89 | FEASIBLE | 6928.89 | FEASIBLE | 6 | 6.58 s |
| 2017 | 3 | 5156.62 | 4 | 5162.25 | FEASIBLE | 5156.62 | FEASIBLE | 4 | 9.95 s |
| 2018 | 2 | 4155.35 | 3 | 4199.33 | FEASIBLE | 4155.35 | FEASIBLE | 3 | 9.96 s |
| 2019 | 3 | 1676.10 | 0 | 1856.23 | FEASIBLE | 1676.10 | FEASIBLE | 0 | 10.49 s |

ALNS stops short of the best plan on seeds 2001, 2003, 2009, by 0.9% at most. Until 0.7 it also stopped 16% short on seed 2004: the better plan serves one more order, and getting there takes two changes at once, the new pair into a route and a stop already on it moved. One destroy-and-repair step makes one of them; the exact re-sequencing of short routes (`vrp.reseat`) makes both, and ALNS now ends at the value CP-SAT proves with a longer budget. The hint has a price too: started from the ALNS plan, CP-SAT can stay near it, and the cold run ends lower on seeds 2001, 2009. `mobiroute vrp-solve --solver exact` therefore runs both, each on half of `--time-limit`, skips the cold run when the warm one proves the optimum, and keeps the cheapest verified plan, ALNS's included.

Reproducibility costs proofs. With the batch size of the interleaved search left to OR-Tools 9.15, the 0.6.1 run of this study got 5 optimality proofs, but 2 of 8 identical runs of one instance returned another plan; with the batch size fixed (as `solve_exact` does) every run repeats, and 1 cold and 2 warm proofs fit in the budget. A longer one proves more: with 60 s, seed 2004 is proven optimal (the slow test in `tests/test_vrp_engine.py`).

Reproduce: `python benchmark/warm_start_study.py`.
