use super::*;

fn profile() -> MoveProfile {
    MoveProfile {
        start_m: 0.0,
        end_m: 0.01,
        initial_velocity_m_s: 0.0,
        final_velocity_m_s: 0.0,
        duration_s: 1.0,
        travel_min_m: -1.0,
        travel_max_m: 1.0,
        max_speed_m_s: 10.0,
        max_acceleration_m_s2: 100.0,
        max_deceleration_m_s2: 100.0,
        moving_mass_kg: 0.02,
        mass_includes: "Analytic fixture, complete moving mass including cap".into(),
        coulomb_friction_n: 0.0,
        damping_n_s_per_m: 0.0,
        external_load_n: 0.0,
        time_step_s: 0.001,
    }
}

fn electrical() -> MoveElectricalModel {
    MoveElectricalModel {
        winding: WindingModel::BalancedStarSinusoidal,
        phase_resistance_hot_ohm: 0.5,
        effective_phase_inductance_h: 47e-6,
        electrical_period_m: 0.012,
        electrical_angle_at_zero_rad: 0.0,
        force_map: vec![
            ForceConstantPoint {
                position_m: -1.0,
                kf_n_per_a: 2.0,
            },
            ForceConstantPoint {
                position_m: 1.0,
                kf_n_per_a: 2.0,
            },
        ],
        phase_peak_limit_a: 5.0,
        source_voltage_v: 12.0,
        voltage_headroom: 0.85,
        driver_path_resistance_ohm: 0.2,
        additional_driver_loss_w: Some(0.01),
        source_accepts_regeneration: true,
    }
}

fn near(a: f64, b: f64, tolerance: f64) {
    assert!(
        (a - b).abs() <= tolerance,
        "{a:.12e} != {b:.12e}, tolerance {tolerance:.3e}"
    );
}

#[test]
fn resistive_hold_uses_phase_amplitude_not_rms_or_source_current() {
    let mut p = profile();
    p.end_m = p.start_m;
    p.external_load_n = 2.0;
    let e = electrical();
    let r = evaluate_move(&p, &e).unwrap();
    assert!(r.feasible);
    near(r.copper_energy_j, 1.5 * 0.5, 1e-12);
    near(r.conduction_energy_j, 0.75 * 0.2, 1e-12);
    let source = r.source.unwrap();
    near(source.net_energy_j, 0.75 + 0.15 + 0.01, 1e-12);
    near(source.sampled_positive_peak_current_a, 0.91 / 12.0, 1e-12);
    assert!(source.sampled_positive_peak_current_a < 1.0);
    // Parked currents are [0, -sqrt(3)/2, sqrt(3)/2], not 1/sqrt(2).
    near(r.phase_rms_a[0], 0.0, 1e-12);
    near(r.phase_rms_a[1], 3f64.sqrt() / 2.0, 1e-12);
    near(r.magnetic_energy_change_j, 0.0, 1e-12);
    near(r.electrical_balance_residual_j, 0.0, 1e-12);
}

#[test]
fn full_electrical_period_has_rms_amplitude_over_sqrt_two() {
    let mut p = profile();
    p.end_m = 0.012;
    p.initial_velocity_m_s = 0.012;
    p.final_velocity_m_s = 0.012;
    p.external_load_n = 2.0;
    let r = evaluate_move(&p, &electrical()).unwrap();
    for rms in r.phase_rms_a {
        near(rms, 1.0 / 2f64.sqrt(), 1e-12);
    }
    near(r.copper_energy_j, 0.75, 1e-12);
    for s in r.samples {
        near(s.phase_currents_a.iter().sum(), 0.0, 1e-12);
        near(s.phase_currents_a.iter().map(|i| i * i).sum(), 1.5, 1e-12);
        near(s.required_q_voltage_v, 0.5 + 2.0 / 3.0 * 2.0 * 0.012, 1e-12);
    }
}

