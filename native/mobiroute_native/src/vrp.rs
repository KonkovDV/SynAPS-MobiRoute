//! Rich-VRP repair kernel: regret-k insertion with constant-time tests.
//!
//! Port of `src/mobiroute/vrp/insertion.py`. Every floating-point expression
//! keeps the Python evaluation order, ties break the same way and the noise
//! stream is the same SplitMix64, so the reference implementation and this
//! kernel return identical plans for one seed (see tests/test_vrp_native.py).
//!
//! Route state: earliest service start `begin`, latest start `late`, loads per
//! dimension, and for the shift cap the prefix/suffix extrema of `l_k - H_k`
//! and `e_k + G_k` (shortest feasible duration in O(1) per candidate).
//! Ride limits are checked lazily with Bellman-Ford on the cheapest candidates.

use std::sync::Arc;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const EPS: f64 = 1e-9;
const TIME_EPS: f64 = 1e-6;
const LAZY_CHECKS: usize = 32;
const MISSING: f64 = 1e15;

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn uniform(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / 9_007_199_254_740_992.0)
    }
}

#[inline(always)]
fn pick_max(a: f64, b: f64) -> f64 {
    if a > b {
        a
    } else {
        b
    }
}

#[inline(always)]
fn pick_min(a: f64, b: f64) -> f64 {
    if a < b {
        a
    } else {
        b
    }
}

type Candidate = (f64, usize, usize);

#[inline(always)]
fn less(a: &Candidate, b: &Candidate) -> bool {
    a.0 < b.0 || (a.0 == b.0 && (a.1 < b.1 || (a.1 == b.1 && a.2 < b.2)))
}

struct RouteState {
    t: usize,
    nodes: Vec<usize>,
    seq: Vec<usize>,
    begin: Vec<f64>,
    late: Vec<f64>,
    /// Loads after positions 0..=m, `dims` values per position.
    load: Vec<f64>,
    h: Vec<f64>,
    g_total: f64,
    lm_pre: Vec<f64>,
    lm_suf: Vec<f64>,
    a_pre: Vec<f64>,
    a_suf: Vec<f64>,
    has_ride: bool,
    /// Driving minutes along the route (rest rule).
    drive: f64,
    /// Start position of each position's trip; `None` for a route without reloads.
    trip_start: Option<Vec<usize>>,
}

#[pyclass(module = "mobiroute_native")]
pub struct VrpKernel {
    n: usize,
    dims: usize,
    e: Vec<f64>,
    l: Vec<f64>,
    s: Vec<f64>,
    n_types: usize,
    time: Vec<Arc<Vec<f64>>>,
    cost: Vec<Arc<Vec<f64>>>,
    svc_rate: Vec<f64>,
    open_cost: Vec<f64>,
    cap: Vec<f64>,
    count: Vec<usize>,
    start: Vec<usize>,
    end: Vec<usize>,
    t_min: Vec<f64>,
    start_lim: Vec<f64>,
    end_lim: Vec<f64>,
    max_dur: Vec<f64>,
    pick: Vec<i64>,
    deliv: Vec<i64>,
    demand: Vec<f64>,
    max_ride: Vec<f64>,
    allowed: Vec<bool>,
    node_req: Vec<i64>,
    has_ride: bool,
    max_cost: f64,
    /// Rest rule per type: most driving between rests (inf: none), rest length.
    brk_drive: Vec<f64>,
    brk_len: Vec<f64>,
    /// Vehicle type reloading at each node, -1 for every other node.
    reload_of: Vec<i64>,
    has_reload: bool,
}

struct Slot {
    state: RouteState,
    empty: bool,
    offered: bool,
}

impl VrpKernel {
    #[inline(always)]
    fn tm(&self, t: usize, a: usize, b: usize) -> f64 {
        self.time[t][a * self.n + b]
    }

    #[inline(always)]
    fn cs(&self, t: usize, a: usize, b: usize) -> f64 {
        self.cost[t][a * self.n + b]
    }

