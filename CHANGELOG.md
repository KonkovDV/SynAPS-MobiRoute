# Changelog

## Unreleased

- IMPLEMENTED: finalize reconciles the served side too. A trip in
  `served_requests` can no longer publish an `accepted=False` rejection record,
  and a trip claimed on both sides keeps the rejection while accounting reports
  the clash. One trip also publishes one explanation: a duplicate record for the
  same trip id collapses to the last decision instead of shipping two
  contradicting rows. Explanation hygiene only — served/rejected sets, the
  notary verdict and status are unchanged.
- IMPLEMENTED: online insertion re-checks the seated driver against the new
  request. A committed route whose driver is not accessibility-trained is now
  refused for a boarding-assistance trip instead of being scored, and the driver
  of a committed route is never silently swapped (that is manual review). The
  rejection detail lists per-vehicle evidence (`NO_COMPATIBLE_VEHICLE`,
  `NO_QUALIFIED_DRIVER`, `NO_DRIVER`, `INSERT_INFEASIBLE`, `POOLING_BLOCKED`,
  `SIMULATION_FAILED`), deduplicated, and no longer ends in a dangling
  separator when there is no evidence; when more than eight vehicles refused,
  the detail names how many were omitted instead of dropping them silently.
  Frozen protection now uses the same predicate as the diff it publishes
  (vehicle, driver and clocks), so a committed route can no longer be re-seated
  or retimed under a frozen promise while the published `PlanDiff` reports the
  break. Search-side refusal only — no new feasibility claim and no
  driver-certification claim.
- IMPLEMENTED: ALNS republishes `plan_id` after re-stamping its own
  `solution_type`, `status` and `config_hash`. The identity now fingerprints the
  published ALNS answer instead of the greedy seed pass that built the routes
  (same defect class as RHC in 0.2.4), so two destroy/iteration settings can no
  longer share one plan identity. Existing ALNS plan ids intentionally change.
  Identity only — no new feasibility or optimality claim.
- IMPLEMENTED: the incremental-repair lane publishes its own `config_hash` and
  `plan_id`. Re-labelling the recovery answer as `INCREMENTAL_REPAIR` left the
  identity and the execution hash fingerprinting the recovery lane, so a repair
  plan and the recovery plan it was built from could share one identity while
  publishing different `solver_config` values (same defect class as RHC in 0.2.4
  and ALNS above). The new hash chains the recovery hash, so provenance is kept.
  Existing incremental-repair plan ids intentionally change. Identity only — no
  new feasibility, recovery or optimality claim.
- IMPLEMENTED: a manual override republishes what it changed. Rejecting a served
  trip through the operator journal now rewrites that trip's explanation (it
  could still claim service), re-fingerprints `config_hash` over the override
  and republishes `plan_id`, so an overridden plan is no longer published under
  the identity of the plan the operator overrode. The journal entry must name
  the trip being overridden, `apply_reject` only records `REJECT`, and an empty
  reason code is normalised instead of published. Stop clocks and load maps are
  removed by trip ownership (`t1:PU`), so overriding `t1` no longer strips the
  clocks of `t10`. Ride/wait summaries, itineraries and inherited fairness are
  dropped with the trip so a leftover metric cannot still describe service.
  Totals the override cannot re-measure (`violations` and the ride / quota /
  billable minutes) are dropped instead of republished, and the override chains
  what it overrode (`base_plan_id`, `event_type=MANUAL_OVERRIDE`).
  Re-verification publishes the dropped totals again.
  Audit and identity hygiene — a manual override is still not an operational
  authorization claim.
- IMPLEMENTED: greedy (pooling and sequential/FIFO) re-checks the seated driver
  against every new trip. An untrained driver already on the van is no longer
  kept for a boarding-assistance insert; day-ahead may swap to a trained driver
  on that unfinished route. Online still refuses a committed untrained driver
  (manual review). A swap that is scored but not chosen is rolled back in the
  native fleet payload before the plan is emitted, so published clocks are
  measured against the driver the route publishes and a losing candidate can no
  longer hide the seated driver's rest window (notary `DRIVER_REST`).
  Search-side qualification only — no driver-certification claim.