#[test]
fn constant_speed_work_includes_friction_damping_and_signed_load() {
    let mut p = profile();
    p.end_m = 0.1;
    p.initial_velocity_m_s = 0.1;
    p.final_velocity_m_s = 0.1;
    p.coulomb_friction_n = 0.2;
    p.damping_n_s_per_m = 0.5;
    p.external_load_n = 0.3;
    let r = evaluate_move(&p, &electrical()).unwrap();
    near(r.mechanical_work_j, 0.055, 1e-12);
    near(r.friction_damping_energy_j, 0.025, 1e-12);
    near(r.external_load_work_j, 0.03, 1e-12);
    near(r.mechanical_balance_residual_j, 0.0, 1e-12);
    near(r.electrical_balance_residual_j, 0.0, 1e-12);
    assert!(r.feasible);
}

#[test]
fn acceleration_reconciles_kinetic_and_magnetic_energy() {
    let mut p = profile();
    p.end_m = 0.1;
    p.final_velocity_m_s = 0.15;
    p.coulomb_friction_n = 0.03;
    let r = evaluate_move(&p, &electrical()).unwrap();
    near(
        r.kinetic_energy_change_j,
        0.5 * p.moving_mass_kg * 0.15f64.powi(2),
        1e-12,
    );
    near(
        r.mechanical_work_j,
        r.kinetic_energy_change_j + 0.03 * 0.1,
        2e-9,
    );
    near(r.mechanical_balance_residual_j, 0.0, 2e-9);
    near(r.electrical_balance_residual_j, 0.0, 1e-10);
    let source = r.source.unwrap();
    near(
        source.net_energy_j,
        r.kinetic_energy_change_j
            + r.friction_damping_energy_j
            + r.copper_energy_j
            + r.conduction_energy_j
            + r.magnetic_energy_change_j
            + 0.01 * p.duration_s,
        2e-9,
    );
}

#[test]
fn braking_returns_energy_with_explicit_sink() {
    let mut p = profile();
    p.end_m = 0.05;
    p.initial_velocity_m_s = 0.1;
    p.moving_mass_kg = 1.0;
    let mut e = electrical();
    e.phase_resistance_hot_ohm = 0.0;
    e.driver_path_resistance_ohm = 0.0;
    e.additional_driver_loss_w = Some(0.0);
    e.effective_phase_inductance_h = 0.0;
    let r = evaluate_move(&p, &e).unwrap();
    let source = r.source.unwrap();
    near(source.net_energy_j, -0.005, 1e-8);
    near(source.returned_energy_j, 0.005, 1e-8);
    near(source.drawn_energy_j, 0.0, 1e-12);
    near(r.mechanical_balance_residual_j, 0.0, 1e-8);
}

#[test]
fn braking_without_sink_is_not_reported_as_achievable_supply_demand() {
    let mut p = profile();
    p.end_m = 0.05;
    p.initial_velocity_m_s = 0.1;
    p.moving_mass_kg = 1.0;
    let mut e = electrical();
    e.source_accepts_regeneration = false;
    e.additional_driver_loss_w = Some(0.0);
    let r = evaluate_move(&p, &e).unwrap();
    assert!(!r.feasible);
    assert!(r.source.is_none());
    assert!(r
        .limiting_factors
        .iter()
        .any(|s| s.contains("cannot absorb")));
}

#[test]
fn capacitor_endpoints_do_not_imply_a_source_waveform() {
    near(
        capacitor_energy_change_j(1000e-6, 12.0, 14.0).unwrap(),
        0.026,
        1e-12,
    );
    near(
        capacitor_energy_change_j(1000e-6, 14.0, 12.0).unwrap(),
        -0.026,
        1e-12,
    );
    near(
        capacitor_energy_change_j(1000e-6, 12.0, 12.0).unwrap(),
        0.0,
        1e-12,
    );
    assert!(capacitor_energy_change_j(-1.0, 12.0, 14.0).is_err());
    assert!(capacitor_energy_change_j(1.0, f64::NAN, 14.0).is_err());
}

