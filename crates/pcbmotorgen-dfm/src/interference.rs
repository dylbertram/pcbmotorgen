//! Design-rule (DRC) interference checks on generated routing geometry.
//!
//! The routing pattern emits only raw geometry (line endpoints + layer + net,
//! via positions + from/to layers). Trace width and via pad size are owned by
//! the DFM crate via [`DesignRules`](crate::rules::DesignRules) (see the crate
//! division, kata 0rgs). This module verifies copper-to-copper clearance and
//! via-pad-to-trace clearance against those rules. These are *diagnostics* —
//! they are reported, not used to silently alter geometry.
//!
//! IO routing participates like any other copper (kata xa0f): the
//! `io_traces[]` fanout traces join the same-layer clearance checks (against
//! pattern segments and each other, and as via-pad clearance targets), and
//! `io_pads[]` are checked against different-net copper on the layers they
//! declare (`io_pads[i].layers`; a pad relying on the exporter's implicit
//! default layer set cannot be layer-resolved here and is skipped — the host
//! IO generator always declares its layers explicitly).

use std::collections::BTreeMap;

use crate::rules::DesignRules;
use pcbmotorgen_routing::io::IoPad;
use pcbmotorgen_routing::model::{Point, RouteSegment, RoutingResult};

/// One DRC violation.
#[derive(Debug, Clone)]
pub struct InterferenceViolation {
    pub layer: u32,
    pub net_a: String,
    pub net_b: String,
    pub kind: &'static str,
    pub gap_mm: f64,
    pub message: String,
}

/// A same-layer copper run to clearance-check: a routing segment or an IO
/// fanout trace. `label` renders into violation messages (`3` for
/// `segments[3]`, `io_traces[2]` for IO traces).
struct CopperRun<'a> {
    label: String,
    start: Point,
    end: Point,
    net: &'a str,
}

impl<'a> CopperRun<'a> {
    fn seg(s: &'a RouteSegment, index: usize) -> Self {
        Self {
            label: index.to_string(),
            start: s.start,
            end: s.end,
            net: &s.net,
        }
    }

    fn io(t: &'a pcbmotorgen_routing::io::IoTrace, index: usize) -> Self {
        Self {
            label: format!("io_traces[{index}]"),
            start: t.start,
            end: t.end,
            net: &t.net,
        }
    }
}

