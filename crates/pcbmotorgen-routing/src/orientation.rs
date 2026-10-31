//! Host-side reflections, shared by every generated-copper consumer.

use serde::{Deserialize, Serialize};
use crate::{IoPadKind, PhaseBand, Point, RoutingDimensions, RoutingResult};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RoutingOrientation {
    pub mirror_x: bool,
    pub mirror_y: bool,
    pub reverse_layers: bool,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{generate_routing_report, RoutingContext, RouteSegment, RouteCurve, RouteSpline, Via};

    #[test]
    fn all_reflections_are_independent_involutions_and_keep_curve_direction_and_splines() {
        let original = RoutingResult {
            segments: vec![RouteSegment { start: Point::new(1., 2.), end: Point::new(9., 4.), layer: 0, net: "A".into(), is_active: true }],
            curves: vec![RouteCurve { start: Point::new(1., 2.), mid: Point::new(3., 4.), end: Point::new(5., 2.), layer: 1, net: "A".into(), is_active: false }],
            splines: vec![RouteSpline { degree: 1, knots: vec![0.,0.,1.,1.], control_points: vec![Point::new(1.,2.),Point::new(9.,4.)], weights: vec![], layer: 2, net: "B".into(), is_active: false }],
            vias: vec![Via { position: Point::new(1., 2.), from_layer: 0, to_layer: 3, net: "A".into() }],
            ..Default::default()
        };
        for mask in 0..8 {
            let flip = RoutingOrientation { mirror_x: mask & 1 != 0, mirror_y: mask & 2 != 0, reverse_layers: mask & 4 != 0 };
            let mut result = original.clone();
            flip.apply(&mut result, 10., 6., 4);
            assert_eq!(result.segments[0].start, Point::new(if flip.mirror_x {9.} else {1.}, if flip.mirror_y {4.} else {2.}));
            assert_eq!(result.segments[0].layer, if flip.reverse_layers {3} else {0});
            assert_eq!(result.vias[0].from_layer, if flip.reverse_layers {3} else {0});
            assert_eq!(result.vias[0].to_layer, if flip.reverse_layers {0} else {3});
            assert_eq!(result.splines[0].knots, original.splines[0].knots);
            flip.apply(&mut result, 10., 6., 4);
            assert_eq!(result, original);
        }
        assert_eq!(serde_json::from_str::<RoutingOrientation>("{}").unwrap(), RoutingOrientation::default());
    }

    #[test]
    fn all_native_braid_orientations_transform_geometry_and_dimension_sidecars_together() {
        for layers in [2,4,6,8] {
            let mut ctx = RoutingContext { active_area_length_mm: 100., board_width_mm: 10., num_layers: layers, phases: 3,
                min_trace_mm: 0.127, trace_width_mm: 0.127, min_space_mm: 0.127, magnet_pitch_mm: Some(6.),
                params: std::collections::HashMap::from([("num_strands".into(),3.),("connection".into(),2.)]), ..Default::default() };
            let original = generate_routing_report(&ctx,"infinity-braid").unwrap();
            for mask in 0..8 {
                ctx.orientation = RoutingOrientation { mirror_x: mask&1!=0, mirror_y: mask&2!=0, reverse_layers: mask&4!=0 };
                let actual = generate_routing_report(&ctx,"infinity-braid").unwrap();
                let mut expected = original.clone();
                ctx.orientation.apply(&mut expected.result,100.,10.,layers);
                ctx.orientation.dimensions(&mut expected.dimensions,layers);
                assert_eq!(actual, expected);
                assert_eq!(actual.dimensions.pole_regions,actual.result.pole_regions);
                for (old,new) in original.result.segments.iter().zip(&actual.result.segments) {
                    assert!((old.start.distance_to(old.end)-new.start.distance_to(new.end)).abs()<1e-10);
                    assert_eq!(old.net,new.net); assert_eq!(old.is_active,new.is_active);
                }
            }
        }
    }
}

impl RoutingOrientation {
    pub fn point(self, point: &mut Point, length: f64, width: f64) {
        if self.mirror_x { point.x = length - point.x; }
        if self.mirror_y { point.y = width - point.y; }
    }

    pub fn layer(self, layer: u32, count: u32) -> u32 {
        if self.reverse_layers { count - 1 - layer } else { layer }
    }

    fn band(self, band: &mut PhaseBand, length: f64, width: f64, layers: u32) {
        band.layer = self.layer(band.layer, layers);
        if self.mirror_x {
            band.centerline_x_mm = length - band.centerline_x_mm;
            (band.start_x_mm, band.end_x_mm) = (length - band.end_x_mm, length - band.start_x_mm);
        }
        if self.mirror_y {
            (band.y_min_mm, band.y_max_mm) = (width - band.y_max_mm, width - band.y_min_mm);
        }
    }

    pub fn apply(self, result: &mut RoutingResult, length: f64, width: f64, layers: u32) {
        for segment in &mut result.segments {
            self.point(&mut segment.start, length, width);
            self.point(&mut segment.end, length, width);
            segment.layer = self.layer(segment.layer, layers);
        }
        for curve in &mut result.curves {
            self.point(&mut curve.start, length, width);
            self.point(&mut curve.mid, length, width);
            self.point(&mut curve.end, length, width);
            curve.layer = self.layer(curve.layer, layers);
        }
        for spline in &mut result.splines {
            for point in &mut spline.control_points { self.point(point, length, width); }
            spline.layer = self.layer(spline.layer, layers);
        }
        for via in &mut result.vias {
            self.point(&mut via.position, length, width);
            via.from_layer = self.layer(via.from_layer, layers);
            via.to_layer = self.layer(via.to_layer, layers);
        }
        for region in &mut result.pole_regions {
            self.point(&mut region.start, length, width);
            self.point(&mut region.end, length, width);
        }
        for band in &mut result.phase_bands { self.band(band, length, width, layers); }
        for pad in &mut result.io_pads {
            self.point(&mut pad.position, length, width);
            if self.reverse_layers && pad.layers.is_empty() && pad.kind != IoPadKind::Tht {
                pad.layers.push(layers - 1);
            } else {
                for layer in &mut pad.layers { *layer = self.layer(*layer, layers); }
            }
        }
        for trace in &mut result.io_traces {
            self.point(&mut trace.start, length, width);
            self.point(&mut trace.end, length, width);
            trace.layer = self.layer(trace.layer, layers);
        }
    }

    pub fn dimensions(self, dimensions: &mut RoutingDimensions, layers: u32) {
        let length = dimensions.total_routing_length_mm;
        let width = dimensions.board_width_mm;
        for band in &mut dimensions.phase_band_widths { band.layer = self.layer(band.layer, layers); }
        for band in &mut dimensions.phase_bands { self.band(&mut band.band, length, width, layers); }
        for region in &mut dimensions.pole_regions {
            self.point(&mut region.start, length, width);
            self.point(&mut region.end, length, width);
        }
    }
}
