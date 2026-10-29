use super::*;
use pcbmotorgen_simulation::drive::move_power::{MoveProfile, WindingModel};

fn profile() -> MoveProfile {
    MoveProfile {
        start_m: 0.0025,
        end_m: 0.0035,
        initial_velocity_m_s: 0.0,
        final_velocity_m_s: 0.0,
        duration_s: 1.0,
        travel_min_m: 0.0025,
        travel_max_m: 0.0655,
        max_speed_m_s: 0.5,
        max_acceleration_m_s2: 2.0,
        max_deceleration_m_s2: 2.0,
        moving_mass_kg: 0.015,
        mass_includes:
            "Numerical validation scenario only: 15 g assumed total; cap breakdown unconfirmed"
                .into(),
        coulomb_friction_n: 0.05,
        damping_n_s_per_m: 0.0,
        external_load_n: 0.0,
        time_step_s: 0.001,
    }
}

#[test]
fn generated_unknown_and_delta_connections_are_not_silently_reinterpreted() {
    let mut config = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
    assert!(validate_star(&config, None).is_err());
    config.routing_params.insert("connection".into(), 1.0);
    assert!(validate_star(&config, None).is_err());
    config.routing_params.insert("connection".into(), 2.0);
    assert!(validate_star(&config, None).is_ok());
}

#[test]
fn public_move_command_rejects_rotary_or_unspecified_topology_before_work() {
    for inputs in [
        serde_json::json!({"topology":"radial"}),
        serde_json::json!({}),
    ] {
        let error =
            tauri::async_runtime::block_on(evaluate_move_power("topology-check".into(), inputs))
                .unwrap_err();
        assert!(error.contains("explicit linear topology"));
    }
}

#[test]
fn saved_housing_cannot_silently_lose_its_dynamic_drag_and_eddy_losses() {
    let mut sim = crate::config::LinearMotorConfig::default().to_simulation();
    let stack = serde_json::json!({ "layers":[{"material":"flex_ferrite", "thickness_m":0.0002}],
        "housing":{"material":"aluminum6061", "thickness_m":0.001, "gap_m":0.0001} });
    sim.backplane = Some(serde_json::from_value(stack.clone()).unwrap());
    let request = RoutedMoveRequest {
        profile: profile(),
        control: WindingModel::BalancedStarSinusoidal,
        electrical_angle_at_zero_rad: 0.0,
        phase_peak_limit_a: 1.0,
        source: MoveSource::StiffDcLink {
            accepts_regeneration: false,
        },
        additional_driver_loss_w: None,
        force_positions: 65,
    };
    let error = evaluate_routed_move(
        &sim,
        &Default::default(),
        &Default::default(),
        &Default::default(),
        &request,
        4,
        &|| false,
    )
    .unwrap_err();
    assert!(error.contains("backplane or housing"));
    assert_eq!(serde_json::to_value(sim.backplane.unwrap()).unwrap(), stack);
}

#[test]
fn ownership_cancellation_is_identity_bound_and_released_on_drop() {
    let permit = MovePermit::acquire("move-ownership-regression".into()).unwrap();
    assert!(MovePermit::acquire("other".into()).is_err());
    assert!(!cancel_move_power("other".into()).unwrap());
    assert!(!permit.cancelled());
    assert!(cancel_move_power(permit.id.clone()).unwrap());
    assert!(permit.cancelled());
    assert!(MovePermit::acquire("next".into()).is_err());
    drop(permit);
    assert!(MovePermit::acquire("next".into()).is_ok());
}

/// Read-only actual supplied file diagnostic. Does not edit or migrate the
/// original, invent a mass breakdown, or substitute generated copper.
#[test]
#[ignore = "Requires PCB_MOTOR_PROJECT_PATH and explicit bounded local execution"]
fn supplied_saved_design_phase_diagnostics() {
    let path = std::env::var("PCB_MOTOR_PROJECT_PATH").expect("set PCB_MOTOR_PROJECT_PATH");
    let bytes = std::fs::read(&path).unwrap();
    let hash = Sha256::digest(&bytes);
    let file: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    let state = &file["versions"][0]["state"];
    let config: crate::ipc::ProjectConfigStateIpc =
        serde_json::from_value(state["config"].clone()).unwrap();
    let cad: CadGeometry = serde_json::from_value(state["cad_geometry"].clone()).unwrap();
    let ipc = config.to_linear_motor_ipc();
    validate_star(&ipc, Some(&cad)).unwrap();
    let core = ipc.to_core();
    let board = super::super::cad_source::CadBoard::new(&cad, &core).unwrap();
    let sim = board.simulation_input(&cad, &core);
    let hints = super::super::cad_source::CadBoard::drive_hints(&cad);
    let (evaluator, _) = pcbmotorgen_simulation::ForceEvaluator::new(
        2,
        4,
        pcbmotorgen_simulation::CommutationMode::MaxThrust,
        0.0,
    )
    .with_routed_currents(&board.routing, &sim, &config.drive, &hints)
    .unwrap();
    let bounds = evaluator.sweep_center_limits_m(&sim).unwrap();
    eprintln!(
        "file={path}, sha256={hash:x}, full_overlap_bounds_m={bounds:?}, explicit depths={:?}",
        hints.layer_z_m
    );
    // Print actual unit phase coefficients and their balanced-sine coupling.
    // These diagnostics do not select a new controller reference for the user.
    for x in [0.0025, 0.0085, 0.0145, 0.0655] {
        let k = evaluator.unit_phase_force_constants_at(&sim, x).unwrap();
        let theta = std::f64::consts::TAU * x / (2.0 * sim.magnet_pitch_m);
        let q = |offset: f64| {
            k.iter()
                .enumerate()
                .map(|(j, k)| k * (theta + offset - std::f64::consts::TAU * j as f64 / 3.0).sin())
                .sum::<f64>()
        };
        eprintln!(
            "x={x:.9} m; force_per_terminal_amp={k:?} N/A; q(offset=0)={:.9}, q(offset=pi/2)={:.9}",
            q(0.0),
            q(std::f64::consts::FRAC_PI_2)
        );
    }
    assert_eq!(
        &Sha256::digest(std::fs::read(&path).unwrap())[..],
        &hash[..]
    );
}