/// Run design-rule (interference) checks on a validated [`RoutingResult`]
/// using the supplied DFM rules.
///
/// Checks:
/// - Same-layer, different-net segment segments closer than
///   `min_trace + min_space` (edge-to-edge clearance).
/// - Same-layer, different-net IO fanout traces vs segments / other IO traces
///   at the same clearance (IO routing is ordinary copper for DRC purposes,
///   kata xa0f).
/// - Via pad (drill + 2×annular) to different-net traces (segments and IO
///   traces) on the via's from/to layers closer than
///   `via_pad_radius + trace_width/2 + min_space`.
/// - IO pads (on each explicitly declared copper layer) closer than
///   `pad_radius + trace_width/2 + min_space` to different-net copper, or
///   closer than `pad_radius_a + pad_radius_b + min_space` to a different-net
///   IO pad sharing a declared layer. The effective pad radius is the half
///   diagonal of the pad copper (exact for circular pads, conservative for
///   rectangular ones). Pads without declared layers are skipped.
///
/// Bounded at 200k pair checks to avoid runaway on pathological inputs.
pub fn check_interference(
    rules: &DesignRules,
    result: &RoutingResult,
) -> Vec<InterferenceViolation> {
    let mut violations = Vec::new();

    let trace_width = rules.min_trace_mm;
    let min_space = rules.min_space_mm;
    let via_pad_radius = rules.via_pad_radius_mm();

    // Copper pitch: center-to-center distance at which two same-layer,
    // different-net traces just touch (edge-to-edge clearance = min_space).
    let copper_pitch = trace_width + min_space;

    // --- Same-layer, different-net segment clearance ---
    // Group segments by layer, then compare different-net pairs.
    let mut by_layer: BTreeMap<u32, Vec<(usize, &RouteSegment)>> = BTreeMap::new();
    for (i, s) in result.segments.iter().enumerate() {
        by_layer.entry(s.layer).or_default().push((i, s));
    }
    let mut pair_checks = 0usize;
    for (layer, segs) in &by_layer {
        for a in 0..segs.len() {
            for b in a + 1..segs.len() {
                if pair_checks > 200_000 {
                    break;
                }
                pair_checks += 1;
                let (ia, sa) = segs[a];
                let (ib, sb) = segs[b];
                if sa.net == sb.net {
                    continue;
                }
                let d = seg_seg_distance(sa, sb);
                if d < copper_pitch * 0.999 {
                    violations.push(InterferenceViolation {
                        layer: *layer,
                        net_a: sa.net.clone(),
                        net_b: sb.net.clone(),
                        kind: "clearance",
                        gap_mm: d,
                        message: format!(
                            "segments {} (net {}) and {} (net {}) on layer {} are {:.3} mm apart — below copper clearance {:.3} mm",
                            ia, sa.net, ib, sb.net, layer, d, min_space
                        ),
                    });
                }
            }
        }
    }

    // Group ALL copper runs (segments + IO fanout traces) by layer for the
    // IO-involving and pad checks below.
    let mut runs_by_layer: BTreeMap<u32, Vec<CopperRun>> = BTreeMap::new();
    for (layer, segs) in &by_layer {
        for (i, s) in segs.iter() {
            runs_by_layer.entry(*layer).or_default().push(CopperRun::seg(s, *i));
        }
    }
    for (i, t) in result.io_traces.iter().enumerate() {
        runs_by_layer.entry(t.layer).or_default().push(CopperRun::io(t, i));
    }

    // --- IO fanout trace clearance (vs segments and other IO traces) ---
    let mut io_pair_checks = 0usize;
    for (layer, runs) in &runs_by_layer {
        for a in 0..runs.len() {
            let run_a = &runs[a];
            if !run_a.label.starts_with("io_traces") {
                continue;
            }
            for b in 0..runs.len() {
                if b == a || io_pair_checks > 200_000 {
                    continue;
                }
                let run_b = &runs[b];
                // Report each IO pair once (a < b by label order), and skip
                // segment↔segment pairs already covered by the loop above.
                if run_b.label.starts_with("io_traces") && run_a.label >= run_b.label {
                    continue;
                }
                io_pair_checks += 1;
                if run_a.net == run_b.net {
                    continue;
                }
                let seg_a = RouteSegment {
                    start: run_a.start,
                    end: run_a.end,
                    layer: *layer,
                    net: run_a.net.to_string(),
                    is_active: false,
                };
                let seg_b = RouteSegment {
                    start: run_b.start,
                    end: run_b.end,
                    layer: *layer,
                    net: run_b.net.to_string(),
                    is_active: false,
                };
                let d = seg_seg_distance(&seg_a, &seg_b);
                if d < copper_pitch * 0.999 {
                    violations.push(InterferenceViolation {
                        layer: *layer,
                        net_a: run_a.net.to_string(),
                        net_b: run_b.net.to_string(),
                        kind: "clearance",
                        gap_mm: d,
                        message: format!(
                            "IO trace {} (net {}) and {} (net {}) on layer {} are {:.3} mm apart — below copper clearance {:.3} mm",
                            run_a.label, run_a.net, run_b.label, run_b.net, layer, d, min_space
                        ),
                    });
                }
            }
        }
    }

    // --- Via-pad to different-net trace clearance on from/to layers ---
    let via_min_distance = via_pad_radius + trace_width / 2.0 + min_space;
    for (vi, v) in result.vias.iter().enumerate() {
        for (layer, runs) in &runs_by_layer {
            if *layer != v.from_layer && *layer != v.to_layer {
                continue;
            }
            for run in runs {
                if run.net == v.net {
                    continue;
                }
                let seg = RouteSegment {
                    start: run.start,
                    end: run.end,
                    layer: *layer,
                    net: run.net.to_string(),
                    is_active: false,
                };
                let d = point_seg_distance(v.position, &seg);
                if d < via_min_distance * 0.999 {
                    violations.push(InterferenceViolation {
                        layer: *layer,
                        net_a: v.net.clone(),
                        net_b: run.net.to_string(),
                        kind: "via_clearance",
                        gap_mm: d,
                        message: format!(
                            "via {} (net {}) pad is only {:.3} mm from {} (net {}) on layer {} — below required pad clearance {:.3} mm",
                            vi, v.net, d, run.label, run.net, layer, via_min_distance
                        ),
                    });
                }
            }
        }
    }

    // --- IO pad clearance on the layers the pads declare ---
    check_io_pad_clearance(rules, result, &runs_by_layer, &mut violations);

    violations
}

