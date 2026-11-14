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
7. at most $n_k$ routes of type $k$;
8. optionally per type: a driver rest rule (section 4a), reload stops for
   multi-trip days (4b), and time-dependent travel on its road profile (4c).

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

### Merging two routes

Neither insertion nor re-typing replaces two small routes by one route on a
larger vehicle: every intermediate step is worse (moving the first order
leaves two half-empty routes, both paying a fee). The merge operator makes
the step at once: for routes $A$, $B$ and a type $k$ admissible for all their
orders, $B$'s orders are inserted cheapest-first into $A$ re-timed on $k$; the
merge is applied if $c(A \oplus B, k) < c(A) + c(B)$, best merge first, until
none saves money, and the types are then re-picked. Both instances of the
CP-SAT study that ALNS missed before were of this kind; with the operator ALNS
reaches the proven optimum on both.

### Local search with time-window segments

On instances whose orders are all deliveries from the depot (VRPTW), every
new best plan goes through a first-improvement descent over relocate, swap,
2-opt* and 2-opt moves restricted to the 20 nearest customers (granular
neighbourhoods, Toth & Vigo 2003). A stop sequence $\sigma$ is summarised by
its shortest duration $D$, time warp $TW$ (zero iff it can be timed), and the
earliest and latest start $E$, $L$ of its first service (Kindervater &
Savelsbergh 1997; Vidal et al. 2013). For $\sigma_1 \oplus \sigma_2$ with
travel $t$ between them, $\delta = D_1 - TW_1 + t$:

$$
\begin{aligned}
D &= D_1 + D_2 + t + \max(E_2 - \delta - L_1, 0), \qquad
TW = TW_1 + TW_2 + \max(E_1 + \delta - L_2, 0),\\
E &= \max(E_2 - \delta, E_1) - \max(E_2 - \delta - L_1, 0), \qquad
L = \min(L_2 - \delta, L_1) + \max(E_1 + \delta - L_2, 0).
\end{aligned}
$$

With prefix and suffix segments of every route, a move made of three pieces
is an $O(1)$ test; a reversed stretch (2-opt) is built incrementally.

### Set partitioning over the route pool

Optionally, the distinct routes $P$ of accepted plans are recombined
(Rochat & Taillard 1995; Subramanian, Uchoa & Ochi 2013):

$$
\min \sum_{\rho \in P} c_\rho x_\rho + \sum_r \pi_r y_r
\quad\text{s.t.}\quad
\sum_{\rho \ni r} x_\rho + y_r = 1\ \forall r,\quad
\sum_{\rho \in P_k} x_\rho \le n_k\ \forall k,\quad
x, y \in \{0,1\}.
$$

Every column was feasible when found, so every solution is a plan, and the
incumbent's routes make it at least as good as the incumbent. Its LP
relaxation bounds every recombination of the pool from below. Two details
keep the model sound and well scaled:

* an order the incumbent serves gets no $y_r$ (its row becomes
  $\sum_{\rho \ni r} x_\rho = 1$): the incumbent proves that all of them can
  be covered at once, so the optimum is unchanged, and the must-serve
  penalties ($10^9$) leave the matrix — with them GLOP reported the LP as
  abnormal;
* reload stops that are exact copies of one depot are interchangeable, so the
  row for a class $V$ of copies limits how many of them the chosen routes use,
  $\sum_\rho |\rho \cap V|\, x_\rho \le |V|$, and the chosen routes get
  distinct copies afterwards. (A row per stop would make the incumbent
  infeasible as soon as the pool keeps another copy number for one of its
  routes.)
[benchmarks/setpart-solvers.md](benchmarks/setpart-solvers.md) compares
CP-SAT with SCIP, HiGHS and CBC on the same pools.

## 4. Timing of a fixed sequence: difference constraints

For a fixed order of stops, every rule above is $B_v - B_u \le w_{uv}$:

