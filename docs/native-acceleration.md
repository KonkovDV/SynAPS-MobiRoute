# Native insertion acceleration

Greedy, beam, ALNS, and online insertion **require** the PyO3 crate
`mobiroute_native`. Python SoA (`insertion_kernel.py`) is an algebra oracle for
lockstep tests, not a solver backend. The DARP model is not FJSP. Heuristics
remain non-optimal.

## Status (2026-08-12)

| Layer | Status |
| --- | --- |
| Rust `mobiroute_native` scoring + `score_fleet` | REQUIRED for greedy / beam / ALNS / online |
| Python SoA insertion (`insertion_kernel.py`) | Oracle / lockstep tests only |
| Claimed ×N wall-clock speedup | FORBIDDEN without a measured artifact in `benchmark/results/` |
| OPTIMAL from greedy / native scoring | FORBIDDEN |

Generator `medium` is **60 vehicles / 1000 requests**, not 60 trips.

## Build

```bash
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

On Windows GNU (Cyrillic profile paths), the crate sets `rust-lld` for
`x86_64-pc-windows-gnu`. MSVC remains the default host target.

`MOBIROUTE_DISABLE_NATIVE=1` unloads the extension; solvers then raise
`RuntimeError` instead of falling back to Python SoA.

CI `test` and `native-accelerator` jobs build the wheel.

## Semantics

Scoring is sequential and deterministic: lexicographic min of
`(duration, wait_sum, -max_load, i, j)` (and `mid` when the new trip has a VIA).
`wait_sum` is **passenger** delay after earliest (0 if the vehicle snaps to earliest).
The winning `(i, mid, j)` is materialized once through `simulate_stop_sequence`.
Trip table stride is **16** (`via`, `via_svc`). Native `best_insert` returns a
6-tuple; `mid=-1` if there is no VIA. `score_fleet` returns one 7-tuple per
feasible vehicle: `(fleet_index, i, mid, j, dur, wait, max_load)`.
Candidates are simulated on a virtual insert (no copied stop arrays).
Rebuild the wheel after ABI change.
Pickup dwell is \(\max(\mathrm{board},5)\). Dropoff snaps to
`appointment_start - 30` when that field is set (lobby cap, not cabin hold).
VIA detour uses itinerary minutes including VIA service. Vehicle unavail covers
travel and wait, not only boarding. Compat/assist checks run on the **new** trip;
capacity, stretcher, and windows still cover the whole route.

## Measured wall-clock (not a portable product claim)

Remeasured 2026-08-12 after occupancy lockstep (RT-24), CPython 3.13.7,
Windows 11, 20 logical CPUs, generator `medium` seed 42
(60 vehicles / 1000 requests, 0 VIA). Artifact:
`benchmark/results/speed-2026-08-12/day_speed.json` (gitignored).
Greedy served 991/1000, status `PARTIAL`, never `OPTIMAL`. Not real MAST trips.

| Backend | Greedy wall-clock |
| --- | --- |
| Python SoA (oracle only; not a solver path) | 310.2 s (historical) |
| `mobiroute_native` before `score_fleet` / virtual insert | 3.73 s |
| `mobiroute_native` after `score_fleet` / virtual insert | **1.97 s** |

Do not advertise a portable ×N speedup.

## Stress day `stress_200` (not a portable product claim)

Same machine, 2026-08-12, generator `stress_200` seed 42:
**200 vehicles / 3200 requests**, mixed WAV/VIA/wait-return/quota/unavail/dead
vehicles, then a disruption shake. Artifact:
`benchmark/results/stress-2026-08-12/stress_200.json` (gitignored).
Not real MAST trips. Greedy never `OPTIMAL`.

Re-measure after cancel cascade + seed peel + final quota lockstep
(CPU was also busy; wall-clock is a sample, not a SLA):

| Phase | Wall-clock | Served / active | Notary |
| --- | --- | --- | --- |
| Day-ahead greedy (Rust) | 38.2 s | 2589 / 3045 (`PARTIAL`) | pass |
| Batch disruption (5 WAV down, 3 drivers, 25 cancel, 20 no-show) | 15.8 s | 2531 / 2999 (`PARTIAL`) | pass |
| Traffic +8 min (full re-greedy) | 27.6 s | 2242 / 2999 (`PARTIAL`) | pass |
| 8 online medical inserts | 13.8 s (~1.4–2.0 s each) | 8/8 accepted | pass |
| **Pipeline total** | **95.5 s** | — | — |

Earlier the same day-ahead finished in 16.3–24.2 s on a quieter CPU; treat
16–40 s as the observed band, not a SLA. Batch disruption previously left
one `QUOTA:` notary; that hole is closed.
