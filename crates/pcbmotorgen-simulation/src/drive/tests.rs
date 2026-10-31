use super::*;
use pcbmotorgen_routing::{
    generate_routing_result, Point, RouteSegment, RoutingContext, RoutingResult, Via,
};

#[test]
fn compact_braid_simulated_terminal_axes_are_diagnostic_not_a_spacing_target() {
    use crate::magnetic::{CommutationMode, ForceEvaluator};
    let period = 0.012;
    for strands in [2, 3, 5] {
        let ctx = RoutingContext {
            active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: 2, phases: 3,
            min_trace_mm: 0.127, trace_width_mm: 0.2, min_space_mm: 0.127,
            params: std::collections::HashMap::from([("num_strands".into(), strands as f64), ("connection".into(), 2.0)]),
            magnet_pitch_mm: Some(6.0), magnet_array_span_mm: Some(29.0), ..Default::default()
        };
        let routing = generate_routing_result(&ctx, "infinity-braid").unwrap();
        let sim = SimulationInput { active_area_length_m: 0.092, board_width_m: 0.008,
            magnet_dims_m: [0.005, 0.005, 0.003], magnet_count: 5, magnet_pitch_m: 0.006,
            min_trace_m: 0.0002, num_layers: 2, air_gap_m: 0.0005, ..Default::default() };
        let (evaluator, _) = ForceEvaluator::new(2, 8, CommutationMode::MaxThrust, 0.0)
            .with_routed_currents(&routing, &sim, &DriveSettings::default(), &Default::default()).unwrap();
        let mut sine = [0.0; 3];
        let mut cosine = [0.0; 3];
        for n in 0..48 {
            let x = 0.018 + period * n as f64 / 48.0;
            let theta = std::f64::consts::TAU * x / period;
            let force = evaluator.unit_phase_force_constants_at(&sim, x).unwrap();
            for j in 0..3 { sine[j] += force[j] * theta.sin(); cosine[j] += force[j] * theta.cos(); }
        }
        let angles: [f64; 3] = std::array::from_fn(|j| cosine[j].atan2(sine[j]));
        for j in 1..3 {
            // Preserve the observed signed-terminal convention without moving
            // copper to force 120°. Polarity/controller applicability is open.
            let error = angles[j] - angles[0] + j as f64 * std::f64::consts::PI / 3.0;
            let wrapped = error.sin().atan2(error.cos());
            assert!(wrapped.abs() < 0.02, "strands={strands}, terminal phase {j}: error {wrapped} rad");
        }
    }
}

#[test]
fn staggered_braid_pairs_carry_their_own_opening_currents_without_polarity_reversal() {
    for strands in [2, 3, 5] {
      for layers in [2, 4, 6, 8, 10] {
        let ctx = RoutingContext {
            active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: layers, phases: 3,
            min_trace_mm: 0.127, trace_width_mm: 0.2, min_space_mm: 0.127,
            params: std::collections::HashMap::from([("num_strands".into(), strands as f64), ("connection".into(), 2.0)]),
            magnet_pitch_mm: Some(6.0), magnet_array_span_mm: Some(29.0), ..Default::default()
        };
        let routing = generate_routing_result(&ctx, "infinity-braid").unwrap();
        let networks = extract_phase_networks(&routing);
        assert_eq!(networks.len(), 3);
        for net in &networks {
            assert_eq!(net.layers(), (0..layers).collect::<Vec<_>>());
            let solution = solve_network(net, &vec![1.0; net.edges.len()]);
            assert!(solution.connected, "{} must connect line to neutral", net.net);
            let mut joins = 0;
            for (edge, current) in net.edges.iter().zip(&solution.current_share) {
                if let EdgeKind::Via { layers: [a, b], .. } = edge.kind {
                  if a % 2 == 1 && b == a + 1 {
                    joins += 1;
                    assert!((current + 1.0).abs() < 1e-8, "each series link carries one amp from the driver toward neutral");
                  }
                }
            }
            assert_eq!(joins, layers / 2 - 1);
            let active = |layer| net.edges.iter().zip(&solution.current_share).filter_map(|(edge, current)| {
                match &edge.kind {
                    EdgeKind::Trace { layer: l, points, .. } if *l == layer && points.iter().all(|p| p[1] <= 0.008 + 1e-12) => Some((points, current)),
                    _ => None,
                }
            }).collect::<Vec<_>>();
            // Different cuts in the braid mesh need not have equal edge
            // currents. Solve each actual pair separately, keeping its own
            // opening and lead orientation, then compare signed active paths.
            for pair in 0..layers / 2 {
                let lo = 2 * pair;
                let hi = lo + 1;
                let isolated = RoutingResult {
                    segments: routing.segments.iter().filter(|s| s.layer == lo || s.layer == hi).cloned().collect(),
                    vias: routing.vias.iter().filter(|v| v.from_layer == lo && v.to_layer == hi).cloned().collect(),
                    ..Default::default()
                };
                let single = extract_phase_networks(&isolated).into_iter().find(|n| n.net == net.net).unwrap();
                let expected = solve_network(&single, &vec![1.0; single.edges.len()]);
                assert!(expected.connected);
                for layer in [lo, hi] {
                    let actual = active(layer);
                    let standalone: Vec<_> = single.edges.iter().zip(&expected.current_share).filter_map(|(edge, current)| {
                        match &edge.kind {
                            EdgeKind::Trace { layer: l, points, .. } if *l == layer && points.iter().all(|p| p[1] <= 0.008 + 1e-12) => Some((points, current)),
                            _ => None,
                        }
                    }).collect();
                    assert_eq!(actual.len(), standalone.len());
                    for ((a, ia), (b, ib)) in actual.iter().zip(&standalone) {
                        assert_eq!(a, b);
                        assert!((*ia - *ib).abs() < 1e-8, "a series connection must preserve the standalone pair's signed currents");
                    }
                }
            }
        }
        for via in routing.vias.iter().filter(|v| layers > 2 && v.from_layer == 0 && v.to_layer == layers - 1) {
            let mut cut = routing.clone();
            cut.vias.retain(|v| v.position != via.position || v.net != via.net);
            let net = extract_phase_networks(&cut).into_iter().find(|n| n.net == via.net).unwrap();
            assert!(!solve_network(&net, &vec![1.0; net.edges.len()]).connected);
        }
      }
    }
}

