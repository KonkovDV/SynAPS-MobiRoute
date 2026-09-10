# Pilot protocol (outline)

1. Legal / DPA for anonymized operational extracts.  
2. Map operator entities → MobiRoute schemas.  
3. Freeze baseline (current dispatch rules).  
4. Shadow mode: MobiRoute suggestions vs actual assignments (no live control).  
5. Metrics: service rate, medical on-time, waits, reason codes, fairness, churn.  
6. Human review of refusals.  
7. Optional limited live assist with override.  

No effect claims before baseline comparison.

## Degraded mode (analogue practice, not a MobiRoute claim)

Public paratransit procurement documentation expects a scheduling system to say
what happens when it is unavailable: "The fall back mode is expected to be
manual operation… If the staff has been reduced, a degraded mode of operation
must be defined" (US DOT, *Paratransit advanced routing and scheduling system
documentation*). A King County transit technical audit recorded the opposite
failure mode: scheduling software whose cost assumptions were miscalibrated
produced unreliable outputs, and staff reverted to manual methods.

A pilot therefore fixes, before day one: who dispatches when the kernel is
unavailable or distrusted, how a fallback day is recorded, and how those days
are excluded from any comparison. These are findings about other operators'
systems, used as design analogues; they are not evidence about MobiRoute.
