//! MobiRoute insertion scoring kernel (SynAPS-style PyO3 hot path).
//! Prefix-state reuse + incremental (i, j) / VIA walk (Savelsbergh concatenated
//! evaluation; Hu/Omega 2026 linear-test analogue) + persistent fleet
//! (Jaw/Cordeau) + rayon over vehicles + Arc copy-on-write fork.
//! Trip row is 16×i32 = one 64-byte cache line (AoS, not PDX/SoA: access is
//! trip-at-a-time, not dimension-at-a-time). Not Gschwind–Drexl O(1) FTS:
//! VIA, stretcher, unavail occupancy, and appointment lobby snap break that
//! auxiliary-data contract. Heuristic, never OPTIMAL.
//! ABI: trip stride 16; best_insert returns (i, mid, j, dur, wait, max_load); mid=-1 if no VIA.
//! score_fleet returns (fleet_index, i, mid, j, dur, wait, max_load) per feasible vehicle.

use std::sync::Arc;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

const STRIDE: usize = 16;
const FLAG_LIFT: i32 = 1;
const FLAG_RAMP: i32 = 2;
const FLAG_ASSIST: i32 = 4;
const FLAG_STRETCHER: i32 = 8;
const WT_NONE: i32 = 0;
const CURB_WAIT: i32 = 5;
const EARLY_DROPOFF_SLACK: i32 = 30;

struct TripView {
    pu: i32,
    do_: i32,
    earliest: i32,
    latest: i32,
    max_wait: i32,
    max_ride: i32,
    board: i32,
    alight: i32,
    appt_s: i32,
    appt_e: i32,
    seats: i32,
    wunits: i32,
    flags: i32,
    wt: i32,
    via: i32,
    via_svc: i32,
    detour: f64,
}

#[inline(always)]
fn trip_at(table: &[i32], detour: &[f64], idx: usize) -> TripView {
    let o = idx * STRIDE;
    TripView {
        pu: table[o],
        do_: table[o + 1],
        earliest: table[o + 2],
        latest: table[o + 3],
        max_wait: table[o + 4],
        max_ride: table[o + 5],
        board: table[o + 6],
        alight: table[o + 7],
        appt_s: table[o + 8],
        appt_e: table[o + 9],
        seats: table[o + 10],
        wunits: table[o + 11],
        flags: table[o + 12],
        wt: table[o + 13],
        via: table[o + 14],
        via_svc: table[o + 15],
        detour: detour[idx],
    }
}

#[inline(always)]
fn detour_limit(direct: i32, ratio: f64) -> i32 {
    let milli = (ratio * 1000.0).round() as i64;
    (direct as i64 * milli / 1000) as i32 + 1
}

fn occupancy_overlaps(start: i32, end: i32, unavail: &[i32]) -> bool {
    let mut u = 0;
    while u + 1 < unavail.len() {
        let u0 = unavail[u];
        let u1 = unavail[u + 1];
        if start < u1 && end > u0 {
            return true;
        }
        u += 2;
    }
    false
}

fn push_past_unavail(mut tnow: i32, unavail: &[i32]) -> i32 {
    let mut moved = true;
    while moved {
        moved = false;
        let mut u = 0;
        while u + 1 < unavail.len() {
            let u0 = unavail[u];
            let u1 = unavail[u + 1];
            if tnow >= u0 && tnow < u1 {
                tnow = u1;
                moved = true;
            }
            u += 2;
        }
    }
    tnow
}

#[inline(always)]
fn tt(travel: &[i32], n_zones: usize, a: i32, b: i32) -> i32 {
    travel[a as usize * n_zones + b as usize]
}

fn compat(
    t: &TripView,
    cap_p: i32,
    cap_w: i32,
    vflags: i32,
    wmask: i32,
    vstart: i32,
    vend: i32,
    area: &[i32],
) -> bool {
    if t.pu < 0 || t.do_ < 0 {
        return false;
    }
    if !area.is_empty()
        && (!area.contains(&t.pu)
            || !area.contains(&t.do_)
            || (t.via >= 0 && !area.contains(&t.via)))
    {
        return false;
    }
    if t.wt != WT_NONE {
        if cap_w < 1 {
            return false;
        }
        if (wmask & (1 << t.wt)) == 0 {
            return false;
        }
    }
    if (t.flags & FLAG_LIFT) != 0 && (vflags & FLAG_LIFT) == 0 {
        return false;
    }
    if (t.flags & FLAG_RAMP) != 0 && (vflags & (FLAG_RAMP | FLAG_LIFT)) == 0 {
        return false;
    }
    if t.seats > cap_p {
        return false;
    }
    if vend <= vstart {
        return false;
    }
    true
}

#[inline(always)]
fn pair_at(orig_t: &[i32], orig_k: &[i32], new_idx: i32, i: usize, j: usize, k: usize) -> (i32, i32) {
    if k < i {
        (orig_t[k], orig_k[k])
    } else if k == i {
        (new_idx, 0)
    } else if k <= j {
        (orig_t[k - 1], orig_k[k - 1])
    } else if k == j + 1 {
        (new_idx, 1)
    } else {
        (orig_t[k - 2], orig_k[k - 2])
    }
}

