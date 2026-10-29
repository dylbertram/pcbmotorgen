use super::*;
use crate::drive::move_power::losses::{CycleLossLaw, DeclaredRipple, LossBasis, LossDomain};

fn with_losses(mut e: MoveElectricalModel) -> MoveElectricalModel {
    e.additional_driver_loss_w = None;
    e.loss_operating_point = Some(LossOperatingPoint {
        driver_name: "Analytic fixture only".into(),
        pwm_hz: 100_000.0,
        winding_temp_c: 75.0,
    });
    e.loss_model = Some(DeclaredLossModel {
        basis: LossBasis::DeclaredParameters,
        reference: "Analytic numerical validation coefficients, not measured hardware properties"
            .into(),
        domain: LossDomain {
            driver_name: "Analytic fixture only".into(),
            source_voltage_v: e.source_voltage_v,
            pwm_hz: 100_000.0,
            winding_temp_c: 75.0,
            driver_path_resistance_ohm: e.driver_path_resistance_ohm,
            max_phase_peak_a: 5.0,
            max_speed_m_s: 1.0,
        },
        phase_names: ["A".into(), "B".into(), "C".into()],
        winding_fundamental_ac_increment_ohm: [0.01, 0.02, 0.03],
        winding_ripple_ac_increment_ohm: [0.1, 0.2, 0.3],
        external_series_resistance_ohm: [0.05; 3],
        external_core_loss_w: [0.001, 0.002, 0.003],
        ripple: DeclaredRipple {
            covariance_a2: [
                [1e-4, -5e-5, -5e-5],
                [-5e-5, 1e-4, -5e-5],
                [-5e-5, -5e-5, 1e-4],
            ],
            peak_deviation_a: [0.02; 3],
            reference:
                "Analytic constant balanced covariance and peak bounds; not a switching trace"
                    .into(),
        },
        switching: CycleLossLaw {
            constant_j: 1e-7,
            abs_mean_current_j_per_a: 2e-8,
            mean_square_current_j_per_a2: 1e-9,
        },
        deadtime: CycleLossLaw {
            constant_j: 2e-8,
            abs_mean_current_j_per_a: 1e-8,
            mean_square_current_j_per_a2: 0.0,
        },
        controller_power_w: 0.02,
        other_dc_link_power_w: 0.03,
        omitted_losses: vec![],
    });
    e
}

