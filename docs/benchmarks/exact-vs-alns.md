# ALNS against proven optima

40 random instances of the full model, 8 orders each, two or three vehicle types, capacity vector, skills, ride limits on 40% of pairs, shift caps, optional orders priced at 1000. CP-SAT (8 workers, 120 s limit) proves the optimum of its model, whose travel times are rounded up to 0.01 min; ALNS runs 2000 iterations. Both plans are priced by the verifier.

* proven optimal by CP-SAT: **40 / 40**
* ALNS equal to the proven optimum: **40 / 40**
* mean / max gap on proven instances: 0.0% / 0.0%
* mean time: CP-SAT 1.1 s, ALNS 0.15 s
* every plan verified: True

| Seed | Types | CP-SAT status | Optimum | ALNS | Gap | CP-SAT time | ALNS time |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1000 | 2 | OPTIMAL | 3532.54 | 3532.54 | 0.00% | 0.07 s | 0.12 s |
| 1001 | 3 | OPTIMAL | 1229.12 | 1229.12 | 0.00% | 2.88 s | 0.16 s |
| 1002 | 2 | OPTIMAL | 3556.62 | 3556.62 | 0.00% | 0.05 s | 0.14 s |
| 1003 | 3 | OPTIMAL | 1594.13 | 1594.13 | 0.00% | 0.20 s | 0.32 s |
| 1004 | 2 | OPTIMAL | 2832.63 | 2832.63 | 0.00% | 0.22 s | 0.12 s |
| 1005 | 3 | OPTIMAL | 811.90 | 811.90 | 0.00% | 6.29 s | 0.10 s |
| 1006 | 2 | OPTIMAL | 2133.68 | 2133.68 | 0.00% | 1.02 s | 0.10 s |
| 1007 | 3 | OPTIMAL | 2991.33 | 2991.33 | 0.00% | 0.21 s | 0.16 s |
| 1008 | 2 | OPTIMAL | 1211.71 | 1211.71 | 0.00% | 1.04 s | 0.13 s |
| 1009 | 3 | OPTIMAL | 1997.87 | 1997.87 | 0.00% | 0.33 s | 0.17 s |
| 1010 | 2 | OPTIMAL | 940.23 | 940.23 | 0.00% | 0.81 s | 0.08 s |
| 1011 | 3 | OPTIMAL | 2091.22 | 2091.22 | 0.00% | 0.14 s | 0.17 s |
| 1012 | 2 | OPTIMAL | 810.27 | 810.27 | 0.00% | 1.01 s | 0.09 s |
| 1013 | 3 | OPTIMAL | 2731.70 | 2731.70 | 0.00% | 0.25 s | 0.12 s |
| 1014 | 2 | OPTIMAL | 3678.55 | 3678.55 | 0.00% | 0.07 s | 0.21 s |
| 1015 | 3 | OPTIMAL | 1130.67 | 1130.67 | 0.00% | 1.60 s | 0.19 s |
| 1016 | 2 | OPTIMAL | 1628.75 | 1628.75 | 0.00% | 0.76 s | 0.14 s |
| 1017 | 3 | OPTIMAL | 1679.30 | 1679.30 | 0.00% | 0.36 s | 0.16 s |
| 1018 | 2 | OPTIMAL | 2655.80 | 2655.80 | 0.00% | 0.28 s | 0.11 s |
| 1019 | 3 | OPTIMAL | 2714.22 | 2714.22 | 0.00% | 0.12 s | 0.14 s |
| 1020 | 2 | OPTIMAL | 1526.56 | 1526.56 | 0.00% | 0.69 s | 0.19 s |
| 1021 | 3 | OPTIMAL | 2511.77 | 2511.77 | 0.00% | 0.19 s | 0.12 s |
| 1022 | 2 | OPTIMAL | 2800.15 | 2800.15 | 0.00% | 0.09 s | 0.18 s |
| 1023 | 3 | OPTIMAL | 4046.03 | 4046.03 | 0.00% | 0.14 s | 0.12 s |
| 1024 | 2 | OPTIMAL | 2448.52 | 2448.52 | 0.00% | 0.59 s | 0.10 s |
| 1025 | 3 | OPTIMAL | 756.34 | 756.34 | 0.00% | 1.02 s | 0.17 s |
| 1026 | 2 | OPTIMAL | 818.88 | 818.88 | 0.00% | 8.77 s | 0.09 s |
| 1027 | 3 | OPTIMAL | 869.51 | 869.51 | 0.00% | 0.91 s | 0.16 s |
| 1028 | 2 | OPTIMAL | 1657.44 | 1657.44 | 0.00% | 0.41 s | 0.14 s |
| 1029 | 3 | OPTIMAL | 1575.12 | 1575.12 | 0.00% | 0.88 s | 0.11 s |
| 1030 | 2 | OPTIMAL | 1891.52 | 1891.52 | 0.00% | 0.21 s | 0.18 s |
| 1031 | 3 | OPTIMAL | 922.68 | 922.68 | 0.00% | 1.95 s | 0.24 s |
| 1032 | 2 | OPTIMAL | 3004.49 | 3004.49 | 0.00% | 0.04 s | 0.11 s |
| 1033 | 3 | OPTIMAL | 2447.40 | 2447.40 | 0.00% | 0.65 s | 0.20 s |
| 1034 | 2 | OPTIMAL | 953.46 | 953.46 | 0.00% | 1.64 s | 0.12 s |
| 1035 | 3 | OPTIMAL | 692.28 | 692.28 | 0.00% | 1.18 s | 0.11 s |
| 1036 | 2 | OPTIMAL | 1635.59 | 1635.59 | 0.00% | 1.10 s | 0.11 s |
| 1037 | 3 | OPTIMAL | 1975.91 | 1975.91 | 0.00% | 0.28 s | 0.23 s |
| 1038 | 2 | OPTIMAL | 3307.95 | 3307.95 | 0.00% | 1.04 s | 0.14 s |
| 1039 | 3 | OPTIMAL | 909.86 | 909.86 | 0.00% | 4.69 s | 0.08 s |