#[inline(always)]
fn via_at(
    orig_t: &[i32],
    orig_k: &[i32],
    new_idx: i32,
    i: usize,
    mid: usize,
    j: usize,
    k: usize,
) -> (i32, i32) {
    if k < i {
        (orig_t[k], orig_k[k])
    } else if k == i {
        (new_idx, 0)
    } else if k <= mid {
        (orig_t[k - 1], orig_k[k - 1])
    } else if k == mid + 1 {
        (new_idx, 2)
    } else if k <= j + 1 {
        (orig_t[k - 2], orig_k[k - 2])
    } else if k == j + 2 {
        (new_idx, 1)
    } else {
        (orig_t[k - 3], orig_k[k - 3])
    }
}

#[derive(Clone, Copy)]
enum InsertMode {
    Pair { i: usize, j: usize },
    Via { i: usize, mid: usize, j: usize },
    AsIs,
}

#[derive(Default)]
struct RouteTrace {
    rides: Vec<(i32, i32)>,
    waits: Vec<(i32, i32)>,
    stops: Vec<(i32, i32, i32, i32)>,
}

#[derive(Clone, Copy)]
struct Cursor {
    loc: i32,
    tnow: i32,
    end: i32,
    load: i32,
    wload: i32,
    wait_sum: i32,
    max_load: i32,
    stretcher_on: i32,
}

struct World<'a> {
    travel: &'a [i32],
    n_zones: usize,
    table: &'a [i32],
    detour: &'a [f64],
    detour_cap: &'a [i32],
    n_trips: usize,
    depot: i32,
    shift_start: i32,
    shift_end: i32,
    cap_p: i32,
    cap_w: i32,
    vflags: i32,
    wmask: i32,
    dstart: i32,
    dend: i32,
    dassist: bool,
    has_driver: bool,
    unavail: &'a [i32],
    area: &'a [i32],
    check_unavail: bool,
}

fn compute_detour_caps(travel: &[i32], n_zones: usize, table: &[i32], detour: &[f64]) -> Vec<i32> {
    let n = table.len() / STRIDE;
    let mut out = vec![-1i32; n];
    if n_zones == 0 || travel.len() != n_zones * n_zones || detour.len() != n {
        return out;
    }
    let inb = |z: i32| z >= 0 && (z as usize) < n_zones;
    for i in 0..n {
        let t = trip_at(table, detour, i);
        let direct = if t.via >= 0 {
            if inb(t.pu) && inb(t.via) && inb(t.do_) {
                tt(travel, n_zones, t.pu, t.via) + t.via_svc + tt(travel, n_zones, t.via, t.do_)
            } else {
                0
            }
        } else if inb(t.pu) && inb(t.do_) {
            tt(travel, n_zones, t.pu, t.do_)
        } else {
            0
        };
        if direct > 0 {
            out[i] = detour_limit(direct, t.detour);
        }
    }
    out
}

fn start_cursor(w: &World) -> Cursor {
    let mut tnow = w.shift_start;
    let mut end = w.shift_end;
    if w.has_driver {
        if tnow < w.dstart {
            tnow = w.dstart;
        }
        if end > w.dend {
            end = w.dend;
        }
    }
    Cursor {
        loc: w.depot,
        tnow,
        end,
        load: 0,
        wload: 0,
        wait_sum: 0,
        max_load: 0,
        stretcher_on: 0,
    }
}

fn world_from_veh<'a>(
    travel: &'a [i32],
    n_zones: usize,
    table: &'a [i32],
    detour: &'a [f64],
    detour_cap: &'a [i32],
    n_trips: usize,
    veh: &'a [i32],
    unavail: &'a [i32],
) -> Option<World<'a>> {
    let (depot, shift_start, shift_end, cap_p, cap_w, vflags, wmask, dstart, dend, dassist, has_driver, area) =
        parse_veh(veh)?;
    Some(World {
        travel,
        n_zones,
        table,
        detour,
        detour_cap,
        n_trips,
        depot,
        shift_start,
        shift_end,
        cap_p,
        cap_w,
        vflags,
        wmask,
        dstart,
        dend,
        dassist,
        has_driver,
        unavail,
        area,
        check_unavail: !unavail.is_empty(),
    })
}