    fn state(&self, t: usize, nodes: Vec<usize>) -> RouteState {
        let (e, l, s) = (&self.e, &self.l, &self.s);
        let mut seq = Vec::with_capacity(nodes.len() + 2);
        seq.push(self.start[t]);
        seq.extend_from_slice(&nodes);
        seq.push(self.end[t]);
        let m2 = seq.len();
        let mut begin = vec![0.0; m2];
        begin[0] = self.t_min[t];
        for k in 1..m2 {
            let (a, b) = (seq[k - 1], seq[k]);
            let arr = begin[k - 1] + s[a] + self.tm(t, a, b);
            begin[k] = pick_max(arr, e[b]);
        }
        let mut lim: Vec<f64> = seq.iter().map(|&node| l[node]).collect();
        lim[0] = self.start_lim[t];
        lim[m2 - 1] = self.end_lim[t];
        let mut late = vec![0.0; m2];
        late[m2 - 1] = lim[m2 - 1];
        for k in (0..m2 - 1).rev() {
            let (a, b) = (seq[k], seq[k + 1]);
            let back = late[k + 1] - s[a] - self.tm(t, a, b);
            late[k] = pick_min(lim[k], back);
        }
        let mut drive = 0.0;
        for k in 1..m2 {
            drive += self.tm(t, seq[k - 1], seq[k]);
        }
        let (load, trip_start) = if self.has_reload && nodes.iter().any(|&n| self.reload_of[n] >= 0)
        {
            let (load, starts) = self.trip_loads(&nodes);
            (load, Some(starts))
        } else {
            (self.single_trip_loads(&nodes), None)
        };
        let mut h = vec![0.0; m2];
        for k in 1..m2 {
            let (a, b) = (seq[k - 1], seq[k]);
            h[k] = h[k - 1] + s[a] + self.tm(t, a, b);
        }
        let g_total = h[m2 - 1];
        let mut lm_pre = vec![0.0; m2];
        let mut lm_suf = vec![0.0; m2];
        let mut cur_min = f64::INFINITY;
        for k in 0..m2 {
            cur_min = pick_min(lim[k] - h[k], cur_min);
            lm_pre[k] = cur_min;
        }
        cur_min = f64::INFINITY;
        for k in (0..m2).rev() {
            cur_min = pick_min(lim[k] - h[k], cur_min);
            lm_suf[k] = cur_min;
        }
        let mut a_pre = vec![f64::NEG_INFINITY; m2];
        let mut a_suf = vec![f64::NEG_INFINITY; m2 + 1];
        let mut cur_max = f64::NEG_INFINITY;
        for k in 1..m2 {
            cur_max = pick_max(e[seq[k]] + (g_total - h[k]), cur_max);
            a_pre[k] = cur_max;
        }
        cur_max = f64::NEG_INFINITY;
        for k in (1..m2).rev() {
            cur_max = pick_max(e[seq[k]] + (g_total - h[k]), cur_max);
            a_suf[k] = cur_max;
        }
        let has_ride = self.has_ride
            && nodes.iter().any(|&n| {
                self.node_req[n] >= 0 && self.max_ride[self.node_req[n] as usize] < f64::INFINITY
            });
        RouteState {
            t,
            nodes,
            seq,
            begin,
            late,
            load,
            h,
            g_total,
            lm_pre,
            lm_suf,
            a_pre,
            a_suf,
            has_ride,
            drive,
            trip_start,
        }
    }

    /// Loads after positions 0..=m of a route without reloads (Python `single_trip_loads`).
    fn single_trip_loads(&self, nodes: &[usize]) -> Vec<f64> {
        let dims = self.dims;
        let mut initial = vec![0.0; dims];
        for &node in nodes {
            let r = self.node_req[node] as usize;
            if self.pick[r] < 0 {
                for d in 0..dims {
                    initial[d] += self.demand[r * dims + d];
                }
            }
        }
        let mut load = Vec::with_capacity((nodes.len() + 1) * dims);
        load.extend_from_slice(&initial);
        let mut cur = initial;
        for &node in nodes {
            let r = self.node_req[node] as usize;
            let sign = if node as i64 == self.pick[r] {
                1.0
            } else {
                -1.0
            };
            for d in 0..dims {
                cur[d] += sign * self.demand[r * dims + d];
            }
            load.extend_from_slice(&cur);
        }
        load
    }

    /// Loads per trip and each position's trip start (Python `trip_loads`).
    fn trip_loads(&self, nodes: &[usize]) -> (Vec<f64>, Vec<usize>) {
        let dims = self.dims;
        let mut trip_of = Vec::with_capacity(nodes.len());
        let mut trip = 0usize;
        for &node in nodes {
            if self.reload_of[node] >= 0 {
                trip += 1;
            }
            trip_of.push(trip);
        }
        let mut start = vec![0.0; (trip + 1) * dims];
        for (idx, &node) in nodes.iter().enumerate() {
            let r = self.node_req[node];
            if r >= 0 && self.pick[r as usize] < 0 {
                let r = r as usize;
                let row = trip_of[idx] * dims;
                for d in 0..dims {
                    start[row + d] += self.demand[r * dims + d];
                }
            }
        }
        let mut cur: Vec<f64> = start[0..dims].to_vec();
        let mut collected = vec![0.0; dims];
        let mut load = Vec::with_capacity((nodes.len() + 1) * dims);
        load.extend_from_slice(&cur);
        let mut trip_start = Vec::with_capacity(nodes.len() + 1);
        trip_start.push(0usize);
        for (idx, &node) in nodes.iter().enumerate() {
            if self.reload_of[node] >= 0 {
                let row = trip_of[idx] * dims;
                for d in 0..dims {
                    cur[d] = cur[d] - collected[d] + start[row + d];
                }
                collected.iter_mut().for_each(|x| *x = 0.0);
                trip_start.push(idx + 1);
            } else {
                let r = self.node_req[node] as usize;
                if node as i64 == self.pick[r] {
                    for d in 0..dims {
                        cur[d] += self.demand[r * dims + d];
                    }
                    if self.deliv[r] < 0 {
                        for d in 0..dims {
                            collected[d] += self.demand[r * dims + d];
                        }
                    }
                } else {
                    for d in 0..dims {
                        cur[d] -= self.demand[r * dims + d];
                    }
                }
                let last = *trip_start.last().expect("trip start");
                trip_start.push(last);
            }
            load.extend_from_slice(&cur);
        }
        (load, trip_start)
    }

    /// Positions where a single-node order fits on board trip by trip.
    fn single_positions(&self, st: &RouteState, fits: &[bool], prefix: bool) -> Vec<usize> {
        let trip_start = st.trip_start.as_ref().expect("route with reloads");
        let m = st.seq.len() - 2;
        let mut ok = vec![false; m + 1];
        if prefix {
            for i in 0..=m {
                ok[i] = fits[i] && (trip_start[i] == i || ok[i - 1]);
            }
        } else {
            for i in (0..=m).rev() {
                let ends_here = i == m || trip_start[i + 1] == i + 1;
                ok[i] = fits[i] && (ends_here || ok[i + 1]);
            }
        }
        (0..=m).filter(|&i| ok[i]).collect()
    }

