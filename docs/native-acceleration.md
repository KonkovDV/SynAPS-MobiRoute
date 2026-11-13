# Profiling and the Rust kernels

Two hot paths are compiled with PyO3 (`native/mobiroute_native`):

| Kernel | Used by | Python reference | Parity tests |
| --- | --- | --- | --- |
| `VrpKernel` (`src/vrp.rs`) | `mobiroute.vrp`: regret repair, insertion tests, exact route timing, guided ejection | `vrp/insertion.py`, `Alns._eject_insert` | `tests/test_vrp_native.py` — identical plans, identical ALNS trajectories |
| `InsertionEngine` (`src/lib.rs`) | paratransit kernel: greedy, beam, ALNS, online insertion | `solvers/insertion_kernel.py` (structure-of-arrays oracle) | `tests/test_insertion_kernel.py`, `test_native_*` |

Without the extension the rich-VRP engine falls back to Python and gives the
same plans, only slower. `MOBIROUTE_DISABLE_NATIVE=1` forces the fallback. The
paratransit solvers require the extension.

```bash
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

## How the rich-VRP engine got fast

Every step started from a profile (`cProfile`, sorted by own time), not from a
guess.

1. **Pure Python, PDPTW.** `_pair_candidates` (the pickup/delivery scan) and
   route-state rebuilds took most of the time: about 2 ms per ALNS iteration on
   100-customer instances. Acceptable for a reference, not for production.
2. **Pure Python, DARP.** 94% of the time went into exact ride-limit checks,
   and a third of that was allocating 1.75 M labelled arc objects. A flat
   three-list Bellman-Ford (`insertion.exact_feasible`) cut an iteration from
   15.6 to 9.1 ms with the same answers (checked against the labelled version
   on 720 random sequences).
3. **Rust repair.** The whole regret-k repair moved to `VrpKernel` — one call
   per ALNS iteration instead of thousands of evaluations from Python. Every
   floating-point expression keeps the Python evaluation order, ties break the
   same way and the noise comes from the same SplitMix64 stream, so the two
   backends return identical plans.
4. **The next bottleneck was in Python.** With repair in Rust, Shaw removal
   dominated: it re-sorted all orders by relatedness for every removed order.
   Relatedness is static, so each order's ranked neighbour list is computed
   once and cached: R101 went from 0.59 to 0.32 ms per iteration.
5. **Guided ejection.** One ejection step made about 200 Python→Rust calls
   (1.1 ms). The whole scan moved into `VrpKernel.eject_insert`: one call per
   step, same choice as the Python reference.

Current cost per iteration ([benchmarks/vrp-speed.md](benchmarks/vrp-speed.md),
`python benchmark/measure_vrp_speed.py`): Rust is 12× faster on Solomon R101,
14× on a Sartori–Buriol PDPTW, 42× on Cordeau DARP (exact ride checks), with
identical plans. On the 8-type cargo day it is 4.4×: there the per-route
vehicle-type assignment, still in Python, is the next bottleneck — the obvious
next candidate for the kernel.

## How the paratransit kernel got fast

`stress_200` (200 vehicles, 3200 requests, seed 42, one thread):

| Version | Day-ahead greedy | Full pipeline* |
| --- | ---: | ---: |
| 0.2.7 | 47.9 s | 67.6 s |
| 0.3.0 | 2.8 s | 13.1 s |

\*day-ahead, batch disruption, traffic delay, eight urgent inserts.

cProfile put 56% of greedy time into `pooling_stops_violate`, which rebuilt the
request map for every candidate; the map is now passed in. The Rust side keeps
a persistent fleet per solve (`set_fleet`, `score_stored`, `commit_insert`),
reuses the prefix state of the route when scanning `(i, j)`, scores vehicles
in parallel with rayon and forks copy-on-write for online insertion. A trip is
one 64-byte row, because scoring reads one trip at a time.

## What did not help

* Splitting fleet scoring into "empty vehicles first, then loaded vehicles
  under a duration cap" made one rayon call into several and lost about 1 s
  on `stress_200`.
* GPU: the paratransit matrix is 13×13 and the insertion test is sequential and
  branchy; transfer and launch costs would dominate. GPU VRP solvers win by
  evaluating many independent neighbourhood moves at once, which is a
  different algorithm.

Timings are samples on one machine (Linux x86_64, Python 3.13), not an SLA.
