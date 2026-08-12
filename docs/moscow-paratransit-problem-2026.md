# Moscow social taxi / accessible transport — problem map (2026-08-12)

**Claim level:** open primary sources + qualitative user-pain signals.  
**Not** proof of algorithm quality.  
**Not** customer data.

## Booking and service rules (mgovos.ru how-to, retrieved 2026-08-12)

These are **operator-published** rules, encoded in synthetic ops scenarios as policy shapes. They are not a live MAST integration.

| Rule | Value | Kernel? |
| --- | --- | --- |
| Service hours | Daily **06:00–19:00** | Shift + depot return |
| Booking phone | +7 (495) 129-03-30 daily **08:00–20:00** | Intake, not kernel |
| Regular lead time | Not earlier than 3 calendar days, not later than 24 h | CRM calendar |
| Airport / station lead time | 24 h–**30 calendar days** | `trip_purpose=AIRPORT` label |
| Destination wait / return | Requested at booking; **total wait ≤ 60 min** | `same_vehicle_as` + exclusive insert |
| Companions | **Up to 2** | Seats = 1 + companions |
| Hour quotas | 80 h work/study; unlimited treatment/rehab; 20 h other; no roll-over | Billing / CRM |
| Fare | 210 ₽/h Moscow; 420 ₽/h oblast; min 30 min | Not kernel |
| Vehicle class asked | Sedan vs ramp; unaided transfer? | Lift/ramp/WAV flags |
| Child restraint | Asked at booking | Not a hard field yet |

Edge-case algebra, SynAPS mapping, and six extra scripts (`ops_stretcher` … `ops_agency_missed`):
[`docs/edge-cases-algebra-synaps-2026-08-12.md`](edge-cases-algebra-synaps-2026-08-12.md).

## Verified operational context (Aug 2026)

| Fact | Status | Source |
| --- | --- | --- |
| Operator: GBU **Мосавтосантранс** (МАСТ), Dept. of Health | VERIFIED | santrans.ru; mgovos.ru 19 Apr 2026 |
| Contact change from 23 Apr 2026 (transfer from prior Мосгортранс-era contacts) | VERIFIED | mgovos.ru notice 19 Apr 2026 |
| Official site | VERIFIED | https://taxi.santrans.ru/ |
| Registration via mos.ru and/or santrans / in person Bakhrushina 21–23 bldg 5 | VERIFIED | mgovos.ru; taxi.santrans.ru |
| Prior registration still valid (no re-reg) | VERIFIED | mgovos.ru 19 Apr 2026 |
| Booking phone +7 (495) 129-03-30 daily 08:00–20:00 | VERIFIED | taxi.santrans.ru |
| Palliative ID line +7 (495) 357-10-01; coord +7 (499) 444-04-57 | VERIFIED | taxi.santrans.ru |
| Org/group bookings via MGO VOI channels | CLAIMED BY OPERATOR | taxi.santrans.ru |
| Android social-taxi app; also «Московский транспорт» historically referenced | CLAIMED BY OPERATOR / SECONDARY | taxi.santrans.ru; transport.mos.ru (older phone/email may be stale — prefer santrans contacts post-Apr 2026) |
| Fleet gallery: Москвич 3, Largus, Ford Transit, Газель, MAN bus | CLAIMED BY OPERATOR | taxi.santrans.ru |
| Destinations: medical, education, stations/airports, rehab, public offices | CLAIMED BY OPERATOR | taxi.santrans.ru |
| Advance booking: 3 calendar days … 24 h; airports/stations 30 d … 24 h; service 06:00–19:00; dest wait ≤ 60 min; 2 companions | CLAIMED BY OPERATOR (how-to page) | mgovos.ru how-to, retrieved 2026-08-12 |
| Complaints: +7 (495) 215-03-80 / os@santrans.ru | VERIFIED | taxi.santrans.ru |
| Public dataset of real trips | MISSING | — |
| Personal / medical data in real operations | VERIFIED (by nature of service) | implies privacy controls |

## Twelve problem layers — what MobiRoute can / cannot own

| # | Layer | Planner/dispatch core? | Needs other systems |
| --- | --- | --- | --- |
| 1 | Request intake | Partial (API ingest) | App, call center, email |
| 2 | Eligibility | No (signal only) | Registry / CRM / legal |
| 3 | Planning | **Yes** | — |
| 4 | Vehicle assignment | **Yes** | Fleet inventory |
| 5 | Driver assignment | **Yes** | HR / shifts |
| 6 | Routing | **Yes** | Travel-time / maps |
| 7 | Boarding/alighting | Timing constraints **Yes** | Ops training |
| 8 | Online dispatch | **Yes** | CAD/AVL |
| 9 | Cancel / no-show | **Yes** | Intake + policy |
| 10 | Feedback | No | CRM |
| 11 | Quality control | Metrics **Yes** | Auditors |
| 12 | Personal data protection | Redaction / isolation **Yes** | Legal DLP / certification |

### Layer notes (ops, not algorithm proof)

- **Intake:** phone 08:00–20:00, site, Android app, email; palliative ID has a separate line. Queue length is an org/UX problem.  
- **Eligibility:** mos.ru / in-person registry. MobiRoute may carry `eligibility_class` as a **label**, never as a legal decision.  
- **Planning–routing:** the only layer this kernel claims to compute.  
- **Boarding:** dwell times and lift/ramp compatibility are constraints; driver courtesy is not.  
- **Dispatch:** insertion into an existing plan + disruption recovery; live AVL is an adapter, not included.  
- **Complaints:** os@santrans.ru / +7 (495) 215-03-80 — CRM, not the solver.

**Qualitative evidence only (NOT algorithm proof):** app-store ratings, forum complaints about phone queues, opaque refusals, vehicle shortage perceptions — treat as pain signals for UX/org layers, not as solver KPIs.

## MobiRoute must NOT promise to fix

- Phone queue depth  
- Registration / auth bugs  
- Absolute vehicle shortage  
- Driver courtesy  
- Building accessibility  
- Medical care  
- Legal entitlement decisions  

## MobiRoute **does** target (provable layer)

- Assign compatible accessible vehicles  
- Build routes with time windows & capacity  
- Shared rides when feasible  
- Reassign on cancel/delay/breakdown  
- Explain refusal / postpone with **reason codes**  
- Measure fairness of service distribution  

## Allowed claim (bootstrap)

> MobiRoute addresses the **planning and dispatch optimization layer** of accessible demand-responsive transport. It does not replace Мосавтосантранс operational systems, eligibility registries, or passenger apps.