    fn fits(&self, st: &RouteState, r: usize) -> Vec<bool> {
        let dims = self.dims;
        let positions = st.load.len() / dims;
        let cap = &self.cap[st.t * dims..st.t * dims + dims];
        let q = &self.demand[r * dims..r * dims + dims];
        if dims == 1 {
            let room = cap[0] - q[0] + EPS;
            return st.load.iter().map(|&x| x <= room).collect();
        }
        (0..positions)
            .map(|k| (0..dims).all(|d| st.load[k * dims + d] + q[d] <= cap[d] + EPS))
            .collect()
    }

    #[allow(clippy::too_many_arguments)]
    fn min_duration_ok(
        &self,
        st: &RouteState,
        i: usize,
        j: Option<usize>,
        p: usize,
        d: usize,
        mid_min: f64,
        mid_amax: f64,
    ) -> bool {
        let t = st.t;
        let (s, e, l) = (&self.s, &self.e, &self.l);
        let seq = &st.seq;
        let h = &st.h;
        let a = seq[i];
        let b = seq[i + 1];
        let hp = h[i] + s[a] + self.tm(t, a, p);
        let (g0, dep, amax);
        match j {
            None => {
                let delta =
                    (s[a] + self.tm(t, a, p) + s[p] + self.tm(t, p, b)) - (s[a] + self.tm(t, a, b));
                g0 = st.g_total + delta;
                dep = pick_min(pick_min(st.lm_pre[i], st.lm_suf[i + 1] - delta), l[p] - hp);
                amax = pick_max(
                    pick_max(st.a_pre[i] + delta, st.a_suf[i + 1]),
                    e[p] + (g0 - hp),
                );
            }
            Some(jj) if jj == i => {
                let hd = hp + s[p] + self.tm(t, p, d);
                let delta =
                    (s[a] + self.tm(t, a, p) + s[p] + self.tm(t, p, d) + s[d] + self.tm(t, d, b))
                        - (s[a] + self.tm(t, a, b));
                g0 = st.g_total + delta;
                dep = pick_min(
                    pick_min(pick_min(st.lm_pre[i], st.lm_suf[i + 1] - delta), l[p] - hp),
                    l[d] - hd,
                );
                amax = pick_max(
                    pick_max(
                        pick_max(st.a_pre[i] + delta, st.a_suf[i + 1]),
                        e[p] + (g0 - hp),
                    ),
                    e[d] + (g0 - hd),
                );
            }
            Some(jj) => {
                let cj = seq[jj];
                let nx = seq[jj + 1];
                let d1 =
                    (s[a] + self.tm(t, a, p) + s[p] + self.tm(t, p, b)) - (s[a] + self.tm(t, a, b));
                let d2 = (s[cj] + self.tm(t, cj, d) + s[d] + self.tm(t, d, nx))
                    - (s[cj] + self.tm(t, cj, nx));
                let delta = d1 + d2;
                let hd = h[jj] + d1 + s[cj] + self.tm(t, cj, d);
                g0 = st.g_total + delta;
                dep = pick_min(
                    pick_min(
                        pick_min(
                            pick_min(st.lm_pre[i], mid_min - d1),
                            st.lm_suf[jj + 1] - delta,
                        ),
                        l[p] - hp,
                    ),
                    l[d] - hd,
                );
                amax = pick_max(
                    pick_max(
                        pick_max(
                            pick_max(st.a_pre[i] + delta, mid_amax + d2),
                            st.a_suf[jj + 1],
                        ),
                        e[p] + (g0 - hp),
                    ),
                    e[d] + (g0 - hd),
                );
            }
        }
        let duration = if g0 > amax - dep { g0 } else { amax - dep };
        duration <= self.max_dur[t] + EPS
    }