#[test]
fn signed_branch_currents_obey_kirchhoff_and_power_balance() {
    use super::geometry::Edge;
    let net = PhaseNetwork {
        net: "branched".into(), node_count: 4, node_x: vec![0.0; 4],
        terminal_key: vec![0, 1, 2, 3], terminal: vec![0], star: vec![2, 3],
        active_length_m: 0.0,
        edges: vec![Edge { a: 0, b: 1, kind: EdgeKind::Via { layers: [0,1], position_m: [0.,0.] } },
                    Edge { a: 1, b: 2, kind: EdgeKind::Via { layers: [1,2], position_m: [0.,0.] } },
                    Edge { a: 3, b: 1, kind: EdgeKind::Via { layers: [3,1], position_m: [0.,0.] } }],
    };
    let resistances = [1.0, 2.0, 2.0];
    let solved = solve_network(&net, &resistances);
    assert!(solved.connected);
    for (current, expected) in solved.current_share.iter().zip([1.0, 0.5, -0.5]) {
        assert!((current - expected).abs() < 1e-10);
    }
    let dissipation: f64 = solved.current_share.iter().zip(resistances).map(|(i, r)| i*i*r).sum();
    assert!((dissipation - solved.resistance_ohm).abs() < 1e-10);
    for invalid in [vec![1.0], vec![1.0, -1.0, 2.0], vec![1.0, f64::NAN, 2.0]] {
        assert!(!solve_network(&net, &invalid).connected);
    }
    let mut disconnected = net.clone();
    disconnected.edges.truncate(1);
    assert!(!solve_network(&disconnected, &[1.0]).connected);
    let mut shorted_terminals = net.clone();
    shorted_terminals.star.push(0);
    assert!(!solve_network(&shorted_terminals, &resistances).connected);
}

#[test]
fn generated_braid_currents_obey_kirchhoff_and_power_balance() {
    for strands in [2, 3, 5] {
        for length in [92.0, 110.0] {
            let ctx = pcbmotorgen_routing::RoutingContext {
                active_area_length_mm: length, board_width_mm: 8.0,
                num_layers: 2, phases: 3, min_trace_mm: 0.1, trace_width_mm: 0.1, min_space_mm: 0.127,
                expects_continuous: false,
                params: std::collections::HashMap::from([("num_strands".into(), strands as f64), ("connection".into(), 2.0)]),
                magnet_pitch_mm: Some(6.0), magnet_array_span_mm: Some(35.0), phase_clearance_mm: None,
                via_pad_diameter_mm: None,
                orientation: Default::default(),
            };
            let routing = pcbmotorgen_routing::generate_routing_result(&ctx, "infinity-braid").unwrap();
            for net in extract_phase_networks(&routing) {
                // Non-uniform resistances so the split is not trivially symmetric.
                let resistances: Vec<f64> = (0..net.edges.len()).map(|k| 1.0 + 0.1 * (k % 3) as f64).collect();
                let solution = solve_network(&net, &resistances);
                let label = format!("{} strands={strands} length={length}", net.net);
                assert!(solution.connected, "{label}: network did not solve");
                // Positive share flows a -> b; net inflow must vanish at every internal node.
                let mut balance = vec![0.0; net.node_count];
                for (edge, current) in net.edges.iter().zip(&solution.current_share) {
                    balance[edge.a] -= current;
                    balance[edge.b] += current;
                }
                for node in (0..net.node_count)
                    .filter(|n| !net.terminal.contains(n) && !net.star.contains(n))
                {
                    assert!(balance[node].abs() < 1e-9, "{label}: KCL violated at node {node}: {}", balance[node]);
                }
                let injected: f64 = net.terminal.iter().map(|&n| -balance[n]).sum();
                let returned: f64 = net.star.iter().map(|&n| balance[n]).sum();
                assert!(injected > 0.0, "{label}: no current injected");
                assert!((injected - returned).abs() < 1e-9, "{label}: terminal and star currents differ");
                let dissipated: f64 = solution.current_share.iter().zip(&resistances).map(|(i, r)| i * i * r).sum();
                assert!(
                    (dissipated - injected * injected * solution.resistance_ohm).abs() < 1e-9 * dissipated.max(1.0),
                    "{label}: power balance {dissipated} vs {}", injected * injected * solution.resistance_ohm
                );
            }
        }
    }
}

#[test]
fn empty_routing_cannot_produce_a_force_result() {
    use crate::magnetic::force_eval::ForceEvaluator;
    assert!(ForceEvaluator::default().with_routed_currents(
        &RoutingResult::default(), &sim(), &DriveSettings::default(), &DriveGeometryHints::default()
    ).is_err());
}

#[test]
fn unit_terminal_coefficients_reproduce_calibrated_routed_force_without_dividing_by_current() {
    use crate::magnetic::{CommutationMode, ForceEvaluator};
    let routing = two_strand_fixture();
    let mut sim = sim();
    let (mut evaluator, coils) = ForceEvaluator::new(3, 8, CommutationMode::PhaseAOnly, 0.0)
        .with_routed_currents(&routing, &sim, &DriveSettings::default(), &DriveGeometryHints::default()).unwrap();
    let x = 0.003;
    let force = evaluator.evaluate_at(&sim, &coils, x).unwrap().0[0];
    let currents = evaluator.excitation_currents_at(&sim, &coils, x).unwrap();
    let coefficients = evaluator.unit_phase_force_constants_at(&sim, x).unwrap();
    let reconstructed: f64 = coefficients.iter().zip(currents).map(|(k,i)| k*i).sum();
    assert!((force-reconstructed).abs() < 1e-12);
    sim.max_current_a = 0.0;
    assert_eq!(coefficients, evaluator.unit_phase_force_constants_at(&sim, x).unwrap());
    assert!(evaluator.unit_phase_force_constants_at(&sim, f64::NAN).is_err());
}

#[test]
fn native_inductance_matrix_retains_self_mutual_and_phase_order() {
    let routing = two_strand_fixture();
    let analysis = analyze_drive(&sim(), &routing, &DriveSettings::default(), None);
    let matrix = &analysis.phase_inductance_matrix_h;
    assert_eq!(matrix.len(), analysis.phases.len());
    for i in 0..matrix.len() {
        assert_eq!(matrix[i][i], analysis.phases[i].self_inductance_h);
        for j in 0..matrix.len() { assert_eq!(matrix[i][j], matrix[j][i]); }
    }
}

#[test]
fn curved_copper_is_integrated_and_endpoint_order_is_not_current_direction() {
    use crate::magnetic::force_eval::{ForceEvaluator, CommutationMode};
    let mut routing = RoutingResult::default();
    routing.curves.push(pcbmotorgen_routing::RouteCurve {
        start: Point::new(0.0, 0.0), mid: Point::new(2.928932188, 7.071067812),
        end: Point::new(10.0, 10.0), layer: 0, net: "A".into(), is_active: true,
    });
    let evaluate = |routing: &RoutingResult| {
        let (mut evaluator, coils) = ForceEvaluator::new(3, 8, CommutationMode::PhaseAOnly, 0.0)
            .with_routed_currents(routing, &sim(), &DriveSettings::default(), &DriveGeometryHints::default()).unwrap();
        assert!(!evaluator.routed_conductor_samples().unwrap()[0].is_empty());
        evaluator.evaluate_at(&sim(), &coils, 0.003).unwrap().0
    };
    let first = evaluate(&routing);
    let curve = &mut routing.curves[0];
    std::mem::swap(&mut curve.start, &mut curve.end);
    let reversed = evaluate(&routing);
    for (a, b) in first.iter().zip(reversed) {
        assert!((a - b).abs() < 1e-9);
    }
    assert!(first.iter().any(|v| v.abs() > 1e-8));
}

