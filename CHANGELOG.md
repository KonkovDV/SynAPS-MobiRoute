# Changelog

## 0.2.1 — 2026-08-13

- Rolling-horizon day-ahead composition (`solve_rolling_horizon`, CLI `--solver rhc`):
  greedy pooling insertion per time window with seeded previous routes.
  Heuristic only — never `OPTIMAL`. LBBD / Activated Benders remain PLANNED.
- Research cards 6 and 10 filled from primary sources (TRC 169/104801; TCRP Synthesis 168).
- README stress_200 pipeline sample aligned with the measured **8.1 s** band
  (not a SLA). Not real MAST trips.

## 0.2.0 — 2026-08-12

- Implementation audit of 0.1.1 (`docs/implementation-audit-2026-08-12.md`).
- Explicit `DriverAssignment`; no depot-only or `drivers[0]` fallback; one driver per route.
- Route graph: depot start/end, load after stop, passenger itineraries, deadhead.
- Tiny CP-SAT: driver variables, appointment_start/end, frozen, unavailable intervals,
  independent notary; `OPTIMAL` only if OR-Tools OPTIMAL **and** notary; else `NOT_VERIFIED`.
  Fallback never `OPTIMAL`. Sequential model (not pooling) labelled honestly.
- Greedy pooling insertion with dynamic passenger/wheelchair load, detour ratio, stretcher conflict.
- Insertion hot path: Rust `mobiroute_native` (PyO3) is **required** for greedy / beam /
  ALNS / online insert. Python SoA remains an oracle for lockstep tests only.
  No claimed portable ×N speedup.
- Harsh synthetic day `stress_200`: 200 vehicles / 3200 requests, mixed WAV/VIA/
  wait-return/quota/unavail/breakdowns, plus a disruption shake benchmark
  (`python benchmark/run_stress_day.py`). Not real MAST. Greedy never OPTIMAL.
  On this machine, seed 42: day-ahead greedy about **4.0–4.1 s**; the same run with
  breakdowns, cancellations, traffic replan, and 8 urgent inserts about
  **8.1 s** (was 10–11 s). Sample, not a SLA. Prefix-state insert walk, persistent native
  fleet, `eval_route` seed/emit, Arc copy-on-write fork, and O(1) passenger
  quota lookup. Greedy never OPTIMAL.
- Red Team of the speed path: online stash no longer overwrites the baseline
  kernel; combined disruption+emergency replans before insert; full-plan notary
  after online (`tests/test_redteam_combat.py`).
- Native CPU path: prefix-state reuse and incremental `(i, j)` / VIA walk
  (Savelsbergh / Hu–Omega 2026 analogue, not Gschwind–Drexl O(1)); Arc
  copy-on-write `fork`; precomputed integer detour caps. Greedy never OPTIMAL.
- Stress `stress_200` found later pooling could lengthen an already-accepted
  ride past the passenger-day hour quota; greedy/online now recheck every
  onboard passenger against the cap (notary `QUOTA:`).
- Seeded disruption recovery: cancel/no-show cascade to wait-return children;
  greedy peels seed passengers who already exceed the day cap and locksteps
  quota before emit so the notary cannot see a leftover `QUOTA:`.
  Traffic/+unavail seeds that fail `eval_route` peel the last dropoff and its
  wait-return children, then try the peeled trips back onto the same vehicle
  before the global insert loop. Wiping the bus was a near-full re-greedy.
  `score_stored` can take a vehicle index list and a duration cap. Greedy never OPTIMAL.
  GPU is the wrong tool for this kernel (13×13 zone matrix, sequential
  branchy insert); see `docs/native-acceleration.md`.
- Unknown vehicle depot is `ValueError` (not a travel-matrix `KeyError`).
  Online insert and beam report `insertion_backend` like greedy.
