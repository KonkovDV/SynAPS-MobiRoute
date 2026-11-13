# Mathematical formulation (Accessible Dynamic DARP)

## Problem name

**Dynamic Stochastic Accessible Dial-a-Ride Problem with Time Windows,
Heterogeneous Vehicles, Capacity, Pairing, Fairness and Disruption Recovery**
(DSA-DARP-TW-HV).

v0 implements the **deterministic** core (stochastic travel as future extension).

## Sets

- Passengers / requests \\(R\\)
- Vehicles \\(V\\), drivers \\(D\\)
- Zones \\(Z\\), travel times \\(\\tau(i,j)\\)
- Stops: pickup \\(p_r\\), optional via \\(v_r\\), dropoff \\(d_r\\) for each \\(r \\in R\\)
- \\(\\tau(i,j)\\): shortest-path minutes on the labelled zone matrix (Floyd–Warshall), not live roads

## Decision variables (conceptual)

- \\(x_{rv} \\in \\{0,1\\}\\): request \\(r\\) assigned to vehicle \\(v\\)
- Route sequence / arrival times \\(a_s\\), departures \\(u_s\\)
- Reject indicator \\(y_r = 1 - \\sum_v x_{rv}\\) with reason code \\(\\rho_r\\)

## Hard constraints (mandatory)

1. Pairing: pickup and dropoff of \\(r\\) on same \\(v\\)
2. Precedence: \\(a_{p_r} + \\mathrm{board}_r + \\tau \\le a_{d_r}\\)
3. No dropoff before pickup
4–5. Pickup window; `appointment_end` is latest dropoff; earliest alight is
   `appointment_start - 30` (DREDF −30/0 analogue — lobby, not cabin-until-slot)
6–7. Max ride / max wait (empty idle free; onboard hold and passenger delay capped).
   Pickup dwell is \\(\\max(\\mathrm{board}, 5)\\) (FTA/DREDF curb-wait analogue).
   Early-alight snap to \\(start-30\\) is allowed only if this trip is the last onboard;
   otherwise the insertion is infeasible (do not hold other passengers at the clinic).
8–9. Passenger and wheelchair capacity along the route
10–11. Wheelchair type / lift / ramp compatibility
12. Companion seats
13–14. Driver qualifications, shift, and optional rest/unavailable occupancy
   (policy intervals on ``driver.unavailable_intervals``; not a labour-law
   certificate)
15. No double-booking of vehicle time
16–17. Travel and boarding/alighting times
18–19. Depot start / **return by** \\(\\min(T_v,T_d)\\)
20. Blocked locations / **service area** (pickup, via, and dropoff in \\(A_v\\) if \\(A_v\\) nonempty)
21. Invalid pooling forbidden, including stretcher exclusive cabin
22. Optional VIA between pickup and dropoff; passenger stays onboard.
    Detour cap uses door-to-door itinerary minutes including VIA service,
    not geographic hops alone (pharmacy dwell is not a detour).
23. Remaining hour quota if set, using `quota_debit_basis` (`RIDE_DURATION` or
    `BILLABLE_SERVICE` = \\(\\max(\\mathrm{board}, 5)\\) + ride + alight); else unlimited
24. Cancelled requests excluded
25. Urgent insert only if feasible
26. Frozen trips immutable without override
27. Rejected requests keep explainable \\(\\rho_r\\)
28. Reproducible solve (seed, hashes, single thread)

## Time-window tightening (pickup floor)

With alight floor \\(\\underline{a}_r = \\max(0, \\mathrm{appt}_r - 30)\\), ride cap
\\(\\bar{L}_r = \\min(L_r, \\mathrm{detour}_r)\\) and curb service \\(s_r = \\max(\\mathrm{board}_r, 5)\\),
every feasible schedule satisfies

\\[ B_{p_r} \\ge e^{*}_r = \\max\\big(e_r,\; \\underline{a}_r - \\bar{L}_r - s_r\\big), \\]