#[test]
fn routed_force_respects_imported_depths_and_rejects_mismatched_coils() {
    use crate::magnetic::force_eval::{ForceEvaluator, CommutationMode};
    let hints = DriveGeometryHints { layer_z_m: vec![0.0002, -0.003], ..Default::default() };
    let (mut evaluator, coils) = ForceEvaluator::new(3, 20, CommutationMode::PhaseAOnly, 0.0).with_routed_currents(
        &two_strand_fixture(), &sim(), &DriveSettings::default(), &hints,
    ).unwrap();
    let samples = evaluator.routed_conductor_samples().unwrap();
    assert!(samples[0].iter().any(|s| s.midpoint_3d[2] == 0.0002));
    assert!(samples[0].iter().any(|s| s.midpoint_3d[2] == -0.003));
    assert!(samples[0].iter().all(|s| s.dl_3d.iter().all(|v| v.is_finite())));
    assert!(evaluator.excitation_currents_at(&sim(), &coils, 0.0).is_err());
    assert!(evaluator.evaluate(&sim(), &[]).is_err());
    assert!(evaluator.evaluate_at(&sim(), &[], 0.0).is_err());
    assert!(!coils.is_empty());
    let mut wrong_name = coils.clone();
    wrong_name[0].phase_name = "not the solved network".into();
    assert!(evaluator.evaluate(&sim(), &wrong_name).is_err());
    assert!(evaluator.evaluate_at(&sim(), &wrong_name, 0.0).is_err());
    let mut wrong_index = coils.clone();
    wrong_index[0].phase_idx += 1;
    assert!(evaluator.evaluate_at(&sim(), &wrong_index, 0.0).is_err());
    let mut extra = coils.clone();
    extra.push(coils[0].clone());
    assert!(evaluator.evaluate(&sim(), &extra).is_err());
    assert!(evaluator.evaluate_at(&sim(), &coils, 0.0).is_ok());
    assert_eq!(evaluator.excitation_currents_at(&sim(), &coils, 0.0).unwrap(), vec![sim().max_current_a]);
    assert!(evaluator.excitation_currents_at(&sim(), &coils, f64::NAN).is_err());
    assert!(evaluator.excitation_currents_at(&sim(), &wrong_name, 0.0).is_err());
    let mut invalid_current = sim(); invalid_current.max_current_a = f64::NAN;
    assert!(evaluator.excitation_currents_at(&invalid_current, &coils, 0.0).is_err());
}

#[test]
fn force_and_driver_use_the_same_inner_outer_copper_split() {
    use crate::magnetic::force_eval::{ForceEvaluator, CommutationMode};
    let mut config = sim();
    config.num_layers = 4;
    let mut routing = RoutingResult::default();
    routing.segments = vec![seg(0.0, 0.0, 100.0, 0.0, 0, "A"), seg(0.0, 3.0, 100.0, 3.0, 1, "A")];
    let hints = DriveGeometryHints { layer_z_m: vec![0.0, -0.0004, -0.0008, -0.0016], ..Default::default() };
    for (outer, inner, expected) in [(1.0, 1.0, 0.5), (3.0, 1.0, 0.75), (1.0, 3.0, 0.25)] {
        let settings = DriveSettings { outer_copper_oz: outer, inner_copper_oz: inner, ..Default::default() };
        let (evaluator, _) = ForceEvaluator::new(3, 4, CommutationMode::PhaseAOnly, 0.0)
            .with_routed_currents(&routing, &config, &settings, &hints).unwrap();
        let samples = &evaluator.routed_conductor_samples().unwrap()[0];
        let outer_share: f64 = samples.iter().filter(|s| s.midpoint_3d[2] == 0.0).map(|s| s.dl_3d[0] / 0.1).sum();
        let inner_share: f64 = samples.iter().filter(|s| s.midpoint_3d[2] == -0.0004).map(|s| s.dl_3d[0] / 0.1).sum();
        assert!((outer_share - expected).abs() < 1e-9);
        assert!((inner_share - (1.0 - expected)).abs() < 1e-9);
        let analysis = analyze_drive_with(&config, &routing, &settings, None, &hints);
        assert!((analysis.phases[0].max_trace_share - outer_share.max(inner_share)).abs() < 1e-9);
        let r_unit = rho_cu_at(settings.winding_temp_c) * 0.1 / (config.min_trace_m * oz_to_m(1.0));
        assert!((analysis.phase_resistance_ohm - r_unit / (outer + inner)).abs() < 1e-9);
    }
}

fn seg(x0: f64, y0: f64, x1: f64, y1: f64, layer: u32, net: &str) -> RouteSegment {
    RouteSegment {
        start: Point::new(x0, y0),
        end: Point::new(x1, y1),
        layer,
        net: net.to_string(),
        is_active: true,
    }
}

/// Two parallel strands of phase A, each 100 mm on layer 0 then a via and
/// 100 mm back on layer 1.
fn two_strand_fixture() -> RoutingResult {
    let mut r = RoutingResult::default();
    for (k, y) in [(0, 0.0), (1, 5.0)] {
        let _ = k;
        r.segments.push(seg(0.0, y, 100.0, y, 0, "A"));
        r.segments.push(seg(100.0, y, 0.0, y + 1.0, 1, "A"));
        r.vias.push(Via { position: Point::new(100.0, y), from_layer: 0, to_layer: 1, net: "A".into() });
    }
    r
}