#[test]
fn invalid_move_requirements_are_rejected_before_a_force_map() {
    let mut request = RoutedMoveRequest {
        profile: profile(),
        control: WindingModel::BalancedStarSinusoidal,
        electrical_angle_at_zero_rad: 0.0,
        phase_peak_limit_a: 1.0,
        source: MoveSource::StiffDcLink {
            accepts_regeneration: false,
        },
        additional_driver_loss_w: None,
        force_positions: 1,
    };
    let core = crate::config::LinearMotorConfig::default();
    let error = evaluate_routed_move(
        &core.to_simulation(),
        &Default::default(),
        &Default::default(),
        &Default::default(),
        &request,
        4,
        &|| false,
    )
    .unwrap_err();
    assert!(error.contains("positions"));
    request.force_positions = 3;
    request.control = WindingModel::Delta;
    assert!(evaluate_routed_move(
        &core.to_simulation(),
        &Default::default(),
        &Default::default(),
        &Default::default(),
        &request,
        4,
        &|| false
    )
    .unwrap_err()
    .contains("balanced-star"));
}

#[test]
#[ignore = "Requires PCB_MOTOR_PROJECT_PATH; explicit read-only saved-design scenario, not hardware evidence"]
fn supplied_saved_design_move_scenario() {
    let path = std::env::var("PCB_MOTOR_PROJECT_PATH").expect("set PCB_MOTOR_PROJECT_PATH");
    let original = std::fs::read(&path).unwrap();
    let file: serde_json::Value = serde_json::from_slice(&original).unwrap();
    let state = &file["versions"][0]["state"];
    eprintln!("Read-only saved-design scenario: file={path}, file_sha256={:x}, explicitly selected version={}", Sha256::digest(&original), file["versions"][0]["id"]);
    let config: crate::ipc::ProjectConfigStateIpc =
        serde_json::from_value(state["config"].clone()).unwrap();
    let cad: Option<CadGeometry> = serde_json::from_value(state["cad_geometry"].clone()).unwrap();
    let mut p = profile();
    p.start_m = config.magnet_width_mm * 0.0005;
    p.end_m = p.start_m + config.desired_travel_mm * 1e-3;
    p.travel_min_m = p.start_m;
    p.travel_max_m = p.end_m;
    p.max_speed_m_s = config.drive.target_speed_m_s;
    p.max_acceleration_m_s2 = config.max_accel_m_s2;
    p.max_deceleration_m_s2 = config.max_accel_m_s2; // Explicit symmetric test scenario only.
    p.moving_mass_kg = config.carriage_mass_kg;
    p.coulomb_friction_n = config.friction_n;
    let mut request = RoutedMoveRequest {
        profile: p,
        control: WindingModel::BalancedStarSinusoidal,
        // Explicit test-controller choice, not static-preview calibration.
        electrical_angle_at_zero_rad: std::f64::consts::FRAC_PI_2,
        phase_peak_limit_a: config.max_current_a,
        source: MoveSource::StiffDcLink {
            accepts_regeneration: true,
        },
        additional_driver_loss_w: None,
        force_positions: 65,
    };
    let permit = MovePermit::acquire("saved-design-move-regression".into()).unwrap();
    let result = calculate(
        config.to_linear_motor_ipc(),
        config.drive.clone(),
        request,
        cad,
        &permit,
    )
    .unwrap();
    let r = &result.result.demand;
    eprintln!(
        "input_sha256={} provenance={} full_overlap={:?}",
        result.input_sha256, result.provenance, result.result.full_overlap_bounds_m
    );
    eprintln!("requested_distance={} m, feasible={}, factors={:?}, missing={:?}, copper={} J, mechanical={} J, electrical_residual={} J, mechanical_residual={} J, phase_rms={:?} A",
        r.requested_distance_m, r.feasible, r.limiting_factors, r.missing_inputs, r.copper_energy_j,
        r.mechanical_work_j, r.electrical_balance_residual_j, r.mechanical_balance_residual_j, r.phase_rms_a);
    assert_eq!(r.requested_distance_m, config.desired_travel_mm * 1e-3);
    assert!(r.electrical.phase_model.is_some());
    assert!(
        r.source.is_none(),
        "Unknown additional driver losses must withhold total source demand"
    );
    assert_eq!(result.inputs["cad_geometry"], state["cad_geometry"]);
    if std::env::var_os("PCB_MOTOR_MOVE_REFINEMENT").is_some() {
        let mut previous = result.result.demand;
        // Spatial refinement at fixed dt, then time refinement at fixed map.
        for (positions, dt) in [(97, 0.001), (129, 0.001), (129, 0.0005)] {
            request = serde_json::from_value(result.inputs["move_request"].clone()).unwrap();
            request.force_positions = positions;
            request.profile.time_step_s = dt;
            let refined = calculate(
                config.to_linear_motor_ipc(),
                config.drive.clone(),
                request.clone(),
                serde_json::from_value(state["cad_geometry"].clone()).unwrap(),
                &permit,
            )
            .unwrap();
            let r = refined.result.demand;
            let positive_peak = |r: &pcbmotorgen_simulation::drive::move_power::MovePowerResult| {
                r.samples
                    .iter()
                    .map(|s| s.partial_dc_link_power_w)
                    .fold(0.0, f64::max)
            };
            let copper_change =
                (r.copper_energy_j - previous.copper_energy_j).abs() / r.copper_energy_j;
            let peak_change =
                (positive_peak(&r) - positive_peak(&previous)).abs() / positive_peak(&r);
            eprintln!("force_positions={positions}, dt={dt} s; copper={} J, copper_change={copper_change:.6}, partial_peak={} W, peak_change={peak_change:.6}, electrical_residual={} J, mechanical_residual={} J", r.copper_energy_j, positive_peak(&r), r.electrical_balance_residual_j, r.mechanical_balance_residual_j);
            assert!(r.electrical_balance_residual_j.abs() < 1e-6 * r.copper_energy_j.max(1e-6));
            assert!(r.mechanical_balance_residual_j.abs() < 1e-9);
            if positions == 129 {
                assert!(
                    copper_change < 0.02,
                    "Finest two force/time grids must agree in copper energy within 2%"
                );
                assert!(
                    peak_change < 0.02,
                    "Finest two force/time grids must agree in partial peak within 2%"
                );
            }
            previous = r;
        }
        let mut reverse: RoutedMoveRequest =
            serde_json::from_value(result.inputs["move_request"].clone()).unwrap();
        reverse.profile.start_m += 0.01;
        reverse.profile.end_m = reverse.profile.start_m - 0.001;
        reverse.profile.duration_s = 0.25;
        reverse.profile.time_step_s = 0.0005;
        reverse.force_positions = 129;
        let reverse = calculate(
            config.to_linear_motor_ipc(),
            config.drive.clone(),
            reverse,
            serde_json::from_value(state["cad_geometry"].clone()).unwrap(),
            &permit,
        )
        .unwrap()
        .result
        .demand;
        eprintln!("Short reverse scenario: distance={} m, feasible={}, electrical_residual={} J, mechanical_residual={} J", reverse.requested_distance_m, reverse.feasible, reverse.electrical_balance_residual_j, reverse.mechanical_balance_residual_j);
        assert!((reverse.requested_distance_m + 0.001).abs() < 1e-15);
        assert!(
            reverse.electrical_balance_residual_j.abs() < 1e-6 * reverse.copper_energy_j.max(1e-6)
        );
        assert!(reverse.mechanical_balance_residual_j.abs() < 1e-9);
        assert!(reverse.friction_damping_energy_j > 0.0);
        if reverse.feasible {
            // Separate explicitly idealized scenario, never a hardware total
            // or a substitute for unknown driver/inductor/ripple losses.
            let mut ideal_electrical = reverse.electrical.clone();
            ideal_electrical.additional_driver_loss_w = Some(0.0);
            let ideal = pcbmotorgen_simulation::drive::move_power::evaluate_move(
                &reverse.profile,
                &ideal_electrical,
            )
            .unwrap();
            let source = ideal.source.as_ref().unwrap();
            let accounted = ideal.copper_energy_j
                + ideal.conduction_energy_j
                + ideal.mechanical_work_j
                + ideal.magnetic_energy_change_j;
            assert!(
                (source.net_energy_j - accounted).abs() < 1e-6 * ideal.copper_energy_j.max(1e-6)
            );
            assert!(
                (source.average_power_w - source.net_energy_j / ideal.profile.duration_s).abs()
                    < 1e-12
            );
            assert!(
                (source.sampled_positive_peak_current_a
                    - source.sampled_positive_peak_power_w / ideal.electrical.source_voltage_v)
                    .abs()
                    < 1e-12
            );
            eprintln!("Explicitly idealized short-move source scenario, NOT hardware total, worst-case bound or ticket completion: {}", serde_json::to_string(source).unwrap());
        }
    }
    assert_eq!(
        std::fs::read(&path).unwrap(),
        original,
        "Never edit the supplied design"
    );
}