| Rule | Arc |
| --- | --- |
| $B_k \le l_k$ | $z \to k$, weight $l_k$ |
| $B_k \ge e_k$ | $k \to z$, weight $-e_k$ |
| travel | $k{+}1 \to k$, weight $-(s_k + t_{k,k+1})$ |
| ride | $p \to d$, weight $L_r + s_p$ |
| shift cap | $\text{start} \to \text{end}$, weight $T_k$ |
| rest in gap $g$ | $g{+}1 \to g$, weight $-(s_g + t_{g,g+1} + b)$ (replaces the travel arc) |

The system is feasible iff the graph has no negative cycle (CLRS 24.4).
Bellman-Ford from the zero clock $z$ gives the earliest schedule
($B_k = -\delta(k, z)$), the latest one ($B_k = \delta(z, k)$) and the
shortest feasible duration ($-\delta(\text{end}, \text{start})$). A negative
cycle $C$ is a **certificate**: its constraints cannot hold together and
$-\sum_{C} w$ is the number of minutes missing. Example from a cargo day:
*supplier opens at 09:00, loading 26 min, drive 162.8 min, customer closes at
12:00 — short by 8.8 min*.

## 4a. Driver rests

A type may carry a rest rule $(D, b)$: at most $D$ minutes of driving between
rests of at least $b$ minutes, at most $2D$ minutes of driving per route (the
4.5 h / 45 min norm with the 9 h daily limit: EU Regulation 561/2006, art. 7;
the same limits are set for Russian drivers by order No. 424 of the Ministry
of Transport, 16.10.2020). Let $\tau_0, \dots, \tau_m$ be the driving times of
the legs of route $v_0, \dots, v_{m+1}$, $P_g = \sum_{a<g} \tau_a$ and
$\Delta = \sum_a \tau_a$.

**Lemma 1.** If $\Delta \le D$ no rest is needed. If $\Delta > 2D$ the route is
infeasible. Otherwise it is feasible iff there is a gap $g$ with
$P_g \in [\Delta - D, D]$ or $P_{g+1} \in [\Delta - D, D]$ for which the
system of section 4, with the travel arc of gap $g$ lengthened by $b$, has no
negative cycle.

*Proof.* One rest splits the driving into a part before and a part after it;
both must be at most $D$, which with a single rest per route forces
$\Delta \le 2D$. A rest taken between the end of service at $v_g$ and the start
at $v_{g+1}$ is either before leg $g$ (at $v_g$; driving before it is $P_g$) or
after it (at $v_{g+1}$; $P_{g+1}$), and in both cases the only timing
consequence is $B_{g+1} \ge B_g + s_g + \tau_g + b$: the vehicle may wait
anywhere between two services, so waiting for a window counts towards the
rest. For a fixed $g$ the system is again of difference constraints
(section 4). $\square$

The search filters candidates by $\Delta + \Delta_{\text{ins}} \le 2D$ in $O(1)$
(a rest only adds time, so all other fast tests remain necessary conditions)
and checks the cheapest ones exactly, trying the admissible gaps in order.
The verifier implements the lemma separately and returns, for an infeasible
route, the certificate of the gap that misses by the fewest minutes (labels
`TRAVEL+REST`) or a `DRIVING` certificate with the excess minutes.

## 4b. Multi-trip days

A multi-trip type lists reload stops: copies of its depot whose service time
is the reload time. A route visits at most `max_trips - 1` of them; it is
still one vehicle-day, so windows, the shift cap $T_k$, the rest rule and the
fixed cost apply to the whole day, while capacity applies per trip. With
trips split at reload positions, the load after position $j$ in trip $\theta$
is

$$
q_j = \sum_{r \in \mathcal D_\theta} q_r \;-\; \sum_{\substack{r \in \mathcal D_\theta\\ d_r \le j}} q_r
\;+\; \sum_{\substack{r \in \mathcal C_\theta\\ p_r \le j}} q_r
\;+\; \sum_{r \text{ pair},\ p_r \le j < d_r} q_r,
$$