- IMPLEMENTED: CP-SAT fallback republishes `config_hash` and `plan_id` after
  re-labelling the greedy answer as `CPSAT_FALLBACK_GREEDY` (too-large instance
  or missing OR-Tools). The fallback can no longer share the greedy seed's
  identity, and a missing OR-Tools install no longer publishes `status=ERROR`
  over a plan the notary verified: both fallback lanes publish the status of the
  plan they hand over (never `OPTIMAL` or `FEASIBLE`), and the missing engine
  stays in `solver_config` (`reason`, `error`). Existing fallback plan ids
  intentionally change. Identity and status honesty only — the fallback remains
  a heuristic and never `OPTIMAL`.

## 0.2.5 — 2026-09-09

- Package identity matches `main`: `__version__` / `pyproject.toml` / READMEs /
  `APPLICATION.md` / `CITATION.cff` are **0.2.5**. Dated 0.2.2 / 0.2.3 / 0.2.4
  changelog pins are not rewritten. Native crate stays **0.2.0** (ABI unchanged).
- IMPLEMENTED: unresolved insert diagnoses necessary conditions (quota, fleet,
  driver) before `WAIT_RETURN_INFEASIBLE`. A wait-return that cannot be placed
  no longer hides a proven resource or entitlement failure. Frozen clock blocks
  that leave no insertion use `MANUAL_REVIEW_REQUIRED` and the same frozen-trip
  detail as vehicle-reassignment rollback.
- IMPLEMENTED: leftover rebuild/peel rewrites explanations; finalize drops
  `accepted=True` records for unserved trips. The published explanation cannot
  contradict the served/rejected sets.
- IMPLEMENTED: greedy and online pre-search quota gates use `quota_debit_minutes`
  (BILLABLE curb wait + alighting), matching seed-reinsert and the notary lower
  bound. Ride minutes alone cannot understate the debit. A remaining entitlement
  of zero still refuses before search, as before.

## 0.2.4 — 2026-09-09

- Package identity matches `main`: `__version__` / `pyproject.toml` / READMEs /
  `APPLICATION.md` / `CITATION.cff` are **0.2.4**. Dated 0.2.2 / 0.2.3 changelog
  pins are not rewritten. Native crate stays **0.2.0** (ABI unchanged).
- IMPLEMENTED: greedy leftover rebuild/peel and unresolved greedy insert no
  longer stamp `TIME_WINDOW_CONFLICT`. Quota and wait-return keep their codes;
  everything else uses `diagnose_rejection` (unresolved → `MANUAL_REVIEW_REQUIRED`).
  Frozen-protect rollback uses `MANUAL_REVIEW_REQUIRED` and keeps the detail that
  insertion would change frozen trips. `TIME_WINDOW_CONFLICT` remains in the
  vocabulary; search no longer fabricates it.
- IMPLEMENTED: removed unused `_pool_candidates_native` (and its `score_fleet`
  import) from greedy. Live pooling scoring is `score_stored` +
  `pooling_stops_violate`. The native batch ABI `score_fleet` stays for tests.
- Dated 2026-08-12 snapshot docs keep their measured tables. Errata record:
  Cordeau a2-16 is an `open_data_benchmark` gate, not literature BKS; ALNS/RHC
  are heuristics on current main (LBBD still a stub); RT-13's fabricated
  time-window label is stale; greedy leftover no longer matches the seed-42
  `TIME_WINDOW_CONFLICT` strings in the ops snapshot.

- IMPLEMENTED: `check_plan` no longer accepts `only_vehicles`. Finalize enriches
  every route. A subset cannot look like a notary. Search pooling labels use the
  notary code (`POOLING_NOT_OPTED_IN` under `OPT_IN`, not a hard-coded
  `FORBIDDEN`). A pickup/dropoff suffix is `POOLING_INCOMPLETE_SEQUENCE`, not a
  clean mix. `trial_exceeds_quota` no longer takes an ignored `trips` map.
  Solvers leave `input_hash` unsigned; only `finalize_result` publishes
  `fingerprint_problem`. RHC does not re-run greedy after the open last window.
  Docs (plan-diff, limitations, formulation, benchmark-protocol, problem-input,
  linked-trip) match that code. Verifier hygiene — not a new optimality claim.

