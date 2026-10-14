//! Conductor networks: each phase net of a [`RoutingResult`] as a resistor
//! graph, solved for its equivalent resistance and branch currents.
//!
//! Trace endpoints are snapped to a 1 µm grid and become graph nodes keyed by
//! `(layer, x, y)`. Segments and arcs join nodes on one layer; a via joins the
//! copper layers it lands on. Braided patterns tie their strands together at
//! the crossing vias, so a phase is generally a mesh, not a bundle of
//! independent strands, and is solved by nodal analysis.
//!
//! Terminals are trace ends: dangling ends where one trace stops, or, when a
//! piece of copper has none, positions where two traces (summed over layers)
//! both leave toward the same side. A braid strand starts on both layers at
//! one via, which the second rule recognises. The ends are split into two buses
//! by distance along the copper from the farthest-apart pair; the bus holding
//! the lowest-x end is the phase terminal, the other the star (neutral) end.
//! Each bus is one shorted node, the way the fan-out joins the strands.

use pcbmotorgen_routing::{Point, RoutingResult};
use std::collections::{BTreeMap, HashMap, HashSet};

const MM_TO_M: f64 = 1e-3;
/// Snap grid for joining endpoints [mm].
const SNAP_MM: f64 = 1e-3;
/// Chords used to approximate one routed arc.
const ARC_CHORDS: usize = 8;

type NodeKey = (u32, i64, i64);

fn snap(p: Point) -> (i64, i64) {
    ((p.x / SNAP_MM).round() as i64, (p.y / SNAP_MM).round() as i64)
}

/// What an edge of the conductor graph is.
#[derive(Debug, Clone)]
pub enum EdgeKind {
    /// Trace polyline in metres, running from node `a` to node `b`.
    Trace { layer: u32, points: Vec<[f64; 2]>, length_m: f64 },
    /// Plated via barrel between two copper layers.
    Via,
}

#[derive(Debug, Clone)]
pub struct Edge {
    pub a: usize,
    pub b: usize,
    pub kind: EdgeKind,
}

/// The copper of one phase net.
#[derive(Debug, Clone)]
pub struct PhaseNetwork {
    pub net: String,
    pub node_count: usize,
    /// Node x position [m].
    pub node_x: Vec<f64>,
    /// Per node: a key shared by all layers at the same board position.
    pub terminal_key: Vec<i64>,
    pub edges: Vec<Edge>,
    /// Phase-terminal bus nodes.
    pub terminal: Vec<usize>,
    /// Star-end bus nodes.
    pub star: Vec<usize>,
    /// Active (thrust-producing) trace length [m].
    pub active_length_m: f64,
}

impl PhaseNetwork {
    /// Total trace length [m].
    pub fn trace_length_m(&self) -> f64 {
        self.edges
            .iter()
            .map(|e| match e.kind {
                EdgeKind::Trace { length_m, .. } => length_m,
                EdgeKind::Via => 0.0,
            })
            .sum()
    }

    pub fn via_count(&self) -> u32 {
        self.edges.iter().filter(|e| matches!(e.kind, EdgeKind::Via)).count() as u32
    }

    /// Copper layers used.
    pub fn layers(&self) -> Vec<u32> {
        let mut l: Vec<u32> = self
            .edges
            .iter()
            .filter_map(|e| match e.kind {
                EdgeKind::Trace { layer, .. } => Some(layer),
                EdgeKind::Via => None,
            })
            .collect();
        l.sort_unstable();
        l.dedup();
        l
    }

    /// Parallel paths entering at the phase terminal (distinct positions).
    pub fn strands(&self) -> u32 {
        let mut xs: Vec<i64> = self.terminal.iter().map(|&i| self.terminal_key[i]).collect();
        xs.sort_unstable();
        xs.dedup();
        xs.len() as u32
    }
}

/// Solved network: equivalent resistance and the share of the phase current
/// in every edge (signed, positive when flowing from `a` to `b`).
#[derive(Debug, Clone)]
pub struct NetworkSolution {
    pub resistance_ohm: f64,
    pub current_share: Vec<f64>,
    /// Converged and the terminals were connected.
    pub connected: bool,
}

