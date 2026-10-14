//! Partial inductance of routed copper by the Neumann formula
//! `M = μ0/4π ∬ dl₁·dl₂ / r` over straight filaments.
//!
//! Each filament carries a share `wᵢ` of the phase current (from the network
//! solve), so the flux linkage per ampere is `ΣᵢΣⱼ wᵢ·wⱼ·Mᵢⱼ`. Self terms
//! use the closed form for a rectangular bar; close pairs use more quadrature
//! points and the bar's geometric mean distance as a softening length.

use super::geometry::{EdgeKind, PhaseNetwork};
use crate::units::MU_0;
use rayon::prelude::*;

/// One straight current filament [m].
#[derive(Debug, Clone, Copy)]
pub struct Filament {
    pub a: [f64; 3],
    pub b: [f64; 3],
    /// Share of the phase current, signed along `a → b`.
    pub w: f64,
}

impl Filament {
    fn dl(&self) -> [f64; 3] {
        [self.b[0] - self.a[0], self.b[1] - self.a[1], self.b[2] - self.a[2]]
    }
    fn len(&self) -> f64 {
        norm(self.dl())
    }
    fn mid(&self) -> [f64; 3] {
        [
            0.5 * (self.a[0] + self.b[0]),
            0.5 * (self.a[1] + self.b[1]),
            0.5 * (self.a[2] + self.b[2]),
        ]
    }
}