#[inline(always)]
fn apply_stop(
    w: &World,
    cur: &mut Cursor,
    pickup_dep: &mut [i32],
    trip_i: i32,
    kind: i32,
    check_new: bool,
    best_dur: i32,
    best_wait: i32,
    mut trace: Option<&mut RouteTrace>,
) -> bool {
    let idx = trip_i as usize;
    if idx >= w.n_trips {
        return false;
    }
    let t = trip_at(w.table, w.detour, idx);
    let dest = match kind {
        0 => t.pu,
        2 => t.via,
        _ => t.do_,
    };
    if dest < 0 || (dest as usize) >= w.n_zones {
        return false;
    }
    if cur.load == 0 && cur.loc == w.depot {
        cur.tnow = push_past_unavail(cur.tnow, w.unavail);
    }
    let t_begin = cur.tnow;
    let mut arrive = cur.tnow + tt(w.travel, w.n_zones, cur.loc, dest);
    let svc;
    if kind == 0 {
        let mut hold = 0;
        let mut pwait = 0;
        if arrive < t.earliest {
            hold = t.earliest - arrive;
            arrive = t.earliest;
        } else {
            pwait = arrive - t.earliest;
        }
        if (hold > t.max_wait && cur.load > 0) || pwait > t.max_wait || arrive > t.latest {
            return false;
        }
        if check_new {
            if !compat(
                &t,
                w.cap_p,
                w.cap_w,
                w.vflags,
                w.wmask,
                w.shift_start,
                w.shift_end,
                w.area,
            ) {
                return false;
            }
            if (t.flags & FLAG_ASSIST) != 0 && (!w.has_driver || !w.dassist) {
                return false;
            }
        }
        if (t.flags & FLAG_STRETCHER) != 0 && cur.load > 0 {
            return false;
        }
        if cur.stretcher_on > 0 {
            return false;
        }
        svc = t.board.max(CURB_WAIT);
        cur.load += t.seats;
        cur.wload += t.wunits;
        if cur.load > w.cap_p || cur.wload > w.cap_w {
            return false;
        }
        if cur.load > cur.max_load {
            cur.max_load = cur.load;
        }
        if (t.flags & FLAG_STRETCHER) != 0 {
            cur.stretcher_on += 1;
        }
        cur.wait_sum += pwait;
        if let Some(buf) = trace.as_mut() {
            buf.waits.push((trip_i, pwait));
        }
    } else if kind == 2 {
        if pickup_dep[idx] < 0 {
            return false;
        }
        svc = t.via_svc;
    } else {
        if pickup_dep[idx] < 0 {
            return false;
        }
        if t.appt_s >= 0 {
            let mut early_do = t.appt_s - EARLY_DROPOFF_SLACK;
            if early_do < 0 {
                early_do = 0;
            }
            if arrive < early_do {
                if cur.load > t.seats {
                    return false;
                }
                arrive = early_do;
            }
        }
        let ride = arrive - pickup_dep[idx];
        if let Some(buf) = trace.as_mut() {
            buf.rides.push((trip_i, ride));
        }
        if ride > t.max_ride {
            return false;
        }
        let cap = if idx < w.detour_cap.len() {
            w.detour_cap[idx]
        } else {
            -1
        };
        if cap >= 0 && ride > cap {
            return false;
        }
        if t.appt_e >= 0 && arrive > t.appt_e {
            return false;
        }
        svc = t.alight;
        cur.load -= t.seats;
        cur.wload -= t.wunits;
        if cur.load < 0 || cur.wload < 0 {
            return false;
        }
        if (t.flags & FLAG_STRETCHER) != 0 {
            cur.stretcher_on -= 1;
        }
    }
    let leave = arrive + svc;
    if leave > cur.end {
        return false;
    }
    if w.check_unavail && occupancy_overlaps(t_begin, leave, w.unavail) {
        return false;
    }
    if kind == 0 {
        pickup_dep[idx] = leave;
    }
    if let Some(buf) = trace.as_mut() {
        buf.stops.push((arrive, leave, cur.load, cur.wload));
    }
    cur.loc = dest;
    cur.tnow = leave;
    if best_dur != i32::MAX {
        let dur_lb = cur.tnow - w.shift_start;
        if dur_lb > best_dur {
            return false;
        }
        if dur_lb >= best_dur && cur.wait_sum > best_wait {
            return false;
        }
    }
    true
}

#[inline(always)]
fn finish_return(w: &World, cur: &Cursor) -> Option<(i32, i32, i32)> {
    let t_ret = cur.tnow;
    let tnow = t_ret + tt(w.travel, w.n_zones, cur.loc, w.depot);
    if tnow > cur.end {
        return None;
    }
    if w.check_unavail && occupancy_overlaps(t_ret, tnow, w.unavail) {
        return None;
    }
    Some((tnow - w.shift_start, cur.wait_sum, cur.max_load))
}

fn apply_orig_range(
    w: &World,
    cur: &mut Cursor,
    pickup_dep: &mut [i32],
    orig_t: &[i32],
    orig_k: &[i32],
    from: usize,
    to: usize,
    best_dur: i32,
    best_wait: i32,
) -> bool {
    for s in from..to {
        if !apply_stop(
            w,
            cur,
            pickup_dep,
            orig_t[s],
            orig_k[s],
            false,
            best_dur,
            best_wait,
            None,
        ) {
            return false;
        }
    }
    true
}

fn capture_dep(orig_t: &[i32], new_idx: i32, pickup_dep: &[i32]) -> Vec<(usize, i32)> {
    let mut cap = Vec::with_capacity(orig_t.len() + 1);
    for &ti in orig_t {
        let u = ti as usize;
        if u < pickup_dep.len() {
            cap.push((u, pickup_dep[u]));
        }
    }
    let nu = new_idx as usize;
    if nu < pickup_dep.len() {
        cap.push((nu, pickup_dep[nu]));
    }
    cap
}

fn restore_dep(cap: &[(usize, i32)], pickup_dep: &mut [i32]) {
    for &(u, v) in cap {
        pickup_dep[u] = v;
    }
}