/// Solve the network with per-edge resistances by conjugate gradients on the
/// grounded Laplacian (terminal bus at 1 V, star bus at 0 V).
pub fn solve_network(net: &PhaseNetwork, edge_r: &[f64]) -> NetworkSolution {
    let n = net.node_count;
    let fail = NetworkSolution { resistance_ohm: 0.0, current_share: vec![0.0; net.edges.len()], connected: false };
    if n == 0 || net.terminal.is_empty() || net.star.is_empty() {
        return fail;
    }
    let mut fixed: Vec<Option<f64>> = vec![None; n];
    for &t in &net.terminal {
        fixed[t] = Some(1.0);
    }
    for &s in &net.star {
        fixed[s] = Some(0.0);
    }
    // Unknown index map.
    let mut idx = vec![usize::MAX; n];
    let mut m = 0;
    for i in 0..n {
        if fixed[i].is_none() {
            idx[i] = m;
            m += 1;
        }
    }
    let g: Vec<f64> = edge_r.iter().map(|r| if *r > 0.0 { 1.0 / r } else { 1e12 }).collect();
    let mut diag = vec![0.0; m];
    let mut rhs = vec![0.0; m];
    let mut off: Vec<(usize, usize, f64)> = Vec::new();
    for (e, ge) in net.edges.iter().zip(g.iter()) {
        let (ia, ib) = (idx[e.a], idx[e.b]);
        match (ia != usize::MAX, ib != usize::MAX) {
            (true, true) => {
                diag[ia] += ge;
                diag[ib] += ge;
                off.push((ia, ib, *ge));
            }
            (true, false) => {
                diag[ia] += ge;
                rhs[ia] += ge * fixed[e.b].unwrap();
            }
            (false, true) => {
                diag[ib] += ge;
                rhs[ib] += ge * fixed[e.a].unwrap();
            }
            (false, false) => {}
        }
    }
    // Isolated unknowns (floating copper) get a unit diagonal.
    for d in diag.iter_mut() {
        if *d == 0.0 {
            *d = 1.0;
        }
    }
    let matvec = |x: &[f64], y: &mut [f64]| {
        for i in 0..m {
            y[i] = diag[i] * x[i];
        }
        for &(a, b, ge) in &off {
            y[a] -= ge * x[b];
            y[b] -= ge * x[a];
        }
    };
    // Jacobi-preconditioned CG.
    let mut x = vec![0.0; m];
    let mut r = rhs.clone();
    let mut z: Vec<f64> = r.iter().zip(&diag).map(|(r, d)| r / d).collect();
    let mut p = z.clone();
    let mut rz: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
    let norm0 = rhs.iter().map(|v| v * v).sum::<f64>().sqrt().max(1e-300);
    let mut ap = vec![0.0; m];
    for _ in 0..(10 * m + 100) {
        if r.iter().map(|v| v * v).sum::<f64>().sqrt() <= 1e-13 * norm0 {
            break;
        }
        matvec(&p, &mut ap);
        let pap: f64 = p.iter().zip(&ap).map(|(a, b)| a * b).sum();
        if pap <= 0.0 {
            break;
        }
        let alpha = rz / pap;
        for i in 0..m {
            x[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        for i in 0..m {
            z[i] = r[i] / diag[i];
        }
        let rz_new: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
        let beta = rz_new / rz;
        rz = rz_new;
        for i in 0..m {
            p[i] = z[i] + beta * p[i];
        }
    }
    let v = |i: usize| fixed[i].unwrap_or_else(|| x[idx[i]]);
    let currents: Vec<f64> = net
        .edges
        .iter()
        .zip(g.iter())
        .map(|(e, ge)| (v(e.a) - v(e.b)) * ge)
        .collect();
    // Current leaving the terminal bus.
    let term: HashSet<usize> = net.terminal.iter().copied().collect();
    let mut i_total = 0.0;
    for (e, i) in net.edges.iter().zip(currents.iter()) {
        let (ta, tb) = (term.contains(&e.a), term.contains(&e.b));
        if ta && !tb {
            i_total += i;
        } else if tb && !ta {
            i_total -= i;
        }
    }
    if !(i_total > 1e-15) {
        return fail;
    }
    NetworkSolution {
        resistance_ohm: 1.0 / i_total,
        current_share: currents.iter().map(|i| i / i_total).collect(),
        connected: true,
    }
}

fn arc_points(start: Point, mid: Point, end: Point) -> Vec<Point> {
    // Circle through three points; fall back to two chords when collinear.
    let (ax, ay, bx, by, cx, cy) = (start.x, start.y, mid.x, mid.y, end.x, end.y);
    let d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
    if d.abs() < 1e-12 {
        return vec![start, mid, end];
    }
    let a2 = ax * ax + ay * ay;
    let b2 = bx * bx + by * by;
    let c2 = cx * cx + cy * cy;
    let ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d;
    let uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d;
    let r = ((ax - ux).powi(2) + (ay - uy).powi(2)).sqrt();
    let ang = |p: Point| (p.y - uy).atan2(p.x - ux);
    let (t0, tm, t1) = (ang(start), ang(mid), ang(end));
    let tau = std::f64::consts::TAU;
    let norm = |t: f64| ((t % tau) + tau) % tau;
    // Sweep counter-clockwise from start; flip when mid is not on that sweep.
    let ccw_end = norm(t1 - t0);
    let ccw_mid = norm(tm - t0);
    let sweep = if ccw_mid <= ccw_end { ccw_end } else { ccw_end - tau };
    (0..=ARC_CHORDS)
        .map(|k| {
            if k == 0 {
                return start;
            }
            if k == ARC_CHORDS {
                return end;
            }
            let t = t0 + sweep * k as f64 / ARC_CHORDS as f64;
            Point::new(ux + r * t.cos(), uy + r * t.sin())
        })
        .collect()
}

struct Builder {
    nodes: HashMap<NodeKey, usize>,
    keys: Vec<NodeKey>,
    edges: Vec<Edge>,
    active_mm: f64,
}

impl Builder {
    fn node(&mut self, key: NodeKey) -> usize {
        if let Some(&i) = self.nodes.get(&key) {
            return i;
        }
        let i = self.keys.len();
        self.keys.push(key);
        self.nodes.insert(key, i);
        i
    }

    fn trace(&mut self, layer: u32, points: Vec<Point>, active: bool) {
        let (Some(first), Some(last)) = (points.first().copied(), points.last().copied()) else {
            return;
        };
        let (ka, kb) = (snap(first), snap(last));
        if ka == kb {
            return;
        }
        let len_mm: f64 = points.windows(2).map(|w| w[0].distance_to(w[1])).sum();
        if active {
            self.active_mm += len_mm;
        }
        let a = self.node((layer, ka.0, ka.1));
        let b = self.node((layer, kb.0, kb.1));
        self.edges.push(Edge {
            a,
            b,
            kind: EdgeKind::Trace {
                layer,
                points: points.iter().map(|p| [p.x * MM_TO_M, p.y * MM_TO_M]).collect(),
                length_m: len_mm * MM_TO_M,
            },
        });
    }
}

fn builder<'a>(nets: &'a mut BTreeMap<String, Builder>, net: &str) -> &'a mut Builder {
    nets.entry(net.to_string()).or_insert_with(|| Builder {
        nodes: HashMap::new(),
        keys: Vec::new(),
        edges: Vec::new(),
        active_mm: 0.0,
    })
}

