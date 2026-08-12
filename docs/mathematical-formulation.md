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
- Stops: pickup \(p_r\), dropoff \(d_r\) for each \(r \in R\)

## Decision variables (conceptual)

- \(x_{rv} \in \{0,1\}\): request \(r\) assigned to vehicle \(v\)
- Route sequence / arrival times \(a_s\), departures \(u_s\)
- Reject indicator \(y_r = 1 - \sum_v x_{rv}\) with reason code \(\rho_r\)

## Hard constraints (mandatory)

1. Pairing: pickup and dropoff of \(r\) on same \(v\)
2. Precedence: \(a_{p_r} + \mathrm{board}_r + \tau \le a_{d_r}\)
3. No dropoff before pickup
4–5. Pickup / appointment time windows
6–7. Max ride time / max wait
8–9. Passenger and wheelchair capacity along the route
10–11. Wheelchair type / lift / ramp compatibility
12. Companion seats
13–14. Driver qualifications and shift
15. No double-booking of vehicle time
16–17. Travel and boarding/alighting times
18–19. Depot start / optional return
20. Blocked locations unused
21. Invalid pooling forbidden
22. Cancelled requests excluded
23. Urgent insert only if feasible
24. Frozen trips immutable without override
25. Rejected requests keep explainable \(\rho_r\)
26. Reproducible solve (seed, hashes, single thread)

## Lexicographic objective levels

1. Safety / accessibility / medical hard feasibility  
2. Maximize served (esp. medical on-time)  
3. Minimize lateness, wait, ride time, cancels  
4. Fairness, deadhead, cost  

Weighted sum / ε-constraint / Pareto slices are supported as report modes;
never hide poor metrics behind one scalar.

## Dynamic control

Each disruption produces plan \(P_{k+1}\), link to \(P_k\), diff, fingerprint,
frozen set, feasibility re-check, measurable **plan_churn**.
