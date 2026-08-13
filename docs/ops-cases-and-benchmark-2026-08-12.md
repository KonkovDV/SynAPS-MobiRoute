# Moscow social-taxi ops cases and scheduling benchmark

**Research date:** 2026-08-12  
**Claim level:** `synthetic_benchmark`  
**Not** real Мосавтосантранс (MAST) trips, GPS, or Moscow KPI improvement.

This document is the SSOT for (1) operator-shaped rules retrieved 2026-08-12, (2) how real call-centre cases map onto a DARP kernel, (3) world paratransit practice used as **analogues only**, (4) Academy of Innovators 10th-cohort requirements, and (5) measured numbers from `mobiroute ops-benchmark --seed 42`.

Run:

```bash
mobiroute ops-benchmark --seed 42 --out-dir benchmark/results/ops-2026-08-12
```

JSON/CSV under `benchmark/results/` are gitignored. The table in **Measured suite** below is the committed snapshot.

## Clock and generator contract

| Item | Encoding |
| --- | --- |
| Minute 0 | 06:00 (service start, mgovos.ru) |
| Minute 780 | 19:00 (service end) |
| Pickup window | 30 min span (ADA-style ±15 around a negotiated time) |
| Destination wait cap | 60 min (`latest_pickup` on the return leg) |
| Max companions | 2; seats = 1 + companions |
| Wheelchair dwell | board 8 / alight 5 vs ambulatory 3 / 2 |
| Depot pull-out | `shift_start = max(0, first_pickup - 45)` — the simulator otherwise leaves the depot at shift start |
| Zones | Synthetic labels (`Z_NORTH` …). Not OSM / not live Moscow graph |
| `claim_level` | always `synthetic_benchmark` |

Greedy / FIFO / disruption recovery **never** claim `OPTIMAL`.

## Moscow social taxi — verified and operator-claimed rules

Primary pages retrieved 2026-08-12:

- https://taxi.santrans.ru/
- https://mgovos.ru/index.php/vazhnaya-informatsiya/3085-kak-vospolzovatsya-uslugoj-sotsialnoe-taksi
- Transfer notice: operator is GBU **Мосавтосантранс**, Dept. of Health; Mosgortrans-era phones/emails after 23 Apr 2026 are stale.

| Rule | Detail | Kernel? |
| --- | --- | --- |
| Service hours | Daily 06:00–19:00 | Yes — shift + depot return |
| Booking intake | Phone +7 (495) 129-03-30 daily 08:00–20:00; site; email; Android app | No — CRM / call centre |
| Cancel phone | Same number; mgovos lists 06:00–20:00 for cancel | Partial — `CANCELLATION` event, not the phone queue |
| Lead time, regular | Not earlier than 3 calendar days, not later than 24 h | No — intake calendar; kernel sees a day problem |
| Lead time, stations/airports | 24 h–30 calendar days | Label `trip_purpose=AIRPORT` only |
| Wait at destination | Request wait and/or return; **total wait ≤ 60 min** | Yes — `same_vehicle_as` + `insert_immediately_after` |
| Companions | Up to 2 | Yes — seat count |
| Vehicle class | Sedan vs ramp; can the passenger transfer unaided? | Yes — lift/ramp/WAV vs sedan |
| Child restraint | Asked at booking | Not modelled as a hard field |
| Hour quotas | 80 h/month work/study; unlimited treatment/rehab; 20 h other; unused hours do not roll | **Billing / CRM, not kernel** |
| Fare | 210 ₽/h Moscow; 420 ₽/h oblast; min 30 min; pay card at terminal | Not kernel |
| Eligibility | I group; 80+ any group; II/III locomotor; II vision; children; WWII; some large families in low-rise | Label only, never a legal decision |
| Registry | mos.ru and/or in person Bakhrushina 21–23 bldg 5, weekdays 10:00–15:00 | Not kernel |
| Palliative | +7 (495) 357-10-01; coord +7 (499) 444-04-57 | Channel label + priority; not ID issuance |
| Groups | MGO VOI `mgo_voi@mail.ru` / Bakhrushina | `EligibilityClass.ORGANIZATION` + bus |
| Complaints | os@santrans.ru; +7 (495) 215-03-80 weekdays 08:00–15:00 | CRM |
| Fleet gallery | Москвич 3, Largus, Ford Transit, Газель, MAN bus | Synthetic sedan / minibus / bus mix |
| Public real-trip dataset | **MISSING** | Never label synthetic as real Moscow GPS |