/// Build the conductor network of every phase net, in label order.
pub fn extract_phase_networks(routing: &RoutingResult) -> Vec<PhaseNetwork> {
    let mut nets: BTreeMap<String, Builder> = BTreeMap::new();
    for s in &routing.segments {
        builder(&mut nets, &s.net).trace(s.layer, vec![s.start, s.end], s.is_active);
    }
    for c in &routing.curves {
        builder(&mut nets, &c.net).trace(c.layer, arc_points(c.start, c.mid, c.end), c.is_active);
    }
    let mut seen = HashSet::new();
    for v in &routing.vias {
        let Some(b) = nets.get_mut(&v.net) else { continue };
        let (x, y) = snap(v.position);
        if !seen.insert((v.net.clone(), x, y)) {
            continue;
        }
        let (lo, hi) = (v.from_layer.min(v.to_layer), v.from_layer.max(v.to_layer));
        let landed: Vec<usize> = (lo..=hi).filter_map(|l| b.nodes.get(&(l, x, y)).copied()).collect();
        for w in landed.windows(2) {
            b.edges.push(Edge { a: w[0], b: w[1], kind: EdgeKind::Via });
        }
    }

    nets.into_iter()
        .filter(|(_, b)| !b.edges.is_empty())
        .map(|(net, b)| {
            let n = b.keys.len();
            let pos = |i: usize| (b.keys[i].1 as f64 * SNAP_MM, b.keys[i].2 as f64 * SNAP_MM);
            let (terminal, star) = find_terminals(&b, pos);
            PhaseNetwork {
                net,
                node_count: n,
                node_x: (0..n).map(|i| pos(i).0 * MM_TO_M).collect(),
                terminal_key: (0..n)
                    .map(|i| b.keys[i].1.wrapping_mul(1_000_003).wrapping_add(b.keys[i].2))
                    .collect(),
                edges: b.edges,
                terminal,
                star,
                active_length_m: b.active_mm * MM_TO_M,
            }
        })
        .collect()
}