because the ride clock runs from pickup departure \\(B_{p_r} + s_r\\) to dropoff arrival
\\(\\ge \\underline{a}_r\\). This is a valid inequality (Dumas, Desrosiers & Soumis 1991;
Cordeau 2006), so an early vehicle holds until \\(e^{*}_r\\) without losing any schedule of
the sequence. Passenger delay is still measured from \\(e_r\\). Kernel, oracle and notary
share the formula (`pickup_service_floor`).

## Literature lane (Cordeau 2006 algebra)

Nodes \\(0\\) (depot), pickups \\(1..n\\), dropoffs \\(n+1..2n\\), end depot \\(2n+1\\);
Euclidean \\(t_{ij} = c_{ij}\\); service \\(d_i\\); windows \\([e_i, l_i]\\); ride limit \\(L\\);
capacity \\(Q\\); at most \\(K\\) routes.

* **CP-SAT**: `AddMultipleCircuit` over arcs \\(x_{ij}\\); \\(x_{ij} \\Rightarrow B_j \\ge B_i + d_i + \\lceil t_{ij} \\rceil_{1/1000}\\),
  route label \\(V_j = V_i\\) (first pickup names the route), \\(V_i = V_{n+i}\\),
  load propagation, \\(B_{n+i} - B_i - d_i \\le L\\). Rounding travel up keeps every model
  solution feasible in reals.
* **MIP** (compact two-index, Furtado, Munari & Morabito 2017): degree constraints,
  \\(\\sum_j x_{0j} \\le K\\), arc big-M \\(B_j \\ge B_i + d_i + t_{ij} - M_{ij}(1 - x_{ij})\\) with
  \\(M_{ij} = \\max(0, l_i + d_i + t_{ij} - e_j)\\), label and load big-M copies along arcs,
  ride and precedence rows; real-valued travel, solved by SCIP, HiGHS or CBC. The LP
  relaxation is reported as a lower bound (85.27 on a2-16 against 294.25: big-M is weak).
* **Verifier**: for a fixed sequence the constraints
  \\(B_v - B_u \\le w_{uv}\\) (windows via a zero clock \\(z\\), travel, ride, duration) form a
  system of difference constraints. It is feasible iff the constraint graph has no negative
  cycle (Bellman–Ford, CLRS 24.4); the earliest schedule is \\(B_k = -\\delta(k, z)\\). A
  negative cycle \\(C\\) is the certificate: its constraints cannot all hold and
  \\(-\\sum_{(u,v) \\in C} w_{uv}\\) is the number of minutes they miss by.

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
RHC is windowed greedy composition (heuristic, never `OPTIMAL`). LBBD remains PLANNED.

Weighted sum / ε-constraint / Pareto slices are **report-only** modes;
never hide poor metrics behind one scalar.

## Dynamic control

Each disruption produces plan \\(P_{k+1}\\), link to \\(P_k\\), diff, fingerprint,
frozen set, feasibility re-check, measurable **plan_churn**.

## Related work (framing only)

Cited to place this formulation, never to claim parity or a shared bound:

- Ho, Szeto, Kuo, Leung, Petering, Tou, "A survey of dial-a-ride problems",
  Transp. Res. Part B 111:395–421 (2018) — variant and method taxonomy.
- Barth, Reiter, Schmidt, "The Line-Based Dial-a-Ride Problem with Transfers",
  OASIcs ATMOS 2025, 17:1–17:20 — exact liDARP, 80 requests in 15 minutes.
- Gaul, Klamroth, Pfeiffer, Stiglmayr, Schulz, Eur. J. Oper. Res.
  321(2):363–382 (2025) — tighter DARP formulation and event-based horizons.
- "Multiple plan approach for a dynamic dial-a-ride problem", OR Spectrum
  (2025) — several candidate plans instead of one committed plan.
- Lois, Ziliaskopoulos, "Online algorithm for dynamic dial a ride problem and
  its metrics", Transp. Res. Procedia 24:377–384 (2017) — online metrics.

MobiRoute publishes greedy pooling insertion, beam, ALNS, RHC and a sequential
tiny CP-SAT on synthetic days. The only literature comparison is the Cordeau
`a2-16` literature lane above, gated on the instance SHA-256 and the verifier.