with $\mathcal D_\theta$ the depot deliveries of trip $\theta$ (loaded at its
start) and $\mathcal C_\theta$ its collections (unloaded at its end). A depot
delivery inserted after position $i$ therefore needs room from the start of
its trip to $i$, a collection from $i$ to the end of its trip; both are prefix
or suffix scans per trip. Reload stops enter plans through the merge operator:
$A \oplus \text{reload} \oplus B$ keeps every trip's loads, so only the timing
of the day has to be checked, and $B$ may come from another (e.g. hired) type
if its orders are admissible. Emptied trips are removed (a reload stop that
starts, ends or repeats a trip is dropped).

## 4c. Time-dependent travel

A road profile may carry speed factors $f_0, f_1, \dots$ for periods starting
at $\sigma_0 < \sigma_1 < \dots$ (Ichoua, Gendreau & Potvin 2003): a trip with
free-flow time $t$ leaving at $x$ progresses $f(x)$ free-flow minutes per
minute. Its arrival $\alpha_t(x)$ is continuous, strictly increasing and
piecewise linear (FIFO); its inverse is the latest departure
$\beta_t(y) = \alpha_t^{-1}(y)$.

**Lemma 2.** For a fixed sequence, the earliest schedule
$B_k = \max\big(e_k,\ \alpha_{t_{k-1,k}}(B_{k-1} + s_{k-1})\big)$ meets all
windows iff any schedule does, and
$\lambda_k = \min\big(l_k,\ \beta_{t_{k,k+1}}(\lambda_{k+1}) - s_k\big)$ is the
latest start at $v_k$ from which the rest can still be timed.

*Proof.* By induction on $k$: every feasible schedule has $B'_k \ge B_k$
because $\alpha$ and $\max$ are monotone; conversely $B$ itself respects the
lower bounds and, if $B'$ exists, $B_k \le B'_k \le l_k$. The statement for
$\lambda$ is the mirror argument with the monotone $\beta$. $\square$

Hence the insertion tests of section 2 stay exact for windows with
$\alpha$/$\beta$ in place of $+t$/$-t$. The closed-form shortest duration does
not survive; let $R(x)$ be the arrival at the end depot when leaving at $x$.

**Lemma 3.** $R(x) - x$ is piecewise linear on $[e_0, \lambda_0]$, and its
breakpoints are among the departures that, propagated without waiting, make
some service start at its window opening or make some leg start or end on a
period boundary.

*Proof.* $R$ is a composition of the piecewise-linear maps $\alpha$ and
$\max(e_k, \cdot)$. A map $\alpha_t$ bends where its departure or its arrival
crosses a $\sigma_j$, and $\max(e_k,\cdot)$ bends where its argument equals
$e_k$; when some service waits, everything after it is constant in $x$ and
adds no breakpoint. Mapping each such event back to the depot through the
$\beta$ of the preceding legs gives the stated set. $\square$

The verifier evaluates $R(x) - x$ at these candidates and at $e_0$, $\lambda_0$
(exact shortest duration, tested against a 400-point grid). The search uses a
sound test instead: the route passes the shift cap if leaving at $e_0$ or at
$\lambda_0$ keeps it within $T_k$ (both are schedules), so it never accepts an
infeasible route and may, rarely, reject a feasible one. Time costs are
charged on free-flow minutes.

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
[benchmarks/exact-vs-alns.md](benchmarks/exact-vs-alns.md); ALNS reaches it on
all 40.

## 7. Literature lane: Cordeau (2006) DARP

`benchmarks/cordeau_exact.py` solves the published algebra exactly:

* CP-SAT with `AddMultipleCircuit`, route labels ($V_j = V_i$ along arcs, the
  first pickup names the route, $V_i = V_{n+i}$), load and time propagation,
  ride rows; travel rounded up on a $10^{-3}$ grid;
* the compact two-index MIP of Furtado, Munari & Morabito (2017) with
  arc-specific big-M $M_{ij} = \max(0, l_i + s_i + t_{ij} - e_j)$, solved by
  SCIP, HiGHS or CBC, and its LP relaxation as a bound.

a2-16: CP-SAT proves 294.25 in 0.7 s; SCIP and HiGHS reach it in 26.2 s and
41.3 s; the LP bound is 85.27 (big-M is weak: 71% gap) —
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