#[test]
fn zero_distance_zero_current_is_valid_not_nan() {
    let mut p = profile();
    p.end_m = 0.0;
    p.coulomb_friction_n = 5.0; // No fictitious friction work during a stationary hold.
    let mut e = electrical();
    e.phase_peak_limit_a = 0.0;
    e.additional_driver_loss_w = Some(0.0);
    let r = evaluate_move(&p, &e).unwrap();
    assert!(r.feasible);
    near(r.sampled_phase_peak_a, 0.0, 0.0);
    near(r.source.unwrap().net_energy_j, 0.0, 0.0);
    assert_eq!(r.achieved_distance_m, None);
}

#[test]
fn unknown_driver_losses_withhold_total_power_not_partial_diagnostics() {
    let mut e = electrical();
    e.additional_driver_loss_w = None;
    let r = evaluate_move(&profile(), &e).unwrap();
    assert!(r.source.is_none());
    assert!(!r.missing_inputs.is_empty());
    assert!(r
        .samples
        .iter()
        .all(|s| s.required_source_current_a.is_none() && s.required_source_power_w.is_none()));
    assert!(r.samples.iter().any(|s| s.partial_dc_link_power_w > 0.0));
}

#[test]
fn current_and_voltage_limits_reject_motion_without_inventing_saturation_response() {
    let p = profile();
    let mut e = electrical();
    e.phase_peak_limit_a = 0.0;
    let r = evaluate_move(&p, &e).unwrap();
    assert!(!r.feasible);
    assert!(r.source.is_none());
    assert!(r
        .limiting_factors
        .iter()
        .any(|s| s.contains("phase-current")));
    e = electrical();
    e.source_voltage_v = 0.001;
    let r = evaluate_move(&p, &e).unwrap();
    assert!(!r.feasible);
    assert!(r
        .limiting_factors
        .iter()
        .any(|s| s.contains("line voltage")));
    assert_eq!(r.achieved_distance_m, None);
}

#[test]
fn motion_limits_and_asymmetric_acceleration_limits_are_checked() {
    let mut p = profile();
    p.max_speed_m_s = 0.001;
    p.max_deceleration_m_s2 = 0.001;
    let r = evaluate_move(&p, &electrical()).unwrap();
    assert!(!r.feasible);
    assert!(r.limiting_factors.iter().any(|s| s.contains("speed")));
    assert!(r
        .limiting_factors
        .iter()
        .any(|s| s.contains("deceleration")));
    assert_eq!(r.limiting_factors.len(), 2); // Findings are deduplicated.
}

#[test]
fn reverse_move_friction_still_dissipates_and_load_work_keeps_its_sign() {
    let mut p = profile();
    p.end_m = -0.01;
    p.initial_velocity_m_s = -0.01;
    p.final_velocity_m_s = -0.01;
    p.coulomb_friction_n = 0.2;
    p.external_load_n = 0.1;
    let r = evaluate_move(&p, &electrical()).unwrap();
    near(r.friction_damping_energy_j, 0.002, 1e-12);
    near(r.external_load_work_j, -0.001, 1e-12);
    near(r.mechanical_work_j, 0.001, 1e-12);
    near(r.mechanical_balance_residual_j, 0.0, 1e-12);
}

#[test]
fn spatial_force_map_changes_current_and_never_extrapolates() {
    let mut p = profile();
    p.initial_velocity_m_s = 0.01;
    p.final_velocity_m_s = 0.01;
    p.external_load_n = 1.0;
    let mut e = electrical();
    e.force_map = vec![
        ForceConstantPoint {
            position_m: 0.0,
            kf_n_per_a: 1.0,
        },
        ForceConstantPoint {
            position_m: 0.01,
            kf_n_per_a: 2.0,
        },
    ];
    let r = evaluate_move(&p, &e).unwrap();
    near(r.samples[0].q_current_phase_peak_a, 1.0, 1e-12);
    near(r.samples.last().unwrap().q_current_phase_peak_a, 0.5, 1e-12);
    near(
        r.magnetic_energy_change_j,
        0.75 * 47e-6 * (0.25 - 1.0),
        1e-12,
    );
    near(r.electrical_balance_residual_j, 0.0, 2e-10);
    p.end_m = 0.02;
    assert!(evaluate_move(&p, &e).unwrap_err().contains("extrapolation"));
}

