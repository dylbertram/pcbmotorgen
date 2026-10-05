//! Parametric two-layer linear inductive position sensor geometry.
//!
//! Native Rust port of `pcbInductionPosition/pcbSensor`. Curves are sampled
//! uniformly in the base-wave parameter (not in x), and each winding is
//! emitted as one ordered electrical chain. Coordinates are millimetres.

use crate::{Point, RouteSegment, Via};
use serde::{Deserialize, Serialize};

const F_CU: u32 = 0;
const B_CU: u32 = 1;
const EPSILON: f64 = 1e-6;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", default)]
pub struct SensorConfig {
    pub lambda_mm: f64,
    pub x_start_mm: f64,
    pub amplitude_mm: f64,
    pub turns: u32,
    pub trace_width_mm: f64,
    pub trace_gap_mm: f64,
    pub min_clearance_mm: f64,
    pub via_size_mm: f64,
    pub arc_step_mm: f64,
    pub chip_lead_in_mm: f64,
    pub end_inset_mm: f64,
    pub bulge_apex_offset_mm: f64,
    pub tx_enabled: bool,
    pub rx_tx_gap_mm: f64,
    pub tx_strand_pitch_mm: f64,
    pub tx_corner_offset_mm: f64,
    pub tx_trace_width_mm: f64,
    pub tx_via_size_mm: f64,
}

impl Default for SensorConfig {
    fn default() -> Self {
        Self {
            lambda_mm: 120.0,
            x_start_mm: 0.0,
            amplitude_mm: 5.66,
            turns: 2,
            trace_width_mm: 0.15,
            trace_gap_mm: 0.4,
            min_clearance_mm: 0.2,
            via_size_mm: 0.6,
            arc_step_mm: 0.25,
            chip_lead_in_mm: 10.0,
            end_inset_mm: 1.0,
            bulge_apex_offset_mm: 2.0,
            tx_enabled: true,
            rx_tx_gap_mm: 4.0,
            tx_strand_pitch_mm: 0.45,
            tx_corner_offset_mm: 3.0,
            tx_trace_width_mm: 0.15,
            tx_via_size_mm: 0.6,
        }
    }
}

impl SensorConfig {
    fn dy(&self) -> f64 {
        self.trace_width_mm + self.trace_gap_mm
    }

    fn lead_y(&self) -> f64 {
        self.dy() / 2.0
    }

    fn tx_via_offset(&self) -> f64 {
        self.tx_via_size_mm / 2.0 + self.tx_trace_width_mm / 2.0 + self.min_clearance_mm
    }

    fn tx_x1(&self) -> f64 {
        self.x_start_mm - self.rx_tx_gap_mm
    }

    fn tx_x2(&self) -> f64 {
        self.tx_x1() + self.tx_strand_pitch_mm
    }

    fn tx_x3(&self) -> f64 {
        self.tx_x1() + 2.0 * self.tx_strand_pitch_mm
    }

    fn tx_xr(&self) -> f64 {
        self.x_start_mm + self.lambda_mm + self.tx_corner_offset_mm
    }

    fn tx_xri(&self) -> f64 {
        self.tx_xr() - self.tx_strand_pitch_mm
    }

    fn tx_y_inner(&self) -> f64 {
        self.amplitude_mm + f64::from(self.turns) * self.dy()
    }

    fn tx_y_outer(&self) -> f64 {
        self.tx_y_inner() + self.tx_strand_pitch_mm
    }

    fn tx_y_cont(&self) -> f64 {
        self.lead_y() + self.dy()
    }

    fn tx_lead_via_x(&self) -> f64 {
        self.tx_x2() + self.tx_via_offset()
    }

    fn tx_y_l1(&self) -> f64 {
        -(self.lead_y() + self.tx_via_offset())
    }

    fn tx_y_f(&self) -> f64 {
        -(self.lead_y()
            + (self.tx_trace_width_mm + self.trace_width_mm) / 2.0
            + self.min_clearance_mm)
    }

    fn tx_y_p1(&self) -> f64 {
        self.tx_y_f() - (self.tx_via_size_mm + self.min_clearance_mm)
    }

    fn tx_y_u1(&self) -> f64 {
        self.tx_y_cont() + self.tx_via_offset()
    }

