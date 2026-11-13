# BENCHMARK_EVIDENCE_CORDEAU_A2_16_2026_08_27

Open academic DARP instance Cordeau (2006) `a2-16` (2 vehicles, 16 requests).
Vendored at `benchmark/instances/cordeau/a2-16.txt`. Header `2 16 480 3 30`.

Literature BKS **294.25** is the Ho et al. (2018) table value for this
instance (Cordeau 2006 / Ropke et al. 2007). That number is real-valued
Euclidean DARP. MobiRoute uses integer minutes, 5 min curb wait, and
Floyd-Warshall on rounded edges. **Do not quote 294.25 as a MobiRoute
objective.**

Claim level: `open_data_benchmark`. Not Moscow trips. Not aicenter
NYC/Chicago/DC dumps (those stay out of tree until a hashed subset exists).

## Artifact SHA-256

Directory `benchmark/instances/cordeau/`. Rows from `SHA256SUMS.txt`
(working-tree bytes). `benchmark/instances/**` is `-text`.

| File | SHA-256 |
|------|---------|
| `a2-16.txt` | `d25ab2609ad09a3ccbd533dbe8418e1ca6b65140114389d31aa8d6c111c0aa79` |