fn load_prefix(orig_t: &[i32], new_idx: i32, onboard: &[(i32, i32)], pickup_dep: &mut [i32]) {
    for &ti in orig_t {
        let u = ti as usize;
        if u < pickup_dep.len() {
            pickup_dep[u] = -1;
        }
    }
    let nu = new_idx as usize;
    if nu < pickup_dep.len() {
        pickup_dep[nu] = -1;
    }
    for &(ti, leave) in onboard {
        let u = ti as usize;
        if u < pickup_dep.len() {
            pickup_dep[u] = leave;
        }
    }
}

fn simulate_inserted(
    w: &World,
    orig_t: &[i32],
    orig_k: &[i32],
    new_idx: i32,
    mode: InsertMode,
    pickup_dep: &mut [i32],
    mut trace: Option<&mut RouteTrace>,
) -> Option<(i32, i32, i32)> {
    let m = orig_t.len();
    let nstop = match mode {
        InsertMode::Pair { .. } => m + 2,
        InsertMode::Via { .. } => m + 3,
        InsertMode::AsIs => m,
    };
    for &idx in orig_t {
        let u = idx as usize;
        if u < pickup_dep.len() {
            pickup_dep[u] = -1;
        }
    }
    let nu = new_idx as usize;
    if nu < pickup_dep.len() {
        pickup_dep[nu] = -1;
    }
    let mut cur = start_cursor(w);
    for s in 0..nstop {
        let (trip_i, kind) = match mode {
            InsertMode::Pair { i, j } => pair_at(orig_t, orig_k, new_idx, i, j, s),
            InsertMode::Via { i, mid, j } => via_at(orig_t, orig_k, new_idx, i, mid, j, s),
            InsertMode::AsIs => (orig_t[s], orig_k[s]),
        };
        let check_new = matches!(mode, InsertMode::AsIs) || trip_i == new_idx;
        if !apply_stop(
            w,
            &mut cur,
            pickup_dep,
            trip_i,
            kind,
            check_new,
            i32::MAX,
            i32::MAX,
            trace.as_deref_mut(),
        ) {
            return None;
        }
    }
    finish_return(w, &cur)
}

fn parse_veh(veh: &[i32]) -> Option<(i32, i32, i32, i32, i32, i32, i32, i32, i32, bool, bool, &[i32])> {
    if veh.len() < 11 {
        return None;
    }
    let n_area = if veh.len() > 11 {
        veh[11].max(0) as usize
    } else {
        0
    };
    let area: &[i32] = if veh.len() >= 12 + n_area {
        &veh[12..12 + n_area]
    } else {
        &[]
    };
    Some((
        veh[0],
        veh[1],
        veh[2],
        veh[3],
        veh[4],
        veh[5],
        veh[6],
        veh[7],
        veh[8],
        veh[9] != 0,
        veh[10] != 0,
        area,
    ))
}

fn eval_stored(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
    detour_cap: &[i32],
    fv: &FleetVeh,
) -> Option<(i32, i32, RouteTrace)> {
    if fv.stop_trip.is_empty() {
        return Some((0, 0, RouteTrace::default()));
    }
    if table.len() % STRIDE != 0 || n_zones == 0 || travel.len() != n_zones * n_zones {
        return None;
    }
    let n_trips = table.len() / STRIDE;
    if detour.len() != n_trips {
        return None;
    }
    let w = world_from_veh(
        travel,
        n_zones,
        table,
        detour,
        detour_cap,
        n_trips,
        &fv.veh,
        &fv.unavail,
    )?;
    let mut pickup_dep = vec![-1i32; n_trips];
    let mut trace = RouteTrace::default();
    let (dur, wait, _mx) = simulate_inserted(
        &w,
        &fv.stop_trip,
        &fv.stop_kind,
        -1,
        InsertMode::AsIs,
        &mut pickup_dep,
        Some(&mut trace),
    )?;
    Some((dur, wait, trace))
}

fn trial_insert_trace(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
    detour_cap: &[i32],
    fv: &FleetVeh,
    i: i32,
    mid: i32,
    j: i32,
    new_idx: i32,
) -> Option<(i32, i32, RouteTrace)> {
    let n_trips = table.len() / STRIDE;
    if n_trips == 0 {
        return None;
    }
    let w = world_from_veh(
        travel,
        n_zones,
        table,
        detour,
        detour_cap,
        n_trips,
        &fv.veh,
        &fv.unavail,
    )?;
    let mode = if mid < 0 {
        InsertMode::Pair {
            i: i.max(0) as usize,
            j: j.max(0) as usize,
        }
    } else {
        InsertMode::Via {
            i: i.max(0) as usize,
            mid: mid as usize,
            j: j.max(0) as usize,
        }
    };
    let mut pickup_dep = vec![-1i32; n_trips];
    let mut trace = RouteTrace::default();
    let (dur, wait, _mx) = simulate_inserted(
        &w,
        &fv.stop_trip,
        &fv.stop_kind,
        new_idx,
        mode,
        &mut pickup_dep,
        Some(&mut trace),
    )?;
    Some((dur, wait, trace))
}