- IMPLEMENTED: `BILLABLE_SERVICE` quota debit charges the dwell the plan actually
  holds (`max(boarding_duration, 5)` + ride + alighting) in the notary, the
  insertion gates, CP-SAT and the `diagnose_rejection` quota lower bound. A
  declared boarding below the enforced curb wait can no longer understate a
  passenger-day entitlement. Not an operator tariff, billing or legal claim.
- IMPLEMENTED: nearest and beam re-check driver qualification for every trip, so
  an already seated untrained driver can no longer keep a trip that needs
  boarding assistance; a rebuild failure now reports diagnosed evidence instead
  of a fabricated time-window conflict. Accessibility-training data is policy
  input, not a certification claim.
- IMPLEMENTED: `NEAREST_FEASIBLE` ranks candidate vehicles by the deadhead from
  the last accepted dropoff and falls back to the depot only for an empty route.
  The depot-anchored score preferred a vehicle that had already driven away.
  Ranking only — feasibility, quota and notary checks are unchanged.
- IMPLEMENTED: `finalize_result` verifies the whole plan and enriches every
  route. There is no `changed_vehicle_ids` / `only_vehicles` notary mode.
  Verification breadth only — no new feasibility guarantee.
- IMPLEMENTED: RHC republishes `plan_id` after re-stamping, so the identity
  fingerprints the RHC configuration that is actually published instead of the
  greedy pass that built the routes. Two window settings can no longer share one
  plan identity. Existing RHC plan ids intentionally change; `plan_identity` is
  now the shared helper in `solvers/finalize.py`. Identity only — no new
  feasibility or optimality claim.

## 0.2.3 — 2026-09-09

- Package identity matches `main`: `__version__` / `pyproject.toml` / READMEs /
  `APPLICATION.md` / `CITATION.cff` are **0.2.3**. Tagged 0.2.2 remains the
  2026-08-30 pin `6178c93`; this drop records the later contract stack and
  kernel pin on the package version that reviewers actually read.