#[test]
fn unsupported_models_and_invalid_inputs_fail_explicitly() {
    let p = profile();
    for winding in [WindingModel::Delta, WindingModel::PhaseAOnly] {
        let mut e = electrical();
        e.winding = winding;
        assert!(evaluate_move(&p, &e).unwrap_err().contains("balanced star"));
    }
    for value in [f64::NAN, f64::INFINITY, -1.0, 0.0] {
        let mut invalid = p.clone();
        invalid.duration_s = value;
        assert!(evaluate_move(&invalid, &electrical()).is_err());
    }
    let mut invalid = p.clone();
    invalid.mass_includes.clear();
    assert!(evaluate_move(&invalid, &electrical()).is_err());
    invalid = p.clone();
    invalid.end_m = 2.0;
    assert!(evaluate_move(&invalid, &electrical()).is_err());
    invalid = p;
    invalid.time_step_s = 1e-20;
    assert!(evaluate_move(&invalid, &electrical())
        .unwrap_err()
        .contains("budget"));
    let mut e = electrical();
    e.force_map[1].position_m = e.force_map[0].position_m;
    assert!(evaluate_move(&profile(), &e).is_err());
    e = electrical();
    e.additional_driver_loss_w = Some(-1.0);
    assert!(evaluate_move(&profile(), &e).is_err());
}

#[test]
fn energy_and_sampled_peak_converge_separately_under_time_refinement() {
    let mut p = profile();
    p.end_m = 0.08;
    p.moving_mass_kg = 0.5;
    p.coulomb_friction_n = 0.02;
    let mut e = electrical();
    e.effective_phase_inductance_h = 0.01;
    e.additional_driver_loss_w = Some(0.0);
    let mut runs = Vec::new();
    for dt in [0.01, 0.005, 0.0025, 0.000625] {
        p.time_step_s = dt;
        runs.push(evaluate_move(&p, &e).unwrap());
    }
    let reference = runs.last().unwrap();
    let energy = reference.source.as_ref().unwrap().net_energy_j;
    let peak = reference
        .source
        .as_ref()
        .unwrap()
        .sampled_positive_peak_power_w;
    let coarse_energy_error = (runs[0].source.as_ref().unwrap().net_energy_j - energy).abs();
    let fine_energy_error = (runs[2].source.as_ref().unwrap().net_energy_j - energy).abs();
    let coarse_peak_error = (runs[0]
        .source
        .as_ref()
        .unwrap()
        .sampled_positive_peak_power_w
        - peak)
        .abs();
    let fine_peak_error = (runs[2]
        .source
        .as_ref()
        .unwrap()
        .sampled_positive_peak_power_w
        - peak)
        .abs();
    eprintln!("dt refinement: net energy errors coarse={coarse_energy_error:.6e} fine={fine_energy_error:.6e} J; peak errors coarse={coarse_peak_error:.6e} fine={fine_peak_error:.6e} W; reference peak={peak:.6e} W");
    assert!(fine_energy_error < coarse_energy_error / 8.0);
    assert!(fine_peak_error < coarse_peak_error / 4.0);
    assert!(fine_peak_error / peak < 1e-3);
    for r in runs {
        // The independent balance residual is O(dt²), not identically zero.
        let balance_tolerance = 6e-4 * r.actual_time_step_s.powi(2);
        eprintln!(
            "dt={:.6e} s: mechanical residual={:.6e} J; electrical residual={:.6e} J",
            r.actual_time_step_s, r.mechanical_balance_residual_j, r.electrical_balance_residual_j
        );
        near(r.mechanical_balance_residual_j, 0.0, balance_tolerance);
        near(r.electrical_balance_residual_j, 0.0, balance_tolerance);
        let source = r.source.unwrap();
        near(
            source.net_energy_j,
            r.copper_energy_j
                + r.conduction_energy_j
                + r.friction_damping_energy_j
                + r.external_load_work_j
                + r.kinetic_energy_change_j
                + r.magnetic_energy_change_j,
            balance_tolerance * 2.0,
        );
        near(
            source.average_power_w,
            source.net_energy_j / p.duration_s,
            1e-12,
        );
    }
}