#[test]
fn analytic_hold_accounts_for_every_term_once_and_distinguishes_rms_from_source_current() {
    let mut p = profile();
    p.end_m = 0.0;
    p.external_load_n = 2.0;
    let e = with_losses(phase_electrical());
    let r = evaluate_move(&p, &e).unwrap();
    assert!(r.feasible);
    assert_eq!(r.source_model_scope, "declared_loss_model");
    let ledger = r.loss_energy.as_ref().unwrap();
    near(r.copper_energy_j, 0.75 + 0.00012, 1e-12);
    near(ledger.winding_dc_ripple_energy_j, 0.00012, 1e-12);
    near(r.conduction_energy_j, 0.1 * (1.5 + 0.0003), 1e-12);
    near(ledger.winding_ac_energy_j, 0.0375 + 0.00006, 1e-12);
    near(
        ledger.external_series_energy_j,
        0.05 * (1.5 + 0.0003),
        1e-12,
    );
    near(ledger.external_core_energy_j, 0.006, 1e-12);
    let switching = 100_000.0 * (1e-7 + 2e-8 * 3f64.sqrt() + 1e-9 * 1.5003);
    let deadtime = 100_000.0 * (2e-8 + 1e-8 * 3f64.sqrt());
    near(ledger.switching_energy_j, switching, 1e-12); // Whole inverter, not 3x this value.
    near(ledger.deadtime_energy_j, deadtime, 1e-12);
    near(ledger.controller_energy_j, 0.02, 1e-12);
    near(ledger.other_dc_link_energy_j, 0.03, 1e-12);
    let expected =
        0.75012 + 0.15003 + 0.03756 + 0.075015 + 0.006 + switching + deadtime + 0.02 + 0.03;
    let source = r.source.as_ref().unwrap();
    near(source.net_energy_j, expected, 1e-12);
    near(
        source.sampled_positive_peak_current_a,
        expected / 12.0,
        1e-12,
    );
    near(r.accounted_loss_energy_j, expected, 1e-12);
    near(r.source_balance_residual_j.unwrap(), 0.0, 1e-12);
    near(r.electrical_balance_residual_j, 0.0, 1e-12);
    let rms = r.phase_rms_including_declared_ripple_a.unwrap();
    near(rms[0], 0.01, 1e-12);
    near(rms[1], (0.75f64 + 1e-4).sqrt(), 1e-12);
    near(r.phase_rms_a[1], 3f64.sqrt() / 2.0, 1e-12); // Legacy mean-only RMS stays distinct.
    near(
        r.samples[0].required_phase_voltages_v[1],
        -3f64.sqrt() / 2.0 * (0.4 + 0.02 + 0.05),
        1e-12,
    );
    assert!(rms[1] > source.sampled_positive_peak_current_a);
    // Constant covariance contributes stored energy, not a duplicate energy flow.
    let base = evaluate_move(&p, &phase_electrical()).unwrap();
    let extra_stored = e
        .loss_model
        .as_ref()
        .unwrap()
        .ripple_stored_energy_j(e.phase_model.as_ref().unwrap().inductance_h);
    near(
        r.samples[0].magnetic_energy_j - base.samples[0].magnetic_energy_j,
        extra_stored,
        1e-12,
    );
    near(r.magnetic_energy_change_j, 0.0, 1e-12);
}

#[test]
fn zero_mean_current_still_has_declared_ripple_heating_switching_and_controller_demand() {
    let mut p = profile();
    p.end_m = 0.0;
    let r = evaluate_move(&p, &with_losses(phase_electrical())).unwrap();
    near(r.sampled_phase_peak_a, 0.0, 0.0);
    near(
        r.sampled_phase_peak_including_declared_ripple_a.unwrap(),
        0.02,
        1e-12,
    );
    near(r.copper_energy_j, 0.00012, 1e-12);
    near(
        r.loss_energy.as_ref().unwrap().switching_energy_j,
        100_000.0 * (1e-7 + 1e-9 * 0.0003),
        1e-12,
    );
    assert!(r.source.unwrap().net_energy_j > 0.05);
}

#[test]
fn legacy_idealized_zero_ripple_and_omitted_models_do_not_claim_complete_totals() {
    let legacy = evaluate_move(&profile(), &electrical()).unwrap();
    assert_eq!(legacy.source_model_scope, "partial_declared_scenario");
    assert!(legacy.loss_energy.is_none());
    for variant in 0..3 {
        let mut e = with_losses(electrical());
        let model = e.loss_model.as_mut().unwrap();
        match variant {
            0 => model.basis = LossBasis::Idealized,
            1 => {
                model.ripple.covariance_a2 = [[0.0; 3]; 3];
                model.ripple.peak_deviation_a = [0.0; 3];
            }
            _ => model
                .omitted_losses
                .push("Unqualified inductor core loss".into()),
        }
        let r = evaluate_move(&profile(), &e).unwrap();
        assert_eq!(r.source_model_scope, "partial_declared_scenario");
        assert!(!r.missing_inputs.is_empty());
    }
}

#[test]
fn conflicting_legacy_driver_watts_and_component_laws_are_rejected() {
    let mut e = with_losses(electrical());
    e.additional_driver_loss_w = Some(0.0);
    assert!(evaluate_move(&profile(), &e)
        .unwrap_err()
        .contains("double-counting"));
}

