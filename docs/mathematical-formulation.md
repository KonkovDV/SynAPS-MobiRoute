# Mathematical formulation

Two models live in the repository. The **rich VRP** (`mobiroute.vrp`) is the
general one: cargo and passengers, heterogeneous fleet, pickup and delivery.
The **paratransit kernel** adds operator rules for accessible transport; its
specifics are at the end and in [darp-kernel.md](darp-kernel.md).

## 1. Rich VRP

### Sets and data

* $N$ — nodes (depots and service points); travel time $t^p_{ij}$ and distance
  $d^p_{ij}$ for every road profile $p$ (car, van, truck, ...).
* Each node $i$: service-start window $[e_i, l_i]$, service time $s_i$.
* $R$ — orders. An order $r$ is a pickup-delivery pair $(p_r, d_r)$, a
  delivery $d_r$ loaded at the start depot (VRPTW customer) or a collection
  $p_r$ unloaded at the end depot. Demand $q_r \in \mathbb{R}^D_{\ge 0}$
  (kg, m³, pallets, seats, ...), required skills $S_r$, optional ride limit
  $L_r$, optional drop penalty $\pi_r$.
* $K$ — vehicle types: count $n_k$, capacity $Q_k \in \mathbb{R}^D$, start and
  end depots, shift $[a_k, b_k]$, shift cap $T_k$, skills $S_k$, profile
  $p(k)$, fixed cost $f_k$, cost per distance $c^d_k$, cost per time $c^t_k$.

### Decisions

A route per used vehicle: an ordered list of service nodes; service starts
$B_i$; which orders stay unserved.

### Constraints

1. every order on at most one route; both nodes of a pair on the same route,
   pickup before delivery;
2. $S_r \subseteq S_k$ for the vehicle serving $r$;
3. load after every stop within $Q_k$ in every dimension (depot deliveries are
   on board from the start);
4. $B_j \ge B_i + s_i + t^{p(k)}_{ij}$ for consecutive stops, $e_i \le B_i \le l_i$;
5. depot departure $\ge a_k$, return $\le b_k$, $B_{\text{end}} - B_{\text{start}} \le T_k$;
6. $B_{d_r} - (B_{p_r} + s_{p_r}) \le L_r$;
7. at most $n_k$ routes of type $k$.

### Objective

$$
\min \sum_{\text{routes}} \Big( f_k + c^d_k \sum d_{ij} + c^t_k \big(\sum t_{ij} + \sum s_i\big) \Big)
+ M \cdot \#\text{vehicles} + \sum_{r \text{ unserved}} \pi_r
$$

$c^t_k$ is charged on driving and service time, not on idle waiting, so an
insertion changes it by a closed-form amount. $M$ (`vehicle_penalty`) is zero
for cargo days, where vehicles cost $f_k$; benchmarks that rank vehicles first
use $M = 10^5$. Own vehicles have $f_k = 0$ (the truck and driver are paid for
anyway); hired vehicles carry a hire fee and a dearer tariff.

## 2. Insertion in constant time

For a route $v_0, \dots, v_{m+1}$ (depots at both ends) keep

$$
\text{begin}_k = \max\big(\text{begin}_{k-1} + s_{k-1} + t_{k-1,k},\ e_k\big), \qquad
\text{late}_k = \min\big(l_k,\ \text{late}_{k+1} - s_k - t_{k,k+1}\big)
$$

(Savelsbergh 1992). Node $u$ fits between $v_i$ and $v_{i+1}$ iff
$b_u = \max(\text{begin}_i + s_i + t_{iu}, e_u) \le l_u$ and
$b_u + s_u + t_{u,i+1} \le \text{late}_{i+1}$. A pair scans the delivery
position $j \ge i$ forward and pushes the pickup's delay only through
$v_{i+1..j}$, checking their own $l$; load uses the running maximum of the
loads on $v_{i..j}$. A route of $m$ stops costs $O(m^2)$ tests of $O(1)$.