#[test]
fn signed_energy_splits_zero_crossings_without_counting_net_as_drawn() {
    let mut r = evaluate_move(&profile(), &electrical()).unwrap();
    r.samples.truncate(2);
    r.samples[0].time_s = 0.0;
    r.samples[1].time_s = 1.0;
    r.samples[0].partial_dc_link_power_w = -1.0;
    r.samples[1].partial_dc_link_power_w = 3.0;
    let (drawn, returned) = signed_energy(&r.samples, |s| s.partial_dc_link_power_w);
    near(drawn, 1.125, 1e-12);
    near(returned, 0.125, 1e-12);
    near(drawn - returned, 1.0, 1e-12);
}

#[test]
fn exact_export_interval_and_input_identity_are_preserved() {
    let mut p = profile();
    p.duration_s = 0.123;
    p.time_step_s = 0.007;
    let r = evaluate_move(&p, &electrical()).unwrap();
    near(r.samples[0].time_s, 0.0, 0.0);
    near(r.samples.last().unwrap().time_s, p.duration_s, 1e-15);
    assert!(r.actual_time_step_s <= p.time_step_s);
    let json = serde_json::to_value(&r).unwrap();
    assert_eq!(json["model_version"], MODEL_VERSION);
    assert_eq!(json["profile"]["mass_includes"], p.mass_includes);
    assert_eq!(json["electrical"]["source_accepts_regeneration"], true);
    assert_eq!(json["achieved_distance_m"], serde_json::Value::Null);
}

#[test]
fn quintic_matches_explicit_endpoint_velocities_and_zero_acceleration() {
    let mut p = profile();
    p.initial_velocity_m_s = 0.001;
    p.final_velocity_m_s = 0.005;
    let r = evaluate_move(&p, &electrical()).unwrap();
    let (first, last) = (&r.samples[0], r.samples.last().unwrap());
    near(first.position_m, p.start_m, 1e-12);
    near(last.position_m, p.end_m, 1e-12);
    near(first.velocity_m_s, p.initial_velocity_m_s, 1e-12);
    near(last.velocity_m_s, p.final_velocity_m_s, 1e-12);
    near(first.acceleration_m_s2, 0.0, 1e-12);
    near(last.acceleration_m_s2, 0.0, 1e-12);
    for s in r.samples {
        // Independent electrical terminal-power identity using dq voltage.
        near(
            1.5 * s.required_q_voltage_v * s.q_current_phase_peak_a,
            s.partial_dc_link_power_w - s.driver_conduction_loss_w,
            1e-12,
        );
    }
}

#[test]
fn internal_reversal_is_not_smoothed_into_a_fictitious_friction_transient() {
    let mut p = profile();
    p.initial_velocity_m_s = -0.01;
    p.coulomb_friction_n = 0.1;
    let r = evaluate_move(&p, &electrical()).unwrap();
    assert!(!r.feasible);
    assert!(r.source.is_none());
    assert!(r
        .limiting_factors
        .iter()
        .any(|s| s.contains("Internal reversal")));
    p.end_m = p.start_m;
    assert!(evaluate_move(&p, &electrical())
        .unwrap_err()
        .contains("zero-distance"));
}

#[test]
fn finite_inputs_that_overflow_do_not_publish_results() {
    let mut p = profile();
    p.external_load_n = f64::MAX;
    assert!(evaluate_move(&p, &electrical())
        .unwrap_err()
        .contains("overflow"));
    assert!(capacitor_energy_change_j(1.0, 1.0, f64::MAX).is_err());
}
