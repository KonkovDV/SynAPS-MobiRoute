# Rich-VRP engine on public benchmarks

Seed 1, 30000 ALNS iterations per instance (Cordeau: 10000), backend `native`, Linux x86_64, Python 3.13.18.
Every plan is re-checked by the independent verifier; gaps are quoted only for
verified plans that serve every order, and under the hierarchical objective only
at the reference vehicle count. Timings are single-threaded wall clock.

## Summary

| Family | Instances | Verified | At ref. fleet | Fewer veh. | More veh. | Matched ref. | Mean gap | Median gap | Max gap | Mean time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cordeau | 48 | 48 | — | — | — | 19 | 0.495% | 0.266% | 2.133% | 14.67 s |
| lilim | 1 | 1 | 1 | 0 | 0 | 1 | 0.0% | 0.0% | 0.0% | 4.83 s |
| sartori-buriol | 25 | 25 | 22 | 0 | 3 | 4 | 1.124% | 0.922% | 4.86% | 7.01 s |
| solomon | 56 | 56 | 56 | 0 | 0 | 20 | 1.21% | 0.5% | 7.006% | 17.45 s |

## Instances

| Family | Instance | Orders | Vehicles (ref) | Cost (ref) | Gap | Time |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| solomon | C101 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 7.6 s |
| solomon | C102 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 6.1 s |
| solomon | C103 | 100 | 10 (10) | 828.06 (828.06) | 0.00% | 7.9 s |
| solomon | C104 | 100 | 10 (10) | 824.78 (824.78) | 0.00% | 7.3 s |
| solomon | C105 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 7.0 s |
| solomon | C106 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 6.8 s |
| solomon | C107 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 7.8 s |
| solomon | C108 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 7.4 s |
| solomon | C109 | 100 | 10 (10) | 828.94 (828.94) | 0.00% | 7.9 s |
| solomon | C201 | 100 | 3 (3) | 591.56 (591.56) | 0.00% | 14.4 s |
| solomon | C202 | 100 | 3 (3) | 591.56 (591.56) | 0.00% | 11.3 s |
| solomon | C203 | 100 | 3 (3) | 591.17 (591.17) | 0.00% | 11.9 s |
| solomon | C204 | 100 | 3 (3) | 590.60 (590.60) | 0.00% | 11.1 s |
| solomon | C205 | 100 | 3 (3) | 588.88 (588.88) | 0.00% | 12.4 s |
| solomon | C206 | 100 | 3 (3) | 588.49 (588.49) | 0.00% | 12.6 s |
| solomon | C207 | 100 | 3 (3) | 588.29 (588.29) | 0.00% | 11.3 s |
| solomon | C208 | 100 | 3 (3) | 588.32 (588.32) | 0.00% | 11.3 s |
| solomon | R101 | 100 | 19 (19) | 1650.80 (1650.80) | 0.00% | 8.5 s |
| solomon | R102 | 100 | 17 (17) | 1486.96 (1486.12) | 0.06% | 9.2 s |
| solomon | R103 | 100 | 13 (13) | 1296.11 (1292.68) | 0.27% | 9.4 s |
| solomon | R104 | 100 | 9 (9) | 1028.62 (1007.31) | 2.12% | 8.1 s |
| solomon | R105 | 100 | 14 (14) | 1377.63 (1377.11) | 0.04% | 8.4 s |
| solomon | R106 | 100 | 12 (12) | 1264.52 (1252.03) | 1.00% | 8.6 s |
| solomon | R107 | 100 | 10 (10) | 1120.93 (1104.66) | 1.47% | 8.5 s |
| solomon | R108 | 100 | 9 (9) | 965.51 (960.88) | 0.48% | 8.1 s |
| solomon | R109 | 100 | 11 (11) | 1218.50 (1194.73) | 1.99% | 8.7 s |
| solomon | R110 | 100 | 10 (10) | 1152.87 (1118.84) | 3.04% | 8.6 s |
| solomon | R111 | 100 | 10 (10) | 1096.74 (1096.73) | 0.00% | 8.5 s |
| solomon | R112 | 100 | 9 (9) | 1033.49 (982.14) | 5.23% | 8.3 s |
| solomon | R201 | 100 | 4 (4) | 1253.23 (1252.37) | 0.07% | 27.1 s |
| solomon | R202 | 100 | 3 (3) | 1200.73 (1191.70) | 0.76% | 37.2 s |
| solomon | R203 | 100 | 3 (3) | 947.99 (939.50) | 0.90% | 40.9 s |
| solomon | R204 | 100 | 2 (2) | 846.42 (825.52) | 2.53% | 40.7 s |
| solomon | R205 | 100 | 3 (3) | 994.43 (994.42) | 0.00% | 28.9 s |
| solomon | R206 | 100 | 3 (3) | 931.63 (906.14) | 2.81% | 28.1 s |
| solomon | R207 | 100 | 2 (2) | 940.21 (890.61) | 5.57% | 40.2 s |
| solomon | R208 | 100 | 2 (2) | 734.51 (726.82) | 1.06% | 35.1 s |
| solomon | R209 | 100 | 3 (3) | 939.01 (909.16) | 3.28% | 30.4 s |
| solomon | R210 | 100 | 3 (3) | 961.94 (939.37) | 2.40% | 36.4 s |
| solomon | R211 | 100 | 2 (2) | 947.76 (885.71) | 7.01% | 28.7 s |
| solomon | RC101 | 100 | 14 (14) | 1701.55 (1696.95) | 0.27% | 7.7 s |
| solomon | RC102 | 100 | 12 (12) | 1572.19 (1554.75) | 1.12% | 8.9 s |
| solomon | RC103 | 100 | 11 (11) | 1262.02 (1261.67) | 0.03% | 8.7 s |
| solomon | RC104 | 100 | 10 (10) | 1137.25 (1135.48) | 0.16% | 9.0 s |
| solomon | RC105 | 100 | 13 (13) | 1640.57 (1629.44) | 0.68% | 8.4 s |
| solomon | RC106 | 100 | 11 (11) | 1432.12 (1424.73) | 0.52% | 8.5 s |
| solomon | RC107 | 100 | 11 (11) | 1239.08 (1230.48) | 0.70% | 7.9 s |
| solomon | RC108 | 100 | 10 (10) | 1146.66 (1139.82) | 0.60% | 8.1 s |
| solomon | RC201 | 100 | 4 (4) | 1437.51 (1406.94) | 2.17% | 25.9 s |
| solomon | RC202 | 100 | 3 (3) | 1448.95 (1365.65) | 6.10% | 33.7 s |
| solomon | RC203 | 100 | 3 (3) | 1090.61 (1049.62) | 3.90% | 36.8 s |
| solomon | RC204 | 100 | 3 (3) | 816.33 (798.46) | 2.24% | 66.3 s |
| solomon | RC205 | 100 | 4 (4) | 1309.91 (1297.65) | 0.94% | 31.4 s |
| solomon | RC206 | 100 | 3 (3) | 1156.16 (1146.32) | 0.86% | 25.1 s |
| solomon | RC207 | 100 | 3 (3) | 1086.88 (1061.14) | 2.43% | 31.4 s |
| solomon | RC208 | 100 | 3 (3) | 852.44 (828.14) | 2.93% | 20.8 s |
| lilim | LC101 | 53 | 10 (10) | 828.94 (828.94) | 0.00% | 4.8 s |
| sartori-buriol | bar-n100-1 | 50 | 6 (6) | 736.00 (732.00) | 0.55% | 4.4 s |
| sartori-buriol | bar-n100-2 | 50 | 5 (5) | 565.00 (554.00) | 1.99% | 5.3 s |
| sartori-buriol | bar-n100-3 | 50 | 6 (6) | 746.00 (746.00) | 0.00% | 5.4 s |
| sartori-buriol | bar-n100-4 | 50 | 12 (12) | 1172.00 (1150.00) | 1.91% | 4.0 s |
| sartori-buriol | bar-n100-5 | 50 | 6 (6) | 846.00 (838.00) | 0.95% | 5.3 s |
| sartori-buriol | bar-n100-6 | 50 | 3 (3) | 800.00 (784.00) | 2.04% | 6.2 s |
| sartori-buriol | ber-n100-1 | 50 | 13 (13) | 1857.00 (1854.00) | 0.16% | 4.5 s |
| sartori-buriol | ber-n100-2 | 50 | 6 (6) | 1506.00 (1484.00) | 1.48% | 5.4 s |
| sartori-buriol | ber-n100-3 | 50 | 3 (3) | 713.00 (713.00) | 0.00% | 9.4 s |
| sartori-buriol | ber-n100-4 | 50 | 3 (3) | 495.00 (494.00) | 0.20% | 8.0 s |
| sartori-buriol | ber-n100-5 | 50 | 5 (5) | 945.00 (944.00) | 0.11% | 5.2 s |
| sartori-buriol | ber-n100-6 | 50 | 14 (14) | 2147.00 (2116.00) | 1.47% | 4.9 s |
| sartori-buriol | ber-n100-7 | 50 | 7 (7) | 1938.00 (1935.00) | 0.15% | 5.2 s |
| sartori-buriol | nyc-n100-1 | 50 | 6 (6) | 641.00 (634.00) | 1.10% | 8.3 s |
| sartori-buriol | nyc-n100-2 | 50 | 4 (4) | 568.00 (563.00) | 0.89% | 13.0 s |
| sartori-buriol | nyc-n100-3 | 50 | 4 (3) | 457.00 (490.00) | +1 veh. | 12.7 s |
| sartori-buriol | nyc-n100-4 | 50 | 2 (2) | 561.00 (535.00) | 4.86% | 19.5 s |
| sartori-buriol | nyc-n100-5 | 50 | 2 (2) | 669.00 (669.00) | 0.00% | 13.2 s |
| sartori-buriol | poa-n100-1 | 50 | 12 (12) | 1618.00 (1582.00) | 2.28% | 4.9 s |
| sartori-buriol | poa-n100-2 | 50 | 15 (15) | 1554.00 (1539.00) | 0.97% | 4.9 s |
| sartori-buriol | poa-n100-3 | 50 | 11 (10) | 1267.00 (1291.00) | +1 veh. | 4.4 s |
| sartori-buriol | poa-n100-4 | 50 | 8 (7) | 1523.00 (1653.00) | +1 veh. | 4.6 s |
| sartori-buriol | poa-n100-5 | 50 | 6 (6) | 624.00 (624.00) | 0.00% | 4.6 s |
| sartori-buriol | poa-n100-6 | 50 | 3 (3) | 567.00 (562.00) | 0.89% | 8.0 s |
| sartori-buriol | poa-n100-7 | 50 | 5 (5) | 793.00 (772.00) | 2.72% | 4.0 s |
| cordeau | a2-16 | 16 | 2 | 294.25 (294.25) | 0.00% | 2.8 s |
| cordeau | a2-20 | 20 | 2 | 344.83 (344.83) | 0.00% | 6.7 s |
| cordeau | a2-24 | 24 | 2 | 431.12 (431.12) | 0.00% | 8.6 s |
| cordeau | a3-18 | 18 | 3 | 300.63 (300.48) | 0.05% | 2.4 s |
| cordeau | a3-24 | 24 | 3 | 344.83 (344.83) | 0.00% | 7.1 s |
| cordeau | a3-30 | 30 | 3 | 494.85 (494.85) | 0.00% | 12.1 s |
| cordeau | a3-36 | 36 | 3 | 585.04 (583.19) | 0.32% | 20.2 s |
| cordeau | a4-16 | 16 | 4 | 282.68 (282.68) | 0.00% | 1.2 s |
| cordeau | a4-24 | 24 | 4 | 375.02 (375.02) | 0.00% | 3.2 s |
| cordeau | a4-32 | 32 | 4 | 486.57 (485.50) | 0.22% | 5.8 s |
| cordeau | a4-40 | 40 | 4 | 557.94 (557.69) | 0.04% | 13.5 s |
| cordeau | a4-48 | 48 | 4 | 674.02 (668.82) | 0.78% | 31.2 s |
| cordeau | a5-40 | 40 | 4 | 498.41 (498.41) | 0.00% | 13.4 s |
| cordeau | a5-50 | 50 | 4 | 690.22 (686.62) | 0.52% | 30.9 s |
| cordeau | a5-60 | 60 | 5 | 814.76 (808.42) | 0.78% | 38.0 s |
| cordeau | a6-48 | 48 | 6 | 610.89 (604.12) | 1.12% | 19.1 s |
| cordeau | a6-60 | 60 | 6 | 827.85 (819.25) | 1.05% | 24.2 s |
| cordeau | a6-72 | 72 | 6 | 926.29 (916.05) | 1.12% | 48.9 s |
| cordeau | a7-56 | 56 | 6 | 724.09 (724.04) | 0.01% | 27.3 s |
| cordeau | a7-70 | 70 | 7 | 901.02 (889.12) | 1.34% | 38.2 s |
| cordeau | a7-84 | 84 | 7 | 1050.57 (1033.37) | 1.66% | 64.5 s |
| cordeau | a8-64 | 64 | 7 | 756.57 (747.46) | 1.22% | 28.2 s |
| cordeau | a8-80 | 80 | 7 | 961.49 (945.73) | 1.67% | 76.2 s |
| cordeau | a8-96 | 96 | 8 | 1244.07 (1229.66) | 1.17% | 95.2 s |
| cordeau | b2-16 | 16 | 2 | 309.41 (309.41) | 0.00% | 1.1 s |
| cordeau | b2-20 | 20 | 2 | 332.64 (332.64) | 0.00% | 0.9 s |
| cordeau | b2-24 | 24 | 2 | 444.71 (444.71) | 0.00% | 1.7 s |
| cordeau | b3-18 | 18 | 3 | 301.64 (301.64) | 0.00% | 0.7 s |
| cordeau | b3-24 | 24 | 3 | 394.51 (394.51) | 0.00% | 0.9 s |
| cordeau | b3-30 | 30 | 3 | 531.92 (531.44) | 0.09% | 1.9 s |
| cordeau | b3-36 | 36 | 3 | 603.79 (603.79) | 0.00% | 2.3 s |
| cordeau | b4-16 | 16 | 4 | 296.96 (296.96) | 0.00% | 0.6 s |
| cordeau | b4-24 | 24 | 4 | 373.74 (371.41) | 0.63% | 1.1 s |
| cordeau | b4-32 | 32 | 4 | 494.82 (494.82) | 0.00% | 1.5 s |
| cordeau | b4-40 | 40 | 4 | 656.63 (656.63) | 0.00% | 1.9 s |
| cordeau | b4-48 | 48 | 4 | 675.90 (673.81) | 0.31% | 3.6 s |
| cordeau | b5-40 | 40 | 5 | 613.73 (613.72) | 0.00% | 2.7 s |
| cordeau | b5-50 | 50 | 5 | 767.14 (761.40) | 0.75% | 3.1 s |
| cordeau | b5-60 | 60 | 5 | 910.12 (902.04) | 0.90% | 6.4 s |
| cordeau | b6-48 | 48 | 6 | 715.58 (714.83) | 0.10% | 2.6 s |
| cordeau | b6-60 | 60 | 6 | 865.61 (860.07) | 0.65% | 3.5 s |
| cordeau | b6-72 | 72 | 6 | 988.57 (978.47) | 1.03% | 7.7 s |
| cordeau | b7-56 | 56 | 7 | 828.60 (823.97) | 0.56% | 3.1 s |
| cordeau | b7-70 | 70 | 7 | 923.85 (912.62) | 1.23% | 4.6 s |
| cordeau | b7-84 | 84 | 7 | 1229.03 (1203.37) | 2.13% | 8.7 s |
| cordeau | b8-64 | 64 | 8 | 843.05 (839.89) | 0.38% | 4.4 s |
| cordeau | b8-80 | 80 | 8 | 1044.78 (1036.34) | 0.81% | 6.2 s |
| cordeau | b8-96 | 96 | 8 | 1198.93 (1185.55) | 1.13% | 14.0 s |

## Reading the table

* One seed per instance, reported as it came. Solomon's type-2 classes (R2, RC2: two
  to four long routes over wide windows) have the largest gaps and the largest spread
  between seeds; RC202 lands anywhere between 3% and 12% depending on the seed and
  the annealing settings.
* `+1 veh.` means a verified, complete plan with one vehicle more than the reference;
  under the hierarchical objective its distance is not comparable, so no gap is shown.
* Cordeau has no vehicle-count objective: the gap is on total routing cost.

References: solomon: SINTEF TOP VRPTW 100-customer table; cross-checked against Czech & Czarnas best solutions (sun.aei.polsl.pl/~zjc/best-solutions-solomon.html); lilim: SINTEF TOP PDPTW 100-task table (LC101 shares the C101 optimum); sartori-buriol: github.com/cssartori/pdptw-instances, solutions/README.md (retrieved 2026-11-13); cordeau: Ropke, Cordeau & Laporte (2007), Networks 49(4):258-272; compiled in Ho et al. (2018), Transp. Res. B 111:395-421
