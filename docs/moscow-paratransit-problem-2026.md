# Moscow social taxi / accessible transport — problem map (2026-08-12)

**Claim level:** open primary sources + qualitative user-pain signals.  
**Not** proof of algorithm quality.  
**Not** customer data.

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
| Advance booking rules (e.g. not later than ~24h) | SECONDARY / CLAIMED | mgovos.ru how-to page — confirm on current FAQ before ops use |
| Complaints: +7 (495) 215-03-80 / os@santrans.ru | VERIFIED | taxi.santrans.ru |
| Public dataset of real trips | MISSING | — |
| Personal / medical data in real operations | VERIFIED (by nature of service) | implies privacy controls |

**Qualitative evidence only (NOT algorithm proof):** app-store ratings, forum complaints about phone queues, opaque refusals, vehicle shortage perceptions — treat as pain signals for UX/org layers, not as solver KPIs.

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