/// Effective IO pad copper radius [mm]: the half diagonal of the declared pad
/// copper — exact for circular pads (`x == y`), conservative for rectangles.
fn io_pad_radius_mm(pad: &IoPad) -> f64 {
    ((pad.size.x / 2.0).powi(2) + (pad.size.y / 2.0).powi(2)).sqrt()
}

fn check_io_pad_clearance(
    rules: &DesignRules,
    result: &RoutingResult,
    runs_by_layer: &BTreeMap<u32, Vec<CopperRun>>,
    violations: &mut Vec<InterferenceViolation>,
) {
    let trace_width = rules.min_trace_mm;
    let min_space = rules.min_space_mm;

    // Pad ↔ copper: pad centre to a different-net trace on a declared layer.
    for (pi, pad) in result.io_pads.iter().enumerate() {
        let pad_radius = io_pad_radius_mm(pad);
        let pad_min_distance = pad_radius + trace_width / 2.0 + min_space;
        for &layer in &pad.layers {
            let Some(runs) = runs_by_layer.get(&layer) else {
                continue;
            };
            for run in runs {
                if run.net == pad.net {
                    continue;
                }
                let seg = RouteSegment {
                    start: run.start,
                    end: run.end,
                    layer,
                    net: run.net.to_string(),
                    is_active: false,
                };
                let d = point_seg_distance(pad.position, &seg);
                if d < pad_min_distance * 0.999 {
                    violations.push(InterferenceViolation {
                        layer,
                        net_a: pad.net.clone(),
                        net_b: run.net.to_string(),
                        kind: "io_pad_clearance",
                        gap_mm: d,
                        message: format!(
                            "io_pads[{}] (net {}) copper is only {:.3} mm from {} (net {}) on layer {} — below required pad clearance {:.3} mm",
                            pi, pad.net, d, run.label, run.net, layer, pad_min_distance
                        ),
                    });
                }
            }
        }
    }

    // Pad ↔ pad: different-net pads sharing a declared layer.
    for a in 0..result.io_pads.len() {
        let (pa, ra) = (&result.io_pads[a], io_pad_radius_mm(&result.io_pads[a]));
        for b in a + 1..result.io_pads.len() {
            let (pb, rb) = (&result.io_pads[b], io_pad_radius_mm(&result.io_pads[b]));
            if pa.net == pb.net {
                continue;
            }
            let shared = pa.layers.iter().any(|l| pb.layers.contains(l));
            if !shared {
                continue;
            }
            let d = pa.position.distance_to(pb.position);
            if d < (ra + rb + min_space) * 0.999 {
                violations.push(InterferenceViolation {
                    layer: pa.layers.iter().find(|l| pb.layers.contains(l)).copied().unwrap_or(0),
                    net_a: pa.net.clone(),
                    net_b: pb.net.clone(),
                    kind: "io_pad_clearance",
                    gap_mm: d,
                    message: format!(
                        "io_pads[{a}] (net {}) and io_pads[{b}] (net {}) are {:.3} mm apart on a shared copper layer — below required pad-to-pad clearance {:.3} mm",
                        pa.net, pb.net, d, ra + rb + min_space
                    ),
                });
            }
        }
    }
}

