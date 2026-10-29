//! Read-only supplied-design regressions. Design goals must not affect demand.
//! Loss coefficients are numerical fixtures, never production presets.
use super::*;

pub(super) fn inputs(state: &serde_json::Value) -> serde_json::Value {
    let c: crate::ipc::ProjectConfigStateIpc =
        serde_json::from_value(state["config"].clone()).unwrap();
    let mut p = profile();
    p.start_m = c.magnet_width_mm * 0.0005 + 0.01;
    p.end_m = p.start_m - 0.001;
    p.duration_s = 0.25;
    p.time_step_s = 0.0005;
    p.travel_min_m = c.magnet_width_mm * 0.0005;
    p.travel_max_m = p.travel_min_m + c.desired_travel_mm * 1e-3;
    p.max_speed_m_s = c.drive.target_speed_m_s;
    p.max_acceleration_m_s2 = c.max_accel_m_s2;
    p.max_deceleration_m_s2 = c.max_accel_m_s2;
    p.moving_mass_kg = c.carriage_mass_kg;
    p.mass_includes = "Configured carriage mass retained; complete moving assembly/cap coverage unconfirmed. Numerical validation only.".into();
    p.coulomb_friction_n = c.friction_n;
    let request = RoutedMoveRequest {
        profile: p,
        control: WindingModel::BalancedStarSinusoidal,
        electrical_angle_at_zero_rad: std::f64::consts::FRAC_PI_2,
        phase_peak_limit_a: c.max_current_a,
        source: MoveSource::StiffDcLink {
            accepts_regeneration: true,
        },
        additional_driver_loss_w: None,
        loss_model: Some(declared_test_losses(&c)),
        force_positions: 129,
    };
    serde_json::json!({ "topology":"linear", "config":c.to_linear_motor_ipc(), "drive":c.drive,
        "cad_geometry":state["cad_geometry"], "move_request":request })
}