## 9. How results are compared

A heuristic's result on one instance and one seed is one draw. Method
comparisons in this repository run several seeds per instance and report the
mean, standard deviation and best run; two configurations are compared on
paired runs (same instance, same seed) by the two-sided Wilcoxon
signed-rank test (Wilcoxon 1945; exact null distribution up to 25 untied
pairs, normal approximation with tie and continuity corrections above):
[benchmarks/seed-study.md](benchmarks/seed-study.md). Gaps to published
values are quoted only for verified plans that serve every order, and only
at the reference vehicle count when the reference ranks vehicles first.

## References

* Cattaruzza, D., Absi, N., Feillet, D. (2016). Vehicle routing problems with multiple trips. *4OR* 14(3):223–259.
* Christiaens, J., Vanden Berghe, G. (2020). Slack induction by string removals for vehicle routing problems. *Transportation Science* 54(2):417–433.
* Cordeau, J.-F. (2006). A branch-and-cut algorithm for the dial-a-ride problem. *Operations Research* 54(3):573–586.
* Dumas, Y., Desrosiers, J., Soumis, F. (1991). The pickup and delivery problem with time windows. *EJOR* 54(1):7–22.
* European Parliament and Council (2006). Regulation (EC) No 561/2006 on driving times and rest periods, art. 7.
* Furtado, M., Munari, P., Morabito, R. (2017). Pickup and delivery problem with time windows: a new compact two-index formulation. *Operations Research Letters* 45(4):334–341.
* Goel, A. (2009). Vehicle scheduling and routing with drivers' working hours. *Transportation Science* 43(1):17–26.
* Ichoua, S., Gendreau, M., Potvin, J.-Y. (2003). Vehicle dispatching with time-dependent travel times. *EJOR* 144(2):379–396.
* Kindervater, G.A.P., Savelsbergh, M.W.P. (1997). Vehicle routing: handling edge exchanges. In Aarts & Lenstra (eds.), *Local Search in Combinatorial Optimization*, Wiley, 337–360.
* Nagata, Y., Bräysy, O. (2009). A powerful route minimization heuristic for the vehicle routing problem with time windows. *Operations Research Letters* 37(5):333–338.
* Potvin, J.-Y., Rousseau, J.-M. (1993). A parallel route building algorithm for the VRPTW. *EJOR* 66(3):331–340.
* Rochat, Y., Taillard, É.D. (1995). Probabilistic diversification and intensification in local search for vehicle routing. *Journal of Heuristics* 1(1):147–167.
* Ropke, S., Pisinger, D. (2006). An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows. *Transportation Science* 40(4):455–472.
* Ropke, S., Cordeau, J.-F., Laporte, G. (2007). Models and branch-and-cut algorithms for pickup and delivery problems with time windows. *Networks* 49(4):258–272.
* Savelsbergh, M.W.P. (1992). The vehicle routing problem with time windows: minimizing route duration. *ORSA Journal on Computing* 4(2):146–154.
* Campbell, A.M., Savelsbergh, M. (2004). Efficient insertion heuristics for vehicle routing and scheduling problems. *Transportation Science* 38(3):369–378.
* Subramanian, A., Uchoa, E., Ochi, L.S. (2013). A hybrid algorithm for a class of vehicle routing problems. *Computers & Operations Research* 40(10):2519–2531.
* Shaw, P. (1998). Using constraint programming and local search methods to solve vehicle routing problems. *CP 1998*, LNCS 1520:417–431.
* Sartori, C.S., Buriol, L.S. (2020). A study on the pickup and delivery problem with time windows: matheuristics and new instances. *Computers & Operations Research* 124:105065.
* Toth, P., Vigo, D. (2003). The granular tabu search and its application to the vehicle-routing problem. *INFORMS Journal on Computing* 15(4):333–346.
* Vidal, T., Crainic, T.G., Gendreau, M., Prins, C. (2013). A hybrid genetic algorithm with adaptive diversity management for a large class of vehicle routing problems with time-windows. *Computers & Operations Research* 40(1):475–489.
* Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin* 1(6):80–83.