## What actually happens on a call — and who owns the fix

These are **policy-shaped cases**, not a leaked MAST event log.

| # | What the caller / dispatcher sees | Typical operator resolution | Kernel encoding | Not the kernel |
| --- | --- | --- | --- | --- |
| 1 | Not in the registry | Send to mos.ru / Bakhrushina | Reject is an intake decision; if a trip is still posted, `eligibility_class` is a label | Legal entitlement |
| 2 | Purpose not allowed (e.g. visiting friends) | Refuse at booking | `trip_purpose` filter belongs in CRM; kernel will still route a posted trip | Policy catalogue |
| 3 | No free compatible vehicle for that slot | Offer another time or refuse | WAV shortage script; reason codes, never a silent drop | Buying vehicles |
| 4 | Passenger cannot transfer; sedan was booked | Rebook ramp/lift vehicle | `needs_lift` / `needs_ramp` vs fleet flags | Driver courtesy |
| 5 | Two companions | Fit in sedan (3 seats) or need a larger van | `companion_count` vs `passenger_capacity` | Who counts as attendant |
| 6 | Wait at clinic + return, ≤ 60 min | Same vehicle holds or deadheads back | `same_vehicle_as`, exclusive insert after outbound dropoff | How long the doctor actually takes |
| 7 | Airport / rail, booked weeks ahead | Intake 24 h–30 d; still a timed trip on the day | `trip_purpose=AIRPORT`, longer `max_ride` | 30-day calendar |
| 8 | Palliative ID line | Separate phone; protected urgency | `channel=PALLIATIVE_ID`, `MEDICAL_URGENT` | Issuing the ID |
| 9 | Group / MGO VOI | Bus + paper originals at the office | One bus, pooled load, 2 wheelchair spaces | Paper originals |
| 10 | Dialysis / work / school every week | Recurring booking + hour caps | `frozen=True`, `channel=SUBSCRIPTION` | 80 h quota arithmetic |
| 11 | Late cancel / no-show | Phone cancel; possible sanctions after a pattern | `recover_disruption` cancel / no-show | Sanctions policy |
| 12 | Trip near 19:00 | Cannot start a ride that misses depot return | Shift-close reject `TIME_WINDOW_CONFLICT` | Overtime pay |
| 13 | Debt / missing docs / systematic cancels | CRM block | Not modelled | Billing / registry |
| 14 | Child restraint requested | Dispatch note | Not a hard constraint yet | Equipment inventory |
| 15 | Opaque refusal (forum / app-store pain) | Complaint line | Reason codes on every reject | UX of the phone queue |

Qualitative app-store / forum complaints are **pain signals for org/UX layers**, not solver KPIs.

## World practice (retrieved / confirmed 2026-08-12) — analogues, not Moscow law

| Practice | Source | Transfer into MobiRoute | Do not transfer |
| --- | --- | --- | --- |
| Next-day service, **not** 24 h-before-the-clock-time | 49 CFR 37.131(b); FTA ADA circular webinar | `channel=NEXT_DAY` label | Moscow 24 h / 3-day intake as if it were ADA |
| Pickup negotiation ≤ 1 hour from desired time | 49 CFR 37.131(b)(2); FTA Q&A | Window span; denial if cannot negotiate | Copy US denial law into RF |
| Pickup window typically ≤ 30 min; often ±15 | DREDF OTP guide; FTA circular (window not in the CFR text) | 30 min `latest-earliest` | Claim ADA certification |
| Driver wait ~5 min, must not start before the window | DREDF OTP | Future no-show dwell; not yet a 5-minute timer | Treat 5 min as Moscow regulation |
| Drop-off for appointments often −30/0 | DREDF OTP | `appointment_start` / `appointment_end` | Copy % on-time as Moscow effect |
| Will-call / open return is **premium**, not required next-day | ADA practice | Wait-return is explicit and capped | Promise will-call as a right |
| Subscription ≤ 50% of capacity unless excess | 49 CFR 37.133 | Frozen subscription vs next-day leftover | Enforce 50% as Moscow law |
| Capacity constraint = pattern of denials / late / long rides | 49 CFR 37.131(f) | Explain rejects; do not hide them | Claim we “solve ADA capacity” |
| Longer wheelchair dwell | STM Montréal dwell model (TRR 2020; ops from 2018) | 8/5 vs 3/2 minutes | Copy STM minutes as MAST truth |
| Productivity = trips per revenue hour; OTP | TCRP Synthesis 168 / CDO literature | Report served, P95 wait/ride, coverage | Copy published % to Moscow |
| Joint routes + shifts | Savannah CP 2026 (LIPIcs) | Shift windows | Savannah +5% served as Moscow |
| Stochastic day-ahead + disruption | Activated Benders, IJOC 2026 | PLANNED LBBD | Author platform KPIs |
| Fast insertion + reopt | Pfeiffer/Schulz, OR Spectrum 2026 | Greedy / online insertion | Their 2700-instance curves |
| Agency paratransit + apps | SmartTransit.AI / CARTA, IJCAI 2024 | Kernel-only JSON | Passenger app claims |

