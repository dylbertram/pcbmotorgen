//! Read-only supplied-design regressions. Design goals must not affect demand.
//! Loss coefficients are numerical fixtures, never production presets.
use super::*;

/// Read-only, explicit saved-design screening export. Output must be a new
/// directory selected by the caller; never overwrite an earlier receipt.
#[test]
#[ignore = "Requires supplied designs and a new PCB_MOTOR_SCREENING_OUTPUT directory; screening only"]
fn export_saved_design_screening_inputs() {
    use std::io::Write;
    let root = std::env::var("PCB_MOTOR_SUPPLIED_DESIGN_DIR").unwrap();
    let output = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_OUTPUT").unwrap());
    std::fs::create_dir(&output).expect("output must be a new, exclusive directory");
    for (file, hash) in [
        ("Fader-traces-workspace.pmmotor", "567d97900475c92598f9ad6f7df9e7aeaf374dfc542fa25fa7e04b90dbfb287b"),
        ("star_2-layer.pmmotor", "0ed215f6ff403b927dbeac1ea3d4d9587489a1f1c0680e4ce3a2a48658475d82"),
    ] {
        let original = std::fs::read(std::path::Path::new(&root).join(file)).unwrap();
        assert_eq!(format!("{:x}", Sha256::digest(&original)), hash);
        let archive: serde_json::Value = serde_json::from_slice(&original).unwrap();
        let version = archive["versions"].as_array().unwrap().iter()
            .find(|v| v["id"] == 1).unwrap();
        let state = &version["state"];
        let mut baseline = inputs(state);
        baseline["move_request"]["loss_model"] = serde_json::Value::Null;
        let c: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(state["config"].clone()).unwrap();
        let start = c.magnet_width_mm * 0.0005;
        for (name, a, b, duration) in [
            ("full-forward", start, start + c.desired_travel_mm * 1e-3, 1.0),
            ("short-forward", start + 0.010, start + 0.011, 0.25),
            ("short-return", start + 0.011, start + 0.010, 0.25),
        ] {
            let mut input = baseline.clone();
            let p = &mut input["move_request"]["profile"];
            p["start_m"] = serde_json::json!(a);
            p["end_m"] = serde_json::json!(b);
            p["duration_s"] = serde_json::json!(duration);
            p["mass_includes"] = serde_json::json!("15 g full moving assembly including magnets, bushings and moving enclosure, user-approved engineering estimate");
            let result = tauri::async_runtime::block_on(evaluate_move_power(
                format!("screening-{file}-{name}"), input.clone())).unwrap();
            assert_eq!(result.inputs, input);
            assert!(result.result.demand.source.is_none());
            let receipt = serde_json::json!({"archive":file,"archive_sha256":hash,"version":1,
                "scenario":name,"native":result});
            let filename = format!("{}-{name}.json", if file.starts_with("Fader") {"fader"} else {"star2"});
            let mut out = std::fs::OpenOptions::new().write(true).create_new(true).open(output.join(filename)).unwrap();
            serde_json::to_writer(&mut out, &receipt).unwrap();
            out.write_all(b"\n").unwrap();
        }
        assert_eq!(std::fs::read(std::path::Path::new(&root).join(file)).unwrap(), original);
    }
}

