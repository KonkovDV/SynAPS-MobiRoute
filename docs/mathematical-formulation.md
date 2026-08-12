# Mathematical formulation (Accessible Dynamic DARP)

## Problem name

**Dynamic Stochastic Accessible Dial-a-Ride Problem with Time Windows,
Heterogeneous Vehicles, Capacity, Pairing, Fairness and Disruption Recovery**
(DSA-DARP-TW-HV).

v0 implements the **deterministic** core (stochastic travel as future extension).

## Sets

- Passengers / requests \(R\)
- Vehicles \(V\), drivers \(D\)
- Zones \(Z\), travel times \(\tau(i,j)\)
- Stops: pickup \(p_r\), optional via \(v_r\), dropoff \(d_r\) for each \(r \in R\)
- \(\tau(i,j)\): shortest-path minutes on the labelled zone matrix (Floyd–Warshall), not live roads

## Decision variables (conceptual)

- \(x_{rv} \in \{0,1\}\): request \(r\) assigned to vehicle \(v\)
- Route sequence / arrival times \(a_s\), departures \(u_s\)
- Reject indicator \(y_r = 1 - \sum_v x_{rv}\) with reason code \(\rho_r\)

## Hard constraints (mandatory)

1. Pairing: pickup and dropoff of \(r\) on same \(v\)
2. Precedence: \(a_{p_r} + \mathrm{board}_r + \tau \le a_{d_r}\)
3. No dropoff before pickup
4–5. Pickup window; `appointment_end` is latest dropoff; earliest alight is
   `appointment_start - 30` (DREDF −30/0 analogue — lobby, not cabin-until-slot)
6–7. Max ride / max wait (empty idle free; onboard hold and passenger delay capped).
   Pickup dwell is \(\max(\mathrm{board}, 5)\) (FTA/DREDF curb-wait analogue).
   Early-alight snap to \(start-30\) is allowed only if this trip is the last onboard;
   otherwise the insertion is infeasible (do not hold other passengers at the clinic).
8–9. Passenger and wheelchair capacity along the route
10–11. Wheelchair type / lift / ramp compatibility
12. Companion seats
13–14. Driver qualifications and shift
15. No double-booking of vehicle time
16–17. Travel and boarding/alighting times
18–19. Depot start / **return by** \(\min(T_v,T_d)\)
20. Blocked locations / **service area** (pickup, via, and dropoff in \(A_v\) if \(A_v\) nonempty)
21. Invalid pooling forbidden, including stretcher exclusive cabin
22. Optional VIA between pickup and dropoff; passenger stays onboard.
    Detour cap uses door-to-door itinerary minutes including VIA service,
    not geographic hops alone (pharmacy dwell is not a detour).
23. Remaining hour quota (door-to-door ride minutes) if set; else unlimited
24. Cancelled requests excluded
25. Urgent insert only if feasible
26. Frozen trips immutable without override
27. Rejected requests keep explainable \(\rho_r\)
28. Reproducible solve (seed, hashes, single thread)

## Lexicographic objective levels

1. Safety / accessibility / medical hard feasibility  
2. Maximize served (esp. medical on-time)  
3. Minimize lateness, wait, ride time, cancels  
4. Fairness, deadhead, cost  

Tiny CP-SAT in v0.2.0 implements a **sequential** pair model (dropoff of trip *i*
before pickup of trip *j* on the same vehicle). It is not the pooling DARP.
`OPTIMAL` requires OR-Tools OPTIMAL and an independent notary. Greedy insertion
is the pooling heuristic (PARTIAL). ALNS is adaptive LNS (random / Shaw / worst /
route destroy, greedy repair, SA on duration at equal served; never `OPTIMAL`).
LBBD / rolling horizon remain PLANNED.

Weighted sum / ε-constraint / Pareto slices are **report-only** modes;
never hide poor metrics behind one scalar.

## Dynamic control

Each disruption produces plan \(P_{k+1}\), link to \(P_k\), diff, fingerprint,
frozen set, feasibility re-check, measurable **plan_churn**.