#[test]
fn housing_motion_is_opt_in_and_computed_for_generated_and_imported_copper() {
    use crate::backplane::{BackplaneStack, HousingSpec, HousingMaterial, HousingMotionProfile, HousingMotionAnalysis};
    for layers in [2, 4, 16] {
        let mut config = sim(); config.num_layers = layers; config.max_layers = 16;
        config.magnet_count = if layers == 16 { 12 } else { 5 };
        config.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec {
            material: if layers == 4 { HousingMaterial::Stainless316 } else { HousingMaterial::Aluminum6061 },
            thickness_m: 0.001, gap_m: 0.0001,
        }) });
        let mut imported = RoutingResult::default();
        for layer in 0..layers {
            let (a, b) = if layer % 2 == 0 { (0., 10.) } else { (10., 0.) };
            imported.segments.push(seg(a, 0., b, 0., layer, "A"));
            if layer + 1 < layers { imported.vias.push(Via { position: Point::new(b, 0.), from_layer: layer, to_layer: layer+1, net: "A".into() }); }
        }
        let hints = DriveGeometryHints {
            layer_z_m: (0..layers).map(|i| -config.pcb_thickness_m * (i as f64 / (layers-1) as f64).powi(2)).collect(),
            terminals: std::collections::BTreeMap::from([("A".into(), vec![TerminalPair {
                input: TerminalPoint { layer: 0, position: Point::new(0., 0.) },
                output: TerminalPoint { layer: layers-1, position: Point::new(0., 0.) },
            }])]),
        };
        validate_copper_placement(&config, &imported, &hints).unwrap();
        let mut settings = DriveSettings { target_speed_m_s: 3., ..Default::default() };
        let disabled = analyze_drive_with(&config, &imported, &settings, None, &hints);
        assert!(disabled.backplane.as_ref().unwrap().housing_motion.is_none());
        settings.housing_motion = Some(HousingMotionProfile { duration_s: 0.2 });
        let enabled = analyze_drive_with(&config, &imported, &settings, None, &hints);
        assert!(enabled.phases[0].connected);
        assert_eq!(enabled.phase_resistance_ohm, disabled.phase_resistance_ohm);
        match enabled.backplane.unwrap().housing_motion.unwrap() {
            HousingMotionAnalysis::Experimental { estimate } => assert!(estimate.housing_joule_power_w > 0.),
            HousingMotionAnalysis::Unavailable { reason } => panic!("{reason}"),
        }
        assert_eq!(hints.layer_z_m.last().copied(), Some(-config.pcb_thickness_m));
    }
    let config = sim();
    let ctx = RoutingContext { active_area_length_mm: 110., board_width_mm: 8., num_layers: 2, phases: 3,
        min_trace_mm: 0.1, trace_width_mm: 0.1, min_space_mm: 0.127, expects_continuous: false,
        params: std::collections::HashMap::from([("num_strands".into(), 2.), ("connection".into(), 2.)]),
        magnet_pitch_mm: Some(6.), magnet_array_span_mm: Some(35.), phase_clearance_mm: None, via_pad_diameter_mm: None,
        orientation: Default::default() };
    let generated = generate_routing_result(&ctx, "infinity-braid").unwrap();
    let mut config = config;
    config.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec { material: HousingMaterial::Stainless304, thickness_m: 0.001, gap_m: 0.0 }) });
    let settings = DriveSettings { housing_motion: Some(HousingMotionProfile { duration_s: 0.1 }), ..Default::default() };
    let generated_result = analyze_drive(&config, &generated, &settings, None);
    assert!(matches!(generated_result.backplane.unwrap().housing_motion, Some(HousingMotionAnalysis::Experimental { .. })));
}

#[test]
fn housing_motion_settings_round_trip_without_changing_legacy_defaults() {
    let settings = DriveSettings::default();
    let legacy = serde_json::to_value(&settings).unwrap();
    assert!(legacy.get("housing_motion").is_none());
    let restored: DriveSettings = serde_json::from_value(legacy).unwrap();
    assert!(restored.housing_motion.is_none());
    let enabled = DriveSettings {
        housing_motion: Some(crate::backplane::HousingMotionProfile { duration_s: 0.25 }),
        ..settings
    };
    let restored: DriveSettings = serde_json::from_str(&serde_json::to_string(&enabled).unwrap()).unwrap();
    assert_eq!(enabled, restored);
}

#[test]
fn through_barrel_intervals_sum_to_one_physical_barrel() {
    let mut config = sim();
    config.num_layers = 4;
    config.pcb_thickness_m = 0.0016;
    let mut routing = RoutingResult::default();
    for layer in 0..4 { routing.segments.push(seg(0.0, 0.0, 10.0, 0.0, layer, "A")); }
    routing.vias.push(Via { position: Point::new(10.0, 0.0), from_layer: 0, to_layer: 3, net: "A".into() });
    let hints = DriveGeometryHints {
        layer_z_m: vec![0.0, -0.0002, -0.0010, -0.0016],
        terminals: std::collections::BTreeMap::from([("A".into(), vec![TerminalPair {
            input: TerminalPoint { layer: 0, position: Point::new(0.0, 0.0) },
            output: TerminalPoint { layer: 3, position: Point::new(0.0, 0.0) },
        }])]),
    };
    let networks = extract_phase_networks_with_terminals(&routing, &hints.terminals);
    let spans: Vec<_> = networks[0].edges.iter().filter_map(|edge| {
        if let EdgeKind::Via { layers, position_m } = edge.kind {
            assert_eq!(position_m, [0.01, 0.0]); Some(layers)
        } else { None }
    }).collect();
    assert_eq!(spans, vec![[0, 1], [1, 2], [2, 3]]);
    let length: f64 = spans.iter().map(|layers| hints.via_length_m(&config, *layers)).sum();
    assert!((length - config.pcb_thickness_m).abs() < 1e-15);
    let settings = DriveSettings::default();
    let analysis = analyze_drive_with(&config, &routing, &settings, None, &hints);
    let full_barrel = via_resistance_ohm(config.min_via_drill_m, settings.via_plating_m, 0.0016, rho_cu_at(settings.winding_temp_c));
    assert!(analysis.notes.iter().any(|note| note.contains("via-barrel inductance")));
    assert!((analysis.phases[0].via_resistance_ohm / full_barrel - 1.0).abs() < 1e-9);
    // The two inner-layer traces are open stubs, not extra current returns.
    let trace = rho_cu_at(settings.winding_temp_c) * 0.020 / (config.min_trace_m * oz_to_m(settings.outer_copper_oz));
    assert!((analysis.phases[0].resistance_hot_ohm / (trace + full_barrel) - 1.0).abs() < 1e-9);
}

#[test]
fn via_force_uses_signed_current_and_imported_vertical_depth() {
    use crate::magnetic::force_eval::{ForceEvaluator, CommutationMode};
    let config = sim();
    let settings = DriveSettings::default();
    let hints = DriveGeometryHints { layer_z_m: vec![0.0002, -0.003], ..Default::default() };
    let mut routing = two_strand_fixture();
    for reverse in [false, true] {
        if reverse {
            for segment in &mut routing.segments { std::mem::swap(&mut segment.start, &mut segment.end); }
            for via in &mut routing.vias { std::mem::swap(&mut via.from_layer, &mut via.to_layer); }
        }
        let (evaluator, _) = ForceEvaluator::new(3, 20, CommutationMode::PhaseAOnly, 0.0)
            .with_routed_currents(&routing, &config, &settings, &hints).unwrap();
        let samples = &evaluator.routed_conductor_samples().unwrap()[0];
        let vertical: Vec<_> = samples.iter().filter(|s| s.dl_3d[2].abs() > 1e-15).collect();
        assert_eq!(vertical.len(), 40);
        assert!(vertical.iter().all(|s| s.midpoint_3d[2] < 0.0002 && s.midpoint_3d[2] > -0.003));
        let signed_dz: f64 = vertical.iter().map(|s| s.dl_3d[2]).sum();
        assert!((signed_dz + 0.0032).abs() < 1e-12);
        // Independent constant transverse B_y=2 T gives winding F_x=-I*dz*B_y.
        let winding_fx: f64 = samples.iter().map(|s| -2.0 * s.dl_3d[2]).sum();
        assert!((winding_fx - 0.0064).abs() < 1e-12);
        let analysis = analyze_drive_with(&config, &routing, &settings, None, &hints);
        let single_barrel = via_resistance_ohm(config.min_via_drill_m, settings.via_plating_m, 0.0032, rho_cu_at(settings.winding_temp_c));
        assert!((analysis.phases[0].via_resistance_ohm / (single_barrel / 2.0) - 1.0).abs() < 1e-9);
    }
}