#[test]
#[ignore = "Requires screening baseline/model directories and a new output directory; bounded local scenario only"]
fn evaluate_saved_design_screening_assumptions() {
    use std::io::Write;
    let baselines = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_BASELINES").unwrap());
    let models = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_MODELS").unwrap());
    let output = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_OUTPUT").unwrap());
    let estimate = std::env::var_os("PCB_MOTOR_ENGINEERING_ESTIMATE").is_some();
    std::fs::create_dir(&output).expect("output must be a new, exclusive directory");
    for design in ["fader", "star2"] {
        for scenario in ["full-forward", "short-forward", "short-return"] {
            let filename = format!("{design}-{scenario}.json");
            let receipt: serde_json::Value = serde_json::from_slice(&std::fs::read(baselines.join(&filename)).unwrap()).unwrap();
            let model: serde_json::Value = serde_json::from_slice(&std::fs::read(models.join(&filename)).unwrap()).unwrap();
            assert!(!model["omitted_losses"].as_array().unwrap().is_empty());
            let mut input = receipt["native"]["inputs"].clone();
            input["move_request"]["loss_model"] = model;
            let mut records = Vec::new();
            let mut previous: Option<(f64, f64)> = None;
            for (positions, dt) in [(129, 0.0005), (193, 0.0005), (193, 0.00025)] {
                input["move_request"]["force_positions"] = serde_json::json!(positions);
                input["move_request"]["profile"]["time_step_s"] = serde_json::json!(dt);
                let r = tauri::async_runtime::block_on(evaluate_move_power(
                    format!("screen-{design}-{scenario}-{positions}-{dt}"), input.clone())).unwrap();
                assert_eq!(r.inputs, input);
                let m = &r.result.demand;
                assert_eq!(m.source_model_scope, if estimate { "engineering_estimate" } else { "partial_declared_scenario" });
                let source = m.source.as_ref().unwrap();
                let scale = m.accounted_loss_energy_j.max(1e-6);
                assert!(m.source_balance_residual_j.unwrap().abs() < 1e-6 * scale);
                assert!(m.mechanical_balance_residual_j.abs() < 1e-8);
                assert!((source.net_energy_j - m.mechanical_work_j - m.accounted_loss_energy_j - m.magnetic_energy_change_j).abs() < 1e-6 * scale);
                assert!((source.sampled_positive_peak_current_a * 12.0 - source.sampled_positive_peak_power_w).abs() < 1e-9);
                if let Some((old_energy, old_peak)) = previous {
                    let energy_delta = (source.net_energy_j - old_energy).abs() / source.net_energy_j.abs().max(1e-9);
                    let peak_delta = (source.sampled_positive_peak_power_w - old_peak).abs() / source.sampled_positive_peak_power_w.abs().max(1e-9);
                    eprintln!("{design} {scenario} {positions} {dt}: energy change {energy_delta:.6}, peak change {peak_delta:.6}");
                    assert!(energy_delta < 0.02 && peak_delta < 0.02, "unchanged 2% spatial/time convergence gates");
                }
                previous = Some((source.net_energy_j, source.sampled_positive_peak_power_w));
                records.push(r);
            }
            let mut out = std::fs::OpenOptions::new().write(true).create_new(true).open(output.join(&filename)).unwrap();
            serde_json::to_writer(&mut out, &records).unwrap();
            out.write_all(b"\n").unwrap();
        }
    }
}

