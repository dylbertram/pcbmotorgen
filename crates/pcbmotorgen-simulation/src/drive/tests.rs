use super::*;
use pcbmotorgen_routing::{
    generate_routing_result, Point, RouteSegment, RoutingContext, RoutingResult, Via,
};

#[test]
fn signed_branch_currents_obey_kirchhoff_and_power_balance() {
    use super::geometry::Edge;
    let net = PhaseNetwork {
        net: "branched".into(), node_count: 4, node_x: vec![0.0; 4],
        terminal_key: vec![0, 1, 2, 3], terminal: vec![0], star: vec![2, 3],
        active_length_m: 0.0,
        edges: vec![Edge { a: 0, b: 1, kind: EdgeKind::Via },
                    Edge { a: 1, b: 2, kind: EdgeKind::Via },
                    Edge { a: 3, b: 1, kind: EdgeKind::Via }],
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
    use crate::magnetic::force_eval::ForceEvaluator;
    let hints = DriveGeometryHints { layer_z_m: vec![0.0002, -0.003], ..Default::default() };
    let (mut evaluator, coils) = ForceEvaluator::default().with_routed_currents(
        &two_strand_fixture(), &sim(), &DriveSettings::default(), &hints,
    ).unwrap();
    let samples = evaluator.routed_conductor_samples().unwrap();
    assert!(samples[0].iter().any(|s| s.midpoint_3d[2] == 0.0002));
    assert!(samples[0].iter().any(|s| s.midpoint_3d[2] == -0.003));
    assert!(samples[0].iter().all(|s| s.dl_3d.iter().all(|v| v.is_finite())));
    assert!(evaluator.evaluate(&sim(), &[]).is_err());
    assert!(evaluator.evaluate_at(&sim(), &[], 0.0).is_err());
    assert!(!coils.is_empty());
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
    let at_required_pwm = cfg.supply_voltage_v / r_loop
        * (r_loop / (4.0 * a.min_pwm_hz * l_loop)).tanh();
    assert!((at_required_pwm - settings.ripple_limit_fraction * cfg.max_current_a).abs() < 1e-9);
    let mut higher_bus = cfg.clone();
    higher_bus.supply_voltage_v *= 2.0;
    let higher = analyze_drive(&higher_bus, &two_strand_fixture(), &settings, Some(0.5));
    assert!((higher.ripple_pp_a - 2.0 * a.ripple_pp_a).abs() < 1e-10);
    assert_eq!(higher.thrust_n, a.thrust_n);
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
fn braid_fixture_produces_plausible_values() {
    let ctx = RoutingContext {
        active_area_length_mm: 147.0,
        board_width_mm: 20.0,
        num_layers: 4,
        phases: 3,
        min_trace_mm: 0.127,
        trace_width_mm: 0.127,
        min_space_mm: 0.127,
        expects_continuous: false,
        params: Default::default(),
        magnet_pitch_mm: Some(6.0),
        magnet_array_span_mm: Some(72.0),
        phase_clearance_mm: None,
    };
    let routing = generate_routing_result(&ctx, "infinity-braid").expect("braid");
    let s = SimulationInput { num_layers: 4, min_trace_m: 0.127e-3, magnet_pitch_m: 6e-3, ..SimulationInput::default() };
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
