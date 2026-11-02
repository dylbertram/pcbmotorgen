//! Non-mutating diagnostics for barrels with two inner-layer landings.
//! Same-phase copper elsewhere can bypass a winding pair, so net equality
//! alone must not suppress these clearance warnings.

use std::collections::BTreeSet;
use pcbmotorgen_routing::{Point, RoutingResult, Via};
use crate::{DesignRules, InterferenceViolation};

pub(crate) fn indices(r: &RoutingResult) -> Vec<usize> {
    r.vias.iter().enumerate().filter_map(|(i, v)| inner_pair(r, v).map(|_| i)).collect()
}

fn inner_pair(r: &RoutingResult, v: &Via) -> Option<(u32, u32)> {
    let (lo, hi) = (v.from_layer.min(v.to_layer), v.from_layer.max(v.to_layer));
    if hi - lo < 3 { return None; }
    let layers: BTreeSet<_> = r.segments.iter().filter(|s| s.net == v.net
            && s.layer > lo && s.layer < hi
            && (s.start.distance_to(v.position) < 1e-6 || s.end.distance_to(v.position) < 1e-6))
            .map(|s| s.layer).collect();
    if layers.len() != 2 { return None; }
    let (a, b) = (*layers.first().unwrap(), *layers.last().unwrap());
    (b == a + 1).then_some((a, b))
}

pub(crate) fn check(rules: &DesignRules, r: &RoutingResult, series: &[usize]) -> Vec<InterferenceViolation> {
    let mut warnings = Vec::new();
    let pad = rules.via_pad_diameter_mm();
    for &i in series {
        let via = &r.vias[i];
        let (tap_a, tap_b) = inner_pair(r, via).expect("classified series barrel");
        let (lo, hi) = (via.from_layer.min(via.to_layer), via.from_layer.max(via.to_layer));
        let runs = r.segments.iter().map(|s| (s.layer, &s.net, s.start, s.end))
            .chain(r.io_traces.iter().map(|s| (s.layer, &s.net, s.start, s.end)));
        for (layer, net, start, end) in runs {
            if !(lo..=hi).contains(&layer) { continue; }
            if *net == via.net && (layer == tap_a || layer == tap_b)
                && (start.distance_to(via.position) < 1e-6 || end.distance_to(via.position) < 1e-6) {
                continue; // Intended electrical contact, not a bypass warning.
            }
            let gap = distance(via.position, start, end) - pad / 2.0 - rules.trace_width_mm / 2.0;
            if gap + 1e-9 < rules.min_space_mm {
                warnings.push(InterferenceViolation {
                    layer, net_a: via.net.clone(), net_b: net.clone(), kind: "series_via_clearance", gap_mm: gap,
                    message: format!("Series via {i} on net {} has a {gap:.6} mm pad-to-trace edge gap on layer {layer}; minimum {:.6} mm. Review pad and trace sizes. Geometry is unchanged.", via.net, rules.min_space_mm),
                });
            }
        }
        for (j, other) in r.vias.iter().enumerate() {
            if i == j || (j < i && series.contains(&j)) { continue; }
            let (other_lo, other_hi) = (other.from_layer.min(other.to_layer), other.from_layer.max(other.to_layer));
            if other_hi < lo || other_lo > hi { continue; }
            let gap = via.position.distance_to(other.position) - pad;
            if gap + 1e-9 < rules.min_space_mm {
                warnings.push(InterferenceViolation {
                    layer: lo.max(other_lo), net_a: via.net.clone(), net_b: other.net.clone(),
                    kind: "series_via_pad_clearance", gap_mm: gap,
                    message: format!("Series via {i} on net {} to via {j} on net {} has a {gap:.6} mm pad edge gap; minimum {:.6} mm. Review pad sizes. Geometry is unchanged.", via.net, other.net, rules.min_space_mm),
                });
            }
        }
    }
    warnings
}