fn norm(v: [f64; 3]) -> f64 {
    (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt()
}

/// Current-carrying filaments of a phase; layer `l` sits at
/// `z = l·layer_pitch`. `share` is the per-edge current share.
pub fn phase_filaments(net: &PhaseNetwork, share: &[f64], layer_pitch_m: f64) -> Vec<Filament> {
    let mut out = Vec::new();
    for (e, w) in net.edges.iter().zip(share.iter()) {
        if w.abs() < 1e-9 {
            continue;
        }
        if let EdgeKind::Trace { layer, points, .. } = &e.kind {
            let z = *layer as f64 * layer_pitch_m;
            for p in points.windows(2) {
                let f = Filament { a: [p[0][0], p[0][1], z], b: [p[1][0], p[1][1], z], w: *w };
                if f.len() > 0.0 {
                    out.push(f);
                }
            }
        }
    }
    out
}

const GL2: [(f64, f64); 2] = [(-0.577_350_269_189_625_8, 1.0), (0.577_350_269_189_625_8, 1.0)];
const GL4: [(f64, f64); 4] = [
    (-0.861_136_311_594_052_6, 0.347_854_845_137_453_9),
    (-0.339_981_043_584_856_3, 0.652_145_154_862_546_1),
    (0.339_981_043_584_856_3, 0.652_145_154_862_546_1),
    (0.861_136_311_594_052_6, 0.347_854_845_137_453_9),
];
const GL8: [(f64, f64); 8] = [
    (-0.960_289_856_497_536_3, 0.101_228_536_290_376_3),
    (-0.796_666_477_413_626_7, 0.222_381_034_453_374_5),
    (-0.525_532_409_916_329_0, 0.313_706_645_877_887_3),
    (-0.183_434_642_495_649_8, 0.362_683_783_378_362_0),
    (0.183_434_642_495_649_8, 0.362_683_783_378_362_0),
    (0.525_532_409_916_329_0, 0.313_706_645_877_887_3),
    (0.796_666_477_413_626_7, 0.222_381_034_453_374_5),
    (0.960_289_856_497_536_3, 0.101_228_536_290_376_3),
];

/// Partial self inductance of a straight rectangular bar [H].
fn bar_self(len: f64, width: f64, thickness: f64) -> f64 {
    let wt = width + thickness;
    if len <= 0.0 || wt <= 0.0 {
        return 0.0;
    }
    MU_0 * len / (2.0 * std::f64::consts::PI) * ((2.0 * len / wt).ln() + 0.5 + 0.2235 * wt / len)
}

fn sub(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn dot3(a: [f64; 3], b: [f64; 3]) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/// Closest distance between two segments.
fn segment_distance(f: &Filament, g: &Filament) -> f64 {
    let d1 = f.dl();
    let d2 = g.dl();
    let r = sub(f.a, g.a);
    let (a, e, ff) = (dot3(d1, d1), dot3(d2, d2), dot3(d2, r));
    let (mut s, mut t);
    let c = dot3(d1, r);
    let b = dot3(d1, d2);
    let denom = a * e - b * b;
    s = if denom > 1e-30 { ((b * ff - c * e) / denom).clamp(0.0, 1.0) } else { 0.0 };
    t = if e > 0.0 { (b * s + ff) / e } else { 0.0 };
    if t < 0.0 {
        t = 0.0;
        s = if a > 0.0 { (-c / a).clamp(0.0, 1.0) } else { 0.0 };
    } else if t > 1.0 {
        t = 1.0;
        s = if a > 0.0 { ((b - c) / a).clamp(0.0, 1.0) } else { 0.0 };
    }
    let p = [f.a[0] + s * d1[0], f.a[1] + s * d1[1], f.a[2] + s * d1[2]];
    let q = [g.a[0] + t * d2[0], g.a[1] + t * d2[1], g.a[2] + t * d2[2]];
    norm(sub(p, q))
}

fn split(f: &Filament) -> (Filament, Filament) {
    let m = f.mid();
    (Filament { a: f.a, b: m, w: f.w }, Filament { a: m, b: f.b, w: f.w })
}

/// Mutual partial inductance of two filaments [H]. Pairs that are close
/// relative to their length are bisected until the quadrature resolves the
/// `1/r` kernel.
fn mutual(f: &Filament, g: &Filament, gmd: f64) -> f64 {
    let (lf, lg) = (f.len(), g.len());
    if lf == 0.0 || lg == 0.0 {
        return 0.0;
    }
    let d1 = f.dl();
    let d2 = g.dl();
    let cos = dot3(d1, d2) / (lf * lg);
    if cos.abs() > 1.0 - 1e-9 {
        return parallel_mutual(f, g, cos.signum(), gmd);
    }
    mutual_rec(f, g, gmd, 0)
}

/// Exact mutual partial inductance of two parallel filaments (Grover):
/// `M = μ0/4π·[H(l₁−s) + H(s+l₂) − H(l₁−s−l₂) − H(s)]`,
/// `H(u) = u·asinh(u/d) − √(u²+d²)`, softened by the GMD.
fn parallel_mutual(f: &Filament, g: &Filament, sign: f64, gmd: f64) -> f64 {
    let lf = f.len();
    let lg = g.len();
    let u = {
        let d = f.dl();
        [d[0] / lf, d[1] / lf, d[2] / lf]
    };
    // Express g in f's frame with g running along +u.
    let g_start = if sign > 0.0 { g.a } else { g.b };
    let rel = sub(g_start, f.a);
    let s = dot3(rel, u);
    let perp = sub(rel, [s * u[0], s * u[1], s * u[2]]);
    let d = (dot3(perp, perp) + gmd * gmd).sqrt();
    let h = |x: f64| x * (x / d).asinh() - (x * x + d * d).sqrt();
    let integral = h(lf - s) + h(s + lg) - h(lf - s - lg) - h(s);
    sign * MU_0 / (4.0 * std::f64::consts::PI) * integral
}

fn mutual_rec(f: &Filament, g: &Filament, gmd: f64, depth: u32) -> f64 {
    let d1 = f.dl();
    let d2 = g.dl();
    let dot = dot3(d1, d2);
    if dot == 0.0 {
        return 0.0;
    }
    let (lf, lg) = (f.len(), g.len());
    let near = segment_distance(f, g).max(gmd);
    if depth < 16 && lf.max(lg) > 4.0 * near {
        if lf >= lg {
            let (f1, f2) = split(f);
            return mutual_rec(&f1, g, gmd, depth + 1) + mutual_rec(&f2, g, gmd, depth + 1);
        }
        let (g1, g2) = split(g);
        return mutual_rec(f, &g1, gmd, depth + 1) + mutual_rec(f, &g2, gmd, depth + 1);
    }
    let sep = norm(sub(f.mid(), g.mid()));
    let scale = lf.max(lg);
    let rule: &[(f64, f64)] = if sep > 4.0 * scale {
        &GL2
    } else if sep > 1.5 * scale {
        &GL4
    } else {
        &GL8
    };
    let mut acc = 0.0;
    for &(s, ws) in rule {
        let ts = 0.5 * (s + 1.0);
        let p = [f.a[0] + ts * d1[0], f.a[1] + ts * d1[1], f.a[2] + ts * d1[2]];
        for &(t, wt) in rule {
            let tt = 0.5 * (t + 1.0);
            let q = [g.a[0] + tt * d2[0], g.a[1] + tt * d2[1], g.a[2] + tt * d2[2]];
            let r2 = (p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2) + (p[2] - q[2]).powi(2);
            acc += ws * wt / (r2 + gmd * gmd).sqrt();
        }
    }
    // Quadrature over [0,1]² has Jacobian 1/4.
    MU_0 / (4.0 * std::f64::consts::PI) * dot * acc * 0.25
}

fn block_sum(a: &[Filament], b: &[Filament], gmd: f64, same: bool, width: f64, thickness: f64) -> f64 {
    a.par_iter()
        .enumerate()
        .map(|(i, f)| {
            let mut s = 0.0;
            for (j, g) in b.iter().enumerate() {
                let ww = f.w * g.w;
                if same && i == j {
                    s += ww * bar_self(f.len(), width, thickness);
                } else {
                    s += ww * mutual(f, g, gmd);
                }
            }
            s
        })
        .sum()
}

/// Self inductance of a phase [H].
pub fn phase_self_inductance(f: &[Filament], width: f64, thickness: f64) -> f64 {
    let gmd = 0.2235 * (width + thickness);
    block_sum(f, f, gmd, true, width, thickness)
}

/// Mutual inductance between two phases [H].
pub fn phase_mutual_inductance(a: &[Filament], b: &[Filament], width: f64, thickness: f64) -> f64 {
    let gmd = 0.2235 * (width + thickness);
    block_sum(a, b, gmd, false, width, thickness)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn two_wire_line_matches_closed_form() {
        // Two antiparallel 100 mm filaments 2 mm apart: loop partial
        // inductance L = 2(Ls − M). Closed-form mutual of parallel filaments:
        // M = μ0 l/2π [ln(l/d + √(1+l²/d²)) − √(1+d²/l²) + d/l].
        let (l, d) = (0.1_f64, 0.002_f64);
        let f = Filament { a: [0.0, 0.0, 0.0], b: [l, 0.0, 0.0], w: 1.0 };
        let g = Filament { a: [0.0, d, 0.0], b: [l, d, 0.0], w: 1.0 };
        let m_num = mutual(&f, &g, 0.0);
        let m_ref = MU_0 * l / (2.0 * std::f64::consts::PI)
            * ((l / d + (1.0 + (l / d).powi(2)).sqrt()).ln() - (1.0 + (d / l).powi(2)).sqrt() + d / l);
        assert!((m_num - m_ref).abs() / m_ref < 1e-9, "num {m_num} ref {m_ref}");
        // The bisecting quadrature path agrees with the exact parallel form.
        let m_quad = mutual_rec(&f, &g, 0.0, 0);
        assert!((m_quad - m_ref).abs() / m_ref < 0.02, "quad {m_quad} ref {m_ref}");
    }
}