#[test]
fn changed_operating_point_phase_order_or_outside_domain_never_extrapolates_losses() {
    for kind in 0..8 {
        let mut e = with_losses(phase_electrical());
        match kind {
            0 => e.source_voltage_v = 24.0,
            1 => e.loss_operating_point.as_mut().unwrap().pwm_hz = 200_000.0,
            2 => e.loss_operating_point.as_mut().unwrap().winding_temp_c = 80.0,
            3 => e.driver_path_resistance_ohm = 0.3,
            4 => e.loss_operating_point.as_mut().unwrap().driver_name = "Different IC".into(),
            5 => e.loss_model.as_mut().unwrap().phase_names.swap(0, 1),
            6 => e.loss_model.as_mut().unwrap().domain.max_speed_m_s = 0.0,
            _ => e.loss_model.as_mut().unwrap().domain.max_phase_peak_a = 0.0,
        }
        assert!(
            evaluate_move(&profile(), &e).is_err(),
            "case {kind} must reject mismatched or out-of-domain losses"
        );
    }
}

#[test]
fn nonpassive_unbalanced_ripple_invalid_coefficients_and_missing_references_are_rejected() {
    for kind in 0..8 {
        let mut e = with_losses(electrical());
        let l = e.loss_model.as_mut().unwrap();
        match kind {
            0 => l.ripple.covariance_a2[0][1] = 0.0,
            1 => l.ripple.covariance_a2 = [[1e-4, 0.0, 0.0], [0.0, 1e-4, 0.0], [0.0, 0.0, 1e-4]],
            2 => l.ripple.covariance_a2[0][0] = -1e-4,
            3 => l.ripple.peak_deviation_a = [0.001; 3],
            4 => l.switching.constant_j = -1.0,
            5 => l.external_series_resistance_ohm[0] = f64::NAN,
            6 => l.reference.clear(),
            _ => l.ripple.reference.clear(),
        }
        assert!(
            evaluate_move(&profile(), &e).is_err(),
            "case {kind} must not publish a loss result"
        );
    }
    let mut e = with_losses(electrical());
    e.loss_model.as_mut().unwrap().switching.constant_j = f64::MAX;
    assert!(evaluate_move(&profile(), &e)
        .unwrap_err()
        .contains("overflow"));
}

#[test]
fn declared_ripple_is_reported_above_current_goals_without_suppressing_demand() {
    let mut p = profile();
    p.end_m = 0.0;
    p.external_load_n = 1.98;
    let mut e = with_losses(electrical());
    e.electrical_angle_at_zero_rad = std::f64::consts::FRAC_PI_2;
    e.phase_peak_limit_a = 1.0;
    let r = evaluate_move(&p, &e).unwrap();
    near(r.sampled_phase_peak_a, 0.99, 1e-12);
    near(
        r.sampled_phase_peak_including_declared_ripple_a.unwrap(),
        1.01,
        1e-12,
    );
    assert!(r.feasible);
    assert!(r.source.is_some());
    assert!(r.limiting_factors.is_empty());
    assert_eq!(r.samples.len(), 1001); // Still cycle-mean time samples, not synthetic PWM cycles.
}

#[test]
fn switching_law_uses_declared_frequency_once_and_requires_an_explicit_domain_update() {
    let mut p = profile();
    p.end_m = 0.0;
    p.external_load_n = 2.0;
    let mut e = with_losses(phase_electrical());
    let first = evaluate_move(&p, &e).unwrap().loss_energy.unwrap();
    e.loss_operating_point.as_mut().unwrap().pwm_hz *= 2.0;
    assert!(evaluate_move(&p, &e).is_err());
    e.loss_model.as_mut().unwrap().domain.pwm_hz *= 2.0;
    let second = evaluate_move(&p, &e).unwrap().loss_energy.unwrap();
    near(
        second.switching_energy_j,
        2.0 * first.switching_energy_j,
        1e-12,
    );
    near(
        second.deadtime_energy_j,
        2.0 * first.deadtime_energy_j,
        1e-12,
    );
    near(second.winding_ac_energy_j, first.winding_ac_energy_j, 1e-12);
    near(second.controller_energy_j, first.controller_energy_j, 1e-12);
}