/// Locate the trace-end positions and split them into the terminal and star
/// buses (all copper nodes at those positions).
fn find_terminals(b: &Builder, pos: impl Fn(usize) -> (f64, f64)) -> (Vec<usize>, Vec<usize>) {
    let n = b.keys.len();
    // Per board position: incident trace directions (sign of dx; 0 = vertical).
    let mut at: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
    for i in 0..n {
        at.entry((b.keys[i].1, b.keys[i].2)).or_default().push(i);
    }
    let mut dirs: HashMap<(i64, i64), Vec<i8>> = HashMap::new();
    let mut adj: Vec<Vec<(usize, f64)>> = vec![Vec::new(); n];
    for e in &b.edges {
        let w = match e.kind {
            EdgeKind::Trace { length_m, .. } => length_m,
            EdgeKind::Via => 0.0,
        };
        adj[e.a].push((e.b, w));
        adj[e.b].push((e.a, w));
        if let EdgeKind::Trace { points, .. } = &e.kind {
            let (pa, pb) = (points[0], points[1]);
            let (qa, qb) = (points[points.len() - 1], points[points.len() - 2]);
            let side = |from: [f64; 2], to: [f64; 2]| -> i8 {
                let dx = to[0] - from[0];
                if dx.abs() < 1e-9 { 0 } else if dx > 0.0 { 1 } else { -1 }
            };
            dirs.entry((b.keys[e.a].1, b.keys[e.a].2)).or_default().push(side(pa, pb));
            dirs.entry((b.keys[e.b].1, b.keys[e.b].2)).or_default().push(side(qa, qb));
        }
    }
    let mut ends: Vec<(i64, i64)> = dirs
        .iter()
        .filter(|(_, d)| {
            d.len() == 1 || (d.len() == 2 && d[0] == d[1] && d[0] != 0)
        })
        .map(|(k, _)| *k)
        .collect();
    ends.sort_unstable();
    if ends.len() < 2 {
        return (Vec::new(), Vec::new());
    }

    // Distance along the copper from a set of start nodes.
    let dijkstra = |starts: &[usize]| -> Vec<f64> {
        let mut dist = vec![f64::INFINITY; n];
        let mut heap = std::collections::BinaryHeap::new();
        for &s in starts {
            dist[s] = 0.0;
            heap.push(std::cmp::Reverse((OrdF(0.0), s)));
        }
        while let Some(std::cmp::Reverse((OrdF(d), u))) = heap.pop() {
            if d > dist[u] {
                continue;
            }
            for &(v, w) in &adj[u] {
                let nd = d + w;
                if nd < dist[v] {
                    dist[v] = nd;
                    heap.push(std::cmp::Reverse((OrdF(nd), v)));
                }
            }
        }
        dist
    };
    let end_dist = |dist: &[f64], e: &(i64, i64)| -> f64 {
        at[e].iter().map(|i| dist[*i]).fold(f64::INFINITY, f64::min)
    };
    let by_pos = |a: &(i64, i64), b: &(i64, i64)| {
        pos(at[a][0]).partial_cmp(&pos(at[b][0])).unwrap_or(std::cmp::Ordering::Equal)
    };

    // Each connected piece of copper is split on its own, oriented so the
    // bus holding its lowest end is the terminal.
    let (mut terminal, mut star) = (Vec::new(), Vec::new());
    let mut remaining: Vec<(i64, i64)> = ends.clone();
    while !remaining.is_empty() {
        let lowest = *remaining.iter().min_by(|a, b| by_pos(a, b)).unwrap();
        let d0 = dijkstra(&at[&lowest]);
        let mut component: Vec<(i64, i64)> =
            remaining.iter().copied().filter(|e| end_dist(&d0, e).is_finite()).collect();
        remaining.retain(|e| !component.contains(e));
        // Truly dangling ends win over two-layer turn points when present.
        if component.iter().filter(|e| dirs[*e].len() == 1).count() >= 2 {
            component.retain(|e| dirs[e].len() == 1);
        }
        let lowest = *component.iter().min_by(|a, b| by_pos(a, b)).unwrap();
        if component.len() < 2 {
            continue;
        }
        let farthest = |dist: &[f64]| -> (i64, i64) {
            *component
                .iter()
                .max_by(|a, b| end_dist(dist, a).partial_cmp(&end_dist(dist, b)).unwrap())
                .unwrap()
        };
        let e1 = farthest(&d0);
        let d1 = dijkstra(&at[&e1]);
        let e2 = farthest(&d1);
        let d2 = dijkstra(&at[&e2]);
        let (mut g1, mut g2) = (Vec::new(), Vec::new());
        let mut lowest_in_g1 = false;
        for e in &component {
            if end_dist(&d1, e) <= end_dist(&d2, e) {
                g1.extend(at[e].iter().copied());
                lowest_in_g1 |= *e == lowest;
            } else {
                g2.extend(at[e].iter().copied());
            }
        }
        if lowest_in_g1 {
            terminal.extend(g1);
            star.extend(g2);
        } else {
            terminal.extend(g2);
            star.extend(g1);
        }
    }
    (terminal, star)
}

#[derive(Clone, Copy, PartialEq, PartialOrd)]
struct OrdF(f64);
impl Eq for OrdF {}
impl Ord for OrdF {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.0.partial_cmp(&other.0).unwrap_or(std::cmp::Ordering::Equal)
    }
}
