# Where an ALNS run spends its time

`cProfile` over one run per instance and backend (Linux x86_64, Python 3.13.18), functions ranked by own time, top 12. Shares are of the profiled run; a profiler slows Python several times over and native code hardly at all, so compare shares inside a table, not totals between tables (speed: [vrp-speed.md](vrp-speed.md)). Produced by `python benchmark/profile_vrp.py`.

## R101 (100 orders)

**python**, 300 iterations, 2.01 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `vrp/insertion.py:696 _single_candidates` | 205692 | 0.240 | 12.0% |
| `vrp/insertion.py:578 best_insertion` | 205692 | 0.229 | 11.4% |
| `vrp/insertion.py:479 exact_feasible` | 17331 | 0.220 | 11.0% |
| `vrp/insertion.py:278 __init__` | 30461 | 0.199 | 9.9% |
| `vrp/insertion.py:855 regret_repair` | 302 | 0.144 | 7.2% |
| `vrp/insertion.py:408 fits` | 205692 | 0.119 | 5.9% |
| `'append' of 'list' objects` | 1106483 | 0.109 | 5.4% |
| `vrp/insertion.py:175 single_trip_loads` | 30461 | 0.103 | 5.1% |
| `vrp/insertion.py:680 _single_positions` | 205692 | 0.101 | 5.0% |
| `vrp/insertion.py:894 evaluate` | 181155 | 0.073 | 3.7% |
| `builtins.len` | 698575 | 0.065 | 3.2% |
| `builtins.sorted` | 82437 | 0.043 | 2.2% |

**native**, 300 iterations, 0.20 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `vrp/local_search.py:212 _best_move` | 16000 | 0.036 | 17.9% |
| `'repair' of 'mobiroute_native.VrpKernel' objects` | 302 | 0.022 | 11.1% |
| `builtins.sum` | 21193 | 0.014 | 6.9% |
| `'eject_insert' of 'mobiroute_native.VrpKernel' objects` | 105 | 0.012 | 6.0% |
| `vrp/alns.py:210 related` | 9900 | 0.010 | 5.1% |
| `builtins.sorted` | 2230 | 0.009 | 4.6% |
| `vrp/alns.py:222 worst` | 71 | 0.007 | 3.6% |
| `vrp/local_search.py:88 _cat` | 23774 | 0.006 | 3.1% |
| `vrp/local_search.py:127 improve` | 3 | 0.006 | 3.1% |
| `builtins.len` | 60912 | 0.005 | 2.7% |
| `vrp/insertion.py:820 remove_requests` | 301 | 0.005 | 2.5% |
| `vrp/local_search.py:80 _node` | 31297 | 0.004 | 2.2% |

## bar-n100-1 (50 orders)

**python**, 300 iterations, 1.21 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `vrp/insertion.py:736 _pair_candidates` | 57267 | 0.454 | 37.5% |
| `vrp/insertion.py:479 exact_feasible` | 4470 | 0.138 | 11.4% |
| `vrp/insertion.py:278 __init__` | 10079 | 0.111 | 9.1% |
| `'append' of 'list' objects` | 835426 | 0.077 | 6.4% |
| `vrp/insertion.py:578 best_insertion` | 57267 | 0.073 | 6.0% |
| `vrp/insertion.py:175 single_trip_loads` | 10079 | 0.065 | 5.4% |
| `vrp/insertion.py:855 regret_repair` | 302 | 0.056 | 4.6% |
| `vrp/insertion.py:408 fits` | 57267 | 0.044 | 3.7% |
| `vrp/insertion.py:894 evaluate` | 49185 | 0.023 | 1.9% |
| `builtins.len` | 196806 | 0.020 | 1.6% |
| `builtins.sum` | 9801 | 0.013 | 1.1% |
| `vrp/insertion.py:81 next_u64` | 25609 | 0.013 | 1.1% |

**native**, 300 iterations, 0.10 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `'repair' of 'mobiroute_native.VrpKernel' objects` | 302 | 0.021 | 21.7% |
| `builtins.sum` | 9174 | 0.012 | 12.5% |
| `'eject_insert' of 'mobiroute_native.VrpKernel' objects` | 105 | 0.008 | 8.6% |
| `builtins.sorted` | 1682 | 0.004 | 4.5% |
| `vrp/alns.py:256 <genexpr>` | 48846 | 0.004 | 4.3% |
| `vrp/alns.py:222 worst` | 60 | 0.004 | 4.0% |
| `vrp/insertion.py:820 remove_requests` | 301 | 0.003 | 3.2% |
| `vrp/alns.py:210 related` | 2500 | 0.003 | 2.8% |
| `vrp/solution.py:131 evaluate` | 227 | 0.002 | 2.2% |
| `vrp/native.py:104 repair` | 302 | 0.002 | 2.1% |
| `vrp/alns.py:275 shaw` | 64 | 0.002 | 2.0% |
| `vrp/alns.py:405 _served` | 300 | 0.002 | 1.7% |

## a3-24 (24 orders)

**python**, 300 iterations, 8.80 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `vrp/insertion.py:479 exact_feasible` | 73393 | 6.678 | 75.9% |
| `'append' of 'list' objects` | 13403932 | 1.308 | 14.9% |
| `vrp/insertion.py:736 _pair_candidates` | 12952 | 0.252 | 2.9% |
| `vrp/insertion.py:578 best_insertion` | 12952 | 0.081 | 0.9% |
| `vrp/insertion.py:633 route_exact` | 73393 | 0.079 | 0.9% |
| `'get' of 'dict' objects` | 582349 | 0.072 | 0.8% |
| `vrp/insertion.py:559 <genexpr>` | 247529 | 0.041 | 0.5% |
| `vrp/insertion.py:562 _splice` | 75235 | 0.039 | 0.4% |
| `vrp/insertion.py:278 __init__` | 2745 | 0.037 | 0.4% |
| `builtins.all` | 62417 | 0.035 | 0.4% |
| `vrp/insertion.py:855 regret_repair` | 301 | 0.030 | 0.3% |
| `builtins.len` | 194797 | 0.024 | 0.3% |

**native**, 300 iterations, 0.19 s under the profiler

| Function | Calls | Own time, s | Share |
| --- | ---: | ---: | ---: |
| `'repair' of 'mobiroute_native.VrpKernel' objects` | 301 | 0.156 | 80.3% |
| `builtins.sum` | 3923 | 0.005 | 2.7% |
| `vrp/alns.py:222 worst` | 65 | 0.003 | 1.3% |
| `vrp/alns.py:256 <genexpr>` | 25852 | 0.002 | 1.3% |
| `vrp/insertion.py:820 remove_requests` | 300 | 0.002 | 1.2% |
| `vrp/solution.py:131 evaluate` | 309 | 0.002 | 1.1% |
| `builtins.sorted` | 1065 | 0.002 | 0.8% |
| `vrp/alns.py:538 _anneal` | 1 | 0.001 | 0.8% |
| `vrp/native.py:104 repair` | 301 | 0.001 | 0.7% |
| `vrp/alns.py:405 _served` | 300 | 0.001 | 0.6% |
| `vrp/alns.py:441 _step` | 300 | 0.001 | 0.6% |
| `vrp/alns.py:422 _destroy` | 300 | 0.001 | 0.5% |

Reading: on the Python reference the insertion scan and the route-state rebuilds dominate, which is what moved to Rust. On the Rust kernel one call (`VrpKernel.repair`) holds the whole regret repair, and the rest of the table is what still runs in Python: destroy operators, cost bookkeeping, local search, the merge and vehicle-type operators. The largest of those is the next candidate for the kernel.