#[test]
fn imported_copper_below_responding_stack_is_rejected_without_moving_geometry() {
    use crate::backplane::{BackplaneLayer, BackplaneStack, HousingMaterial, HousingSpec, LayerMaterial};
    use crate::magnetic::force_eval::ForceEvaluator;
    let mut config = sim(); config.pcb_thickness_m = 0.0008;
    let routing = two_strand_fixture();
    let hints = DriveGeometryHints { layer_z_m: vec![0.0, -0.0048], ..Default::default() };
    assert!(validate_copper_placement(&config, &routing, &hints).is_ok());
    config.backplane = Some(BackplaneStack { layers: vec![BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002)], housing: None });
    let error = validate_copper_placement(&config, &routing, &hints).unwrap_err().to_string();
    assert!(error.contains("below the first magnetic/conducting stack surface"));
    assert!(ForceEvaluator::default().with_routed_currents(&routing, &config, &Default::default(), &hints).is_err());
    assert_eq!(hints.layer_z_m, vec![0.0, -0.0048]);
    // A matching physical PCB extent is valid, including bottom copper at the surface.
    config.pcb_thickness_m = 0.0048;
    assert!(validate_copper_placement(&config, &routing, &hints).is_ok());
    // Nonmagnetic spacers/air above the first responding surface are allowed.
    config.pcb_thickness_m = 0.0008;
    config.backplane = Some(BackplaneStack { layers: vec![BackplaneLayer::new(LayerMaterial::Fr4, 0.002), BackplaneLayer::new(LayerMaterial::Fr4, 0.002), BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002)], housing: None });
    assert!(validate_copper_placement(&config, &routing, &hints).is_ok());
    config.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec { material: HousingMaterial::Aluminum6061, thickness_m: 0.001, gap_m: 0.005 }) });
    assert!(validate_copper_placement(&config, &routing, &hints).is_ok());
    config.backplane.as_mut().unwrap().housing.as_mut().unwrap().gap_m = 0.0001;
    assert!(validate_copper_placement(&config, &routing, &hints).is_err());
}

#[test]
fn routed_sweep_limits_follow_copper_not_configured_board_length() {
    use crate::magnetic::force_eval::ForceEvaluator;
    let mut cfg = sim();
    cfg.magnet_count = 2;
    cfg.magnet_pitch_m = 0.006;
    cfg.magnet_dims_m[0] = 0.004;
    for offset_mm in [0.0, 20.0] {
        let mut routing = two_strand_fixture();
        for segment in &mut routing.segments {
            segment.start.x += offset_mm;
            segment.end.x += offset_mm;
        }
        for via in &mut routing.vias { via.position.x += offset_mm; }
        let (evaluator, _) = ForceEvaluator::default().with_routed_currents(
            &routing, &cfg, &DriveSettings::default(), &DriveGeometryHints::default(),
        ).unwrap();
        let (start, end) = evaluator.sweep_center_limits_m(&cfg).unwrap();
        assert!((start - cfg.magnet_dims_m[0] / 2.0 - offset_mm * 1e-3).abs() < 1e-12);
        assert!((end + cfg.magnet_pitch_m + cfg.magnet_dims_m[0] / 2.0
            - (100.0 + offset_mm) * 1e-3).abs() < 1e-12);
        let mut oversized = cfg.clone();
        oversized.magnet_count = 100;
        assert!(evaluator.sweep_center_limits_m(&oversized).is_err());
    }
}

#[test]
fn solved_force_is_invariant_to_stored_segment_direction() {
    use crate::magnetic::force_eval::{ForceEvaluator, CommutationMode};
    let config = sim();
    let settings = DriveSettings::default();
    let routing = two_strand_fixture();
    let mut reversed = routing.clone();
    for (i, segment) in reversed.segments.iter_mut().enumerate() {
        if i % 2 == 0 {
            std::mem::swap(&mut segment.start, &mut segment.end);
        }
    }
    let evaluate = |routing: &RoutingResult| {
        let (mut evaluator, coils) = ForceEvaluator::new(3, 4, CommutationMode::PhaseAOnly, 0.0)
            .with_routed_currents(routing, &config, &settings, &DriveGeometryHints::default()).unwrap();
        evaluator.evaluate_at(&config, &coils, 0.003).unwrap().0
    };
    let original = evaluate(&routing);
    let flipped = evaluate(&reversed);
    for (a, b) in original.iter().zip(flipped) {
        assert!((a - b).abs() < 1e-9, "stored direction changed physical force: {a} vs {b}");
    }
}

fn sim() -> SimulationInput {
    SimulationInput {
        num_layers: 2,
        min_trace_m: 0.25e-3,
        min_via_drill_m: 0.3e-3,
        pcb_thickness_m: 1.6e-3,
        max_current_a: 0.8,
        supply_voltage_v: 12.0,
        ..SimulationInput::default()
    }
}

#[test]
fn strands_are_found_from_the_terminal_ends() {
    let nets = extract_phase_networks(&two_strand_fixture());
    assert_eq!(nets.len(), 1);
    let a = &nets[0];
    assert_eq!(a.strands(), 2);
    assert_eq!(a.star.len(), 2);
    assert_eq!(a.via_count(), 2);
    let per_strand = 0.1 + (100f64.powi(2) + 1.0).sqrt() * 1e-3;
    assert!((a.trace_length_m() - 2.0 * per_strand).abs() < 1e-9);
}

#[test]
fn resistance_matches_hand_calculation() {
    // Reproduce the hand example: 0.25 mm × 2 oz, 1.8 m at 75 °C ≈ 2.1 Ω.
    let mut r = RoutingResult::default();
    r.segments.push(seg(0.0, 0.0, 1800.0, 0.0, 0, "A"));
    let settings = DriveSettings {
        outer_copper_oz: 2.0,
        winding_temp_c: 75.0,
        ..DriveSettings::default()
    };
    let a = analyze_drive(&sim(), &r, &settings, None);
    let expected = rho_cu_at(75.0) * 1.8 / (0.25e-3 * oz_to_m(2.0));
    assert!((a.phase_resistance_ohm - expected).abs() < 1e-9);
    assert!((a.phase_resistance_ohm - 2.11).abs() < 0.15, "{}", a.phase_resistance_ohm);
}

