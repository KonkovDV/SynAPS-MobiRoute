//! MobiRoute insertion scoring kernel (SynAPS-style PyO3 hot path).
//! Sequential, deterministic min over (duration, wait, -max_load, i, mid, j).
//! ABI: trip stride 16; best_insert returns (i, mid, j, dur, wait, max_load); mid=-1 if no VIA.
//! score_fleet returns (fleet_index, i, mid, j, dur, wait, max_load) per feasible vehicle.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

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
}

fn simulate_inserted(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
    n_trips: usize,
    orig_t: &[i32],
    orig_k: &[i32],
    new_idx: i32,
    mode: InsertMode,
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
    unavail: &[i32],
    area: &[i32],
    pickup_dep: &mut [i32],
) -> Option<(i32, i32, i32)> {
    let m = orig_t.len();
    let nstop = match mode {
        InsertMode::Pair { .. } => m + 2,
        InsertMode::Via { .. } => m + 3,
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
    let mut loc = depot;
    let mut tnow = shift_start;
    let mut end = shift_end;
    if has_driver {
        if tnow < dstart {
            tnow = dstart;
        }
        if end > dend {
            end = dend;
        }
    }
    let mut load = 0i32;
    let mut wload = 0i32;
    let mut wait_sum = 0i32;
    let mut max_load = 0i32;
    let mut stretcher_on = 0i32;
    let check_unavail = !unavail.is_empty();
    for s in 0..nstop {
        let (trip_i, kind) = match mode {
            InsertMode::Pair { i, j } => pair_at(orig_t, orig_k, new_idx, i, j, s),
            InsertMode::Via { i, mid, j } => via_at(orig_t, orig_k, new_idx, i, mid, j, s),
        };
        let idx = trip_i as usize;
        if idx >= n_trips {
            return None;
        }
        let t = trip_at(table, detour, idx);
        let dest = match kind {
            0 => t.pu,
            2 => t.via,
            _ => t.do_,
        };
        if dest < 0 || (dest as usize) >= n_zones {
            return None;
        }
        if load == 0 && loc == depot {
            tnow = push_past_unavail(tnow, unavail);
        }
        let t_begin = tnow;
        let mut arrive = tnow + tt(travel, n_zones, loc, dest);
        let svc;
        let is_new = trip_i == new_idx;
        if kind == 0 {
            let mut hold = 0;
            let mut pwait = 0;
            if arrive < t.earliest {
                hold = t.earliest - arrive;
                arrive = t.earliest;
            } else {
                pwait = arrive - t.earliest;
            }
            if (hold > t.max_wait && load > 0) || pwait > t.max_wait || arrive > t.latest {
                return None;
            }
            if is_new {
                if !compat(&t, cap_p, cap_w, vflags, wmask, shift_start, shift_end, area) {
                    return None;
                }
                if (t.flags & FLAG_ASSIST) != 0 && (!has_driver || !dassist) {
                    return None;
                }
            }
            if (t.flags & FLAG_STRETCHER) != 0 && load > 0 {
                return None;
            }
            if stretcher_on > 0 {
                return None;
            }
            svc = t.board.max(CURB_WAIT);
            load += t.seats;
            wload += t.wunits;
            if load > cap_p || wload > cap_w {
                return None;
            }
            if load > max_load {
                max_load = load;
            }
            if (t.flags & FLAG_STRETCHER) != 0 {
                stretcher_on += 1;
            }
            wait_sum += pwait;
        } else if kind == 2 {
            if pickup_dep[idx] < 0 {
                return None;
            }
            svc = t.via_svc;
        } else {
            if pickup_dep[idx] < 0 {
                return None;
            }
            if t.appt_s >= 0 {
                let mut early_do = t.appt_s - EARLY_DROPOFF_SLACK;
                if early_do < 0 {
                    early_do = 0;
                }
                if arrive < early_do {
                    if load > t.seats {
                        return None;
                    }
                    arrive = early_do;
                }
            }
            let ride = arrive - pickup_dep[idx];
            if ride > t.max_ride {
                return None;
            }
            let direct = if t.via >= 0 {
                tt(travel, n_zones, t.pu, t.via) + t.via_svc + tt(travel, n_zones, t.via, t.do_)
            } else {
                tt(travel, n_zones, t.pu, t.do_)
            };
            if direct > 0 && ride > detour_limit(direct, t.detour) {
                return None;
            }
            if t.appt_e >= 0 && arrive > t.appt_e {
                return None;
            }
            svc = t.alight;
            load -= t.seats;
            wload -= t.wunits;
            if load < 0 || wload < 0 {
                return None;
            }
            if (t.flags & FLAG_STRETCHER) != 0 {
                stretcher_on -= 1;
            }
        }
        let leave = arrive + svc;
        if leave > end {
            return None;
        }
        if check_unavail && occupancy_overlaps(t_begin, leave, unavail) {
            return None;
        }
        if kind == 0 {
            pickup_dep[idx] = leave;
        }
        loc = dest;
        tnow = leave;
    }
    let t_ret = tnow;
    tnow += tt(travel, n_zones, loc, depot);
    if tnow > end {
        return None;
    }
    if check_unavail && occupancy_overlaps(t_ret, tnow, unavail) {
        return None;
    }
    Some((tnow - shift_start, wait_sum, max_load))
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

fn best_insert_inner(
    travel: &[i32],
    n_zones: usize,
    table: &[i32],
    detour: &[f64],
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
    let (depot, shift_start, shift_end, cap_p, cap_w, vflags, wmask, dstart, dend, dassist, has_driver, area) =
        parse_veh(veh)?;
    let m = stop_trip.len();
    let nt = trip_at(table, detour, new_idx as usize);
    let has_via = nt.via >= 0;
    let mut best: Option<(i32, i32, i32, i32, i32, i32)> = None;
    let mut best_key: Option<(i32, i32, i32, i32, i32, i32)> = None;
    if has_via {
        for i in 0..=m {
            for mid in i..=m {
                for j in mid..=m {
                    if let Some((dur, wait, mx)) = simulate_inserted(
                        travel,
                        n_zones,
                        table,
                        detour,
                        n_trips,
                        stop_trip,
                        stop_kind,
                        new_idx,
                        InsertMode::Via { i, mid, j },
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
                        pickup_dep,
                    ) {
                        let i32i = i as i32;
                        let mid32 = mid as i32;
                        let j32 = j as i32;
                        let key = (dur, wait, -mx, i32i, mid32, j32);
                        if best_key.map(|b| key < b).unwrap_or(true) {
                            best_key = Some(key);
                            best = Some((i32i, mid32, j32, dur, wait, mx));
                        }
                    }
                }
            }
        }
    } else {
        for i in 0..=m {
            for j in i..=m {
                if let Some((dur, wait, mx)) = simulate_inserted(
                    travel,
                    n_zones,
                    table,
                    detour,
                    n_trips,
                    stop_trip,
                    stop_kind,
                    new_idx,
                    InsertMode::Pair { i, j },
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
                    pickup_dep,
                ) {
                    let i32i = i as i32;
                    let j32 = j as i32;
                    let key = (dur, wait, -mx, i32i, j32, 0);
                    if best_key.map(|b| key < b).unwrap_or(true) {
                        best_key = Some(key);
                        best = Some((i32i, -1, j32, dur, wait, mx));
                    }
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
    let mut pickup_dep = vec![-1i32; n_trips];
    let mut out = Vec::new();
    for v in 0..n {
        if let Some((i, mid, j, dur, wait, mx)) = best_insert_inner(
            travel,
            n_zones,
            table,
            detour,
            &stop_trips[v],
            &stop_kinds[v],
            new_idx,
            &vehs[v],
            &unavails[v],
            &mut pickup_dep,
        ) {
            out.push((v as i32, i, mid, j, dur, wait, mx));
        }
    }
    out
}

#[pyclass(module = "mobiroute_native")]
struct InsertionEngine {
    travel: Vec<i32>,
    n_zones: usize,
    table: Vec<i32>,
    detour: Vec<f64>,
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
        Ok(Self {
            travel,
            n_zones,
            table: trip_table,
            detour,
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
        let mut pickup_dep = vec![-1i32; n_trips];
        best_insert_inner(
            &travel,
            n_zones,
            &trip_table,
            &detour,
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