    fn exact_feasible(
        &self,
        t: usize,
        nodes: &[usize],
        rest_arc: Option<usize>,
        rest: f64,
    ) -> bool {
        let (e, l, s) = (&self.e, &self.l, &self.s);
        let mut seq = Vec::with_capacity(nodes.len() + 2);
        seq.push(self.start[t]);
        seq.extend_from_slice(nodes);
        seq.push(self.end[t]);
        let m = seq.len();
        let z = m;
        let last = m - 1;
        let mut tails: Vec<usize> = Vec::with_capacity(4 * m);
        let mut heads: Vec<usize> = Vec::with_capacity(4 * m);
        let mut weights: Vec<f64> = Vec::with_capacity(4 * m);
        for k in 0..m {
            let node = seq[k];
            let (lo, hi) = if k == 0 {
                (self.t_min[t], self.start_lim[t])
            } else if k == last {
                (e[node], self.end_lim[t])
            } else {
                (e[node], l[node])
            };
            if hi < f64::INFINITY {
                tails.push(z);
                heads.push(k);
                weights.push(hi);
            }
            tails.push(k);
            heads.push(z);
            weights.push(-lo);
        }
        for k in 0..m - 1 {
            let (a, b) = (seq[k], seq[k + 1]);
            tails.push(k + 1);
            heads.push(k);
            if rest_arc == Some(k) {
                weights.push(-(s[a] + self.tm(t, a, b) + rest));
            } else {
                weights.push(-(s[a] + self.tm(t, a, b)));
            }
        }
        for k in 1..last {
            let node = seq[k];
            if self.node_req[node] < 0 {
                continue;
            }
            let r = self.node_req[node] as usize;
            if self.pick[r] == node as i64 && self.max_ride[r] < f64::INFINITY {
                let target = self.deliv[r];
                if let Some(kd) = (1..last).find(|&x| seq[x] as i64 == target) {
                    tails.push(k);
                    heads.push(kd);
                    weights.push(self.max_ride[r] + s[node]);
                }
            }
        }
        if self.max_dur[t] < f64::INFINITY {
            tails.push(0);
            heads.push(last);
            weights.push(self.max_dur[t]);
        }
        let n_vertices = m + 1;
        let mut dist = vec![f64::INFINITY; n_vertices];
        dist[z] = 0.0;
        for _ in 0..n_vertices - 1 {
            let mut changed = false;
            for x in 0..tails.len() {
                let cand = dist[heads[x]] + weights[x];
                if cand < dist[tails[x]] - 1e-12 {
                    dist[tails[x]] = cand;
                    changed = true;
                }
            }
            if !changed {
                return true;
            }
        }
        (0..tails.len()).all(|x| dist[heads[x]] + weights[x] >= dist[tails[x]] - TIME_EPS)
    }

    /// Exact feasibility with the rest rule (Python `route_exact`).
    fn route_exact(&self, t: usize, nodes: &[usize]) -> bool {
        let limit = self.brk_drive[t];
        if limit == f64::INFINITY {
            return self.exact_feasible(t, nodes, None, 0.0);
        }
        let mut seq = Vec::with_capacity(nodes.len() + 2);
        seq.push(self.start[t]);
        seq.extend_from_slice(nodes);
        seq.push(self.end[t]);
        let legs: Vec<f64> = (0..seq.len() - 1)
            .map(|k| self.tm(t, seq[k], seq[k + 1]))
            .collect();
        let mut total = 0.0;
        for &leg in &legs {
            total += leg;
        }
        if total <= limit + EPS {
            return self.exact_feasible(t, nodes, None, 0.0);
        }
        if total > 2.0 * limit + EPS {
            return false;
        }
        let low = total - limit - EPS;
        let high = limit + EPS;
        let mut done = 0.0;
        for (k, &leg) in legs.iter().enumerate() {
            let after = done + leg;
            if ((low <= done && done <= high) || (low <= after && after <= high))
                && self.exact_feasible(t, nodes, Some(k), self.brk_len[t])
            {
                return true;
            }
            done = after;
        }
        false
    }

    /// Extra driving of inserting `p`/`d` at `i`/`j` (Python `_drive_delta`).
    fn drive_delta(&self, st: &RouteState, p: i64, d: i64, i: usize, j: usize) -> f64 {
        let t = st.t;
        let seq = &st.seq;
        let (a, b) = (seq[i], seq[i + 1]);
        if p < 0 || d < 0 {
            let u = if p >= 0 { p as usize } else { d as usize };
            return self.tm(t, a, u) + self.tm(t, u, b) - self.tm(t, a, b);
        }
        let (p, d) = (p as usize, d as usize);
        if j == i {
            return self.tm(t, a, p) + self.tm(t, p, d) + self.tm(t, d, b) - self.tm(t, a, b);
        }
        let (cj, nx) = (seq[j], seq[j + 1]);
        (self.tm(t, a, p) + self.tm(t, p, b) - self.tm(t, a, b))
            + (self.tm(t, cj, d) + self.tm(t, d, nx) - self.tm(t, cj, nx))
    }

    fn splice(nodes: &[usize], i: usize, j: usize, p: usize, d: Option<usize>) -> Vec<usize> {
        let mut out = Vec::with_capacity(nodes.len() + 2);
        match d {
            None => {
                out.extend_from_slice(&nodes[..i]);
                out.push(p);
                out.extend_from_slice(&nodes[i..]);
            }
            Some(dd) if j == i => {
                out.extend_from_slice(&nodes[..i]);
                out.push(p);
                out.push(dd);
                out.extend_from_slice(&nodes[i..]);
            }
            Some(dd) => {
                out.extend_from_slice(&nodes[..i]);
                out.push(p);
                out.extend_from_slice(&nodes[i..j]);
                out.push(dd);
                out.extend_from_slice(&nodes[j..]);
            }
        }
        out
    }

    fn apply(&self, nodes: &[usize], r: usize, i: usize, j: usize) -> Vec<usize> {
        let (p, d) = (self.pick[r], self.deliv[r]);
        if p >= 0 && d >= 0 {
            Self::splice(nodes, i, j, p as usize, Some(d as usize))
        } else {
            let u = if p >= 0 { p } else { d } as usize;
            Self::splice(nodes, i, i, u, None)
        }
    }