#[test]
fn parallel_strands_divide_resistance() {
    let settings = DriveSettings::default();
    let a = analyze_drive(&sim(), &two_strand_fixture(), &settings, None);
    let ph = &a.phases[0];
    assert!(ph.connected);
    assert!((ph.max_trace_share - 0.5).abs() < 1e-9);
    let rho = rho_cu_at(settings.winding_temp_c);
    let strand = rho * ph.strand_length_m / (0.25e-3 * oz_to_m(1.0)) + a.via_resistance_each_ohm;
    assert!((ph.resistance_hot_ohm - strand / 2.0).abs() < 1e-9);
    assert!(a.via_resistance_each_ohm > 0.5e-3 && a.via_resistance_each_ohm < 3e-3);
    for phase in &a.phases {
        assert!(phase.via_resistance_ohm > 0.0);
        assert!(phase.via_resistance_ohm < phase.resistance_hot_ohm);
    }
}

#[test]
fn floating_closed_copper_does_not_gain_inferred_terminal_buses() {
    let mut routing = two_strand_fixture();
    for (a, b) in [((200.0, 0.0), (210.0, 10.0)), ((210.0, 10.0), (220.0, 0.0)),
        ((220.0, 0.0), (210.0, -10.0)), ((210.0, -10.0), (200.0, 0.0))] {
        routing.segments.push(seg(a.0, a.1, b.0, b.1, 0, "A"));
    }
    let baseline = extract_phase_networks(&two_strand_fixture()).remove(0);
    let net = extract_phase_networks(&routing).remove(0);
    assert_eq!(net.terminal.len(), baseline.terminal.len());
    assert_eq!(net.star.len(), baseline.star.len());
    let solution = solve_network(&net, &vec![1.0; net.edges.len()]);
    assert!(solution.connected);
    for (edge, current) in net.edges.iter().zip(&solution.current_share) {
        if let EdgeKind::Trace { points, .. } = &edge.kind {
            if points.iter().all(|p| p[0] >= 0.2) {
                assert!(current.abs() < 1e-10, "floating copper carries invented current");
            }
        }
    }
}

#[test]
fn generated_braid_remains_one_connected_winding_across_repeat_counts() {
    for strands in [2, 3, 4, 5] {
        for length in [92.0, 98.0, 110.0, 120.0] {
            let ctx = pcbmotorgen_routing::RoutingContext {
                active_area_length_mm: length, board_width_mm: 8.0,
                num_layers: 2, phases: 3, min_trace_mm: 0.1, trace_width_mm: 0.1, min_space_mm: 0.127,
                expects_continuous: false,
                params: std::collections::HashMap::from([("num_strands".into(), strands as f64), ("connection".into(), 2.0)]),
                magnet_pitch_mm: Some(6.0), magnet_array_span_mm: Some(35.0), phase_clearance_mm: None,
                via_pad_diameter_mm: None,
                orientation: Default::default(),
            };
            let routing = pcbmotorgen_routing::generate_routing_result(&ctx, "infinity-braid").unwrap();
            for net in extract_phase_networks(&routing) {
                let mut adj = vec![Vec::new(); net.node_count];
                for e in &net.edges { adj[e.a].push(e.b); adj[e.b].push(e.a); }
                let mut seen = vec![false; net.node_count];
                let mut stack = vec![0];
                seen[0] = true;
                while let Some(node) = stack.pop() {
                    for &next in &adj[node] {
                        if !seen[next] { seen[next] = true; stack.push(next); }
                    }
                }
                assert!(seen.iter().all(|v| *v), "{} split: strands={strands}, length={length}", net.net);
            }
        }
    }
}

#[test]
fn ripple_and_voltage_follow_the_formulas() {
    let settings = DriveSettings::default();
    let a = analyze_drive(&sim(), &two_strand_fixture(), &settings, Some(0.5));
    let expected_ripple = 12.0 / (2.0 * a.phase_resistance_ohm)
        * (a.phase_resistance_ohm / (4.0 * settings.pwm_hz * a.synchronous_inductance_h)).tanh();
    assert!((a.ripple_pp_a - expected_ripple).abs() / expected_ripple < 1e-9);
    let hold = 3f64.sqrt() * 0.8 * a.phase_resistance_ohm + 0.8 * settings.driver.rds_on_ohm;
    assert!((a.holding_voltage_v - hold).abs() < 1e-9);
    assert!(a.speed_voltage_v.unwrap() > a.holding_voltage_v);
    let vmax = a.max_speed_m_s.unwrap();
    assert!(vmax > 0.0);
    assert_eq!(a.thrust_n, Some(0.4));
    assert!(a.checks.iter().all(|c| c.status != CheckStatus::Unknown));
    assert!(a.checks.iter().find(|c| c.id == "ripple").unwrap().detail.contains("not a switched-waveform simulation"));
    assert!(a.checks.iter().find(|c| c.id == "thrust").unwrap().detail.contains("not a position-specific"));
}

#[test]
fn ripple_estimate_matches_the_assumed_fifty_percent_rl_loop() {
    let settings = DriveSettings::default();
    let cfg = sim();
    let a = analyze_drive(&cfg, &two_strand_fixture(), &settings, Some(0.5));
    // Independent steady-state RL solution for the assumed alternating
    // +/- Vbus/2 excitation of a two-phase loop, not a PWM-controller oracle.
    // Ipp = Vbus/Rloop * tanh(Rloop/(4*f*Lloop)).
    let r_loop = 2.0 * a.phase_resistance_ohm;
    let l_loop = 2.0 * a.synchronous_inductance_h;
    let exact = cfg.supply_voltage_v / r_loop
        * (r_loop / (4.0 * settings.pwm_hz * l_loop)).tanh();
    assert!(exact > 0.0);
    assert!((exact - a.ripple_pp_a).abs() < 1e-10);
    assert!(a.ripple_pp_a <= cfg.supply_voltage_v / r_loop);
    // March the two half-cycle RL responses to periodic steady state.
    // This uses exponential settling, independently of the tanh formula.
    let decay = (-r_loop / (2.0 * settings.pwm_hz * l_loop)).exp();
    let target = cfg.supply_voltage_v / (2.0 * r_loop);
    let mut current = 0.0;
    let mut high = 0.0;
    for _ in 0..10_000 {
        high = target + (current - target) * decay;
        current = -target + (high + target) * decay;
    }
    assert!((high - current - a.ripple_pp_a).abs() < 1e-9);
    let mut higher_bus = cfg.clone();
    higher_bus.supply_voltage_v *= 2.0;
    let higher = analyze_drive(&higher_bus, &two_strand_fixture(), &settings, Some(0.5));
    assert!((higher.ripple_pp_a - 2.0 * a.ripple_pp_a).abs() < 1e-10);
    assert_eq!(higher.thrust_n, a.thrust_n);
}

