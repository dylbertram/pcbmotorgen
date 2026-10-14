use super::*;
use pcbmotorgen_routing::{
    generate_routing_result, Point, RouteSegment, RoutingContext, RoutingResult, Via,
};

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
}

#[test]
fn ripple_and_voltage_follow_the_formulas() {
    let settings = DriveSettings::default();
    let a = analyze_drive(&sim(), &two_strand_fixture(), &settings, Some(0.5));
    let expected_ripple = 12.0 / (8.0 * settings.pwm_hz * a.synchronous_inductance_h);
    assert!((a.ripple_pp_a - expected_ripple).abs() / expected_ripple < 1e-9);
    let hold = 3f64.sqrt() * 0.8 * a.phase_resistance_ohm + 0.8 * settings.driver.rds_on_ohm;
    assert!((a.holding_voltage_v - hold).abs() < 1e-9);
    assert!(a.speed_voltage_v.unwrap() > a.holding_voltage_v);
    let vmax = a.max_speed_m_s.unwrap();
    assert!(vmax > 0.0);
    assert_eq!(a.thrust_n, Some(0.4));
    assert!(a.checks.iter().all(|c| c.status != CheckStatus::Unknown));
}

#[test]
fn braid_fixture_produces_plausible_values() {
    let ctx = RoutingContext {
        active_area_length_mm: 147.0,
        board_width_mm: 20.0,
        num_layers: 4,
        phases: 3,
        min_trace_mm: 0.127,
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