    fn single_candidates(
        &self,
        st: &RouteState,
        u: usize,
        fits: &[bool],
        extra: f64,
        check_dur: bool,
        lazy: bool,
        prefix: bool,
        out: &mut Vec<Candidate>,
    ) -> Option<Candidate> {
        let t = st.t;
        let (seq, begin, late) = (&st.seq, &st.begin, &st.late);
        let s = &self.s;
        let (eu, lu, su) = (self.e[u], self.l[u], self.s[u]);
        let m = seq.len() - 2;
        let mut best: Option<Candidate> = None;
        // A delivery from the depot rides from its trip's start, a collection to
        // its trip's end; without reloads the trip is the whole route.
        let (lo, hi) = if prefix {
            let mut last = 0;
            while last <= m && fits[last] {
                last += 1;
            }
            (0, last)
        } else {
            let mut first = m + 1;
            while first > 0 && fits[first - 1] {
                first -= 1;
            }
            (first, m + 1)
        };
        let mut visit = |i: usize| {
            let (a, b) = (seq[i], seq[i + 1]);
            let arr = begin[i] + s[a] + self.tm(t, a, u);
            let bu = pick_max(arr, eu);
            if bu > lu + EPS || bu + su + self.tm(t, u, b) > late[i + 1] + EPS {
                return;
            }
            if check_dur && !self.min_duration_ok(st, i, None, u, u, 0.0, 0.0) {
                return;
            }
            let cand = (
                (self.cs(t, a, u) + self.cs(t, u, b) - self.cs(t, a, b)) + extra,
                i,
                i,
            );
            if lazy {
                out.push(cand);
            } else if best.as_ref().is_none_or(|bst| less(&cand, bst)) {
                best = Some(cand);
            }
        };
        if st.trip_start.is_some() {
            for i in self.single_positions(st, fits, prefix) {
                visit(i);
            }
        } else {
            for i in lo..hi {
                visit(i);
            }
        }
        best
    }

    fn pair_candidates(
        &self,
        st: &RouteState,
        p: usize,
        d: usize,
        fits: &[bool],
        extra: f64,
        check_dur: bool,
        lazy: bool,
        out: &mut Vec<Candidate>,
    ) -> Option<Candidate> {
        let t = st.t;
        let (seq, begin, late) = (&st.seq, &st.begin, &st.late);
        let (e, l, s) = (&self.e, &self.l, &self.s);
        let (ep, lp, sp) = (e[p], l[p], s[p]);
        let (ed, ld, sd) = (e[d], l[d], s[d]);
        let tpd = self.tm(t, p, d);
        let cpd = self.cs(t, p, d);
        let m = seq.len() - 2;
        let mut best: Option<Candidate> = None;
        for i in 0..m + 1 {
            if !fits[i] {
                continue;
            }
            let (a, b) = (seq[i], seq[i + 1]);
            let arr = begin[i] + s[a] + self.tm(t, a, p);
            let bp = pick_max(arr, ep);
            if bp > lp + EPS {
                continue;
            }
            let arr_d = bp + sp + tpd;
            let bd = pick_max(arr_d, ed);
            if bd <= ld + EPS
                && bd + sd + self.tm(t, d, b) <= late[i + 1] + EPS
                && (!check_dur || self.min_duration_ok(st, i, Some(i), p, d, 0.0, 0.0))
            {
                let cand = (
                    (self.cs(t, a, p) + cpd + self.cs(t, d, b) - self.cs(t, a, b)) + extra,
                    i,
                    i,
                );
                if lazy {
                    out.push(cand);
                } else if best.as_ref().is_none_or(|bst| less(&cand, bst)) {
                    best = Some(cand);
                }
            }
            let detour_p = self.cs(t, a, p) + self.cs(t, p, b) - self.cs(t, a, b);
            let mut tcur = bp + sp + self.tm(t, p, b);
            let mut mid_min = f64::INFINITY;
            let mut mid_amax = f64::NEG_INFINITY;
            for j in i + 1..m + 1 {
                let cj = seq[j];
                let ej = e[cj];
                let bj = pick_max(tcur, ej);
                if bj > l[cj] + EPS || !fits[j] {
                    break;
                }
                if check_dur {
                    mid_min = pick_min(l[cj] - st.h[j], mid_min);
                    mid_amax = pick_max(ej + (st.g_total - st.h[j]), mid_amax);
                }
                let nx = seq[j + 1];
                let arr_d = bj + s[cj] + self.tm(t, cj, d);
                let bd = pick_max(arr_d, ed);
                if bd <= ld + EPS
                    && bd + sd + self.tm(t, d, nx) <= late[j + 1] + EPS
                    && (!check_dur || self.min_duration_ok(st, i, Some(j), p, d, mid_min, mid_amax))
                {
                    let cand = (
                        detour_p
                            + (self.cs(t, cj, d) + self.cs(t, d, nx) - self.cs(t, cj, nx))
                            + extra,
                        i,
                        j,
                    );
                    if lazy {
                        out.push(cand);
                    } else if best.as_ref().is_none_or(|bst| less(&cand, bst)) {
                        best = Some(cand);
                    }
                }
                tcur = bj + s[cj] + self.tm(t, cj, nx);
            }
        }
        best
    }