#[test]
fn ripple_goal_recommendation_inverts_the_formula_without_changing_predicted_ripple() {
    // This is a design-advice utility test, not numerical physics acceptance
    // based on meeting a ripple target. Tightening the goal changes the proposed
    // PWM floor, never the calculated ripple at the actual configured frequency.
    let cfg = sim();
    let settings = DriveSettings::default();
    let baseline = analyze_drive(&cfg, &two_strand_fixture(), &settings, Some(0.5));
    for fraction in [0.1, 0.3, 0.6] {
        let goals = DriveSettings { ripple_limit_fraction: fraction, ..settings.clone() };
        let a = analyze_drive(&cfg, &two_strand_fixture(), &goals, Some(0.5));
        assert_eq!(a.ripple_pp_a, baseline.ripple_pp_a);
        let r_loop = 2.0 * a.phase_resistance_ohm;
        let l_loop = 2.0 * a.synchronous_inductance_h;
        let at_proposed_pwm = cfg.supply_voltage_v / r_loop
            * (r_loop / (4.0 * a.min_pwm_hz * l_loop)).tanh();
        assert!((at_proposed_pwm - fraction * cfg.max_current_a).abs() < 1e-9);
    }
}

#[test]
fn external_series_inductance_tames_ripple_and_raises_voltage() {
    let base = analyze_drive(&sim(), &two_strand_fixture(), &DriveSettings::default(), Some(0.5));
    let extra = 1e-3; // 1 mH per phase at the driver terminals
    let settings = DriveSettings { series_inductance_h: extra, ..DriveSettings::default() };
    let a = analyze_drive(&sim(), &two_strand_fixture(), &settings, Some(0.5));

    assert!((a.series_inductance_h - extra).abs() < 1e-15);
    assert!((a.effective_inductance_h - (a.synchronous_inductance_h + extra)).abs() < 1e-15);
    // More series inductance: less ripple, a longer time constant, a lower
    // PWM floor, and less extra inductance still needed.
    assert!(a.ripple_pp_a < base.ripple_pp_a);
    assert!(a.min_pwm_hz < base.min_pwm_hz);
    assert!(a.time_constant_s > base.time_constant_s);
    assert!(a.added_inductance_h <= base.added_inductance_h);
    // Standstill holding voltage is resistive, so it is unchanged; the
    // at-speed voltage grows by ω·ΔL·I.
    assert!((a.holding_voltage_v - base.holding_voltage_v).abs() < 1e-12);
    assert!(a.speed_voltage_v.unwrap() > base.speed_voltage_v.unwrap());
    assert!(a.notes.iter().any(|note| note.contains("external series inductance")));
    // The copper-only value is untouched, so the UI can still show it.
    assert!((a.synchronous_inductance_h - base.synchronous_inductance_h).abs() < 1e-15);
}

#[test]
fn backplane_ripple_uses_the_pwm_inductance_and_reports_eddy_drag() {
    use crate::backplane::*;
    let settings = DriveSettings::default();
    let bare = analyze_drive(&sim(), &two_strand_fixture(), &settings, Some(0.5));
    assert!(bare.backplane.is_none());
    assert!(!serde_json::to_string(&bare).unwrap().contains("backplane"));

    let with = |stack: BackplaneStack| {
        let cfg = SimulationInput {
            backplane: Some(stack),
            ..sim()
        };
        analyze_drive(&cfg, &two_strand_fixture(), &settings, Some(0.5))
    };
    // Ferrite alone: no eddy currents, so every frequency sees the same L.
    let ferrite = with(BackplaneStack {
        layers: vec![BackplaneLayer::new(LayerMaterial::NiZnFerrite, 5e-3)],
        housing: None,
    });
    let bp = ferrite.backplane.as_ref().unwrap();
    assert_eq!(bp.pwm_inductance_h, ferrite.effective_inductance_h);
    assert_eq!(
        (bp.pwm_resistance_ohm, bp.ripple_eddy_loss_w, bp.drag_n),
        (0.0, 0.0, 0.0)
    );
    assert!(ferrite.checks.iter().all(|c| c.id != "eddy_drag"));

    // An aluminium wall right under the PCB screens the coil at 100 kHz and
    // drags the moving magnets.
    let al = with(al_stack().unwrap());
    let bp = al.backplane.as_ref().unwrap();
    assert_eq!(al.synchronous_inductance_h, bare.synchronous_inductance_h);
    assert!(bp.pwm_inductance_h < al.effective_inductance_h);
    assert!(bp.pwm_resistance_ohm > 0.0 && bp.ripple_eddy_loss_w > 0.0);
    let expected_ripple = 12.0 / (2.0 * al.phase_resistance_ohm)
        * (al.phase_resistance_ohm / (4.0 * settings.pwm_hz * bp.pwm_inductance_h)).tanh();
    assert!((al.ripple_pp_a - expected_ripple).abs() < 1e-12);
    assert!(al.ripple_pp_a >= bare.ripple_pp_a);
    assert!(bp.drag_n > 0.0 && bp.drag_curve.len() == al.speed_curve.len());
    assert_eq!(bp.drag_curve[0].drag_n, 0.0);
    assert!((bp.drag_power_w - bp.drag_n * settings.target_speed_m_s).abs() < 1e-15);
    assert_eq!(bp.net_thrust_n, Some(0.4 - bp.drag_n));
    let check = al.checks.iter().find(|c| c.id == "eddy_drag").unwrap();
    assert_eq!(check.value, bp.drag_n);
    // The 0.4 N thrust is reached on the curve, and the bisection finds it.
    let v = bp.drag_limited_speed_m_s.unwrap();
    let s = SimulationInput {
        backplane: al_stack(),
        ..sim()
    };
    let solved = s.backplane.as_ref().unwrap().solve(&s);
    assert!((solved.magnet_forces(&s, v).drag_n / 0.4 - 1.0).abs() < 1e-6);
}

fn al_stack() -> Option<crate::backplane::BackplaneStack> {
    use crate::backplane::*;
    Some(BackplaneStack {
        layers: vec![],
        housing: Some(HousingSpec {
            material: HousingMaterial::Aluminum6061,
            thickness_m: 3e-3,
            gap_m: 0.1e-3,
        }),
    })
}

#[test]
fn backplane_physics_and_drag_crossing_do_not_depend_on_goal_driven_plot_bounds() {
    let cfg = SimulationInput { backplane: al_stack(), ..sim() };
    let baseline = DriveSettings { target_speed_m_s: 0.001, ..Default::default() };
    let strict = DriveSettings { voltage_headroom: 0.0001, ripple_limit_fraction: 0.0001,
        allowed_rise_c: 0.1, ..baseline.clone() };
    let a = analyze_drive(&cfg, &two_strand_fixture(), &baseline, Some(0.5));
    let b = analyze_drive(&cfg, &two_strand_fixture(), &strict, Some(0.5));
    let x = a.backplane.unwrap();
    let y = b.backplane.unwrap();
    assert_eq!(x.drag_n, y.drag_n);
    assert_eq!(x.normal_force_n, y.normal_force_n);
    assert_eq!(x.pwm_inductance_h, y.pwm_inductance_h);
    assert_eq!(x.pwm_resistance_ohm, y.pwm_resistance_ohm);
    assert_eq!(x.ripple_eddy_loss_w, y.ripple_eddy_loss_w);
    assert_eq!(x.net_thrust_n, y.net_thrust_n);
    assert!(x.drag_limited_speed_m_s.is_some());
    assert_eq!(x.drag_limited_speed_m_s, y.drag_limited_speed_m_s,
        "A goal-dependent plot range cannot decide whether the physical drag/thrust crossing exists");
    let thrust = a.thrust_n.unwrap();
    let solved = cfg.backplane.as_ref().unwrap().solve(&cfg);
    let crossing = x.drag_limited_speed_m_s.unwrap();
    assert!((solved.magnet_forces(&cfg, crossing).drag_n / thrust - 1.0).abs() < 1e-9);
    let changed_excitation = SimulationInput { max_current_a: 2.0 * cfg.max_current_a, ..cfg };
    let physical = analyze_drive(&changed_excitation, &two_strand_fixture(), &baseline, Some(0.5));
    assert_ne!(physical.backplane.unwrap().drag_limited_speed_m_s, x.drag_limited_speed_m_s);
}