Moscow **24 h notice** is the opposite of ADA next-day. Encoding both as labels on the same synthetic day is intentional: it shows the kernel can carry either policy, not that Moscow adopted FTA rules.

## Academy of Innovators — 10th cohort (as of 2026-08-12)

| Item | Evidence | MobiRoute mapping |
| --- | --- | --- |
| Organizer | Moscow Innovation Cluster / i.moscow/academy | One project: MobiRoute only |
| Deadline | **14 September 2026** (Sergunina; iz.ru / vm.ru / m24.ru 24 Jun 2026) | Submit before that date |
| Age | 14+ | Team eligibility is off-repo |
| Cost | Free (FAQ on i.moscow/academy) | — |
| Application package | Project card + **presentation** + team + **motivation letter** answering “why us?” | `docs/academy-innovators-application-ru.md`, `docs/pitch-deck-15-points-ru.md`, `docs/motivation-letter-ru.md` |
| Tracker | Personal business tracker; meetings not skippable; ≥1 teammate present; tracker sessions online | Ask for tracker on a **shadow pilot**, not “already deployed at MAST” |
| Education | 2×/week, in-person with recording | — |
| Cohort size | “100 best projects” (site) | Do not invent a ranking |
| Pilot help | Help launching pilots with city / corporate customers | Shadow mode: synthetic → de-identified partner data |
| Demo day | Best projects on stage | Pitch the kernel, not a passenger app |
| Ecosystem marketing | 40k+ / 45k+ participants, ₽1+ bn, 230+ pilots, ₽3.7 bn resident turnover 2025 | Operator marketing — **not** MobiRoute evidence |
| Site timeline widget | HTML scrape on 2026-08-12 still listed “9 поток” without dates | Prefer the 24 Jun 2026 news for the 10th-cohort deadline |

**Forbidden in the application:** mixing SynAPS Energy / GridPlan / AeroBIM; claiming Moscow KPI improvement; calling greedy `OPTIMAL`.

## Scenario catalogue (kernel scripts)

| Mode | Moscow rule | World analogue | What the solver must show |
| --- | --- | --- | --- |
| `ops_clinic_peak` | Medical destinations, 06:00–19:00 | Appointment −30/0, longer WC dwell | Mixed WAV/sedan, one explained reject |
| `ops_wait_return` | Same vehicle, dest wait ≤ 60 min | Will-call is premium | Return sits immediately after outbound dropoff |
| `ops_airport` | 24 h–30 d intake | Airport will-call / long deadhead | Long ride + companion seat |
| `ops_palliative` | Separate phone | NEMT / hospice priority | Channel + trained WAV; eligibility is a label |
| `ops_group` | MGO VOI group bus | Subscription/group loads | Pooling on one 18-seat / 2-WC bus |
| `ops_wav_shortage` | No free compatible vehicle | ADA capacity-constraint **pattern** (we only explain) | Partial serve + non-empty reason codes |
| `ops_companions` | Two accompanying persons | PCA occupies a seat | Sedan capacity 3 |
| `ops_subscription_vs_nextday` | Hour caps are billing | FTA 50% analog as **label only** | Frozen trips; cancel recovery |
| `ops_fairness_districts` | Citywide service | Equity-aware DARP | Multi-metric fairness; `fair_by_single_metric=false` |
| `ops_shift_close` | 19:00 close + depot return | Hours of service = comparable network | Reject if leave + deadhead > shift_end |
| `ops_stretcher` | Lying passenger, dedicated cabin | Many ADA agencies exclude stretchers | Exclusive load; 1/2 served |
| `ops_scooter` | Sedan vs ramp / type fit | Default mask MANUAL/POWER | `NO_COMPATIBLE_VEHICLE` |
| `ops_medical_vs_dacha` | Hospital outranks dacha (RUSSPASS) | Lex medical first | One WAV seat; medical kept |
| `ops_service_area` | Geographic beat | Corridor-comparable service | Pickup and dropoff in \(A_v\) |
| `ops_untrained_driver` | Unaided transfer vs trained help | Passenger assistance skill | `NO_DRIVER` |
| `ops_agency_missed` | Promised vehicle never arrived | Agency error ≠ rider no-show | `VEHICLE_BREAKDOWN` |
| `ops_via` | Clinic then pharmacy | Origin-destination plus a via | PU-VIA-DO; passenger stays onboard |
| `ops_quota` | Remaining entitlement minutes | Subscription cap as remaining minutes | One served, one `QUOTA_EXCEEDED` |

