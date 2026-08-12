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
The winning `(i, mid, j)` is committed in the native fleet; Python builds
`RoutePlan` from `eval_route` / `trial_eval` stop times. FIFO and the rare
frozen-retry path still use `simulate_stop_sequence`.
Trip table stride is **16** (`via`, `via_svc`). One trip row is 64 bytes (one
cache line); the kernel keeps AoS because scoring is trip-at-a-time, not a
PDX/SoA dimension scan (Kuffo/Krippner/Boncz, SIGMOD 2025). `best_insert`
returns a 6-tuple; `mid=-1` if there is no VIA. `score_fleet` returns one
7-tuple per feasible vehicle: `(fleet_index, i, mid, j, dur, wait, max_load)`.
Candidates are simulated on a virtual insert (no copied stop arrays).
The engine keeps a persistent fleet (`set_fleet` / `score_stored` / `commit_insert`)
and can `eval_route` / `eval_fleet` an existing sequence (seed + emit) without
Pydantic. `score_stored(new_idx, fleet_idx=None, max_dur=None)` scores a subset
of vehicles and can abort a vehicle whose current depot-to-depot duration
already exceeds `max_dur`. Online insertion forks that engine (`Arc` copy-on-write of travel and
trip tables) and `append_trip` instead of repacking 3200 trips.
`best_insert` reuses the original-route prefix (Savelsbergh concatenated
evaluation; Hu/Omega 2026 linear-test analogue) and walks `(i, j)` / VIA
incrementally. It is **not** Gschwind–Drexl O(1) FTS: VIA, stretcher, unavail
occupancy, and appointment lobby snap break that auxiliary-data contract.
Rebuild the wheel after ABI change.
Pickup dwell is \(\max(\mathrm{board},5)\). Dropoff snaps to
`appointment_start - 30` when that field is set (lobby cap, not cabin hold).
VIA detour uses itinerary minutes including VIA service. Vehicle unavail covers
travel and wait, not only boarding. Compat/assist checks run on the **new** trip
during insertion; `eval_route` (existing sequence) rechecks every pickup.
Capacity, stretcher, and windows still cover the whole route.

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

Re-measured 2026-08-12 after tail-peel + same-vehicle reinsert of dropped
trips, skip redundant `set_vehicle`, TLS pickup-dep reuse, and `score_stored`
subset/`max_dur` ABI (two consecutive runs, seed 42). Sample, not a SLA:

| Phase | Wall-clock | Served / active | Notary |
| --- | --- | --- | --- |
| Day-ahead greedy (Rust) | 4.0–4.1 s | 2589 / 3045 (`PARTIAL`) | pass |
| Batch disruption (seeded replan) | 0.93–0.94 s | 2533 / 2999 (`PARTIAL`) | pass |
| Traffic +8 min (seeded replan) | 2.49–2.50 s | 2233 / 2999 (`PARTIAL`) | pass |
| 8 online medical inserts | 0.54–0.61 s | 8/8 accepted | pass |
| **Pipeline total** | **8.1 s** | — | — |

Earlier the same day the pipeline was about 95 s, then ~24 s after stored-fleet
scoring, then **13–15 s** after persistent eval, then **10–11 s** after prefix
insert. Treat **8.1 s** as the current observed band on this machine, not a
product SLA. Served counts after traffic may differ from the 10–11 s band
because peel keeps a feasible tail instead of wiping the bus. Greedy never
`OPTIMAL`. Batch disruption previously left one `QUOTA:` notary; that hole is
closed.

## Algebra (what moved the needle, what did not)

Depot-to-depot duration is monotonic in extra stops. A two-phase “score empties,
then skip loaded with `current_dur > D`” is correct only after a
**quota-feasible** \(D\). On `stress_200` that split turned one 200-way Rayon
call into several smaller ones and **lost** about 1 s on day-ahead. The hot
path stays one `score_stored` over the fleet.

Uniform +8 min on every arc makes most seeded routes fail `eval_route` (13/188
ok before peel). Peeling the last dropoff (and wait-return children) then
re-inserting dropped trips onto **that** vehicle keeps a feasible core without
a 200-vehicle search per trip. Leftovers still go to global greedy — that is
why traffic is ~2.5 s, not sub-second. A 2–3 s **pipeline** would need
day-ahead itself under ~1.5 s; that is still ~3000 sequential lex inserts
against 200 vehicles and is not this pass.

## GPU (honest no)

Not for this kernel. The travel matrix is **13×13** integers. The hot path is a
sequential, branchy insertion test (VIA, stretcher exclusive, unavail occupancy,
appointment lobby snap, hour quota). NVIDIA cuOpt (open-source, Apache 2.0)
speeds VRP by evaluating **many independent neighborhood moves** in parallel
(thread block per hypothetical route, insert/eject/swap nets; NVIDIA tech blog
2024, cuOpt 25.08 routing). That is ALNS/local-search parallelism, not one
constructive lex insert against a persistent CPU fleet. PCIe plus kernel launch
would dominate a 13-zone table already in L1. Stay on CPU (Rayon over vehicles).
A future ALNS neighborhood on a large Euclidean instance could revisit cuOpt;
it would be a different solver, never `OPTIMAL` from greedy, and not this
notary-locked DARP.