    fn best_insertion_state(&self, st: &RouteState, r: usize) -> Option<Candidate> {
        let t = st.t;
        if !self.allowed[r * self.n_types + t] {
            return None;
        }
        let (p, d) = (self.pick[r], self.deliv[r]);
        let rests = self.brk_drive[t] < f64::INFINITY;
        let lazy = (self.has_ride && (st.has_ride || self.max_ride[r] < f64::INFINITY)) || rests;
        let check_dur = !lazy && self.max_dur[t] < f64::INFINITY;
        let fits = self.fits(st, r);
        let m = st.seq.len() - 2;
        let sp = if p >= 0 { self.s[p as usize] } else { 0.0 };
        let sd = if d >= 0 { self.s[d as usize] } else { 0.0 };
        let mut extra = self.svc_rate[t] * (sp + sd);
        if m == 0 {
            extra += self.open_cost[t];
        }
        let mut out: Vec<Candidate> = Vec::new();
        let best = if p >= 0 && d >= 0 {
            self.pair_candidates(
                st, p as usize, d as usize, &fits, extra, check_dur, lazy, &mut out,
            )
        } else if d >= 0 {
            self.single_candidates(
                st, d as usize, &fits, extra, check_dur, lazy, true, &mut out,
            )
        } else {
            self.single_candidates(
                st, p as usize, &fits, extra, check_dur, lazy, false, &mut out,
            )
        };
        if !lazy {
            return best;
        }
        if rests {
            let room = 2.0 * self.brk_drive[t] - st.drive + EPS;
            out.retain(|cand| self.drive_delta(st, p, d, cand.1, cand.2) <= room);
        }
        out.sort_by(|a, b| {
            a.0.partial_cmp(&b.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.1.cmp(&b.1))
                .then(a.2.cmp(&b.2))
        });
        for cand in out.iter().take(LAZY_CHECKS) {
            let nodes = self.apply(&st.nodes, r, cand.1, cand.2);
            if self.route_exact(t, &nodes) {
                return Some(*cand);
            }
        }
        None
    }

    fn evaluate(&self, r: usize, slot: &Slot, rng: &mut Option<SplitMix64>, amp: f64) -> f64 {
        if !slot.offered {
            return MISSING;
        }
        let found = self.best_insertion_state(&slot.state, r);
        if let Some(gen) = rng.as_mut() {
            let jitter = amp * (2.0 * gen.uniform() - 1.0);
            return match found {
                None => MISSING,
                Some(c) => {
                    let value = c.0 + jitter;
                    if value > 0.0 {
                        value
                    } else {
                        0.0
                    }
                }
            };
        }
        match found {
            None => MISSING,
            Some(c) => c.0,
        }
    }

    fn repair_inner(
        &self,
        routes: Vec<(usize, Vec<usize>)>,
        unassigned: Vec<usize>,
        regret: usize,
        noise: f64,
        seed: u64,
        max_vehicles: Option<usize>,
    ) -> (Vec<(usize, Vec<usize>)>, Vec<usize>) {
        let mut rng = if noise > 0.0 {
            Some(SplitMix64::new(seed))
        } else {
            None
        };
        let amp = noise * self.max_cost;
        let mut slots: Vec<Slot> = Vec::new();
        let mut used = vec![0usize; self.n_types];
        for (t, nodes) in routes {
            if !nodes.is_empty() {
                slots.push(Slot {
                    state: self.state(t, nodes),
                    empty: false,
                    offered: true,
                });
                used[t] += 1;
            }
        }
        let limit = max_vehicles.unwrap_or_else(|| self.count.iter().sum());
        if used.iter().sum::<usize>() < limit {
            for t in 0..self.n_types {
                if used[t] < self.count[t] {
                    slots.push(Slot {
                        state: self.state(t, Vec::new()),
                        empty: true,
                        offered: true,
                    });
                }
            }
        }
        let mut pending = unassigned;
        pending.sort_unstable();
        pending.dedup();
        let mut table: Vec<Vec<f64>> = Vec::with_capacity(pending.len());
        for &r in &pending {
            let row: Vec<f64> = slots
                .iter()
                .map(|slot| self.evaluate(r, slot, &mut rng, amp))
                .collect();
            table.push(row);
        }
        let k = regret.max(1);
        let mut unserved: Vec<usize> = Vec::new();
        let mut sorted_row: Vec<f64> = Vec::new();
        while !pending.is_empty() {
            let mut pick: Option<(usize, (f64, f64, usize))> = None;
            for (idx, &r) in pending.iter().enumerate() {
                sorted_row.clear();
                sorted_row.extend_from_slice(&table[idx]);
                sorted_row.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                let c1 = if sorted_row.is_empty() {
                    MISSING
                } else {
                    sorted_row[0]
                };
                if c1 >= MISSING {
                    continue;
                }
                let key = if k == 1 {
                    (0.0, c1, r)
                } else {
                    let mut rg = 0.0;
                    for hh in 1..k {
                        let ch = if hh < sorted_row.len() {
                            sorted_row[hh]
                        } else {
                            MISSING
                        };
                        rg += ch - c1;
                    }
                    (-rg, c1, r)
                };
                let better = match &pick {
                    None => true,
                    Some((_, pk)) => {
                        key.0 < pk.0
                            || (key.0 == pk.0 && (key.1 < pk.1 || (key.1 == pk.1 && key.2 < pk.2)))
                    }
                };
                if better {
                    pick = Some((idx, key));
                }
            }
            let Some((pidx, _)) = pick else {
                unserved.extend_from_slice(&pending);
                break;
            };
            let pick_r = pending[pidx];
            let values = &table[pidx];
            let mut best_slot = 0;
            for x in 1..slots.len() {
                if values[x] < values[best_slot] {
                    best_slot = x;
                }
            }
            let found = self
                .best_insertion_state(&slots[best_slot].state, pick_r)
                .expect("chosen slot must accept the request");
            let t = slots[best_slot].state.t;
            let new_nodes = self.apply(&slots[best_slot].state.nodes, pick_r, found.1, found.2);
            slots[best_slot].state = self.state(t, new_nodes);
            pending.remove(pidx);
            table.remove(pidx);
            let mut refresh = vec![best_slot];
            if slots[best_slot].empty {
                slots[best_slot].empty = false;
                used[t] += 1;
                if used.iter().sum::<usize>() >= limit {
                    for slot in slots.iter_mut() {
                        if slot.empty {
                            slot.offered = false;
                        }
                    }
                    for row in table.iter_mut() {
                        for (x, slot) in slots.iter().enumerate() {
                            if slot.empty {
                                row[x] = MISSING;
                            }
                        }
                    }
                } else if used[t] < self.count[t] {
                    slots.push(Slot {
                        state: self.state(t, Vec::new()),
                        empty: true,
                        offered: true,
                    });
                    refresh.push(slots.len() - 1);
                }
            }
            for (idx, &r) in pending.iter().enumerate() {
                for &x in &refresh {
                    let value = self.evaluate(r, &slots[x], &mut rng, amp);
                    let row = &mut table[idx];
                    if x < row.len() {
                        row[x] = value;
                    } else {
                        row.push(value);
                    }
                }
            }
        }
        let out_routes = slots
            .into_iter()
            .filter(|slot| !slot.state.nodes.is_empty())
            .map(|slot| (slot.state.t, slot.state.nodes))
            .collect();
        unserved.sort_unstable();
        (out_routes, unserved)
    }

