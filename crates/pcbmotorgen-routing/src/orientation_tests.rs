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