**Shortest feasible duration.** With windows and travel only, leaving the
depot at $t$ gives the earliest arrival at the end
$\max(t + G_0,\ A)$, where $G_k$ is the pure driving and service time from
stop $k$ to the end and $A = \max_{k\ge1}(e_k + G_k)$. The latest departure is
$\min_k (l_k - H_k)$ with $H_k$ the time from the start to $k$. Hence

$$
\text{duration}_{\min} = \max\big(G_0,\ A - \min_k(l_k - H_k)\big).
$$

After an insertion, $G$ and $H$ shift by known constants on three segments
(before the pickup, between pickup and delivery, after the delivery), so
prefix and suffix extrema of $e_k + G_k$ and $l_k - H_k$ give the new duration
in $O(1)$ per candidate (`insertion._min_duration_ok`).

**Ride limits** couple two stops, so local slack does not decide them.
Candidates that pass the fast tests are sorted by cost and the cheapest are
timed exactly (section 4).

## 3. Regret-k repair and ALNS

Each step inserts the order with the largest regret
$\sum_{h=2}^{k}(c_h - c_1)$ over its best routes (Potvin & Rousseau 1993); an
empty vehicle of each type with spare units is an option priced with its
fixed cost. Ruin operators: random, worst saving, related (Shaw: distance,
time, size), string removal (Christiaens & Vanden Berghe 2020) and whole
route. Adaptive weights and simulated annealing follow Ropke & Pisinger
(2006). To save vehicles, a route is removed and its orders are fitted back by
guided ejection (Nagata & Bräysy 2009): eject at most two orders with the
smallest penalty counters, perturb, repeat.

### Vehicle type of a finished route

Insertion opens vehicles one order at a time, so a type whose fee is paid up
front is never chosen for a single order even when a whole route is cheaper on
it. After every repair the types are re-chosen exactly: route $\rho$ may take
any type $k$ that keeps it feasible (capacity, skills, schedule on $k$'s
profile, shift cap), at cost $c_{\rho k}$, with at most $n_k$ routes per type.
That is a transportation problem, solved as a min-cost flow
source → route → type → sink by successive shortest paths (Bellman-Ford on
the residual graph). On the CP-SAT study this closed a 19.6% gap.

## 4. Timing of a fixed sequence: difference constraints

For a fixed order of stops, every rule above is $B_v - B_u \le w_{uv}$:

| Rule | Arc |
| --- | --- |
| $B_k \le l_k$ | $z \to k$, weight $l_k$ |
| $B_k \ge e_k$ | $k \to z$, weight $-e_k$ |
| travel | $k{+}1 \to k$, weight $-(s_k + t_{k,k+1})$ |
| ride | $p \to d$, weight $L_r + s_p$ |
| shift cap | $\text{start} \to \text{end}$, weight $T_k$ |

The system is feasible iff the graph has no negative cycle (CLRS 24.4).
Bellman-Ford from the zero clock $z$ gives the earliest schedule
($B_k = -\delta(k, z)$), the latest one ($B_k = \delta(z, k)$) and the
shortest feasible duration ($-\delta(\text{end}, \text{start})$). A negative
cycle $C$ is a **certificate**: its constraints cannot hold together and
$-\sum_{C} w$ is the number of minutes missing. Example from a cargo day:
*supplier opens at 09:00, loading 26 min, drive 162.8 min, customer closes at
12:00 — short by 8.8 min*.

## 5. Lateness instead of soft windows

Soft windows hide how late a plan is. The repository keeps windows hard and
prices a delay explicitly (`vrp/lateness.py`):

* **minimal maximum lateness**: the least $\delta$ such that replacing every
  $l_k$ by $l_k + \delta$ removes all negative cycles; bisection on
  Bellman-Ford. For a single conflicting window it equals the certificate's
  deficit.
* **minimal total lateness**:
  $\min \sum_k w_k \lambda_k$ subject to $B_k \le l_k + \lambda_k$,
  $\lambda_k \ge 0$ and the other constraints of section 4, solved by GLOP.
  The constraint matrix is a network matrix, so the dual is a min-cost flow.

## 6. Exact CP-SAT model