fn distance(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b.x - a.x, b.y - a.y);
    let length_squared = dx * dx + dy * dy;
    if length_squared == 0.0 { return p.distance_to(a); }
    let t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / length_squared).clamp(0.0, 1.0);
    p.distance_to(Point::new(a.x + t * dx, a.y + t * dy))
}

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::{RouteSegment, Via};

    #[test]
    fn reports_other_phase_inner_copper_same_phase_bypass_and_pad_gaps() {
        let via = Point::new(1.0, 1.0);
        let trace = |layer, net: &str, start, end| RouteSegment { layer, net: net.into(), start, end, is_active: false };
        let r = RoutingResult {
            segments: vec![trace(1, "A", via, Point::new(1.0, 2.0)), trace(2, "A", via, Point::new(1.0, 2.0)),
                trace(3, "A", Point::new(1.3, 0.5), Point::new(1.3, 1.5)),
                trace(1, "B", Point::new(1.45, 0.5), Point::new(1.45, 1.5))],
            vias: vec![Via { position: via, from_layer: 0, to_layer: 3, net: "A".into() },
                Via { position: Point::new(1.6, 1.0), from_layer: 0, to_layer: 1, net: "A".into() }],
            ..Default::default()
        };
        let before = r.clone();
        let rules = DesignRules { trace_width_mm: 0.2, min_via_drill_mm: 0.3, ..Default::default() };
        let warnings = check(&rules, &r, &indices(&r));
        assert_eq!(warnings.len(), 3);
        assert!(warnings.iter().any(|w| w.net_b == "A" && w.layer == 3 && (w.gap_mm + 0.05).abs() < 1e-9));
        assert!(warnings.iter().any(|w| w.net_b == "B" && w.layer == 1 && (w.gap_mm - 0.1).abs() < 1e-9));
        assert!(warnings.iter().any(|w| w.kind == "series_via_pad_clearance" && (w.gap_mm - 0.1).abs() < 1e-9));
        assert_eq!(r, before, "DFM must not mutate the drawn geometry");
        let mut bypass = r.clone();
        bypass.segments.push(trace(0, "A", via, Point::new(2.0, 1.0)));
        let warnings = check(&rules, &bypass, &indices(&bypass));
        assert!(warnings.iter().any(|w| w.kind == "series_via_clearance" && w.layer == 0
            && w.net_a == "A" && w.net_b == "A" && (w.gap_mm + 0.35).abs() < 1e-9),
            "an unintended outer-layer endpoint must not stop series classification and hide a bypass");
    }

    #[test]
    fn exact_generated_braid_warns_without_changing_geometry() {
      for matched in [0.0, 1.0] {
        for layers in [4, 6, 8] {
            let ctx = pcbmotorgen_routing::RoutingContext {
                active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: layers, phases: 3,
                min_trace_mm: 0.2, trace_width_mm: 0.2, min_space_mm: 0.127,
                via_pad_diameter_mm: Some(0.5), magnet_pitch_mm: Some(6.0),
                params: std::collections::HashMap::from([("num_strands".into(), 3.0), ("connection".into(), 2.0), ("pole_matched".into(), matched)]),
                ..Default::default()
            };
            let r = pcbmotorgen_routing::generate_routing_result(&ctx, "infinity-braid").unwrap();
            let before = r.clone();
            let rules = DesignRules { trace_width_mm: 0.2, min_via_drill_mm: 0.3, ..Default::default() };
            let warnings = crate::check_interference(&rules, &r);
            assert!(warnings.iter().any(|w| w.kind == "series_via_clearance" && (w.gap_mm - 0.0944444444).abs() < 1e-8));
            assert!(warnings.iter().any(|w| w.kind == "series_via_pad_clearance" && (w.gap_mm - 0.0555555556).abs() < 1e-8));
            assert_eq!(r, before);
        }
      }
    }

    #[test]
    fn exact_two_strand_fanout_reports_a_cross_phase_overlap() {
        let ctx = pcbmotorgen_routing::RoutingContext {
            active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: 4, phases: 3,
            min_trace_mm: 0.2, trace_width_mm: 0.2, min_space_mm: 0.127,
            via_pad_diameter_mm: Some(0.5), magnet_pitch_mm: Some(6.0),
            params: std::collections::HashMap::from([("num_strands".into(), 2.0), ("connection".into(), 2.0)]),
            ..Default::default()
        };
        let r = pcbmotorgen_routing::generate_routing_result(&ctx, "infinity-braid").unwrap();
        let rules = DesignRules { trace_width_mm: 0.2, min_via_drill_mm: 0.3, ..Default::default() };
        let warnings = crate::check_interference(&rules, &r);
        assert!(warnings.iter().any(|w| w.kind == "series_via_clearance" && w.layer == 3
            && w.net_a == "B" && w.net_b == "C" && (w.gap_mm + 0.35).abs() < 1e-8));
    }
}