- SynAPS pin bumped to
  [`07f11ebb`](https://github.com/KonkovDV/SynAPS/commit/07f11ebb31357ff65c8c078f94207c965a255cc1)
  to close the 2026-09-09 lag (two kernel commits: domain-pin record, then
  industrial seed42 RHC precedence). ADR-0004 regressions stay: fail-closed
  coverage, calendar encode, claims-lint. DARP search is still this repo.
  KI-N12 stays closed. Not a courtesy float on future kernel HEAD.
- IMPLEMENTED: pooling `FORBIDDEN` / `OPT_IN` is simultaneous onboard occupancy.
  Sequential PU→DO pairs on one vehicle are not pooling. Search and notary use
  the same walk.
- IMPLEMENTED: insertion and CP-SAT quota gates use `quota_debit_basis`
  (`BILLABLE_SERVICE` includes boarding and alighting), matching the notary.
- IMPLEMENTED: cancel/no-show cascade follows both `same_vehicle_as` and
  `insert_immediately_after`.
- IMPLEMENTED: day-ahead and dispatch `input_hash` is always `fingerprint_problem`
  after finalize. Beam / nearest / CP-SAT no longer stamp a full JSON dump.
- IMPLEMENTED: `PlanDiff` and online freeze protection treat pickup/dropoff
  departure shifts (dwell-only) as retiming / broken frozen, not unchanged.
- IMPLEMENTED: `PlanDiff` reports same-vehicle retiming, driver changes and
  add/remove-only routes. Frozen trips with shifted clocks are no longer
  classified unchanged. Assignment-churn keys keep their previous meaning;
  see `docs/plan-diff-contract.md`. Reporting only — not frozen-promise
  certification.
- IMPLEMENTED: versioned laboratory `OperatorPolicy` is distinct from solver
  capability. Pooling permission, mandatory fulfillment groups and quota-debit
  basis are explicit; ride duration, quota debit and billable service are
  separate clocks. Dispatch outcomes are never operational authorization.
  See `docs/operator-policy-contract.md`. Input fingerprints intentionally
  change.
- IMPLEMENTED: planning-input fingerprints include vehicle wheelchair-type
  compatibility. Changing this operative capability can no longer retain the
  previous fingerprint. Existing fingerprint values intentionally change.
- IMPLEMENTED: rejection diagnostics distinguish supported resource/quota evidence
  from unresolved search failure; mixed causes and appointment metadata cannot
  fabricate a time-window explanation. Cordeau now requires verified, nonempty,
  complete accounting, without claiming literature-BKS or full-service quality.
- IMPLEMENTED: every online/recovery outcome is fully reverified with fresh input
  and execution fingerprints, detached routes and regenerated explanations.
  Version-2 event/child identities cover full event payloads and route evidence;
  see `docs/dispatch-lineage-contract.md`. No inherited feasibility certificate.
- IMPLEMENTED: notary accounting rejects duplicate/unknown IDs, served/rejected
  overlaps, cancelled/no-show service and mismatched inactive rejection reasons.
  Valid partial plans and optional inactive accounting remain supported.
- IMPLEMENTED: passenger-day quota evidence is reconstructed from pickup departure
  and dropoff arrival, including VIA dwell and multiple vehicles. Optional cached
  ride summaries cannot hide quota use; inconsistent supplied values are diagnosed.
  This is a verifier hardening change, not production-safety certification.
- Public fixture export rejects non-synthetic/mixed provenance and restricted profiles;
  nested PII field paths and numeric-email masking covered by regression tests.
  These guards are not customer-data anonymization or certification.
- CLI `solve` exits nonzero for unverified/error/unknown statuses, retaining diagnostic files.
- Independent notary rejects phantom service, driverless service, reversed timestamps,
  wrong pickup/dropoff locations, early pickups and missing alighting/VIA dwell;
  validates explicit/implicit depot-return occupancy against driver/vehicle unavailability.
- Honesty: freeze-protection and ops recovery tests assert `broken_frozen` /
  removed-or-moved trips, not key presence in `plan_churn`. Dated 2026-08-12
  implementation audit keeps the snapshot and records a 2026-09-09 erratum:
  greedy pooling load ≥ 2 is covered by `tests/test_pooling.py`.

## 0.2.2 — 2026-08-30

- SynAPS pin bumped to
  [`6178c93`](https://github.com/KonkovDV/SynAPS/commit/6178c93b705ff58be21fa74a98651883a2da1169)
  (ADR-0004). Regression: fail-closed coverage, calendar encode, kernel
  claims-lint. DARP search is still this repo, not kernel COVER. KI-N12
  stays closed. Not a courtesy float on the kernel default branch.
- GitHub default branch is ``main`` (CI push/PR triggers). Pin remains a
  full SHA.
- Driver ``unavailable_intervals`` use the same occupancy algebra as vehicle
  shop windows (Python SoA, native payload union, notary ``DRIVER_REST``).
  Policy data only — not ГОСТ 70314 / 580-FZ certification. Multi-day
  rostering remains out of scope. LBBD stays a stub.
- Cordeau (2006) ``a2-16`` loader + instance SHA-256 gate. Literature BKS
  294.25 (Ho et al. 2018) is cited, not claimed: integer travel, 5 min curb
  wait, Floyd-Warshall on rounded edges. Not aicenter NYC/Chicago dumps.
  Solver results copy ``problem.claim_level`` (open_data_benchmark on a2-16)
  instead of hard-coding synthetic_benchmark.
- Documented honestly: LBBD/Activated Benders remain **out of scope** (stub);
  GPU insertion is **refused** (13×13 zones, branchy VIA/quota insert);
  CI already builds `mobiroute_native` (`test` + `native-accelerator`).
  `stress_200` 8.1 s → 2–3 s is **not** claimed this drop; day-ahead ~4 s
  sequential lex insert is the remaining tail. Native/Python lockstep unchanged.

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
- Pickup curb wait \\(\\max(board,5)\\) and appointment earliest alight \\(start-30\\)
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