#[test]
#[ignore = "Requires PCB_MOTOR_SUPPLIED_DESIGN_DIR; read-only numerical loss fixtures, not hardware data"]
fn supplied_loss_model_demand_is_independent_of_design_goals() {
    let root = std::env::var("PCB_MOTOR_SUPPLIED_DESIGN_DIR")
        .expect("set PCB_MOTOR_SUPPLIED_DESIGN_DIR to the supplied archives folder");
    // Pin exact input archives. A changed archive needs deliberate requalification.
    for (filename, expected_hash) in [
        (
            "star_2-layer.pmmotor",
            "0ed215f6ff403b927dbeac1ea3d4d9587489a1f1c0680e4ce3a2a48658475d82",
        ),
        (
            "star_4-layer.pmmotor",
            "6a550dcb4327a6e846582fb883c4958a0d275cba85b33271337deee405794e81",
        ),
    ] {
        let path = std::path::Path::new(&root).join(filename);
        let original = std::fs::read(&path).unwrap();
        assert_eq!(format!("{:x}", Sha256::digest(&original)), expected_hash);
        let archive: serde_json::Value = serde_json::from_slice(&original).unwrap();
        let version = archive["versions"]
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["id"] == 1)
            .expect("Select version 1 explicitly, not the active or first version");
        let base = inputs(&version["state"]);
        let mut previous: Option<(f64, f64, f64)> = None;
        for (positions, dt) in [(129, 0.0005), (193, 0.0005), (193, 0.00025)] {
            let mut input = base.clone();
            input["move_request"]["force_positions"] = serde_json::json!(positions);
            input["move_request"]["profile"]["time_step_s"] = serde_json::json!(dt);
            let result = tauri::async_runtime::block_on(evaluate_move_power(
                format!("rejected-loss-{filename}-{positions}-{dt}"),
                input.clone(),
            ))
            .unwrap();
            assert_eq!(result.inputs, input);
            let m = &result.result.demand;
            let source = m
                .source
                .as_ref()
                .expect("Design goals cannot suppress calculated demand");
            assert_eq!(m.source_model_scope, "declared_loss_model");
            assert!(m.loss_energy.is_some());
            let scale = m.accounted_loss_energy_j.max(1e-6);
            assert!(m.source_balance_residual_j.unwrap().abs() < 1e-6 * scale);
            assert!(m.mechanical_balance_residual_j.abs() < 1e-8);
            let peak = m.sampled_phase_peak_including_declared_ripple_a.unwrap();
            let voltage = m
                .samples
                .iter()
                .map(|s| s.required_line_voltage_v)
                .fold(0.0, f64::max);
            assert!(
                (source.net_energy_j
                    - m.mechanical_work_j
                    - m.accounted_loss_energy_j
                    - m.magnetic_energy_change_j)
                    .abs()
                    < 1e-6 * scale
            );
            if positions == 129 {
                let mut changed = input.clone();
                changed["config"]["max_current_a"] = serde_json::json!(0.0);
                changed["config"]["target_force_n"] = serde_json::json!(100.0);
                changed["config"]["peak_force_n"] = serde_json::json!(0.001);
                changed["config"]["max_accel_m_s2"] = serde_json::json!(0.0);
                changed["drive"]["target_speed_m_s"] = serde_json::json!(0.0001);
                changed["drive"]["voltage_headroom"] = serde_json::json!(0.001);
                changed["drive"]["driver"]["peak_current_a"] = serde_json::json!(0.001);
                changed["move_request"]["phase_peak_limit_a"] = serde_json::json!(0.0);
                for key in [
                    "max_speed_m_s",
                    "max_acceleration_m_s2",
                    "max_deceleration_m_s2",
                ] {
                    changed["move_request"]["profile"][key] = serde_json::json!(0.0);
                }
                let rerun = tauri::async_runtime::block_on(evaluate_move_power(
                    format!("independent-goals-{filename}"),
                    changed.clone(),
                ))
                .unwrap();
                assert_eq!(rerun.inputs, changed);
                let other = &rerun.result.demand;
                assert_eq!(serde_json::to_value(&m.samples).unwrap(), serde_json::to_value(&other.samples).unwrap(),
                    "Same geometry, physical settings and move must produce identical traces despite changed goals");
                assert_eq!(
                    serde_json::to_value(&m.source).unwrap(),
                    serde_json::to_value(&other.source).unwrap()
                );
                assert_eq!(m.limiting_factors, other.limiting_factors);
            }
            if let Some((loss, current, line_v)) = previous {
                for (value, old) in [
                    (m.accounted_loss_energy_j, loss),
                    (peak, current),
                    (voltage, line_v),
                ] {
                    assert!(
                        (value - old).abs() / value.abs().max(1e-12) < 0.02,
                        "Separate spatial/time rejection diagnostics must agree within 2%"
                    );
                }
            }
            eprintln!("declared-loss demand fixture {filename} version=1 force_positions={positions} dt={dt} input_sha256={} physical_findings={:?} phase_envelope={peak} A line_voltage={voltage} V accounted_losses={} J source_balance={} J source={}",
                result.input_sha256, m.limiting_factors, m.accounted_loss_energy_j, m.source_balance_residual_j.unwrap(), serde_json::to_string(source).unwrap());
            previous = Some((m.accounted_loss_energy_j, peak, voltage));
        }
        if filename == "star_2-layer.pmmotor" {
            let stack_version = archive["versions"]
                .as_array()
                .unwrap()
                .iter()
                .find(|v| v["id"] == 2)
                .expect("Select saved housing version 2 explicitly");
            let stack_inputs = inputs(&stack_version["state"]);
            assert!(
                !stack_inputs["config"]["backplane"].is_null(),
                "Do not drop the saved stack"
            );
            let error = tauri::async_runtime::block_on(evaluate_move_power(
                "declared-loss-saved-stack-v2".into(),
                stack_inputs,
            ))
            .unwrap_err();
            eprintln!("rejected declared-loss fixture {filename} version=2: {error}");
            assert!(error.contains("dynamic inductance/eddy and drag losses are not integrated"));
        }
        assert_eq!(std::fs::read(path).unwrap(), original);
    }
}