fn consider_best(
    best: &mut Option<(i32, i32, i32, i32, i32, i32)>,
    best_key: &mut Option<(i32, i32, i32, i32, i32, i32)>,
    best_dur: &mut i32,
    best_wait: &mut i32,
    key: (i32, i32, i32, i32, i32, i32),
    row: (i32, i32, i32, i32, i32, i32),
) {
    if best_key.map(|b| key < b).unwrap_or(true) {
        *best_key = Some(key);
        *best = Some(row);
        *best_dur = row.3;
        *best_wait = row.4;
    }
}

fn best_insert_inner(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
    detour_cap: &[i32],
    stop_trip: &[i32],
    stop_kind: &[i32],
    new_idx: i32,
    veh: &[i32],
    unavail: &[i32],
    pickup_dep: &mut [i32],
) -> Option<(i32, i32, i32, i32, i32, i32)> {
    if table.len() % STRIDE != 0 || n_zones == 0 {
        return None;
    }
    if travel.len() != n_zones * n_zones {
        return None;
    }
    let n_trips = table.len() / STRIDE;
    if detour.len() != n_trips || pickup_dep.len() < n_trips {
        return None;
    }
    if stop_trip.len() != stop_kind.len() {
        return None;
    }
    if new_idx < 0 || (new_idx as usize) >= n_trips {
        return None;
    }
    let w = world_from_veh(
        travel,
        n_zones,
        table,
        detour,
        detour_cap,
        n_trips,
        veh,
        unavail,
    )?;
    let nt = trip_at(table, detour, new_idx as usize);
    if !compat(
        &nt,
        w.cap_p,
        w.cap_w,
        w.vflags,
        w.wmask,
        w.shift_start,
        w.shift_end,
        w.area,
    ) {
        return None;
    }
    if (nt.flags & FLAG_ASSIST) != 0 && (!w.has_driver || !w.dassist) {
        return None;
    }
    let m = stop_trip.len();
    for &idx in stop_trip {
        let u = idx as usize;
        if u < pickup_dep.len() {
            pickup_dep[u] = -1;
        }
    }
    let nu = new_idx as usize;
    if nu < pickup_dep.len() {
        pickup_dep[nu] = -1;
    }
    let mut prefixes: Vec<(Cursor, Vec<(i32, i32)>)> = Vec::with_capacity(m + 1);
    let mut cur = start_cursor(&w);
    let mut onboard: Vec<(i32, i32)> = Vec::new();
    prefixes.push((cur, onboard.clone()));
    for s in 0..m {
        if !apply_stop(
            &w,
            &mut cur,
            pickup_dep,
            stop_trip[s],
            stop_kind[s],
            false,
            i32::MAX,
            i32::MAX,
            None,
        ) {
            return None;
        }
        if stop_kind[s] == 0 {
            onboard.push((stop_trip[s], pickup_dep[stop_trip[s] as usize]));
        } else if stop_kind[s] == 1 {
            let tid = stop_trip[s];
            onboard.retain(|(ti, _)| *ti != tid);
        }
        prefixes.push((cur, onboard.clone()));
    }
    let has_via = nt.via >= 0;
    let mut best: Option<(i32, i32, i32, i32, i32, i32)> = None;
    let mut best_key: Option<(i32, i32, i32, i32, i32, i32)> = None;
    let mut best_dur = i32::MAX;
    let mut best_wait = i32::MAX;
    if has_via {
        for i in 0..=m {
            load_prefix(stop_trip, new_idx, &prefixes[i].1, pickup_dep);
            let mut walk_mid = prefixes[i].0;
            if !apply_stop(
                &w,
                &mut walk_mid,
                pickup_dep,
                new_idx,
                0,
                true,
                i32::MAX,
                i32::MAX,
                None,
            ) {
                continue;
            }
            for mid in i..=m {
                let cap_mid = capture_dep(stop_trip, new_idx, pickup_dep);
                let mut after_via = walk_mid;
                if apply_stop(
                    &w,
                    &mut after_via,
                    pickup_dep,
                    new_idx,
                    2,
                    false,
                    i32::MAX,
                    i32::MAX,
                    None,
                ) {
                    let mut walk_j = after_via;
                    for j in mid..=m {
                        let cap_j = capture_dep(stop_trip, new_idx, pickup_dep);
                        let mut trial = walk_j;
                        let scored = if apply_stop(
                            &w,
                            &mut trial,
                            pickup_dep,
                            new_idx,
                            1,
                            false,
                            best_dur,
                            best_wait,
                            None,
                        ) && apply_orig_range(
                            &w,
                            &mut trial,
                            pickup_dep,
                            stop_trip,
                            stop_kind,
                            j,
                            m,
                            best_dur,
                            best_wait,
                        ) {
                            finish_return(&w, &trial)
                        } else {
                            None
                        };
                        restore_dep(&cap_j, pickup_dep);
                        if let Some((dur, wait, mx)) = scored {
                            let i32i = i as i32;
                            let mid32 = mid as i32;
                            let j32 = j as i32;
                            consider_best(
                                &mut best,
                                &mut best_key,
                                &mut best_dur,
                                &mut best_wait,
                                (dur, wait, -mx, i32i, mid32, j32),
                                (i32i, mid32, j32, dur, wait, mx),
                            );
                        }
                        if j < m
                            && !apply_stop(
                                &w,
                                &mut walk_j,
                                pickup_dep,
                                stop_trip[j],
                                stop_kind[j],
                                false,
                                i32::MAX,
                                i32::MAX,
                                None,
                            )
                        {
                            break;
                        }
                    }
                }
                restore_dep(&cap_mid, pickup_dep);
                if mid < m
                    && !apply_stop(
                        &w,
                        &mut walk_mid,
                        pickup_dep,
                        stop_trip[mid],
                        stop_kind[mid],
                        false,
                        i32::MAX,
                        i32::MAX,
                        None,
                    )
                {
                    break;
                }
            }
        }
    } else {
        for i in 0..=m {
            load_prefix(stop_trip, new_idx, &prefixes[i].1, pickup_dep);
            let mut walk = prefixes[i].0;
            if !apply_stop(
                &w,
                &mut walk,
                pickup_dep,
                new_idx,
                0,
                true,
                i32::MAX,
                i32::MAX,
                None,
            ) {
                continue;
            }
            for j in i..=m {
                let cap_j = capture_dep(stop_trip, new_idx, pickup_dep);
                let mut trial = walk;
                let scored = if apply_stop(
                    &w,
                    &mut trial,
                    pickup_dep,
                    new_idx,
                    1,
                    false,
                    best_dur,
                    best_wait,
                    None,
                ) && apply_orig_range(
                    &w,
                    &mut trial,
                    pickup_dep,
                    stop_trip,
                    stop_kind,
                    j,
                    m,
                    best_dur,
                    best_wait,
                ) {
                    finish_return(&w, &trial)
                } else {
                    None
                };
                restore_dep(&cap_j, pickup_dep);
                if let Some((dur, wait, mx)) = scored {
                    let i32i = i as i32;
                    let j32 = j as i32;
                    consider_best(
                        &mut best,
                        &mut best_key,
                        &mut best_dur,
                        &mut best_wait,
                        (dur, wait, -mx, i32i, j32, 0),
                        (i32i, -1, j32, dur, wait, mx),
                    );
                }
                if j < m
                    && !apply_stop(
                        &w,
                        &mut walk,
                        pickup_dep,
                        stop_trip[j],
                        stop_kind[j],
                        false,
                        i32::MAX,
                        i32::MAX,
                        None,
                    )
                {
                    break;
                }
            }
        }
    }
    best
}

