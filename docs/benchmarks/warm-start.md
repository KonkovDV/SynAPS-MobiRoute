# Warm start: CP-SAT from the ALNS plan

20 random instances of the full model with 14 orders (the generator of the exact-vs-ALNS study), two or three vehicle types, ride limits on 40% of pairs, every order optional at a price of 1000. ALNS runs 2000 iterations (seed 1). CP-SAT runs twice with `deterministic=True`, eight workers and a 20 s limit (10 s of deterministic time): cold, and with the ALNS plan as a hint. *Best* is the lowest verified objective of the three; objectives include the price of refused orders.

* CP-SAT proves the optimum: cold 1 / 20, warm 1 / 20
* ALNS at the best value: 16 / 20; mean gap 0.88%, worst 16.02%
* warm CP-SAT at the best value: 17 / 20, never worse than ALNS: True
* cold CP-SAT worse than ALNS (or no plan): 9 / 20
* both runs, cheaper verified plan kept (what `vrp-solve --solver exact` does): at the best value 20 / 20
* mean time: cold 4.98 s, warm 6.43 s; every run ended by the deterministic stop or a proof: True

| Seed | Types | ALNS | Left out | Cold CP-SAT | Status | Warm CP-SAT | Status | Left out | Warm time |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |
| 2000 | 2 | 2285.51 | 0 | 2950.29 | FEASIBLE | 2285.51 | FEASIBLE | 0 | 7.09 s |
| 2001 | 3 | 4004.59 | 3 | 3979.82 | FEASIBLE | 4004.59 | FEASIBLE | 3 | 6.08 s |
| 2002 | 2 | 4041.18 | 3 | 4082.40 | FEASIBLE | 4041.18 | FEASIBLE | 3 | 5.30 s |
| 2003 | 3 | 3002.74 | 1 | 2975.87 | FEASIBLE | 3002.74 | FEASIBLE | 1 | 7.82 s |
| 2004 | 2 | 6211.58 | 5 | 5353.99 | FEASIBLE | 5353.99 | FEASIBLE | 4 | 5.08 s |
| 2005 | 3 | 1177.73 | 0 | 1869.84 | FEASIBLE | 1177.73 | FEASIBLE | 0 | 8.82 s |
| 2006 | 2 | 5776.22 | 5 | 5776.22 | FEASIBLE | 5776.22 | FEASIBLE | 5 | 4.35 s |
| 2007 | 3 | 2477.32 | 1 | 2477.32 | FEASIBLE | 2477.32 | FEASIBLE | 1 | 7.65 s |
| 2008 | 2 | 5231.68 | 4 | 5231.68 | FEASIBLE | 5231.68 | FEASIBLE | 4 | 6.82 s |
| 2009 | 3 | 3183.86 | 1 | 3180.11 | FEASIBLE | 3183.86 | FEASIBLE | 1 | 6.76 s |
| 2010 | 2 | 2921.48 | 2 | 2930.22 | FEASIBLE | 2921.48 | FEASIBLE | 2 | 4.76 s |
| 2011 | 3 | 1513.07 | 0 | 1642.55 | FEASIBLE | 1513.07 | FEASIBLE | 0 | 7.36 s |
| 2012 | 2 | 7499.87 | 7 | 7499.87 | OPTIMAL | 7499.87 | OPTIMAL | 7 | 2.50 s |
| 2013 | 3 | 2850.69 | 1 | 3757.97 | FEASIBLE | 2850.69 | FEASIBLE | 1 | 7.90 s |
| 2014 | 2 | 4493.93 | 3 | 4493.93 | FEASIBLE | 4493.93 | FEASIBLE | 3 | 5.05 s |
| 2015 | 3 | 2470.82 | 1 | 2470.82 | FEASIBLE | 2470.82 | FEASIBLE | 1 | 7.16 s |
| 2016 | 2 | 6928.89 | 6 | 6928.89 | FEASIBLE | 6928.89 | FEASIBLE | 6 | 4.70 s |
| 2017 | 3 | 5156.62 | 4 | 5162.25 | FEASIBLE | 5156.62 | FEASIBLE | 4 | 7.50 s |
| 2018 | 2 | 4155.35 | 3 | 4199.33 | FEASIBLE | 4155.35 | FEASIBLE | 3 | 7.46 s |
| 2019 | 3 | 1676.10 | 0 | 1856.23 | FEASIBLE | 1676.10 | FEASIBLE | 0 | 8.40 s |

ALNS stops short of the best plan on seeds 2001, 2003, 2004, 2009. On seed 2004 the better plan serves one more order, and getting there takes two changes at once: the new pair goes into a route and a stop already on it moves. One destroy-and-repair step of ALNS makes one of them; CP-SAT makes both. The hint has a price too: started from the ALNS plan, CP-SAT can stay near it, and the cold run ends lower on seeds 2001, 2003, 2009. `mobiroute vrp-solve --solver exact` therefore runs both, each on half of `--time-limit`, skips the cold run when the warm one proves the optimum, and keeps the cheapest verified plan, ALNS's included.

Reproducibility costs proofs. With the batch size of the interleaved search left to OR-Tools 9.15, the same 20 instances got 5 optimality proofs, but 2 of 8 identical runs of one instance returned another plan; with the batch size fixed (as `solve_exact` does) every run repeats and 1 proof remains within the budget. A longer one proves more: with 60 s, seed 2004 is proven optimal (the slow test in `tests/test_vrp_engine.py`).

Reproduce: `python benchmark/warm_start_study.py`.
