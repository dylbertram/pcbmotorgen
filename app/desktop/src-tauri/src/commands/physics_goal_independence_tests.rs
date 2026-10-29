//! Numerical accuracy is not a requirement to meet performance goals.
use super::*;
use pcbmotorgen_simulation::drive::{DriveAnalysis, DriveSettings};

fn config() -> LinearMotorConfigIpc {
    let mut c = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
    c.routing_params.insert("connection".into(), 2.0);
    c.n_positions = 9;
    c.meshing = 3;
    c
}

fn changed_goals(mut c: LinearMotorConfigIpc) -> LinearMotorConfigIpc {
    c.target_force_n = 100.0;
    c.peak_force_n = 0.001; // Deliberately contradictory design goals.
    c.max_accel_m_s2 = 0.0;
    c.max_temperature_rise_c = 0.0;
    // max_current_a remains fixed: in a static sweep this is actual excitation.
    c
}

fn value(v: impl serde::Serialize) -> serde_json::Value {
    serde_json::to_value(v).unwrap()
}

pub(super) fn assert_electrical_equal(a: &DriveAnalysis, b: &DriveAnalysis) {
    let a = value(a);
    let b = value(b);
    // Recommendations/check statuses legitimately depend on the requested goals.
    // These physical results must not. Evaluate voltage at the SAME speed/current.
    for key in [
        "phase_resistance_ohm",
        "phase_inductance_h",
        "mutual_inductance_h",
        "phase_inductance_matrix_h",
        "line_inductance_h",
        "synchronous_inductance_h",
        "effective_inductance_h",
        "line_resistance_ohm",
        "time_constant_s",
        "holding_voltage_v",
        "speed_voltage_v",
        "ripple_pp_a",
        "peak_current_a",
        "copper_loss_w",
        "thrust_n",
        "thrust_constant_n_per_a",
        "back_emf_constant_v_s_per_m",
    ] {
        assert_eq!(a[key], b[key], "Design goals changed calculated {key}");
    }
}

#[test]
fn fields_force_electrical_and_geometry_do_not_benchmark_against_goals() {
    let c = config();
    let changed = changed_goals(c.clone());
    let drive = DriveSettings::default();
    let run = |c: LinearMotorConfigIpc| {
        let force = tauri::async_runtime::block_on(evaluate_force_sweep(
            c.clone(),
            None,
            Some(drive.clone()),
        ))
        .unwrap();
        let kf = force.mean_thrust_n / force.current_a;
        let electrical =
            tauri::async_runtime::block_on(analyze_drive(c.clone(), drive.clone(), Some(kf), None))
                .unwrap();
        let field = tauri::async_runtime::block_on(sample_b_field(
            c.clone(),
            3,
            3,
            [0.0, 0.01],
            [0.001, 0.005],
        ))
        .unwrap();
        let height = tauri::async_runtime::block_on(compute_height_stack(c.clone())).unwrap();
        let friction = tauri::async_runtime::block_on(compute_friction(c.clone())).unwrap();
        let geometry = tauri::async_runtime::block_on(generate_coils(c.clone())).unwrap();
        let travel = tauri::async_runtime::block_on(travel_envelope(c)).unwrap();
        (
            value(force),
            electrical,
            value(field),
            value(height),
            value(friction),
            value(geometry),
            value(travel),
        )
    };
    let a = run(c);
    let b = run(changed);
    assert_eq!(a.0, b.0);
    assert_electrical_equal(&a.1, &b.1);
    assert_eq!((a.2, a.3, a.4, a.5, a.6), (b.2, b.3, b.4, b.5, b.6));
}

#[test]
fn failing_goal_advice_does_not_change_physics() {
    let c = config();
    let mut easy = c.clone();
    easy.target_force_n = 0.001;
    let mut strict = c;
    strict.target_force_n = 100.0;
    strict.peak_force_n = 101.0;
    let settings = DriveSettings::default();
    let a = tauri::async_runtime::block_on(analyze_drive(easy, settings.clone(), Some(0.4), None))
        .unwrap();
    let mut goals = settings;
    goals.voltage_headroom = 0.01;
    goals.ripple_limit_fraction = 0.0001;
    goals.allowed_rise_c = 0.1;
    let b = tauri::async_runtime::block_on(analyze_drive(strict, goals, Some(0.4), None)).unwrap();
    assert_electrical_equal(&a, &b);
    let thrust_status =
        |a: &DriveAnalysis| a.checks.iter().find(|c| c.id == "thrust").unwrap().status;
    assert_ne!(
        thrust_status(&a),
        thrust_status(&b),
        "Exercise different advice without requiring either design to pass"
    );
}

#[test]
fn visualization_dc_geometry_and_housing_do_not_benchmark_against_goals() {
    use pcbmotorgen_simulation::backplane::{
        BackplaneStack, HousingMaterial, HousingMotionProfile, HousingSpec,
    };
    use pcbmotorgen_simulation::visualization::VisualizationRequest;
    let c = config();
    let changed = changed_goals(c.clone());
    let request = VisualizationRequest {
        request_id: "goal-independent".into(),
        mover_position_m: 0.01,
        bounds_m: [[0.0, 0.02], [0.0, 0.008], [-0.001, 0.005]],
        counts: [3, 3, 3],
        phase_peak_a: 1.0,
        fields: true,
        heat: true,
    };
    let preview = |c| {
        value(
            tauri::async_runtime::block_on(
                crate::commands::visualization::sample_simulation_visualization(
                    c,
                    Default::default(),
                    None,
                    request.clone(),
                ),
            )
            .unwrap(),
        )
    };
    let a = preview(c.clone());
    let b = preview(changed.clone());
    assert_eq!(a["field"], b["field"]);
    assert_eq!(a["heat"], b["heat"]);
    assert!(a["heat_unavailable_reason"].is_null() && b["heat_unavailable_reason"].is_null());
    let dc = |c| {
        tauri::async_runtime::block_on(prepare_dc_winding_geometry(c, Default::default(), None))
            .unwrap()
    };
    let a = dc(c.clone());
    let b = dc(changed.clone());
    for key in ["networks", "finite_copper", "routing", "geometry_hints"] {
        assert_eq!(a[key], b[key]);
    }
    let housing = |mut c: LinearMotorConfigIpc| {
        c.backplane = Some(BackplaneStack {
            layers: vec![],
            housing: Some(HousingSpec {
                material: HousingMaterial::Aluminum6061,
                thickness_m: 0.001,
                gap_m: 0.001,
            }),
        });
        value(
            tauri::async_runtime::block_on(analyze_housing_motion(
                c,
                HousingMotionProfile { duration_s: 0.1 },
                0.3,
                None,
            ))
            .unwrap(),
        )
    };
    assert_eq!(housing(c), housing(changed));
}