fn score_fleet_inner(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
    stop_trips: &[Vec<i32>],
    stop_kinds: &[Vec<i32>],
    vehs: &[Vec<i32>],
    unavails: &[Vec<i32>],
    new_idx: i32,
) -> Vec<(i32, i32, i32, i32, i32, i32, i32)> {
    let n = stop_trips.len();
    if n == 0 || n != stop_kinds.len() || n != vehs.len() || n != unavails.len() {
        return Vec::new();
    }
    if table.len() % STRIDE != 0 {
        return Vec::new();
    }
    let n_trips = table.len() / STRIDE;
    let detour_cap = compute_detour_caps(travel, n_zones, table, detour);
    (0..n)
        .into_par_iter()
        .filter_map(|v| {
            let mut pickup_dep = vec![-1i32; n_trips];
            best_insert_inner(
                travel,
                n_zones,
                table,
                detour,
                &detour_cap,
                &stop_trips[v],
                &stop_kinds[v],
                new_idx,
                &vehs[v],
                &unavails[v],
                &mut pickup_dep,
            )
            .map(|(i, mid, j, dur, wait, mx)| (v as i32, i, mid, j, dur, wait, mx))
        })
        .collect()
}

fn materialize_insert(
    orig_t: &[i32],
    orig_k: &[i32],
    new_idx: i32,
    i: i32,
    mid: i32,
    j: i32,
) -> (Vec<i32>, Vec<i32>) {
    let iu = i.max(0) as usize;
    let ju = j.max(0) as usize;
    if mid < 0 {
        let n = orig_t.len() + 2;
        let mut t = Vec::with_capacity(n);
        let mut k = Vec::with_capacity(n);
        for s in 0..n {
            let (ti, ki) = pair_at(orig_t, orig_k, new_idx, iu, ju, s);
            t.push(ti);
            k.push(ki);
        }
        (t, k)
    } else {
        let n = orig_t.len() + 3;
        let mu = mid as usize;
        let mut t = Vec::with_capacity(n);
        let mut k = Vec::with_capacity(n);
        for s in 0..n {
            let (ti, ki) = via_at(orig_t, orig_k, new_idx, iu, mu, ju, s);
            t.push(ti);
            k.push(ki);
        }
        (t, k)
    }
}

#[derive(Clone)]
struct FleetVeh {
    stop_trip: Vec<i32>,
    stop_kind: Vec<i32>,
    veh: Vec<i32>,
    unavail: Vec<i32>,
}

#[pyclass(module = "mobiroute_native")]
struct InsertionEngine {
    travel: Arc<Vec<i32>>,
    n_zones: usize,
    table: Arc<Vec<i32>>,
    detour: Arc<Vec<f64>>,
    detour_cap: Arc<Vec<i32>>,
    fleet: Vec<FleetVeh>,
}