fn point_seg_distance(p: Point, s: &RouteSegment) -> f64 {
    let (px, py) = (p.x, p.y);
    let (ax, ay) = (s.start.x, s.start.y);
    let (bx, by) = (s.end.x, s.end.y);
    let abx = bx - ax;
    let aby = by - ay;
    let denom = abx * abx + aby * aby;
    if denom <= 1e-12 {
        return ((px - ax).powi(2) + (py - ay).powi(2)).sqrt();
    }
    let t = (((px - ax) * abx + (py - ay) * aby) / denom).clamp(0.0, 1.0);
    let cx = ax + t * abx;
    let cy = ay + t * aby;
    ((px - cx).powi(2) + (py - cy).powi(2)).sqrt()
}

/// Minimum distance between two line segments (2D).
fn seg_seg_distance(a: &RouteSegment, b: &RouteSegment) -> f64 {
    let mut d = f64::INFINITY;
    // Endpoints of a to b, and of b to a.
    for &(p, q) in [
        (a.start, b),
        (a.end, b),
        (b.start, a),
        (b.end, a),
    ]
    .iter()
    {
        d = d.min(point_seg_distance(p, q));
    }
    // Intersection (distance 0) check.
    if segments_intersect(a, b) {
        return 0.0;
    }
    d
}

