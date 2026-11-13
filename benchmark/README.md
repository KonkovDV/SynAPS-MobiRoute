# Benchmarks

Scripts that produce every number in the README and on the site. Each writes
raw JSON to `benchmark/results/` (not committed) and, where noted, a Markdown
table to `docs/benchmarks/`. Rules: [docs/benchmark-protocol.md](../docs/benchmark-protocol.md).

| Script | What it measures | Output |
| --- | --- | --- |
| `vrp_benchmark.py` | rich-VRP engine on 130 public instances (Solomon, Li & Lim, Sartori–Buriol, Cordeau), gaps to references | `docs/benchmarks/vrp-public-benchmarks.md` |
| `exact_vs_alns.py` | ALNS against CP-SAT proven optima on random instances of the full model | `docs/benchmarks/exact-vs-alns.md` |
| `ortools_vs_alns.py` | OR-Tools Routing (PCI + GLS) against ALNS at equal wall clock | `docs/benchmarks/ortools-vs-alns.md` |
| `realtime_dispatch.py` | live dispatch policies on shuttle and plant days | `docs/benchmarks/realtime-dispatch.md` |
| `measure_vrp_speed.py` | cost of an ALNS iteration, Python reference vs Rust kernel | `docs/benchmarks/vrp-speed.md` |
| `solver_lab.py` | Cordeau a2-16 through CP-SAT, MIP (SCIP, HiGHS, CBC), LP bound, ALNS and OR-Tools | `docs/benchmarks/solver-lab-a2-16.md` |
| `export_site_data.py`, `export_vrp_site_data.py` | data and figures for the site | `site/data/`, `docs/img/` |
| `run_stress_day.py`, `measure_day_speed.py`, `run_ops_benchmark.py`, `run_benchmark.py`, `generate_day.py`, `generate_moscow_day.py` | paratransit kernel: stress day, speed, synthetic operator scenarios | `benchmark/results/` |

Instances and their provenance: [instances/README.md](instances/README.md).
Reference values: [references/](references).

```bash
python benchmark/vrp_benchmark.py --iterations 30000 --cordeau-iterations 10000 --workers 3
python benchmark/exact_vs_alns.py --instances 40
python benchmark/ortools_vs_alns.py --time-limit 10
python benchmark/realtime_dispatch.py --with-ortools
python benchmark/measure_vrp_speed.py
python benchmark/solver_lab.py
python benchmark/export_vrp_site_data.py
```