#[test]
#[ignore = "Requires screening result receipts and a new output directory; assumption sensitivity only"]
fn screening_assumption_sensitivity() {
    use std::io::Write;
    let base = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_RESULTS").unwrap());
    let output = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_OUTPUT").unwrap());
    std::fs::create_dir(&output).expect("output must be new");
    for design in ["fader", "star2"] {
        let filename = format!("{design}-full-forward.json");
        let baseline: Vec<serde_json::Value> = serde_json::from_slice(&std::fs::read(base.join(&filename)).unwrap()).unwrap();
        let reference = baseline.last().unwrap();
        let mut records = Vec::new();
        for (label, ripple_scale, driver_scale) in [("lower", 0.5, 0.5), ("higher", 2.0, 2.0)] {
            let mut input = reference["inputs"].clone();
            let model = &mut input["move_request"]["loss_model"];
            for row in model["ripple"]["covariance_a2"].as_array_mut().unwrap() {
                for entry in row.as_array_mut().unwrap() { *entry = serde_json::json!(entry.as_f64().unwrap() * ripple_scale * ripple_scale); }
            }
            for entry in model["ripple"]["peak_deviation_a"].as_array_mut().unwrap() { *entry = serde_json::json!(entry.as_f64().unwrap() * ripple_scale); }
            for entry in model["external_core_loss_w"].as_array_mut().unwrap() { *entry = serde_json::json!(entry.as_f64().unwrap() * ripple_scale * ripple_scale); }
            for key in ["switching", "deadtime"] {
                model[key]["abs_mean_current_j_per_a"] = serde_json::json!(model[key]["abs_mean_current_j_per_a"].as_f64().unwrap() * driver_scale);
            }
            model["reference"] = serde_json::json!(format!("{}; {label} sensitivity: ripple ×{ripple_scale}, Q proxy ×{}, driver switching/dead-time ×{driver_scale}; not component data", model["reference"].as_str().unwrap(), ripple_scale * ripple_scale));
            model["ripple"]["reference"] = serde_json::json!(format!("{}; ripple ×{ripple_scale} sensitivity", model["ripple"]["reference"].as_str().unwrap()));
            let result = tauri::async_runtime::block_on(evaluate_move_power(format!("{design}-{label}"), input)).unwrap();
            let demand = &result.result.demand;
            assert_eq!(demand.source_model_scope, "partial_declared_scenario");
            assert!(demand.source_balance_residual_j.unwrap().abs() < 1e-6 * demand.accounted_loss_energy_j.max(1e-6));
            eprintln!("{design} {label}: {}", serde_json::to_string(&demand.source).unwrap());
            records.push(result);
        }
        let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(output.join(filename)).unwrap();
        serde_json::to_writer(&mut file, &records).unwrap();
        file.write_all(b"\n").unwrap();
    }
}

#[test]
#[ignore = "Requires engineering results and new output directory; hypothetical winding sensitivity only"]
fn winding_ac_uncertainty_sensitivity() {
    use std::io::Write;
    let base = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_RESULTS").unwrap());
    let output = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SCREENING_OUTPUT").unwrap());
    std::fs::create_dir(&output).expect("output must be new");
    for design in ["fader", "star2"] {
        let filename = format!("{design}-full-forward.json");
        let baseline: Vec<serde_json::Value> = serde_json::from_slice(&std::fs::read(base.join(&filename)).unwrap()).unwrap();
        let reference = baseline.last().unwrap();
        let r = reference["result"]["drive"]["phases"].as_array().unwrap().iter()
            .map(|p| p["resistance_hot_ohm"].as_f64().unwrap()).collect::<Vec<_>>();
        let mut results = Vec::new();
        // Stress tests, not new purported component data or fitted values.
        for multiplier in [0.10, 1.0] {
            let mut input = reference["inputs"].clone();
            let model = &mut input["move_request"]["loss_model"];
            for key in ["winding_fundamental_ac_increment_ohm", "winding_ripple_ac_increment_ohm"] {
                for (i, entry) in model[key].as_array_mut().unwrap().iter_mut().enumerate() {
                    *entry = serde_json::json!(entry.as_f64().unwrap() + multiplier * r[i]);
                }
            }
            model["reference"] = serde_json::json!(format!("{}; hypothetical AC sensitivity adds {:.0}% hot DC phase resistance, not measured winding data", model["reference"].as_str().unwrap(), 100.0 * multiplier));
            let result = tauri::async_runtime::block_on(evaluate_move_power(format!("{design}-ac-{multiplier}"), input)).unwrap();
            let demand = &result.result.demand;
            assert_eq!(demand.source_model_scope, "engineering_estimate");
            assert!(demand.source_balance_residual_j.unwrap().abs() < 1e-6 * demand.accounted_loss_energy_j.max(1e-6));
            eprintln!("{design} winding +{:.0}% R: {}", 100.0 * multiplier, serde_json::to_string(&demand.source).unwrap());
            results.push(result);
        }
        let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(output.join(filename)).unwrap();
        serde_json::to_writer(&mut file, &results).unwrap();
        file.write_all(b"\n").unwrap();
    }
}

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