fn segments_intersect(a: &RouteSegment, b: &RouteSegment) -> bool {
    fn ccw(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> f64 {
        (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    }
    let (ax1, ay1, ax2, ay2) = (a.start.x, a.start.y, a.end.x, a.end.y);
    let (bx1, by1, bx2, by2) = (b.start.x, b.start.y, b.end.x, b.end.y);
    let d1 = ccw(bx1, by1, bx2, by2, ax1, ay1);
    let d2 = ccw(bx1, by1, bx2, by2, ax2, ay2);
    let d3 = ccw(ax1, ay1, ax2, ay2, bx1, by1);
    let d4 = ccw(ax1, ay1, ax2, ay2, bx2, by2);
    (d1 * d2) < 0.0 && (d3 * d4) < 0.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::model::Via;

    fn rules() -> DesignRules {
        DesignRules {
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.1,
        }
    }

    fn seg(x1: f64, y1: f64, x2: f64, y2: f64, layer: u32, net: &str) -> RouteSegment {
        RouteSegment {
            start: Point::new(x1, y1),
            end: Point::new(x2, y2),
            layer,
            net: net.to_string(),
            is_active: true,
        }
    }

    fn result(segments: Vec<RouteSegment>, vias: Vec<Via>) -> RoutingResult {
        RoutingResult {
            format_version: pcbmotorgen_routing::model::FORMAT_VERSION,
            segments,
            vias,
            io_pads: Vec::new(),
            io_traces: Vec::new(),
            ..RoutingResult::default()
        }
    }

    #[test]
    fn clear_different_net_segments_pass() {
        // 1 mm apart vertically; copper pitch = 0.2 mm → no violation.
        let r = result(
            vec![
                seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
                seg(0.0, 1.0, 10.0, 1.0, 0, "B"),
            ],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn too_close_different_net_segments_violate() {
        // 0.05 mm apart; below copper pitch (0.2) → clearance violation.
        let r = result(
            vec![
                seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
                seg(0.0, 0.05, 10.0, 0.05, 0, "B"),
            ],
            Vec::new(),
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "clearance");
        assert_eq!(v[0].net_a, "A");
        assert_eq!(v[0].net_b, "B");
        assert_eq!(v[0].layer, 0);
    }

    #[test]
    fn same_net_segments_never_violate() {
        let r = result(
            vec![
                seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
                seg(0.0, 0.05, 10.0, 0.05, 0, "A"),
            ],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn different_layers_are_independent() {
        let r = result(
            vec![
                seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
                seg(0.0, 0.05, 10.0, 0.05, 1, "B"),
            ],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn crossing_segments_report_zero_gap() {
        let r = result(
            vec![
                seg(0.0, 0.0, 10.0, 10.0, 0, "A"),
                seg(0.0, 10.0, 10.0, 0.0, 0, "B"),
            ],
            Vec::new(),
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "clearance");
        assert_eq!(v[0].gap_mm, 0.0);
    }

    #[test]
    fn via_pad_near_different_net_trace_violates() {
        // Via pad radius 0.2, trace half width 0.05, space 0.1 → required
        // pad-to-trace-centre distance 0.35 mm. The via sits 0.1 mm from the
        // B trace centre → violation.
        let r = result(
            vec![seg(0.0, 1.0, 10.0, 1.0, 0, "B")],
            vec![Via {
                position: Point::new(5.0, 0.9),
                from_layer: 0,
                to_layer: 1,
                net: "A".to_string(),
            }],
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "via_clearance");
        assert_eq!(v[0].net_a, "A");
        assert_eq!(v[0].net_b, "B");
    }

    #[test]
    fn via_pad_on_same_net_never_violates() {
        let r = result(
            vec![seg(0.0, 1.0, 10.0, 1.0, 0, "A")],
            vec![Via {
                position: Point::new(5.0, 1.0),
                from_layer: 0,
                to_layer: 1,
                net: "A".to_string(),
            }],
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn via_checked_only_on_from_to_layers() {
        // Segment on layer 2 only; via spans layers 0↔1 → not compared.
        let r = result(
            vec![seg(0.0, 1.0, 10.0, 1.0, 2, "B")],
            vec![Via {
                position: Point::new(5.0, 0.9),
                from_layer: 0,
                to_layer: 1,
                net: "A".to_string(),
            }],
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    // --- IO coverage (kata xa0f) -------------------------------------------

    use pcbmotorgen_routing::{IoPad, IoPadKind, IoTrace, IoTraceRole, PadSize};

    fn io_trace(x1: f64, y1: f64, x2: f64, y2: f64, layer: u32, net: &str) -> IoTrace {
        IoTrace {
            start: Point::new(x1, y1),
            end: Point::new(x2, y2),
            layer,
            net: net.to_string(),
            role: IoTraceRole::Fanout,
        }
    }

    fn io_pad(x: f64, y: f64, d: f64, layer: u32, net: &str) -> IoPad {
        IoPad {
            position: Point::new(x, y),
            size: PadSize { x: d, y: d },
            drill_mm: Some(0.2),
            layers: vec![layer],
            kind: IoPadKind::Tht,
            net: net.to_string(),
            number: None,
        }
    }

    fn result_with_io(
        segments: Vec<RouteSegment>,
        vias: Vec<Via>,
        io_pads: Vec<IoPad>,
        io_traces: Vec<IoTrace>,
    ) -> RoutingResult {
        RoutingResult {
            format_version: pcbmotorgen_routing::model::FORMAT_VERSION,
            segments,
            vias,
            io_pads,
            io_traces,
            ..RoutingResult::default()
        }
    }

    #[test]
    fn io_trace_too_close_to_different_net_segment_violates() {
        // IO fanout 0.05 mm from a segment — below the 0.2 mm copper pitch.
        let r = result_with_io(
            vec![seg(0.0, 0.0, 10.0, 0.0, 0, "A")],
            Vec::new(),
            Vec::new(),
            vec![io_trace(0.0, 0.05, 10.0, 0.05, 0, "B")],
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "clearance");
        // The IO trace leads the pair it participates in.
        assert_eq!(v[0].net_a, "B");
        assert_eq!(v[0].net_b, "A");
        assert!(v[0].message.contains("io_traces[0]"), "{}", v[0].message);
    }

    #[test]
    fn io_traces_too_close_to_each_other_violate_once() {
        let r = result_with_io(
            Vec::new(),
            Vec::new(),
            Vec::new(),
            vec![
                io_trace(0.0, 0.0, 10.0, 0.0, 0, "A"),
                io_trace(0.0, 0.05, 10.0, 0.05, 0, "B"),
            ],
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1, "each IO pair reports exactly once");
        assert_eq!(v[0].kind, "clearance");
    }

    #[test]
    fn io_trace_same_net_or_far_apart_is_clear() {
        let r = result_with_io(
            Vec::new(),
            Vec::new(),
            Vec::new(),
            vec![
                io_trace(0.0, 0.0, 10.0, 0.0, 0, "A"),
                io_trace(0.0, 0.05, 10.0, 0.05, 0, "A"),
                io_trace(0.0, 1.0, 10.0, 1.0, 0, "B"),
                io_trace(0.0, 0.05, 10.0, 0.05, 1, "C"),
            ],
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn via_pad_near_different_net_io_trace_violates() {
        // Required via-pad distance 0.35 mm; the via sits 0.1 mm from the IO
        // trace centre.
        let r = result_with_io(
            Vec::new(),
            vec![Via {
                position: Point::new(5.0, 0.9),
                from_layer: 0,
                to_layer: 1,
                net: "A".to_string(),
            }],
            Vec::new(),
            vec![io_trace(0.0, 1.0, 10.0, 1.0, 0, "B")],
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "via_clearance");
        assert_eq!(v[0].net_b, "B");
    }

    #[test]
    fn io_pad_near_different_net_trace_violates() {
        // Pad radius 0.3, trace half width 0.05, space 0.1 → required 0.45 mm.
        // The pad centre sits 0.2 mm from the B trace → violation.
        let r = result_with_io(
            vec![seg(0.0, 1.0, 10.0, 1.0, 0, "B")],
            Vec::new(),
            vec![io_pad(5.0, 1.2, 0.6, 0, "A")],
            Vec::new(),
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "io_pad_clearance");
        assert_eq!(v[0].net_a, "A");
        assert_eq!(v[0].net_b, "B");
        assert_eq!(v[0].layer, 0);
    }

    #[test]
    fn io_pad_checks_only_declared_layers() {
        // Pad declares layer 1 only; the offending segment is on layer 0 →
        // no violation (the pad's copper is not on layer 0).
        let r = result_with_io(
            vec![seg(0.0, 1.0, 10.0, 1.0, 0, "B")],
            Vec::new(),
            vec![io_pad(5.0, 1.2, 0.6, 1, "A")],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn io_pad_without_declared_layers_is_skipped() {
        // A pad relying on the exporter's implicit default layer set cannot
        // be layer-resolved by the DFM crate — it is skipped, not guessed.
        let mut pad = io_pad(5.0, 1.2, 0.6, 0, "A");
        pad.layers = Vec::new();
        let r = result_with_io(
            vec![seg(0.0, 1.0, 10.0, 1.0, 0, "B")],
            Vec::new(),
            vec![pad],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn io_pads_on_different_nets_too_close_violate() {
        // Effective pad radius = half diagonal = 0.3·√2 ≈ 0.424 mm → required
        // pad-to-pad clearance 0.948 mm; the pads sit 0.8 mm apart → violation.
        let r = result_with_io(
            Vec::new(),
            Vec::new(),
            vec![
                io_pad(5.0, 1.0, 0.6, 0, "A"),
                io_pad(5.8, 1.0, 0.6, 0, "B"),
            ],
            Vec::new(),
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "io_pad_clearance");
        assert_eq!(v[0].net_a, "A");
        assert_eq!(v[0].net_b, "B");
    }

    #[test]
    fn io_pads_same_net_or_far_apart_or_other_layers_are_clear() {
        let r = result_with_io(
            Vec::new(),
            Vec::new(),
            vec![
                io_pad(5.0, 1.0, 0.6, 0, "A"),
                io_pad(6.0, 1.0, 0.6, 0, "A"),   // same net
                io_pad(20.0, 1.0, 0.6, 0, "B"),  // far away
                io_pad(6.0, 1.0, 0.6, 1, "C"),   // other layer
            ],
            Vec::new(),
        );
        assert!(check_interference(&rules(), &r).is_empty());
    }

    #[test]
    fn io_pad_colliding_with_io_trace_violates() {
        // Pad radius 0.3 → required pad-to-trace-centre distance 0.45 mm; the
        // IO trace passes 0.1 mm from the pad centre.
        let r = result_with_io(
            Vec::new(),
            Vec::new(),
            vec![io_pad(5.0, 1.1, 0.6, 0, "A")],
            vec![io_trace(0.0, 1.0, 10.0, 1.0, 0, "B")],
        );
        let v = check_interference(&rules(), &r);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, "io_pad_clearance");
    }
}