- Versioned online plans (`plan_id`, `base_plan_id`, `event_type`) including appointment change.
- Fairness: P95 wait/ride, wheelchair on-time, coverage; never `fair_by_single_metric`.
- Per-trip explanations and extra reason codes.
- Generator modes `driver_unavailable`, `vehicle_breakdown`.
- Policy-shaped ops suite (Moscow social-taxi rules + world paratransit analogues):
  `same_vehicle_as` / wait-return, eighteen `ops_*` generators, `mobiroute ops-benchmark`.
  `service_area` is a hard compatibility check. Stretcher exclusive, scooter mask,
  medical-vs-dacha, untrained driver, agency missed-trip recovery, VIA (clinic then
  pharmacy), remaining hour quota.
  Measured tables: `docs/ops-cases-and-benchmark-2026-08-12.md`,
  `docs/edge-cases-algebra-synaps-2026-08-12.md`.
  Not real MAST trips. Greedy never OPTIMAL.
- Red Team of algebra + solvers + notary + pipeline (`docs/redteam-algebra-2026-08-12.md`):
  stretcher exclusive in the notary, vehicle shift end, empty-vehicle idle,
  outbound-before-return sort, FIFO paired insert, disruption route seeding,
  diagnose no longer maps every appointment miss to `APPOINTMENT_CONFLICT`.
  FIFO wait-return 3/3; FIFO subscription `PARTIAL` (verified), not `NOT_VERIFIED`.
- Unified `max_wait`: passenger delay after earliest **and** onboard hold (empty idle free).
  `appointment_start` is lobby metadata; dropoff may be early; `appointment_end` remains hard.
- Zone travel is Floyd–Warshall on the labelled matrix (not live Moscow roads).
- Adaptive ALNS: Shaw / worst / route / random destroy, roulette weights, SA
  (never fewer served; never `OPTIMAL`). Pattern from SynAPS ALNS + Ropke/Pisinger,
  DARP operators from Hu et al. Omega 2026 (feasibility-test ALNS) — not FJSP.
- Pickup curb wait \(\max(board,5)\) and appointment earliest alight \(start-30\)
  (DREDF/FTA analogues, not Moscow law). Early-alight wait is forbidden if another
  passenger is still onboard. Itinerary `travel_path` is the zone shortest path,
  including VIA.
- Red Team close: VIA detour includes pharmacy dwell; vehicle unavail covers
  travel/wait; online insert does not retime frozen clocks and subtracts used
  quota; notary flags unexplained VIA/dropoff idle. Native simulate reuses the
  pickup-departure buffer (no per-candidate alloc).
- Native ABI: trip stride 16 (via + via service); `best_insert` returns a 6-tuple
  `(i, mid, j, dur, wait, max_load)` with `mid=-1` if no VIA. `score_fleet` scores
  every vehicle in one call. Virtual insert (no sequence copy). Rebuild the wheel
  after ABI change. CI pytest builds the native wheel.

## 0.1.1 — 2026-08-12

- Greedy **pooling insertion** (interleaved pickup/dropoff), not sequential PU–DO only.
- Online insertion into existing routes; reject if a frozen trip would move.
- Beam search heuristic; incremental-repair named lane.
- Driver accessibility training checked in simulation and feasibility.
- Deeper research cards (CP 2026, IJOC Benders, OR Spectrum 2026, IJCAI 2024).
- Still synthetic_benchmark only. ALNS/LBBD/RHC remain PLANNED.

## 0.1.0 — 2026-08-12

- Initial public engineering prototype.
- SynAPS audit, Moscow problem map, research and competitor notes.
- Domain models, schemas, FIFO / nearest / greedy / CP-SAT-tiny, online insertion,
  disruption recovery (cancel, no-show, traffic, breakdown), fairness metrics,
  privacy redaction, HITL override journal, CLI, synthetic Moscow-zone generator,
  adversarial tests.
- Community files: CI, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CITATION.cff.
- Claim level: `synthetic_benchmark` only.