#[test]
fn two_layer_braid_fixture_produces_plausible_values() {
    // These original bounds describe the two-layer weave that this fixture
    // historically generated, even when it incorrectly requested four layers.
    let ctx = RoutingContext {
        active_area_length_mm: 147.0,
        board_width_mm: 20.0,
        num_layers: 2,
        phases: 3,
        min_trace_mm: 0.127,
        trace_width_mm: 0.127,
        min_space_mm: 0.127,
        expects_continuous: false,
        params: Default::default(),
        magnet_pitch_mm: Some(6.0),
        magnet_array_span_mm: Some(72.0),
        phase_clearance_mm: None,
        via_pad_diameter_mm: None,
        orientation: Default::default(),
    };
    let routing = generate_routing_result(&ctx, "infinity-braid").expect("braid");
    let s = SimulationInput { num_layers: 2, min_trace_m: 0.127e-3, magnet_pitch_m: 6e-3, ..SimulationInput::default() };
    let a = analyze_drive(&s, &routing, &DriveSettings::default(), Some(0.3));
    eprintln!(
        "R={:.3} Ω L={:.2} µH M={:.2} µH L_LL={:.2} µH ripple={:.2} A strands={} vias/strand={} len/strand={:.1} mm",
        a.phase_resistance_ohm,
        a.phase_inductance_h * 1e6,
        a.mutual_inductance_h * 1e6,
        a.line_inductance_h * 1e6,
        a.ripple_pp_a,
        a.phases[0].strands,
        a.phases[0].vias_per_strand,
        a.phases[0].strand_length_m * 1e3,
    );
    assert_eq!(a.phases.len(), 3);
    for ph in &a.phases {
        assert!(ph.connected, "{} disconnected", ph.net);
        assert_eq!(ph.strands, 5, "{} strands", ph.net);
        assert_eq!(ph.layers, vec![0, 1]);
        assert!(ph.vias_per_strand > 1.0);
    }
    assert!(a.phase_resistance_ohm > 0.1 && a.phase_resistance_ohm < 20.0);
    assert!(a.line_inductance_h > 0.1e-6 && a.line_inductance_h < 100e-6);
}



#[test]
fn picked_terminals_override_the_inferred_ones() {
    // Pick the strand end on layer 1 as IN: the inferred terminal is the
    // layer-0 end, so the buses swap.
    let r = two_strand_fixture();
    let pick = |y: f64| TerminalPair {
        input: TerminalPoint { layer: 1, position: Point::new(0.0, y + 1.0) },
        output: TerminalPoint { layer: 0, position: Point::new(0.0, y) },
    };
    let picked = std::collections::BTreeMap::from([("A".to_string(), vec![pick(0.0), pick(5.0)])]);
    let inferred = &extract_phase_networks(&r)[0];
    let explicit = &extract_phase_networks_with_terminals(&r, &picked)[0];
    assert_eq!(explicit.terminal, inferred.star);
    assert_eq!(explicit.star, inferred.terminal);
    let a = analyze_drive_with(&sim(), &r, &DriveSettings::default(), None, &DriveGeometryHints {
        layer_z_m: vec![0.0, 1.6e-3],
        terminals: picked,
    });
    assert!(a.phases[0].connected);
    assert_eq!(a.phases[0].strands, 2);
}

#[test]
fn through_hole_barrel_connects_inner_layers_without_outer_trace_stubs() {
    let mut routing = RoutingResult::default();
    routing.segments = vec![
        RouteSegment { start: Point::new(0.0, 0.0), end: Point::new(1.0, 0.0), layer: 1, net: "A".into(), is_active: true },
        RouteSegment { start: Point::new(1.0, 0.0), end: Point::new(2.0, 0.0), layer: 2, net: "A".into(), is_active: true },
    ];
    routing.vias.push(Via { position: Point::new(1.0, 0.0), from_layer: 0, to_layer: 3, net: "A".into() });
    let hints = DriveGeometryHints {
        layer_z_m: vec![0.0, 0.3e-3, 0.5e-3, 0.8e-3],
        terminals: std::collections::BTreeMap::from([("A".into(), vec![TerminalPair {
            input: TerminalPoint { layer: 1, position: Point::new(0.0, 0.0) },
            output: TerminalPoint { layer: 2, position: Point::new(2.0, 0.0) },
        }])]),
    };
    let s = SimulationInput { num_layers: 4, ..sim() };
    let a = analyze_drive_with(&s, &routing, &DriveSettings::default(), None, &hints);
    assert!(a.phases[0].connected);
    assert_eq!(a.phases[0].layers, vec![1, 2]);
    assert_eq!(extract_phase_networks(&routing)[0].via_count(), 1);
}

#[test]
fn coincident_vias_preserve_distinct_spans_without_duplicate_connections() {
    let mut routing = RoutingResult::default();
    for layer in 0..4 {
        routing.segments.push(RouteSegment {
            start: Point::new(0.0, 0.0), end: Point::new(1.0, 0.0),
            layer, net: "A".into(), is_active: true,
        });
    }
    // Distinct layer pairs at the same XY must both survive. Exact duplicate
    // records, including a reversed one, must not add parallel conductances.
    for (from_layer, to_layer) in [(0, 1), (2, 3), (0, 1), (3, 2)] {
        routing.vias.push(Via { position: Point::new(1.0, 0.0), from_layer, to_layer, net: "A".into() });
    }
    let networks = extract_phase_networks(&routing);
    assert_eq!(networks[0].via_count(), 2);
    // A full-span barrel adds only the missing inner connection, regardless
    // of whether it is listed before or after the shorter spans.
    routing.vias.push(Via { position: Point::new(1.0, 0.0), from_layer: 0, to_layer: 3, net: "A".into() });
    assert_eq!(extract_phase_networks(&routing)[0].via_count(), 3);
    routing.vias.reverse();
    assert_eq!(extract_phase_networks(&routing)[0].via_count(), 3);
}