    fn tx_y_j2(&self) -> f64 {
        self.tx_y_u1() + self.dy()
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SensorNetGeometry {
    pub name: String,
    pub segments: Vec<RouteSegment>,
    pub vias: Vec<Via>,
    pub trace_width_mm: f64,
    pub via_size_mm: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SensorGeometry {
    pub nets: Vec<SensorNetGeometry>,
    /// Prototype terminal coordinates, not physical KiCad pads.
    pub terminal_markers: Vec<(String, Point)>,
    pub board_bounds_mm: [f64; 4],
}

#[derive(Clone, Copy, Debug)]
enum WaveKind {
    Sine,
    Cosine,
}

#[derive(Clone, Copy)]
enum Element {
    Connector {
        start: Point,
        end: Point,
        layer: u32,
        strand: u32,
    },
    Wave {
        kind: WaveKind,
        side: f64,
        x_start: f64,
        x_end: f64,
        layer: u32,
        strand: u32,
    },
    Bulge {
        start: Point,
        end: Point,
        apex_x: f64,
        layer: u32,
        strand: u32,
    },
}

fn point(x: f64, y: f64) -> Point {
    Point::new(x, y)
}

fn connector(start: (f64, f64), end: (f64, f64), layer: u32, strand: u32) -> Element {
    Element::Connector {
        start: point(start.0, start.1),
        end: point(end.0, end.1),
        layer,
        strand,
    }
}

fn wave(kind: WaveKind, side: f64, x_start: f64, x_end: f64, layer: u32, strand: u32) -> Element {
    Element::Wave {
        kind,
        side,
        x_start,
        x_end,
        layer,
        strand,
    }
}

fn bulge(start: (f64, f64), end: (f64, f64), apex_x: f64, layer: u32, strand: u32) -> Element {
    Element::Bulge {
        start: point(start.0, start.1),
        end: point(end.0, end.1),
        apex_x,
        layer,
        strand,
    }
}

fn base_and_slope(c: &SensorConfig, kind: WaveKind, t: f64) -> (f64, f64) {
    let k = std::f64::consts::TAU / c.lambda_mm;
    let u = k * (t - c.x_start_mm);
    match kind {
        WaveKind::Sine => (c.amplitude_mm * u.sin(), c.amplitude_mm * k * u.cos()),
        WaveKind::Cosine => (c.amplitude_mm * u.cos(), -c.amplitude_mm * k * u.sin()),
    }
}

fn wave_point(c: &SensorConfig, kind: WaveKind, side: f64, t: f64, strand: u32) -> Point {
    let offset = f64::from(strand) * c.dy();
    let (f, fp) = base_and_slope(c, kind, t);
    if offset == 0.0 {
        return point(t, side * f);
    }
    let norm = fp.hypot(1.0);
    point(t + offset * fp / norm, side * (f - offset / norm))
}

fn t_for_x(c: &SensorConfig, kind: WaveKind, x: f64, strand: u32) -> f64 {
    let offset = f64::from(strand) * c.dy();
    if offset == 0.0 {
        return x;
    }
    let k = std::f64::consts::TAU / c.lambda_mm;
    let mut t = x;
    for _ in 0..50 {
        let (f, fp) = base_and_slope(c, kind, t);
        let norm = fp.hypot(1.0);
        let error = t + offset * fp / norm - x;
        if error.abs() < 1e-13 {
            return t;
        }
        t -= error / (1.0 - offset * k * k * f / norm.powi(3));
    }

    let (mut lo, mut hi) = (x - offset, x + offset);
    for _ in 0..100 {
        let mid = (lo + hi) / 2.0;
        let (_, fp) = base_and_slope(c, kind, mid);
        if mid + offset * fp / fp.hypot(1.0) < x {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    (lo + hi) / 2.0
}

fn wave_y(c: &SensorConfig, kind: WaveKind, side: f64, x: f64, strand: u32) -> f64 {
    wave_point(c, kind, side, t_for_x(c, kind, x, strand), strand).y
}

fn leg_point(c: &SensorConfig, kind: WaveKind, side: f64, x: f64, strand: u32) -> Point {
    point(x, wave_y(c, kind, side, x, strand))
}

fn wave_normal(c: &SensorConfig, kind: WaveKind, side: f64, x: f64, strand: u32) -> Point {
    let offset = f64::from(strand) * c.dy();
    let t = t_for_x(c, kind, x, strand);
    let (f, fp) = base_and_slope(c, kind, t);
    let k = std::f64::consts::TAU / c.lambda_mm;
    let x_dot = 1.0 - offset * k * k * f / fp.hypot(1.0).powi(3);
    let y_dot = if side < 0.0 { -fp * x_dot } else { fp * x_dot };
    let norm = x_dot.hypot(y_dot);
    point(-y_dot / norm, x_dot / norm)
}

fn tangent_via(
    c: &SensorConfig,
    kind: WaveKind,
    side: f64,
    x: f64,
    strand: u32,
    sigma: f64,
) -> (Point, Point) {
    let foot = leg_point(c, kind, side, x, strand);
    let normal = wave_normal(c, kind, side, x, strand);
    let distance = c.via_size_mm / 2.0 + c.trace_width_mm / 2.0;
    (
        foot,
        point(
            foot.x + sigma * distance * normal.x,
            foot.y + sigma * distance * normal.y,
        ),
    )
}

fn root_on_wave(
    c: &SensorConfig,
    kind: WaveKind,
    strand: u32,
    target_y: f64,
    mut lo: f64,
    mut hi: f64,
) -> f64 {
    for _ in 0..80 {
        let mid = (lo + hi) / 2.0;
        if wave_y(c, kind, 1.0, mid, strand) < target_y {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    (lo + hi) / 2.0
}

fn sine_start_junction(c: &SensorConfig, strand: u32) -> f64 {
    if strand == 0 {
        c.x_start_mm
    } else {
        root_on_wave(
            c,
            WaveKind::Sine,
            strand,
            0.0,
            c.x_start_mm,
            c.x_start_mm + c.lambda_mm / 4.0,
        )
    }
}

fn sine_lead_junction(c: &SensorConfig, y: f64) -> f64 {
    root_on_wave(
        c,
        WaveKind::Sine,
        0,
        y,
        c.x_start_mm,
        c.x_start_mm + c.lambda_mm / 4.0,
    )
}

fn sine_handover_x(c: &SensorConfig, strand: u32, next: u32) -> Result<f64, String> {
    let x_start = c.x_start_mm;
    let x_end = x_start + c.lambda_mm;
    let samples_per_period = (c.lambda_mm / 0.01).ceil().max(2.0) as usize;
    let samples = samples_per_period * 2;
    let step = c.lambda_mm / samples_per_period as f64;
    let diff =
        |x| wave_y(c, WaveKind::Sine, 1.0, x, strand) - wave_y(c, WaveKind::Sine, -1.0, x, next);

    let mut roots = Vec::new();
    let mut x_prev = x_start;
    let mut f_prev = diff(x_prev);
    for i in 1..=samples {
        let x_cur = x_start + i as f64 * step;
        let f_cur = diff(x_cur);
        if f_prev == 0.0 {
            roots.push(x_prev);
        } else if f_prev * f_cur < 0.0 {
            let (mut lo, mut hi) = (x_prev, x_cur);
            for _ in 0..60 {
                let mid = (lo + hi) / 2.0;
                if diff(lo) * diff(mid) <= 0.0 {
                    hi = mid;
                } else {
                    lo = mid;
                }
            }
            roots.push((lo + hi) / 2.0);
        }
        x_prev = x_cur;
        f_prev = f_cur;
    }
    roots
        .into_iter()
        .find(|x| *x > x_end)
        .ok_or_else(|| "no sine strand handover intersection beyond the period".to_string())
}

fn make_sine_elements(c: &SensorConfig) -> Result<Vec<Element>, String> {
    let mut chain = Vec::new();
    let lambda = c.lambda_mm;
    let x0 = c.x_start_mm;
    let quarter = lambda / 4.0;
    let lead_x = x0 - c.chip_lead_in_mm;
    let lead_y = c.lead_y();
    let lead_trim = sine_lead_junction(c, lead_y);
    let begin_swap = x0 + lambda / 32.0;
    let end_swap = x0 + 31.0 * lambda / 32.0;
    let quarter_via = x0 + quarter + lambda / 16.0;
    let three_quarter_via = x0 + 3.0 * quarter + lambda / 16.0;

    for strand in 0..c.turns {
        let next = (strand + 1) % c.turns;
        let begin = if strand == 0 {
            lead_trim
        } else {
            sine_start_junction(c, strand)
        };
        let handover = sine_handover_x(c, strand, next)?;
        if handover < x0 + quarter {
            return Err("sine handover intersection is left of the mid crossing".into());
        }

        if strand == 0 {
            let p = leg_point(c, WaveKind::Sine, 1.0, lead_trim, strand);
            chain.push(connector((lead_x, lead_y), (p.x, p.y), B_CU, strand));
        }

        let sigma_forward = if strand == 0 { 1.0 } else { -1.0 };
        let sigma_return = if next == 1 { 1.0 } else { -1.0 };
        let (pfq, vfq) = tangent_via(c, WaveKind::Sine, 1.0, quarter_via, strand, sigma_forward);
        let (pfm, vfm) = tangent_via(
            c,
            WaveKind::Sine,
            1.0,
            three_quarter_via,
            strand,
            sigma_forward,
        );
        let (prm, vrm) = tangent_via(
            c,
            WaveKind::Sine,
            -1.0,
            three_quarter_via,
            next,
            sigma_return,
        );
        let (prq, vrq) = tangent_via(c, WaveKind::Sine, -1.0, quarter_via, next, sigma_return);

        if strand == 1 {
            let (p, v) = tangent_via(c, WaveKind::Sine, 1.0, begin_swap, strand, -1.0);
            chain.push(wave(WaveKind::Sine, 1.0, begin, begin_swap, F_CU, strand));
            chain.push(connector((p.x, p.y), (v.x, v.y), F_CU, strand));
            chain.push(connector((v.x, v.y), (p.x, p.y), B_CU, strand));
            chain.push(wave(
                WaveKind::Sine,
                1.0,
                begin_swap,
                quarter_via,
                B_CU,
                strand,
            ));
        } else {
            chain.push(wave(WaveKind::Sine, 1.0, begin, quarter_via, B_CU, strand));
        }

        chain.push(connector((pfq.x, pfq.y), (vfq.x, vfq.y), B_CU, strand));
        chain.push(connector((vfq.x, vfq.y), (pfq.x, pfq.y), F_CU, strand));
        chain.push(wave(
            WaveKind::Sine,
            1.0,
            quarter_via,
            three_quarter_via,
            F_CU,
            strand,
        ));
        chain.push(connector((pfm.x, pfm.y), (vfm.x, vfm.y), F_CU, strand));
        chain.push(connector((vfm.x, vfm.y), (pfm.x, pfm.y), B_CU, strand));

        if strand == 1 {
            let (p, v) = tangent_via(c, WaveKind::Sine, 1.0, end_swap, strand, -1.0);
            chain.push(wave(
                WaveKind::Sine,
                1.0,
                three_quarter_via,
                end_swap,
                B_CU,
                strand,
            ));
            chain.push(connector((p.x, p.y), (v.x, v.y), B_CU, strand));
            chain.push(connector((v.x, v.y), (p.x, p.y), F_CU, strand));
            chain.push(wave(WaveKind::Sine, 1.0, end_swap, handover, F_CU, strand));
        } else {
            chain.push(wave(
                WaveKind::Sine,
                1.0,
                three_quarter_via,
                handover,
                B_CU,
                strand,
            ));
        }

        if next == 1 {
            let (p, v) = tangent_via(c, WaveKind::Sine, -1.0, end_swap, next, 1.0);
            chain.push(wave(WaveKind::Sine, -1.0, handover, end_swap, B_CU, next));
            chain.push(connector((p.x, p.y), (v.x, v.y), B_CU, next));
            chain.push(connector((v.x, v.y), (p.x, p.y), F_CU, next));
            chain.push(wave(
                WaveKind::Sine,
                -1.0,
                end_swap,
                three_quarter_via,
                F_CU,
                next,
            ));
        } else {
            chain.push(wave(
                WaveKind::Sine,
                -1.0,
                handover,
                three_quarter_via,
                F_CU,
                next,
            ));
        }

        chain.push(connector((prm.x, prm.y), (vrm.x, vrm.y), F_CU, next));
        chain.push(connector((vrm.x, vrm.y), (prm.x, prm.y), B_CU, next));
        chain.push(wave(
            WaveKind::Sine,
            -1.0,
            three_quarter_via,
            quarter_via,
            B_CU,
            next,
        ));
        chain.push(connector((prq.x, prq.y), (vrq.x, vrq.y), B_CU, next));
        chain.push(connector((vrq.x, vrq.y), (prq.x, prq.y), F_CU, next));

        if next == 0 {
            let (p, v) = tangent_via(c, WaveKind::Sine, -1.0, begin_swap, next, -1.0);
            chain.push(wave(
                WaveKind::Sine,
                -1.0,
                quarter_via,
                begin_swap,
                F_CU,
                next,
            ));
            chain.push(connector((p.x, p.y), (v.x, v.y), F_CU, next));
            chain.push(connector((v.x, v.y), (p.x, p.y), B_CU, next));
            chain.push(wave(
                WaveKind::Sine,
                -1.0,
                begin_swap,
                lead_trim,
                B_CU,
                next,
            ));
            let p = leg_point(c, WaveKind::Sine, -1.0, lead_trim, next);
            chain.push(connector((p.x, p.y), (x0, -lead_y), B_CU, next));
            chain.push(connector((x0, -lead_y), (lead_x, -lead_y), B_CU, next));
        } else {
            chain.push(wave(
                WaveKind::Sine,
                -1.0,
                quarter_via,
                sine_start_junction(c, next),
                F_CU,
                next,
            ));
        }
    }
    Ok(chain)
}

fn make_cosine_elements(c: &SensorConfig) -> Result<Vec<Element>, String> {
    let mut chain = Vec::new();
    let lambda = c.lambda_mm;
    let x0 = c.x_start_mm;
    let end_swap = x0 + 31.0 * lambda / 32.0;
    let crossover_via = x0 + 9.0 * lambda / 16.0;
    let half_amplitude = c.amplitude_mm / 2.0;
    let apex_x = x0 + lambda + c.bulge_apex_offset_mm;
    let via_offset = c.via_size_mm / 2.0 + c.trace_width_mm / 2.0;
    let lead_x = x0 - c.chip_lead_in_mm;
    let lead_y = c.lead_y();

    if x0 + lambda / 2.0 >= end_swap {
        return Err("cosine re-layering occurs before the mid crossing".into());
    }
    for strand in 0..c.turns {
        let next = (strand + 1) % c.turns;
        let x_in = x0 + f64::from(strand) * c.dy();
        let x_out = x0 + lambda + f64::from(c.turns - 1 - strand) * c.dy();
        let x_in_next = x0 + f64::from(next) * c.dy();
        let x_out_next = x0 + lambda + f64::from(c.turns - 1 - next) * c.dy();
        if x_in >= x0 + lambda / 2.0 {
            return Err("cosine strand inset reaches the mid crossing".into());
        }
        if x_out <= end_swap {
            return Err("cosine end vertical is inside its re-layering".into());
        }

        let y_in = wave_y(c, WaveKind::Cosine, 1.0, x_in, strand);
        let y_out = wave_y(c, WaveKind::Cosine, 1.0, x_out, strand);
        let y_out_next = wave_y(c, WaveKind::Cosine, 1.0, x_out_next, next);
        if y_out <= half_amplitude {
            return Err("cosine end vertical stub does not clear the cut".into());
        }

        let (pf, vf) = tangent_via(
            c,
            WaveKind::Cosine,
            1.0,
            end_swap,
            strand,
            if strand == 0 { 1.0 } else { -1.0 },
        );
        let (pr, vr) = tangent_via(
            c,
            WaveKind::Cosine,
            -1.0,
            end_swap,
            next,
            if next == 0 { -1.0 } else { 1.0 },
        );
        let (pfh, vfh) = tangent_via(
            c,
            WaveKind::Cosine,
            1.0,
            crossover_via,
            strand,
            if strand == 0 { 1.0 } else { -1.0 },
        );
        let (prh, vrh) = tangent_via(
            c,
            WaveKind::Cosine,
            -1.0,
            crossover_via,
            next,
            if next == 0 { -1.0 } else { 1.0 },
        );

        if strand == 0 {
            if c.tx_enabled {
                let via_x = c.tx_lead_via_x();
                chain.push(connector(
                    (lead_x, c.tx_y_cont()),
                    (via_x, c.tx_y_cont()),
                    B_CU,
                    strand,
                ));
                chain.push(connector(
                    (via_x, c.tx_y_cont()),
                    (via_x, lead_y),
                    F_CU,
                    strand,
                ));
                chain.push(connector((via_x, lead_y), (x_in, lead_y), F_CU, strand));
                chain.push(connector((x_in, lead_y), (x_in, y_in), F_CU, strand));
            } else {
                chain.push(connector((lead_x, lead_y), (x_in, lead_y), F_CU, strand));
                chain.push(connector((x_in, lead_y), (x_in, y_in), F_CU, strand));
            }
        } else {
            let mid_via = (x_in + via_offset, -half_amplitude);
            chain.push(connector(
                (x_in, -y_in),
                (x_in, -half_amplitude),
                B_CU,
                strand,
            ));
            chain.push(connector((x_in, -half_amplitude), mid_via, B_CU, strand));
            chain.push(connector(mid_via, (x_in, -half_amplitude), F_CU, strand));
            chain.push(connector(
                (x_in, -half_amplitude),
                (x_in, y_in),
                F_CU,
                strand,
            ));
        }

        let bulge_layer = if strand % 2 == 0 { F_CU } else { B_CU };
        let mut handover = vec![connector(
            (x_out, y_out),
            (x_out, half_amplitude),
            F_CU,
            strand,
        )];
        if bulge_layer != F_CU {
            let via_top = (x_out - via_offset, half_amplitude);
            handover.push(connector((x_out, half_amplitude), via_top, F_CU, strand));
            handover.push(connector(
                via_top,
                (x_out, half_amplitude),
                bulge_layer,
                strand,
            ));
        }
        handover.push(bulge(
            (x_out, half_amplitude),
            (x_out_next, -half_amplitude),
            apex_x,
            bulge_layer,
            strand,
        ));
        if bulge_layer != B_CU {
            let via_bottom = (x_out_next - via_offset, -half_amplitude);
            handover.push(connector(
                (x_out_next, -half_amplitude),
                via_bottom,
                bulge_layer,
                strand,
            ));
            handover.push(connector(
                via_bottom,
                (x_out_next, -half_amplitude),
                B_CU,
                strand,
            ));
        }
        handover.push(connector(
            (x_out_next, -half_amplitude),
            (x_out_next, -y_out_next),
            B_CU,
            next,
        ));

        chain.push(wave(
            WaveKind::Cosine,
            1.0,
            x_in,
            crossover_via,
            F_CU,
            strand,
        ));
        chain.push(connector((pfh.x, pfh.y), (vfh.x, vfh.y), F_CU, strand));
        chain.push(connector((vfh.x, vfh.y), (pfh.x, pfh.y), B_CU, strand));
        chain.push(wave(
            WaveKind::Cosine,
            1.0,
            crossover_via,
            end_swap,
            B_CU,
            strand,
        ));
        chain.push(connector((pf.x, pf.y), (vf.x, vf.y), B_CU, strand));
        chain.push(connector((vf.x, vf.y), (pf.x, pf.y), F_CU, strand));
        chain.push(wave(WaveKind::Cosine, 1.0, end_swap, x_out, F_CU, strand));
        chain.extend(handover);

        chain.push(wave(
            WaveKind::Cosine,
            -1.0,
            x_out_next,
            end_swap,
            B_CU,
            next,
        ));
        chain.push(connector((pr.x, pr.y), (vr.x, vr.y), B_CU, next));
        chain.push(connector((vr.x, vr.y), (pr.x, pr.y), F_CU, next));
        chain.push(wave(
            WaveKind::Cosine,
            -1.0,
            end_swap,
            crossover_via,
            F_CU,
            next,
        ));
        chain.push(connector((prh.x, prh.y), (vrh.x, vrh.y), F_CU, next));
        chain.push(connector((vrh.x, vrh.y), (prh.x, prh.y), B_CU, next));
        chain.push(wave(
            WaveKind::Cosine,
            -1.0,
            crossover_via,
            x_in_next,
            B_CU,
            next,
        ));
    }

    let y_start = wave_y(c, WaveKind::Cosine, 1.0, x0, 0);
    chain.push(connector((x0, -y_start), (x0, -lead_y), B_CU, 0));
    Ok(chain)
}

fn element_endpoints(c: &SensorConfig, element: Element) -> (Point, Point, u32, u32) {
    match element {
        Element::Connector {
            start,
            end,
            layer,
            strand,
        }
        | Element::Bulge {
            start,
            end,
            layer,
            strand,
            ..
        } => (start, end, layer, strand),
        Element::Wave {
            kind,
            side,
            x_start,
            x_end,
            layer,
            strand,
        } => (
            leg_point(c, kind, side, x_start, strand),
            leg_point(c, kind, side, x_end, strand),
            layer,
            strand,
        ),
    }
}

fn wave_segments(
    c: &SensorConfig,
    kind: WaveKind,
    side: f64,
    x_start: f64,
    x_end: f64,
    strand: u32,
    first: Point,
    last: Point,
) -> Vec<(Point, Point)> {
    if x_start == x_end {
        return Vec::new();
    }
    let t_start = t_for_x(c, kind, x_start, strand);
    let t_end = t_for_x(c, kind, x_end, strand);
    let delta = t_end - t_start;
    let count = (delta.abs() / c.arc_step_mm).ceil().max(1.0) as usize;
    let mut points: Vec<Point> = (0..=count)
        .map(|i| {
            wave_point(
                c,
                kind,
                side,
                t_start + delta * i as f64 / count as f64,
                strand,
            )
        })
        .collect();
    // Canonicalize adjoining endpoints. This removes inversion roundoff and
    // makes the emitted polyline exactly contiguous at every chain junction.
    points[0] = first;
    points[count] = last;
    points.windows(2).map(|pair| (pair[0], pair[1])).collect()
}

fn bulge_segments(
    c: &SensorConfig,
    start: Point,
    end: Point,
    apex_x: f64,
) -> Result<Vec<(Point, Point)>, String> {
    if (start.x - end.x).abs() < 1e-9 && (start.y - end.y).abs() < 1e-9 {
        return Ok(Vec::new());
    }
    let (x1, y1, x2, y2) = (start.x, start.y, end.x, end.y);
    let (a1, b1) = (x2 - x1, y2 - y1);
    let c1 = 0.5 * (x2 * x2 + y2 * y2 - x1 * x1 - y1 * y1);
    let (a2, b2) = (2.0 * (apex_x - x1), -2.0 * y1);
    let c2 = apex_x * apex_x - x1 * x1 - y1 * y1;
    let determinant = a1 * b2 - a2 * b1;
    if determinant.abs() <= 1e-9 {
        return Err("bulge arc has degenerate circle conditions".into());
    }
    let cx = (c1 * b2 - c2 * b1) / determinant;
    let cy = (a1 * c2 - a2 * c1) / determinant;
    let radius = apex_x - cx;
    if radius <= 0.0 {
        return Err("bulge arc apex lies left of the circle center".into());
    }
    let angle_start = (y1 - cy).atan2(x1 - cx);
    let angle_end = (y2 - cy).atan2(x2 - cx);
    let tau = std::f64::consts::TAU;
    let ccw = (angle_end - angle_start).rem_euclid(tau);
    let apex_sweep = (0.0 - angle_start).rem_euclid(tau);
    let sweep = if apex_sweep < ccw {
        ccw
    } else {
        -((angle_start - angle_end).rem_euclid(tau))
    };
    let count = (sweep.abs() * radius / c.arc_step_mm).ceil().max(1.0) as usize;
    let mut points: Vec<Point> = (0..=count)
        .map(|i| {
            let angle = angle_start + sweep * i as f64 / count as f64;
            point(cx + radius * angle.cos(), cy + radius * angle.sin())
        })
        .collect();
    points[0] = start;
    points[count] = end;
    Ok(points.windows(2).map(|pair| (pair[0], pair[1])).collect())
}

fn same_point(a: Point, b: Point) -> bool {
    (a.x - b.x).abs() <= EPSILON && (a.y - b.y).abs() <= EPSILON
}

fn via_key(p: Point) -> (i64, i64) {
    (
        (p.x * 1_000_000.0).round() as i64,
        (p.y * 1_000_000.0).round() as i64,
    )
}

fn emit_chain(
    c: &SensorConfig,
    elements: &[Element],
    net: &str,
    is_active: bool,
) -> Result<(Vec<RouteSegment>, Vec<Via>), String> {
    let mut segments = Vec::new();
    let mut vias = Vec::new();
    let mut seen_vias = Vec::new();
    let mut previous: Option<(Point, u32, u32)> = None;

    for (index, element) in elements.iter().copied().enumerate() {
        let (mut start, end, layer, strand) = element_endpoints(c, element);
        if let Some((previous_end, previous_layer, _previous_strand)) = previous {
            if !same_point(start, previous_end) {
                return Err(format!(
                    "{net} chain is discontinuous before element {index}: ({:.9}, {:.9}) != ({:.9}, {:.9})",
                    start.x, start.y, previous_end.x, previous_end.y
                ));
            }
            // Use the previous element's endpoint as the exact shared node.
            start = previous_end;
            if layer != previous_layer {
                let key = via_key(start);
                if !seen_vias.contains(&key) {
                    seen_vias.push(key);
                    vias.push(Via {
                        position: start,
                        from_layer: previous_layer,
                        to_layer: layer,
                        net: net.to_string(),
                    });
                }
            }
        }

        let pieces = match element {
            Element::Connector { .. } => vec![(start, end)],
            Element::Wave {
                kind,
                side,
                x_start,
                x_end,
                strand,
                ..
            } => wave_segments(c, kind, side, x_start, x_end, strand, start, end),
            Element::Bulge { apex_x, .. } => bulge_segments(c, start, end, apex_x)?,
        };
        segments.extend(pieces.into_iter().map(|(start, end)| RouteSegment {
            start,
            end,
            layer,
            net: net.to_string(),
            is_active,
        }));
        previous = Some((end, layer, strand));
    }
    Ok((segments, vias))
}

fn generate_tx(c: &SensorConfig) -> (Vec<RouteSegment>, Vec<Via>, Vec<(String, Point)>) {
    let x1 = c.tx_x1();
    let x2 = c.tx_x2();
    let x3 = c.tx_x3();
    let xr = c.tx_xr();
    let xri = c.tx_xri();
    let lead_x = c.x_start_mm - c.chip_lead_in_mm;
    let y_out = c.tx_y_outer();
    let y_in = c.tx_y_inner();
    let y_l1 = c.tx_y_l1();
    let y_f = c.tx_y_f();
    let y_p1 = c.tx_y_p1();
    let y_u1 = c.tx_y_u1();
    let y_j2 = c.tx_y_j2();

    let tagged = [
        ((lead_x, y_p1), (x1, y_p1), F_CU),
        ((x1, y_p1), (x1, y_out), F_CU),
        ((x1, y_out), (xr, y_out), F_CU),
        ((xr, y_out), (xr, -y_out), F_CU),
        ((xr, -y_out), (x1, -y_out), F_CU),
        ((x1, -y_out), (x1, y_l1), F_CU),
        ((x1, y_l1), (x1, -y_out), B_CU),
        ((x1, -y_out), (xr, -y_out), B_CU),
        ((xr, -y_out), (xr, y_out), B_CU),
        ((xr, y_out), (x2, y_out), B_CU),
        ((x2, y_out), (x2, y_u1), B_CU),
        ((x2, y_u1), (x2, -y_in), F_CU),
        ((x2, -y_in), (xri, -y_in), F_CU),
        ((xri, -y_in), (xri, y_in), F_CU),
        ((xri, y_in), (x2, y_in), F_CU),
        ((x2, y_in), (x2, y_j2), F_CU),
        ((x2, y_j2), (x3, y_j2), B_CU),
        ((x3, y_j2), (x3, y_in), B_CU),
        ((x3, y_in), (xri, y_in), B_CU),
        ((xri, y_in), (xri, -y_in), B_CU),
        ((xri, -y_in), (x2, -y_in), B_CU),
        ((x2, -y_in), (x2, y_f), B_CU),
        ((x2, y_f), (lead_x, y_f), B_CU),
    ];
    let segments = tagged
        .into_iter()
        .map(|((x1, y1), (x2, y2), layer)| RouteSegment {
            start: point(x1, y1),
            end: point(x2, y2),
            layer,
            net: "OSC".into(),
            is_active: false,
        })
        .collect();
    let vias = [(x1, y_l1), (x2, y_u1), (x2, y_j2)]
        .into_iter()
        .map(|(x, y)| Via {
            position: point(x, y),
            from_layer: F_CU,
            to_layer: B_CU,
            net: "OSC".into(),
        })
        .collect();
    let terminals = vec![
        ("OSC".to_string(), point(lead_x, y_p1)),
        ("OSC".to_string(), point(lead_x, y_f)),
    ];
    (segments, vias, terminals)
}

/// Generate the cosine (CL1), sine (CL2), and optional transmitter (OSC).
pub fn generate_sensor(c: &SensorConfig) -> Result<SensorGeometry, String> {
    validate(c)?;
    let cosine = make_cosine_elements(c)?;
    let sine = make_sine_elements(c)?;
    let (cl1_segments, cl1_vias) = emit_chain(c, &cosine, "CL1", true)?;
    let (cl2_segments, cl2_vias) = emit_chain(c, &sine, "CL2", true)?;
    let mut nets = vec![
        SensorNetGeometry {
            name: "CL1".into(),
            segments: cl1_segments,
            vias: cl1_vias,
            trace_width_mm: c.trace_width_mm,
            via_size_mm: c.via_size_mm,
        },
        SensorNetGeometry {
            name: "CL2".into(),
            segments: cl2_segments,
            vias: cl2_vias,
            trace_width_mm: c.trace_width_mm,
            via_size_mm: c.via_size_mm,
        },
    ];
    let mut terminal_markers = Vec::new();
    if c.tx_enabled {
        let (segments, vias, terminals) = generate_tx(c);
        terminal_markers = terminals;
        nets.push(SensorNetGeometry {
            name: "OSC".into(),
            segments,
            vias,
            trace_width_mm: c.tx_trace_width_mm,
            via_size_mm: c.tx_via_size_mm,
        });
    }

    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for net in &nets {
        for segment in &net.segments {
            for p in [segment.start, segment.end] {
                bounds[0] = bounds[0].min(p.x);
                bounds[1] = bounds[1].min(p.y);
                bounds[2] = bounds[2].max(p.x);
                bounds[3] = bounds[3].max(p.y);
            }
        }
        for via in &net.vias {
            bounds[0] = bounds[0].min(via.position.x);
            bounds[1] = bounds[1].min(via.position.y);
            bounds[2] = bounds[2].max(via.position.x);
            bounds[3] = bounds[3].max(via.position.y);
        }
    }
    for (_, p) in &terminal_markers {
        bounds[0] = bounds[0].min(p.x);
        bounds[1] = bounds[1].min(p.y);
        bounds[2] = bounds[2].max(p.x);
        bounds[3] = bounds[3].max(p.y);
    }

    Ok(SensorGeometry {
        nets,
        terminal_markers,
        board_bounds_mm: bounds,
    })
}

fn validate(c: &SensorConfig) -> Result<(), String> {
    let positive = [
        ("wavelength", c.lambda_mm),
        ("amplitude", c.amplitude_mm),
        ("trace width", c.trace_width_mm),
        ("via size", c.via_size_mm),
        ("curve sampling step", c.arc_step_mm),
        ("chip lead-in", c.chip_lead_in_mm),
    ];
    for (name, value) in positive {
        if !value.is_finite() || value <= 0.0 {
            return Err(format!("Sensor {name} must be positive and finite"));
        }
    }
    if !c.x_start_mm.is_finite()
        || !c.trace_gap_mm.is_finite()
        || c.trace_gap_mm < 0.0
        || !c.min_clearance_mm.is_finite()
        || c.min_clearance_mm < 0.0
        || !c.end_inset_mm.is_finite()
        || c.end_inset_mm < 0.0
        || !c.bulge_apex_offset_mm.is_finite()
    {
        return Err("Sensor coordinates, gaps, and offsets must be finite and non-negative".into());
    }
    if c.turns == 0 || c.turns > 8 {
        return Err("Sensor turns must be between 1 and 8".into());
    }

    let max_offset = f64::from(c.turns - 1) * c.dy();
    let min_radius = c.lambda_mm.powi(2) / (4.0 * std::f64::consts::PI.powi(2) * c.amplitude_mm);
    if max_offset >= min_radius {
        return Err(format!(
            "Sensor turn offset ({max_offset:.3} mm) reaches the minimum wave curvature radius ({min_radius:.3} mm)"
        ));
    }
    if max_offset >= c.amplitude_mm {
        return Err("Sensor strand offset is too large for the sine axis crossing".into());
    }
    if c.lead_y() >= c.amplitude_mm {
        return Err("Sensor lead-in height is outside the sine wave range".into());
    }

    if c.tx_enabled {
        let tx_positive = [
            ("RX/TX gap", c.rx_tx_gap_mm),
            ("TX strand pitch", c.tx_strand_pitch_mm),
            ("TX trace width", c.tx_trace_width_mm),
            ("TX via size", c.tx_via_size_mm),
        ];
        for (name, value) in tx_positive {
            if !value.is_finite() || value <= 0.0 {
                return Err(format!("Sensor {name} must be positive and finite"));
            }
        }
        if !c.tx_corner_offset_mm.is_finite() || c.tx_corner_offset_mm <= 0.0 {
            return Err("TX corner offset must be positive and finite".into());
        }
        let offset = c.tx_via_offset();
        if c.rx_tx_gap_mm <= c.tx_strand_pitch_mm + offset {
            return Err("RX/TX gap is too small for the cosine lead-in via".into());
        }
        if c.rx_tx_gap_mm >= c.chip_lead_in_mm {
            return Err("RX/TX gap must stay below chip lead-in length".into());
        }
        if c.tx_y_u1() < c.tx_y_cont() + offset || c.tx_y_j2() < c.tx_y_cont() + offset {
            return Err("TX upper left-side vias do not clear the cosine lead-in".into());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_point_near(actual: Point, expected: Point) {
        assert!(
            (actual.x - expected.x).abs() < 1e-10,
            "x: {actual:?} != {expected:?}"
        );
        assert!(
            (actual.y - expected.y).abs() < 1e-10,
            "y: {actual:?} != {expected:?}"
        );
    }

    fn push_hash_value(hash: &mut u64, value: i64) {
        for byte in value.to_le_bytes() {
            *hash ^= u64::from(byte);
            *hash = hash.wrapping_mul(0x100000001b3);
        }
    }

    fn segment_hash(segments: &[RouteSegment]) -> u64 {
        let mut hash = 0xcbf29ce484222325;
        for segment in segments {
            for value in [
                segment.start.x,
                segment.start.y,
                segment.end.x,
                segment.end.y,
            ] {
                push_hash_value(&mut hash, (value * 1_000_000.0).round() as i64);
            }
            push_hash_value(&mut hash, i64::from(segment.layer));
        }
        hash
    }

    fn via_hash(vias: &[Via]) -> u64 {
        let mut hash = 0xcbf29ce484222325;
        for via in vias {
            for value in [via.position.x, via.position.y] {
                push_hash_value(&mut hash, (value * 1_000_000.0).round() as i64);
            }
        }
        hash
    }

    #[test]
    fn default_geometry_has_ordered_python_reference_counts() {
        let geometry = generate_sensor(&SensorConfig::default()).unwrap();
        assert_eq!(
            geometry
                .nets
                .iter()
                .map(|net| net.name.as_str())
                .collect::<Vec<_>>(),
            ["CL1", "CL2", "OSC"]
        );
        assert_eq!(geometry.nets[0].segments.len(), 2015);
        assert_eq!(geometry.nets[0].vias.len(), 12);
        assert_eq!(geometry.nets[1].segments.len(), 1945);
        assert_eq!(geometry.nets[1].vias.len(), 12);
        assert_eq!(geometry.nets[2].segments.len(), 23);
        assert_eq!(geometry.nets[2].vias.len(), 3);
        assert_eq!(geometry.terminal_markers.len(), 2);
    }

    #[test]
    fn every_receiver_chain_is_point_aligned_and_layer_changes_have_vias() {
        let geometry = generate_sensor(&SensorConfig::default()).unwrap();
        for net in &geometry.nets[..2] {
            for pair in net.segments.windows(2) {
                assert_eq!(pair[0].end, pair[1].start, "{} segment chain", net.name);
                if pair[0].layer != pair[1].layer {
                    assert!(net.vias.iter().any(|via| via.position == pair[0].end));
                }
            }
            assert!(net.segments.iter().all(|segment| segment.net == net.name));
            assert!(net.vias.iter().all(|via| via.net == net.name));
        }
    }

    #[test]
    fn default_geometry_matches_reference_terminals_and_tx_vias() {
        let geometry = generate_sensor(&SensorConfig::default()).unwrap();
        let cl1 = &geometry.nets[0];
        let cl2 = &geometry.nets[1];
        assert_point_near(cl1.segments[0].start, point(-10.0, 0.825));
        assert_point_near(cl2.segments[0].start, point(-10.0, 0.275));
        assert_point_near(cl2.segments.last().unwrap().end, point(-10.0, -0.275));
        for (via, expected) in geometry.nets[2].vias.iter().zip([
            point(-4.0, -0.85),
            point(-3.55, 1.4),
            point(-3.55, 1.95),
        ]) {
            assert_point_near(via.position, expected);
        }
    }

    #[test]
    fn default_geometry_matches_python_reference_coordinate_fingerprints() {
        let geometry = generate_sensor(&SensorConfig::default()).unwrap();
        // Fingerprints are generated from the Python prototype, rounding
        // coordinates to 1 um before hashing to ignore libm last-bit noise.
        assert_eq!(segment_hash(&geometry.nets[0].segments), 0x8ddb4ba52991ccc6);
        assert_eq!(via_hash(&geometry.nets[0].vias), 0x4f9274dfa19241b8);
        assert_eq!(segment_hash(&geometry.nets[1].segments), 0x58199ed5cc38b87e);
        assert_eq!(via_hash(&geometry.nets[1].vias), 0xce2415f56dddbbec);
        assert_eq!(segment_hash(&geometry.nets[2].segments), 0xc5ddd3f717ccfb40);
        assert_eq!(via_hash(&geometry.nets[2].vias), 0xf7a47817bc5c7a2f);
    }

    #[test]
    fn tx_can_be_disabled_without_changing_rx_dimension_contract() {
        let mut config = SensorConfig::default();
        config.tx_enabled = false;
        let geometry = generate_sensor(&config).unwrap();
        assert_eq!(geometry.nets.len(), 2);
        assert!(geometry.terminal_markers.is_empty());
    }

    #[test]
    fn one_and_three_turn_configurations_generate_contiguous_chains() {
        for turns in [1, 3] {
            let config = SensorConfig {
                turns,
                ..SensorConfig::default()
            };
            let geometry =
                generate_sensor(&config).unwrap_or_else(|error| panic!("{turns} turns: {error}"));
            for net in &geometry.nets[..2] {
                assert!(
                    net.segments
                        .windows(2)
                        .all(|pair| pair[0].end == pair[1].start),
                    "{} must remain an ordered chain for {turns} turns",
                    net.name
                );
            }
        }
    }

    #[test]
    fn rejects_offset_curve_self_intersection() {
        let mut config = SensorConfig::default();
        config.turns = 8;
        config.lambda_mm = 30.0;
        config.amplitude_mm = 8.0;
        assert!(generate_sensor(&config)
            .unwrap_err()
            .contains("curvature radius"));
    }
}