#[test]
fn braking_balance_keeps_returned_energy_separate_from_losses_and_source_draw() {
    let mut p = profile();
    p.end_m = 0.05;
    p.initial_velocity_m_s = 0.1;
    p.moving_mass_kg = 10.0;
    let mut e = electrical();
    e.phase_resistance_hot_ohm = 0.0;
    e.driver_path_resistance_ohm = 0.0;
    e.effective_phase_inductance_h = 0.0;
    let mut e = with_losses(e);
    let l = e.loss_model.as_mut().unwrap();
    l.winding_fundamental_ac_increment_ohm = [0.0; 3];
    l.winding_ripple_ac_increment_ohm = [0.0; 3];
    l.external_series_resistance_ohm = [0.0; 3];
    l.external_core_loss_w = [0.0001; 3];
    l.switching = CycleLossLaw {
        constant_j: 1e-9,
        abs_mean_current_j_per_a: 0.0,
        mean_square_current_j_per_a2: 0.0,
    };
    l.deadtime = CycleLossLaw {
        constant_j: 5e-10,
        abs_mean_current_j_per_a: 0.0,
        mean_square_current_j_per_a2: 0.0,
    };
    l.controller_power_w = 0.001;
    l.other_dc_link_power_w = 0.0002;
    let r = evaluate_move(&p, &e).unwrap();
    let source = r.source.as_ref().unwrap();
    near(source.net_energy_j, -0.05 + 0.00165, 1e-7);
    near(
        source.drawn_energy_j - source.returned_energy_j,
        source.net_energy_j,
        1e-12,
    );
    assert!(source.returned_energy_j > 0.048);
    assert!(source.drawn_energy_j > 0.0);
    near(r.source_balance_residual_j.unwrap(), 0.0, 1e-12);
    e.source_accepts_regeneration = false;
    let rejected = evaluate_move(&p, &e).unwrap();
    assert!(!rejected.feasible);
    assert!(rejected.source.is_none());
}

#[test]
fn source_ledger_and_peak_converge_for_a_dynamic_move_with_declared_losses() {
    let mut p = profile();
    p.end_m = 0.008;
    p.moving_mass_kg = 0.5;
    p.external_load_n = 0.1;
    p.coulomb_friction_n = 0.02;
    let e = with_losses(electrical());
    let mut runs = Vec::new();
    for dt in [0.01, 0.005, 0.0025, 0.000625] {
        p.time_step_s = dt;
        runs.push(evaluate_move(&p, &e).unwrap());
    }
    let reference = runs.last().unwrap().source.as_ref().unwrap();
    let fine = runs[2].source.as_ref().unwrap();
    assert!(
        (fine.net_energy_j - reference.net_energy_j).abs() / reference.net_energy_j.abs() < 1e-4
    );
    assert!(
        (fine.sampled_positive_peak_power_w - reference.sampled_positive_peak_power_w).abs()
            / reference.sampled_positive_peak_power_w
            < 1e-3
    );
    for r in runs {
        let source = r.source.as_ref().unwrap();
        eprintln!(
            "loss-model dt={} s, net={} J, sampled peak={} W, source balance={} J",
            r.actual_time_step_s,
            source.net_energy_j,
            source.sampled_positive_peak_power_w,
            r.source_balance_residual_j.unwrap()
        );
        near(
            source.net_energy_j,
            r.mechanical_work_j + r.accounted_loss_energy_j + r.magnetic_energy_change_j,
            1e-8,
        );
        near(r.source_balance_residual_j.unwrap(), 0.0, 1e-8);
        near(r.mechanical_balance_residual_j, 0.0, 1e-9);
    }
}