One `AddCircuit` per vehicle unit over its depot and the service nodes it may
serve; a self-loop means "skip this node", a depot self-loop means "unit
unused". Literal $x^u_{ij} \Rightarrow B^u_j \ge B^u_i + s_i + t^u_{ij}$ and
$Q^u_j = Q^u_i + q_j$; pairs share the visit literal; ride limits and the
shift cap are linear constraints guarded by it; identical units are used in
order (symmetry breaking). Travel is rounded **up** on a 0.01 min grid, so any
model solution is feasible in reals; the verifier re-prices it.

CP-SAT proves the optimum of all 40 random instances of the full model in
[benchmarks/exact-vs-alns.md](benchmarks/exact-vs-alns.md); ALNS matches 38 of
them, mean gap 0.13%.

## 7. Literature lane: Cordeau (2006) DARP

`benchmarks/cordeau_exact.py` solves the published algebra exactly:

* CP-SAT with `AddMultipleCircuit`, route labels ($V_j = V_i$ along arcs, the
  first pickup names the route, $V_i = V_{n+i}$), load and time propagation,
  ride rows; travel rounded up on a $10^{-3}$ grid;
* the compact two-index MIP of Furtado, Munari & Morabito (2017) with
  arc-specific big-M $M_{ij} = \max(0, l_i + s_i + t_{ij} - e_j)$, solved by
  SCIP, HiGHS or CBC, and its LP relaxation as a bound.

a2-16: CP-SAT proves 294.25 in 0.6 s; SCIP and HiGHS reach it in 26.2 s and
43.3 s; the LP bound is 85.27 (big-M is weak: 71% gap) —
[benchmarks/solver-lab-a2-16.md](benchmarks/solver-lab-a2-16.md).

## 8. Paratransit kernel specifics

Integer minutes on a zone graph (Floyd-Warshall), curb dwell
$\max(\text{board}, 5)$, alighting no earlier than 30 min before an
appointment, detour cap, wheelchair places, accessibility skills, quotas,
linked trips. Valid inequality used by search and notary alike:

$$
B_{p_r} \ge \max\big(e_r,\ \underline{a}_r - \bar L_r - s_r\big),
\qquad \underline{a}_r = \max(0, \text{appt}_r - 30),\ \bar L_r = \min(L_r, \text{detour}_r)
$$

(Dumas, Desrosiers & Soumis 1991).

## References

* Christiaens, J., Vanden Berghe, G. (2020). Slack induction by string removals for vehicle routing problems. *Transportation Science* 54(2):417–433.
* Cordeau, J.-F. (2006). A branch-and-cut algorithm for the dial-a-ride problem. *Operations Research* 54(3):573–586.
* Dumas, Y., Desrosiers, J., Soumis, F. (1991). The pickup and delivery problem with time windows. *EJOR* 54(1):7–22.
* Furtado, M., Munari, P., Morabito, R. (2017). Pickup and delivery problem with time windows: a new compact two-index formulation. *Operations Research Letters* 45(4):334–341.
* Nagata, Y., Bräysy, O. (2009). A powerful route minimization heuristic for the vehicle routing problem with time windows. *Operations Research Letters* 37(5):333–338.
* Potvin, J.-Y., Rousseau, J.-M. (1993). A parallel route building algorithm for the VRPTW. *EJOR* 66(3):331–340.
* Ropke, S., Pisinger, D. (2006). An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows. *Transportation Science* 40(4):455–472.
* Ropke, S., Cordeau, J.-F., Laporte, G. (2007). Models and branch-and-cut algorithms for pickup and delivery problems with time windows. *Networks* 49(4):258–272.
* Savelsbergh, M.W.P. (1992). The vehicle routing problem with time windows: minimizing route duration. *ORSA Journal on Computing* 4(2):146–154.
* Campbell, A.M., Savelsbergh, M. (2004). Efficient insertion heuristics for vehicle routing and scheduling problems. *Transportation Science* 38(3):369–378.
* Shaw, P. (1998). Using constraint programming and local search methods to solve vehicle routing problems. *CP 1998*, LNCS 1520:417–431.
* Sartori, C.S., Buriol, L.S. (2020). A study on the pickup and delivery problem with time windows: matheuristics and new instances. *Computers & Operations Research* 124:105065.