    fn request_nodes(&self, r: usize) -> [i64; 2] {
        [self.pick[r], self.deliv[r]]
    }

    fn eject_inner(
        &self,
        routes: &[(usize, Vec<usize>)],
        v: usize,
        penalty: &[i64],
    ) -> Option<(usize, Vec<usize>, Vec<usize>)> {
        let mut options: Vec<(i64, usize, Vec<usize>)> = Vec::new();
        for (ri, (t, nodes)) in routes.iter().enumerate() {
            if !self.allowed[v * self.n_types + *t] {
                continue;
            }
            let mut on: Vec<usize> = nodes
                .iter()
                .filter(|&&n| self.node_req[n] >= 0)
                .map(|&n| self.node_req[n] as usize)
                .collect();
            on.sort_unstable();
            on.dedup();
            options.push((0, ri, Vec::new()));
            for &a in &on {
                options.push((penalty[a], ri, vec![a]));
            }
            for x in 0..on.len() {
                for y in x + 1..on.len() {
                    let (a, b) = (on[x], on[y]);
                    options.push((penalty[a] + penalty[b], ri, vec![a, b]));
                }
            }
        }
        options.sort();
        let mut best: Option<(i64, f64, usize, Vec<usize>, usize, usize, Vec<usize>)> = None;
        for (score, ri, eject) in options {
            if let Some(bst) = &best {
                if score > bst.0 {
                    break;
                }
            }
            let (t, nodes) = &routes[ri];
            let gone: Vec<i64> = eject
                .iter()
                .flat_map(|&e| self.request_nodes(e))
                .filter(|&n| n >= 0)
                .collect();
            let kept: Vec<usize> = nodes
                .iter()
                .copied()
                .filter(|&n| !gone.contains(&(n as i64)))
                .collect();
            if !eject.is_empty() && !self.route_exact(*t, &kept) {
                continue;
            }
            let st = self.state(*t, kept);
            let Some(found) = self.best_insertion_state(&st, v) else {
                continue;
            };
            let better = match &best {
                None => true,
                Some(bst) => {
                    score < bst.0
                        || (score == bst.0 && (found.0 < bst.1 || (found.0 == bst.1 && ri < bst.2)))
                }
            };
            if better {
                best = Some((score, found.0, ri, eject, found.1, found.2, st.nodes));
            }
        }
        best.map(|(_, _, ri, eject, i, j, kept)| (ri, self.apply(&kept, v, i, j), eject))
    }

    fn check_route(&self, t: usize, nodes: &[usize]) -> PyResult<()> {
        if t >= self.n_types {
            return Err(PyValueError::new_err("VRP_KERNEL_TYPE_OUT_OF_RANGE"));
        }
        if nodes
            .iter()
            .any(|&n| n >= self.n || (self.node_req[n] < 0 && self.reload_of[n] != t as i64))
        {
            return Err(PyValueError::new_err("VRP_KERNEL_NOT_A_SERVICE_NODE"));
        }
        Ok(())
    }
}