#[pymethods]
impl InsertionEngine {
    #[new]
    fn new(
        travel: Vec<i32>,
        n_zones: usize,
        trip_table: Vec<i32>,
        detour: Vec<f64>,
    ) -> PyResult<Self> {
        if n_zones == 0 || travel.len() != n_zones * n_zones {
            return Err(PyValueError::new_err("travel/n_zones mismatch"));
        }
        if trip_table.len() % STRIDE != 0 || detour.len() != trip_table.len() / STRIDE {
            return Err(PyValueError::new_err("trip table/detour mismatch"));
        }
        let detour_cap = compute_detour_caps(&travel, n_zones, &trip_table, &detour);
        Ok(Self {
            travel: Arc::new(travel),
            n_zones,
            table: Arc::new(trip_table),
            detour: Arc::new(detour),
            detour_cap: Arc::new(detour_cap),
            fleet: Vec::new(),
        })
    }

    fn best_insert(
        &self,
        py: Python<'_>,
        stop_trip: Vec<i32>,
        stop_kind: Vec<i32>,
        new_idx: i32,
        veh: Vec<i32>,
        unavail: Vec<i32>,
    ) -> Option<(i32, i32, i32, i32, i32, i32)> {
        py.allow_threads(|| {
            let n_trips = self.table.len() / STRIDE;
            let mut pickup_dep = vec![-1i32; n_trips];
            best_insert_inner(
                &self.travel,
                self.n_zones,
                &self.table,
                &self.detour,
                &self.detour_cap,
                &stop_trip,
                &stop_kind,
                new_idx,
                &veh,
                &unavail,
                &mut pickup_dep,
            )
        })
    }

    /// Score one new trip against every vehicle route. Returns
    /// (fleet_index, i, mid, j, duration, wait_sum, max_load) per feasible vehicle.
    fn score_fleet(
        &self,
        py: Python<'_>,
        stop_trips: Vec<Vec<i32>>,
        stop_kinds: Vec<Vec<i32>>,
        vehs: Vec<Vec<i32>>,
        unavails: Vec<Vec<i32>>,
        new_idx: i32,
    ) -> Vec<(i32, i32, i32, i32, i32, i32, i32)> {
        py.allow_threads(|| {
            score_fleet_inner(
                &self.travel,
                self.n_zones,
                &self.table,
                &self.detour,
                &stop_trips,
                &stop_kinds,
                &vehs,
                &unavails,
                new_idx,
            )
        })
    }

    fn set_fleet(
        &mut self,
        stop_trips: Vec<Vec<i32>>,
        stop_kinds: Vec<Vec<i32>>,
        vehs: Vec<Vec<i32>>,
        unavails: Vec<Vec<i32>>,
    ) -> PyResult<()> {
        let n = stop_trips.len();
        if n != stop_kinds.len() || n != vehs.len() || n != unavails.len() {
            return Err(PyValueError::new_err("set_fleet length mismatch"));
        }
        self.fleet = (0..n)
            .map(|i| FleetVeh {
                stop_trip: stop_trips[i].clone(),
                stop_kind: stop_kinds[i].clone(),
                veh: vehs[i].clone(),
                unavail: unavails[i].clone(),
            })
            .collect();
        Ok(())
    }

    fn set_vehicle(&mut self, fleet_i: usize, veh: Vec<i32>, unavail: Vec<i32>) -> PyResult<()> {
        let slot = self
            .fleet
            .get_mut(fleet_i)
            .ok_or_else(|| PyValueError::new_err("set_vehicle index"))?;
        slot.veh = veh;
        slot.unavail = unavail;
        Ok(())
    }

    fn score_stored(
        &self,
        py: Python<'_>,
        new_idx: i32,
    ) -> Vec<(i32, i32, i32, i32, i32, i32, i32)> {
        py.allow_threads(|| {
            let n_trips = self.table.len() / STRIDE;
            (0..self.fleet.len())
                .into_par_iter()
                .filter_map(|v| {
                    let fv = &self.fleet[v];
                    let mut pickup_dep = vec![-1i32; n_trips];
                    best_insert_inner(
                        &self.travel,
                        self.n_zones,
                        &self.table,
                        &self.detour,
                        &self.detour_cap,
                        &fv.stop_trip,
                        &fv.stop_kind,
                        new_idx,
                        &fv.veh,
                        &fv.unavail,
                        &mut pickup_dep,
                    )
                    .map(|(i, mid, j, dur, wait, mx)| (v as i32, i, mid, j, dur, wait, mx))
                })
                .collect()
        })
    }

    fn commit_insert(
        &mut self,
        fleet_i: usize,
        i: i32,
        mid: i32,
        j: i32,
        new_idx: i32,
    ) -> PyResult<()> {
        let slot = self
            .fleet
            .get_mut(fleet_i)
            .ok_or_else(|| PyValueError::new_err("commit_insert index"))?;
        let (t, k) = materialize_insert(&slot.stop_trip, &slot.stop_kind, new_idx, i, mid, j);
        slot.stop_trip = t;
        slot.stop_kind = k;
        Ok(())
    }

    fn fleet_len(&self) -> usize {
        self.fleet.len()
    }

