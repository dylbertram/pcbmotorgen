//! Prescribed-motion, PWM-cycle-averaged electrical demand kernel.
//!
//! This is not yet an active-design simulation command. Callers must qualify
//! the force map, balanced sinusoidal winding model and source assumptions.
//! See research_notes/linear-drive-move-power.md for the integration gates.

use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;

pub const MODEL_VERSION: &str = "linear-move-sinusoidal-v1";
const MAX_INTERVALS: usize = 200_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoveProfile {
    /// Absolute first-magnet-center positions, not mover center or track edge.
    pub start_m: f64,
    pub end_m: f64,
    pub initial_velocity_m_s: f64,
    pub final_velocity_m_s: f64,
    pub duration_s: f64,
    pub travel_min_m: f64,
    pub travel_max_m: f64,
    pub max_speed_m_s: f64,
    pub max_acceleration_m_s2: f64,
    pub max_deceleration_m_s2: f64,
    pub moving_mass_kg: f64,
    /// Must state which moving parts are included. No inferred cap mass.
    pub mass_includes: String,
    pub coulomb_friction_n: f64,
    pub damping_n_s_per_m: f64,
    /// Signed force the motor must overcome, positive toward +X.
    pub external_load_n: f64,
    pub time_step_s: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForceConstantPoint {
    pub position_m: f64,
    /// Force per signed q-axis phase-peak ampere at this position.
    pub kf_n_per_a: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum WindingModel {
    BalancedStarSinusoidal,
    Delta,
    PhaseAOnly,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoveElectricalModel {
    pub winding: WindingModel,
    pub phase_resistance_hot_ohm: f64,
    /// Constant synchronous copper plus external series phase inductance.
    pub effective_phase_inductance_h: f64,
    pub electrical_period_m: f64,
    pub electrical_angle_at_zero_rad: f64,
    pub force_map: Vec<ForceConstantPoint>,
    pub phase_peak_limit_a: f64,
    pub source_voltage_v: f64,
    pub voltage_headroom: f64,
    /// HS + LS resistance; equal high/low FET resistance is assumed.
    pub driver_path_resistance_ohm: f64,
    /// Explicit scenario loss declaration, not a measured or worst-case law.
    /// None withholds total source results rather than assuming zero losses.
    pub additional_driver_loss_w: Option<f64>,
    /// Explicit stiff DC-link source assumption. No capacitor transient model.
    pub source_accepts_regeneration: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MovePowerSample {
    pub time_s: f64,
    pub position_m: f64,
    pub velocity_m_s: f64,
    pub acceleration_m_s2: f64,
    pub motor_force_n: f64,
    pub q_current_phase_peak_a: f64,
    pub phase_currents_a: [f64; 3],
    pub required_q_voltage_v: f64,
    pub required_d_voltage_v: f64,
    pub required_line_voltage_v: f64,
    pub mechanical_power_w: f64,
    pub copper_loss_w: f64,
    pub driver_conduction_loss_w: f64,
    pub friction_damping_loss_w: f64,
    pub external_load_power_w: f64,
    pub kinetic_energy_j: f64,
    pub magnetic_energy_j: f64,
    pub magnetic_power_w: f64,
    /// Motor + conduction only. Never total source demand.
    pub partial_dc_link_power_w: f64,
    pub required_source_voltage_v: f64,
    pub required_source_current_a: Option<f64>,
    pub required_source_power_w: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceDemand {
    /// Sampled scenario peak, not a guaranteed maximum or switching peak.
    pub sampled_positive_peak_power_w: f64,
    pub sampled_positive_peak_current_a: f64,
    pub average_power_w: f64,
    pub drawn_energy_j: f64,
    pub returned_energy_j: f64,
    pub net_energy_j: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MovePowerResult {
    pub model_version: String,
    pub profile: MoveProfile,
    pub electrical: MoveElectricalModel,
    pub actual_time_step_s: f64,
    /// Necessary sampled envelope checks only, not controller qualification.
    pub feasible: bool,
    pub limiting_factors: Vec<String>,
    pub missing_inputs: Vec<String>,
    pub requested_distance_m: f64,
    /// This imposed-trajectory model never claims to integrate achieved motion.
    pub achieved_distance_m: Option<f64>,
    pub sampled_phase_peak_a: f64,
    /// Per-phase time RMS over this move, not amplitude / sqrt(2) at hold.
    pub phase_rms_a: [f64; 3],
    pub copper_energy_j: f64,
    pub conduction_energy_j: f64,
    pub mechanical_work_j: f64,
    pub friction_damping_energy_j: f64,
    pub external_load_work_j: f64,
    pub kinetic_energy_change_j: f64,
    pub magnetic_energy_change_j: f64,
    pub capacitor_energy_change_j: f64,
    /// Independent trapezoidal residual, not forced to zero.
    pub mechanical_balance_residual_j: f64,
    pub electrical_balance_residual_j: f64,
    /// Withheld for infeasible motion, unknown driver losses or no sink.
    pub source: Option<SourceDemand>,
    pub notes: Vec<String>,
    pub samples: Vec<MovePowerSample>,
}

fn nonnegative(x: f64) -> bool {
    x.is_finite() && x >= 0.0
}
fn positive(x: f64) -> bool {
    x.is_finite() && x > 0.0
}

/// Capacitor endpoint energy change only, not a source-current waveform.
pub fn capacitor_energy_change_j(c_f: f64, start_v: f64, end_v: f64) -> Result<f64, String> {
    if ![c_f, start_v, end_v].into_iter().all(nonnegative) {
        return Err("Capacitance and capacitor voltages must be finite and nonnegative".into());
    }
    let energy = 0.5 * c_f * (end_v * end_v - start_v * start_v);
    if !energy.is_finite() {
        return Err("Capacitor energy overflow".into());
    }
    Ok(energy)
}

fn validate(p: &MoveProfile, e: &MoveElectricalModel) -> Result<usize, String> {
    if e.winding != WindingModel::BalancedStarSinusoidal {
        return Err("Move power supports only balanced star sinusoidal FOC, id = 0".into());
    }
    if ![
        p.start_m,
        p.end_m,
        p.initial_velocity_m_s,
        p.final_velocity_m_s,
        p.travel_min_m,
        p.travel_max_m,
        p.external_load_n,
        e.electrical_angle_at_zero_rad,
    ]
    .into_iter()
    .all(f64::is_finite)
        || ![
            p.duration_s,
            p.moving_mass_kg,
            p.time_step_s,
            e.electrical_period_m,
            e.source_voltage_v,
        ]
        .into_iter()
        .all(positive)
        || ![
            p.max_speed_m_s,
            p.max_acceleration_m_s2,
            p.max_deceleration_m_s2,
            p.coulomb_friction_n,
            p.damping_n_s_per_m,
            e.phase_resistance_hot_ohm,
            e.effective_phase_inductance_h,
            e.phase_peak_limit_a,
            e.driver_path_resistance_ohm,
        ]
        .into_iter()
        .all(nonnegative)
        || !positive(e.voltage_headroom)
        || e.voltage_headroom > 1.0
        || e.additional_driver_loss_w.is_some_and(|v| !nonnegative(v))
    {
        return Err(
            "Move and electrical inputs must be finite and within their declared physical ranges"
                .into(),
        );
    }
    if p.mass_includes.trim().is_empty() {
        return Err("Declare which parts the moving mass includes".into());
    }
    if p.start_m == p.end_m && (p.initial_velocity_m_s != 0.0 || p.final_velocity_m_s != 0.0) {
        return Err("A zero-distance hold requires zero endpoint velocities; split reversals into separate moves".into());
    }
    if p.travel_min_m > p.travel_max_m
        || [p.start_m, p.end_m]
            .iter()
            .any(|x| *x < p.travel_min_m || *x > p.travel_max_m)
    {
        return Err("Move endpoints must be within declared travel bounds".into());
    }
    if e.force_map.len() < 2
        || e.force_map
            .iter()
            .any(|v| !v.position_m.is_finite() || !positive(v.kf_n_per_a))
        || e.force_map
            .windows(2)
            .any(|w| w[0].position_m >= w[1].position_m)
    {
        return Err(
            "Force map needs at least two strictly increasing positions with positive finite Kf"
                .into(),
        );
    }
    let intervals = (p.duration_s / p.time_step_s).ceil().max(4.0);
    if !intervals.is_finite() || intervals > MAX_INTERVALS as f64 {
        return Err(format!("Move exceeds the {MAX_INTERVALS} interval budget"));
    }
    Ok(intervals as usize)
}

/// Quintic with explicit endpoint velocities and zero endpoint acceleration.
fn trajectory(p: &MoveProfile, u: f64) -> (f64, f64, f64) {
    let d = p.end_m - p.start_m;
    let v0 = p.initial_velocity_m_s * p.duration_s;
    let v1 = p.final_velocity_m_s * p.duration_s;
    let a = 10.0 * d - 6.0 * v0 - 4.0 * v1;
    let b = -15.0 * d + 8.0 * v0 + 7.0 * v1;
    let c = 6.0 * d - 3.0 * v0 - 3.0 * v1;
    (
        p.start_m + v0 * u + a * u.powi(3) + b * u.powi(4) + c * u.powi(5),
        (v0 + 3.0 * a * u * u + 4.0 * b * u.powi(3) + 5.0 * c * u.powi(4)) / p.duration_s,
        (6.0 * a * u + 12.0 * b * u * u + 20.0 * c * u.powi(3)) / p.duration_s.powi(2),
    )
}

fn kf_at(map: &[ForceConstantPoint], x: f64) -> Result<f64, String> {
    if x < map[0].position_m - 1e-12 || x > map.last().unwrap().position_m + 1e-12 {
        return Err(
            "Requested trajectory leaves the force-map interval; extrapolation is not supported"
                .into(),
        );
    }
    let hi = map
        .partition_point(|p| p.position_m < x)
        .clamp(1, map.len() - 1);
    let (a, b) = (&map[hi - 1], &map[hi]);
    let u = ((x - a.position_m) / (b.position_m - a.position_m)).clamp(0.0, 1.0);
    Ok(a.kf_n_per_a + u * (b.kf_n_per_a - a.kf_n_per_a))
}

fn integral(samples: &[MovePowerSample], f: impl Fn(&MovePowerSample) -> f64) -> f64 {
    samples
        .windows(2)
        .map(|w| 0.5 * (f(&w[0]) + f(&w[1])) * (w[1].time_s - w[0].time_s))
        .sum()
}

/// Integrals of positive and negative magnitudes of piecewise-linear power.
fn signed_energy(samples: &[MovePowerSample], f: impl Fn(&MovePowerSample) -> f64) -> (f64, f64) {
    let mut drawn = 0.0;
    let mut returned = 0.0;
    for w in samples.windows(2) {
        let (a, b, dt) = (f(&w[0]), f(&w[1]), w[1].time_s - w[0].time_s);
        if a * b < 0.0 {
            let split = a.abs() / (a.abs() + b.abs());
            let first = 0.5 * a * dt * split;
            let second = 0.5 * b * dt * (1.0 - split);
            drawn += first.max(0.0) + second.max(0.0);
            returned += (-first).max(0.0) + (-second).max(0.0);
        } else {
            let energy = 0.5 * (a + b) * dt;
            drawn += energy.max(0.0);
            returned += (-energy).max(0.0);
        }
    }
    (drawn, returned)
}

fn limit(factors: &mut Vec<String>, condition: bool, text: &str) {
    if condition && !factors.iter().any(|s| s == text) {
        factors.push(text.into());
    }
}

/// Calculate required demand for an imposed trajectory. This does not simulate
/// achieved motion. No frontend arithmetic or geometry substitution is involved.
pub fn evaluate_move(p: &MoveProfile, e: &MoveElectricalModel) -> Result<MovePowerResult, String> {
    let n = validate(p, e)?;
    let dt = p.duration_s / n as f64;
    let mut samples = Vec::with_capacity(n + 1);
    let mut factors = Vec::new();
    for i in 0..=n {
        let (x, v, a) = trajectory(p, i as f64 / n as f64);
        let kf = kf_at(&e.force_map, x)?;
        let direction = if v.abs() > 1e-12 {
            v.signum()
        } else {
            (p.end_m - p.start_m).signum()
        };
        // f64::signum(0) is +1; a stationary hold has no Coulomb force.
        let friction = if p.start_m == p.end_m && v.abs() <= 1e-12 {
            0.0
        } else {
            p.coulomb_friction_n * direction
        };
        let force = p.moving_mass_kg * a + friction + p.damping_n_s_per_m * v + p.external_load_n;
        let current = force / kf;
        let theta = TAU * x / e.electrical_period_m + e.electrical_angle_at_zero_rad;
        let phase_currents_a =
            std::array::from_fn(|j| current * (theta - TAU * j as f64 / 3.0).sin());
        limit(
            &mut factors,
            v * (p.end_m - p.start_m) < -1e-12,
            "Internal reversal is unsupported; split into separate forward and reverse moves",
        );
        limit(
            &mut factors,
            x < p.travel_min_m - 1e-12 || x > p.travel_max_m + 1e-12,
            "Trajectory exceeds declared travel bounds",
        );
        limit(
            &mut factors,
            v.abs() > p.max_speed_m_s + 1e-12,
            "Requested speed exceeds declared speed limit",
        );
        let accelerating = a * v >= 0.0;
        limit(
            &mut factors,
            a.abs()
                > if accelerating {
                    p.max_acceleration_m_s2
                } else {
                    p.max_deceleration_m_s2
                } + 1e-12,
            "Requested acceleration/deceleration exceeds its declared limit",
        );
        limit(
            &mut factors,
            current.abs() > e.phase_peak_limit_a + 1e-12,
            "Required phase-current amplitude exceeds declared limit",
        );
        samples.push(MovePowerSample {
            time_s: i as f64 * dt,
            position_m: x,
            velocity_m_s: v,
            acceleration_m_s2: a,
            motor_force_n: force,
            q_current_phase_peak_a: current,
            phase_currents_a,
            required_q_voltage_v: 0.0,
            required_d_voltage_v: 0.0,
            required_line_voltage_v: 0.0,
            mechanical_power_w: force * v,
            copper_loss_w: 1.5 * e.phase_resistance_hot_ohm * current * current,
            driver_conduction_loss_w: 0.75 * e.driver_path_resistance_ohm * current * current,
            friction_damping_loss_w: friction * v + p.damping_n_s_per_m * v * v,
            external_load_power_w: p.external_load_n * v,
            kinetic_energy_j: 0.5 * p.moving_mass_kg * v * v,
            magnetic_energy_j: 0.75 * e.effective_phase_inductance_h * current * current,
            magnetic_power_w: 0.0,
            partial_dc_link_power_w: 0.0,
            required_source_voltage_v: e.source_voltage_v,
            required_source_current_a: None,
            required_source_power_w: None,
        });
    }
    for i in 0..=n {
        let q = |j: usize| samples[j].q_current_phase_peak_a;
        let di = if i == 0 {
            (-3.0 * q(0) + 4.0 * q(1) - q(2)) / (2.0 * dt)
        } else if i == n {
            (3.0 * q(n) - 4.0 * q(n - 1) + q(n - 2)) / (2.0 * dt)
        } else {
            (q(i + 1) - q(i - 1)) / (2.0 * dt)
        };
        let s = &mut samples[i];
        let ke = 2.0 / 3.0 * kf_at(&e.force_map, s.position_m)?;
        s.required_q_voltage_v = e.phase_resistance_hot_ohm * s.q_current_phase_peak_a
            + e.effective_phase_inductance_h * di
            + ke * s.velocity_m_s;
        s.required_d_voltage_v = -TAU * s.velocity_m_s / e.electrical_period_m
            * e.effective_phase_inductance_h
            * s.q_current_phase_peak_a;
        s.required_line_voltage_v = 3f64.sqrt()
            * s.required_q_voltage_v.hypot(s.required_d_voltage_v)
            + s.q_current_phase_peak_a.abs() * e.driver_path_resistance_ohm;
        s.magnetic_power_w = 1.5 * e.effective_phase_inductance_h * s.q_current_phase_peak_a * di;
        s.partial_dc_link_power_w = s.mechanical_power_w
            + s.copper_loss_w
            + s.magnetic_power_w
            + s.driver_conduction_loss_w;
        s.required_source_power_w = e
            .additional_driver_loss_w
            .map(|loss| s.partial_dc_link_power_w + loss);
        s.required_source_current_a = s
            .required_source_power_w
            .map(|power| power / e.source_voltage_v);
        limit(
            &mut factors,
            s.required_line_voltage_v > e.source_voltage_v * e.voltage_headroom + 1e-12,
            "Required line voltage exceeds available envelope; imposed motion is not achieved",
        );
        limit(
            &mut factors,
            !e.source_accepts_regeneration && s.required_source_power_w.is_some_and(|p| p < -1e-12),
            "Source cannot absorb returned energy; DC-link transient or brake model is required",
        );
    }
    let first = &samples[0];
    let last = &samples[n];
    let kinetic_delta = last.kinetic_energy_j - first.kinetic_energy_j;
    let magnetic_delta = last.magnetic_energy_j - first.magnetic_energy_j;
    let mechanical_work = integral(&samples, |s| s.mechanical_power_w);
    let friction_energy = integral(&samples, |s| s.friction_damping_loss_w);
    let load_work = integral(&samples, |s| s.external_load_power_w);
    let copper = integral(&samples, |s| s.copper_loss_w);
    let conduction = integral(&samples, |s| s.driver_conduction_loss_w);
    let partial_energy = integral(&samples, |s| s.partial_dc_link_power_w);
    let source = if factors.is_empty() && e.additional_driver_loss_w.is_some() {
        let power = |s: &MovePowerSample| s.required_source_power_w.unwrap();
        let (drawn, returned) = signed_energy(&samples, power);
        let peak = samples.iter().map(power).fold(0.0, f64::max);
        Some(SourceDemand {
            sampled_positive_peak_power_w: peak,
            sampled_positive_peak_current_a: peak / e.source_voltage_v,
            average_power_w: (drawn - returned) / p.duration_s,
            drawn_energy_j: drawn,
            returned_energy_j: returned,
            net_energy_j: drawn - returned,
        })
    } else {
        None
    };
    let result = MovePowerResult {
        model_version: MODEL_VERSION.into(), profile: p.clone(), electrical: e.clone(), actual_time_step_s: dt,
        feasible: factors.is_empty(), limiting_factors: factors,
        missing_inputs: if e.additional_driver_loss_w.is_none() { vec!["Additional switching/dead-time/control loss declaration required for total source demand".into()] } else { vec![] },
        requested_distance_m: p.end_m-p.start_m, achieved_distance_m: None,
        sampled_phase_peak_a: samples.iter().flat_map(|s| s.phase_currents_a).map(f64::abs).fold(0.0, f64::max),
        phase_rms_a: std::array::from_fn(|j| (integral(&samples, |s| s.phase_currents_a[j].powi(2))/p.duration_s).sqrt()),
        copper_energy_j: copper, conduction_energy_j: conduction, mechanical_work_j: mechanical_work,
        friction_damping_energy_j: friction_energy, external_load_work_j: load_work,
        kinetic_energy_change_j: kinetic_delta, magnetic_energy_change_j: magnetic_delta,
        capacitor_energy_change_j: 0.0,
        mechanical_balance_residual_j: mechanical_work-friction_energy-load_work-kinetic_delta,
        electrical_balance_residual_j: partial_energy-mechanical_work-copper-conduction-magnetic_delta,
        source,
        notes: vec![
            "Required imposed quintic motion, not force/mass-integrated achieved motion. Feasibility is a sampled necessary envelope check, not a controller or thermal qualification.".into(),
            "PWM-cycle-averaged scenario samples; no analytical or switching-resolved ripple. Sampled peaks are not guaranteed worst-case maxima.".into(),
            "Boundary: explicitly stiff source directly at the DC link, constant voltage; capacitor energy change is zero. Positive P=VI draws power; negative returns it.".into(),
            "Interval [0, duration] only. No preceding current startup, subsequent shutdown, idle, settling or repetition model. Endpoint magnetic/kinetic energy is recorded.".into(),
            "Each move must be monotonic. A reversal requires separate forward and reverse moves; a Coulomb-friction sign jump is not treated as a finite-voltage current transient.".into(),
            "Balanced sinusoidal FOC id=0, Ke=2Kf/3 phase peak. Constant synchronous plus external inductance; no saliency, eddy/core/AC copper or external-inductor losses. Production integration must reject designs needing omitted losses.".into(),
            "Driver conduction assumes equal high/low on-resistance. Additional constant driver loss is a declared scenario input, not a validated bound or measured data.".into(),
        ], samples,
    };
    // Never let overflow masquerade as a successful finite engineering result.
    // serde_json intentionally turns NaN into null, so check numbers first.
    if !result_is_finite(&result) {
        return Err("Move calculation overflowed; no result is available".into());
    }
    Ok(result)
}

fn result_is_finite(r: &MovePowerResult) -> bool {
    let summary = [
        r.actual_time_step_s,
        r.sampled_phase_peak_a,
        r.copper_energy_j,
        r.conduction_energy_j,
        r.mechanical_work_j,
        r.friction_damping_energy_j,
        r.external_load_work_j,
        r.kinetic_energy_change_j,
        r.magnetic_energy_change_j,
        r.mechanical_balance_residual_j,
        r.electrical_balance_residual_j,
    ];
    summary.into_iter().chain(r.phase_rms_a).all(f64::is_finite)
        && r.source.as_ref().map_or(true, |s| {
            [
                s.sampled_positive_peak_power_w,
                s.sampled_positive_peak_current_a,
                s.average_power_w,
                s.drawn_energy_j,
                s.returned_energy_j,
                s.net_energy_j,
            ]
            .into_iter()
            .all(f64::is_finite)
        })
        && r.samples.iter().all(|s| {
            [
                s.time_s,
                s.position_m,
                s.velocity_m_s,
                s.acceleration_m_s2,
                s.motor_force_n,
                s.q_current_phase_peak_a,
                s.required_q_voltage_v,
                s.required_d_voltage_v,
                s.required_line_voltage_v,
                s.mechanical_power_w,
                s.copper_loss_w,
                s.driver_conduction_loss_w,
                s.friction_damping_loss_w,
                s.external_load_power_w,
                s.kinetic_energy_j,
                s.magnetic_energy_j,
                s.magnetic_power_w,
                s.partial_dc_link_power_w,
            ]
            .into_iter()
            .chain(s.phase_currents_a)
            .chain(s.required_source_power_w)
            .chain(s.required_source_current_a)
            .all(f64::is_finite)
        })
}

#[cfg(test)]
mod tests;