## Measured suite (seed 42, 2026-08-12, this machine)

Insertion backend on this run: **native** scoring (required). Do not quote a portable ×N. Greedy never `OPTIMAL`. Notary checked every row. FIFO served counts and greedy reason codes were remeasured after the 2026-08-12 Red Team pass; P95 wait is from the same-day greedy native run.

| Scenario | Greedy served | FIFO served | Greedy P95 wait (min) | Greedy reasons | Notes |
| --- | --- | --- | --- | --- | --- |
| Morning clinic peak | 9/10 (90%) | 6/10 (60%) | 24 | 9 ACCEPTED, 1 TIME_WINDOW_CONFLICT | Diagnose: trip is feasible alone; fleet/window conflict. No-show recovery: 8 served |
| Wait-and-return | 3/3 (100%) | 3/3 (100%) | 32 | all ACCEPTED | FIFO now processes outbound before return (red-team RT-04/05) |
| Airport / station | 5/5 (100%) | 4/5 (80%) | 47 | all ACCEPTED | FIFO drops one local trip |
| Palliative ID | 4/4 (100%) | 2/4 (50%) | 22 | all ACCEPTED | Priority sort keeps the palliative trip |
| Organization / group | 6/6 (100%) | 1/6 (17%) | 12 | all ACCEPTED | Pooling vs sequential; this is the point of the script |
| WAV shortage | 2/5 (40%) | 1/5 (20%) | 7 | 2 ACCEPTED, 3 TIME_WINDOW_CONFLICT | A WAV exists; remaining trips miss the window — not a silent drop |
| Two companions | 1/1 (100%) | 1/1 (100%) | 22 | ACCEPTED | Sedan seats = 1+2 |
| Subscription vs next-day | 6/6 (100%) | 2/6 (33%) | 17 | all ACCEPTED | FIFO `PARTIAL` and verified (sequential cannot pool). Frozen reject is explained. Cancel recovery: 5 served |
| District skew | 8/8 (100%) | 5/8 (62.5%) | 27 | all ACCEPTED | Jain is not a fairness proof |
| Shift close 19:00 | 0/1 (0%) | 0/1 (0%) | — | TIME_WINDOW_CONFLICT | Intended reject: cannot return to depot |
| Clinic then pharmacy | 1/1 (100%) | — | — | ACCEPTED | VIA between pickup and dropoff; not live roads |
| Remaining hour quota | 1/2 (50%) | — | — | 1 ACCEPTED, 1 QUOTA_EXCEEDED | Remaining minutes, not annual 80h CRM |

Statuses: greedy rows are `HEURISTIC_FEASIBLE` or `PARTIAL`. Zero `OPTIMAL`.

## Honesty constraints

- Do not say this improved Moscow social taxi.
- Do not label the generator as real MAST GPS.
- Do not treat P95 wait as ADA on-time performance.
- Do not treat `APPOINTMENT_CONFLICT` on the WAV script as “the city has no wheelchairs” — it means the remaining compatible vehicle cannot hit the window.
- ALNS is adaptive LNS (`mobiroute solve --solver alns`): Shaw / worst / route / random destroy, greedy repair, SA on duration at equal served; never OPTIMAL.
- RHC is windowed greedy composition (`--solver rhc`); never OPTIMAL. LBBD remains PLANNED.
- Fare, annual 80h ledger, registry, and 152-FZ are out of this kernel. Remaining minutes (`quota_minutes_remaining`) are in-kernel.
