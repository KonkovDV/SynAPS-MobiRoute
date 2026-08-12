# Benchmarks

Synthetic only. Never label as Moscow operational data.

```bash
python benchmark/generate_day.py --mode tiny --seed 42 --out benchmark/instances/tiny.json
python benchmark/run_benchmark.py --mode tiny --seed 42 --out-dir benchmark/results/tiny
```

See `docs/benchmark-protocol.md`.