#[pymethods]
impl VrpKernel {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(
        n: usize,
        dims: usize,
        e: Vec<f64>,
        l: Vec<f64>,
        s: Vec<f64>,
        matrices: Vec<Vec<f64>>,
        time_idx: Vec<usize>,
        cost_idx: Vec<usize>,
        svc_rate: Vec<f64>,
        open_cost: Vec<f64>,
        cap: Vec<f64>,
        count: Vec<usize>,
        start: Vec<usize>,
        end: Vec<usize>,
        t_min: Vec<f64>,
        start_lim: Vec<f64>,
        end_lim: Vec<f64>,
        max_dur: Vec<f64>,
        pick: Vec<i64>,
        deliv: Vec<i64>,
        demand: Vec<f64>,
        max_ride: Vec<f64>,
        allowed: Vec<bool>,
        node_req: Vec<i64>,
        max_cost: f64,
        brk_drive: Vec<f64>,
        brk_len: Vec<f64>,
        reload_of: Vec<i64>,
    ) -> PyResult<Self> {
        let n_types = time_idx.len();
        let n_req = pick.len();
        let bad = |what: &str| PyValueError::new_err(format!("VRP_KERNEL_SHAPE:{what}"));
        if dims == 0
            || e.len() != n
            || l.len() != n
            || s.len() != n
            || node_req.len() != n
            || reload_of.len() != n
        {
            return Err(bad("nodes"));
        }
        if matrices.iter().any(|m| m.len() != n * n) {
            return Err(bad("matrix"));
        }
        let per_type = [
            cost_idx.len(),
            svc_rate.len(),
            open_cost.len(),
            count.len(),
            start.len(),
            end.len(),
            t_min.len(),
            start_lim.len(),
            end_lim.len(),
            max_dur.len(),
            brk_drive.len(),
            brk_len.len(),
        ];
        if n_types == 0 || per_type.iter().any(|&x| x != n_types) || cap.len() != n_types * dims {
            return Err(bad("types"));
        }
        if time_idx
            .iter()
            .chain(cost_idx.iter())
            .any(|&x| x >= matrices.len())
        {
            return Err(bad("matrix index"));
        }
        if start.iter().chain(end.iter()).any(|&x| x >= n) {
            return Err(bad("depot"));
        }
        if deliv.len() != n_req
            || max_ride.len() != n_req
            || demand.len() != n_req * dims
            || allowed.len() != n_req * n_types
        {
            return Err(bad("requests"));
        }
        if pick.iter().chain(deliv.iter()).any(|&x| x >= n as i64)
            || node_req.iter().any(|&x| x >= n_req as i64)
        {
            return Err(bad("request nodes"));
        }
        let shared: Vec<Arc<Vec<f64>>> = matrices.into_iter().map(Arc::new).collect();
        let has_ride = max_ride.iter().any(|&x| x < f64::INFINITY);
        if reload_of.iter().any(|&x| x >= n_types as i64) {
            return Err(bad("reload types"));
        }
        let has_reload = reload_of.iter().any(|&x| x >= 0);
        Ok(Self {
            n,
            dims,
            e,
            l,
            s,
            n_types,
            time: time_idx.iter().map(|&k| Arc::clone(&shared[k])).collect(),
            cost: cost_idx.iter().map(|&k| Arc::clone(&shared[k])).collect(),
            svc_rate,
            open_cost,
            cap,
            count,
            start,
            end,
            t_min,
            start_lim,
            end_lim,
            max_dur,
            pick,
            deliv,
            demand,
            max_ride,
            allowed,
            node_req,
            has_ride,
            max_cost,
            brk_drive,
            brk_len,
            reload_of,
            has_reload,
        })
    }

    /// Regret-k repair; returns `(routes, unassigned)` like the Python reference.
    #[pyo3(signature = (routes, unassigned, regret, noise, seed, max_vehicles=None))]
    fn repair(
        &self,
        py: Python<'_>,
        routes: Vec<(usize, Vec<usize>)>,
        unassigned: Vec<usize>,
        regret: usize,
        noise: f64,
        seed: u64,
        max_vehicles: Option<usize>,
    ) -> PyResult<(Vec<(usize, Vec<usize>)>, Vec<usize>)> {
        for (t, nodes) in &routes {
            self.check_route(*t, nodes)?;
        }
        if unassigned.iter().any(|&r| r >= self.pick.len()) {
            return Err(PyValueError::new_err("VRP_KERNEL_REQUEST_OUT_OF_RANGE"));
        }
        Ok(py.detach(|| self.repair_inner(routes, unassigned, regret, noise, seed, max_vehicles)))
    }

    /// Cheapest feasible `(delta, i, j)` of request `r` in route `(t, nodes)`.
    fn best_insertion(
        &self,
        t: usize,
        nodes: Vec<usize>,
        r: usize,
    ) -> PyResult<Option<(f64, usize, usize)>> {
        self.check_route(t, &nodes)?;
        if r >= self.pick.len() {
            return Err(PyValueError::new_err("VRP_KERNEL_REQUEST_OUT_OF_RANGE"));
        }
        let st = self.state(t, nodes);
        Ok(self.best_insertion_state(&st, r))
    }

    /// Guided-ejection step: fit request `v` into one route by ejecting at most
    /// two orders, choosing the ejection set with the lowest penalty sum, then
    /// the cheapest insertion, then the lowest route index. Mirrors
    /// `Alns._eject_insert`; returns `(route index, new nodes, ejected)`.
    fn eject_insert(
        &self,
        py: Python<'_>,
        routes: Vec<(usize, Vec<usize>)>,
        v: usize,
        penalty: Vec<i64>,
    ) -> PyResult<Option<(usize, Vec<usize>, Vec<usize>)>> {
        for (t, nodes) in &routes {
            self.check_route(*t, nodes)?;
        }
        if v >= self.pick.len() || penalty.len() != self.pick.len() {
            return Err(PyValueError::new_err("VRP_KERNEL_REQUEST_OUT_OF_RANGE"));
        }
        Ok(py.detach(|| self.eject_inner(&routes, v, &penalty)))
    }

    /// Exact timing feasibility of a fixed sequence (ride and shift limits included).
    fn exact_feasible_route(&self, t: usize, nodes: Vec<usize>) -> PyResult<bool> {
        self.check_route(t, &nodes)?;
        Ok(self.route_exact(t, &nodes))
    }
}