    fn trial_rides(
        &self,
        py: Python<'_>,
        fleet_i: usize,
        i: i32,
        mid: i32,
        j: i32,
        new_idx: i32,
    ) -> Option<Vec<(i32, i32)>> {
        py.allow_threads(|| {
            let fv = self.fleet.get(fleet_i)?;
            trial_insert_trace(
                &self.travel,
                self.n_zones,
                &self.table,
                &self.detour,
                &self.detour_cap,
                fv,
                i,
                mid,
                j,
                new_idx,
            )
            .map(|(_dur, _wait, trace)| trace.rides)
        })
    }

    fn trial_eval(
        &self,
        py: Python<'_>,
        fleet_i: usize,
        i: i32,
        mid: i32,
        j: i32,
        new_idx: i32,
    ) -> Option<(
        i32,
        i32,
        Vec<(i32, i32)>,
        Vec<(i32, i32)>,
        Vec<(i32, i32, i32, i32)>,
    )> {
        py.allow_threads(|| {
            let fv = self.fleet.get(fleet_i)?;
            trial_insert_trace(
                &self.travel,
                self.n_zones,
                &self.table,
                &self.detour,
                &self.detour_cap,
                fv,
                i,
                mid,
                j,
                new_idx,
            )
            .map(|(dur, wait, trace)| (dur, wait, trace.rides, trace.waits, trace.stops))
        })
    }

    fn set_route(
        &mut self,
        fleet_i: usize,
        stop_trip: Vec<i32>,
        stop_kind: Vec<i32>,
    ) -> PyResult<()> {
        if stop_trip.len() != stop_kind.len() {
            return Err(PyValueError::new_err("set_route length mismatch"));
        }
        let slot = self
            .fleet
            .get_mut(fleet_i)
            .ok_or_else(|| PyValueError::new_err("set_route index"))?;
        slot.stop_trip = stop_trip;
        slot.stop_kind = stop_kind;
        Ok(())
    }

    fn append_trip(&mut self, row: Vec<i32>, detour: f64) -> PyResult<i32> {
        if row.len() != STRIDE {
            return Err(PyValueError::new_err("append_trip stride"));
        }
        let cap = compute_detour_caps(&self.travel, self.n_zones, &row, &[detour])[0];
        Arc::make_mut(&mut self.table).extend_from_slice(&row);
        Arc::make_mut(&mut self.detour).push(detour);
        Arc::make_mut(&mut self.detour_cap).push(cap);
        Ok((self.detour.len() - 1) as i32)
    }

    fn fork(&self) -> Self {
        Self {
            travel: Arc::clone(&self.travel),
            n_zones: self.n_zones,
            table: Arc::clone(&self.table),
            detour: Arc::clone(&self.detour),
            detour_cap: Arc::clone(&self.detour_cap),
            fleet: self.fleet.clone(),
        }
    }

    fn eval_route(
        &self,
        py: Python<'_>,
        fleet_i: usize,
    ) -> Option<(
        i32,
        i32,
        Vec<(i32, i32)>,
        Vec<(i32, i32)>,
        Vec<(i32, i32, i32, i32)>,
    )> {
        py.allow_threads(|| {
            let fv = self.fleet.get(fleet_i)?;
            eval_stored(
                &self.travel,
                self.n_zones,
                &self.table,
                &self.detour,
                &self.detour_cap,
                fv,
            )
            .map(|(dur, wait, trace)| (dur, wait, trace.rides, trace.waits, trace.stops))
        })
    }

    fn eval_fleet(
        &self,
        py: Python<'_>,
    ) -> Vec<
        Option<(
            i32,
            i32,
            Vec<(i32, i32)>,
            Vec<(i32, i32)>,
            Vec<(i32, i32, i32, i32)>,
        )>,
    > {
        py.allow_threads(|| {
            (0..self.fleet.len())
                .into_par_iter()
                .map(|v| {
                    let fv = &self.fleet[v];
                    eval_stored(
                        &self.travel,
                        self.n_zones,
                        &self.table,
                        &self.detour,
                        &self.detour_cap,
                        fv,
                    )
                    .map(|(dur, wait, trace)| (dur, wait, trace.rides, trace.waits, trace.stops))
                })
                .collect()
        })
    }
}

#[pyfunction]
#[pyo3(signature = (travel, n_zones, trip_table, detour, stop_trip, stop_kind, new_idx, veh, unavail))]
fn best_insert(
    py: Python<'_>,
    travel: Vec<i32>,
    n_zones: usize,
    trip_table: Vec<i32>,
    detour: Vec<f64>,
    stop_trip: Vec<i32>,
    stop_kind: Vec<i32>,
    new_idx: i32,
    veh: Vec<i32>,
    unavail: Vec<i32>,
) -> Option<(i32, i32, i32, i32, i32, i32)> {
    py.allow_threads(|| {
        let n_trips = trip_table.len() / STRIDE;
        let detour_cap = compute_detour_caps(&travel, n_zones, &trip_table, &detour);
        let mut pickup_dep = vec![-1i32; n_trips];
        best_insert_inner(
            &travel,
            n_zones,
            &trip_table,
            &detour,
            &detour_cap,
            &stop_trip,
            &stop_kind,
            new_idx,
            &veh,
            &unavail,
            &mut pickup_dep,
        )
    })
}

#[pymodule]
fn mobiroute_native(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(best_insert, module)?)?;
    module.add_class::<InsertionEngine>()?;
    module.add("__version__", "0.2.0")?;
    Ok(())
}
