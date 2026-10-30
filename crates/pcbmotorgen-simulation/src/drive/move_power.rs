//! Prescribed-motion, PWM-cycle-averaged electrical demand kernel.
//!
//! Native adapters supply actual per-phase force maps and electrical networks.
//! Scalar reciprocal parameters remain available for analytic limiting cases.
//! See research_notes/linear-drive-move-power.md for the integration gates.

use losses::{DeclaredLossModel, LossEnergy, LossOperatingPoint, LossSample};
use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;

pub const MODEL_VERSION: &str = "linear-move-demand-v6";
const MAX_INTERVALS: usize = 200_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MoveProfile {
    /// Absolute first-magnet-center positions, not mover center or track edge.
    pub start_m: f64,
    pub end_m: f64,
    pub initial_velocity_m_s: f64,
    pub final_velocity_m_s: f64,
    pub duration_s: f64,
    pub travel_min_m: f64,
    pub travel_max_m: f64,
    /// Legacy design goals, retained for saved-file compatibility only.
    #[serde(default)]
    pub max_speed_m_s: f64,
    #[serde(default)]
    pub max_acceleration_m_s2: f64,
    #[serde(default)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseForcePoint {
    pub position_m: f64,
    /// Signed reciprocal terminal coefficients, not commutated forces.
    pub force_n_per_a: [f64; 3],
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseDomainModel {
    pub phase_names: [String; 3],
    pub resistance_hot_ohm: [f64; 3],
    /// Constant, symmetric inductance including external series per phase.
    pub inductance_h: [[f64; 3]; 3],
    pub force_map: Vec<PhaseForcePoint>,
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
    /// Legacy goal, never clamps or suppresses imposed-move demand.
    #[serde(default)]
    pub phase_peak_limit_a: f64,
    pub source_voltage_v: f64,
    /// Legacy design margin, not part of the physical demand calculation.
    #[serde(default)]
    pub voltage_headroom: f64,
    /// HS + LS resistance; equal high/low FET resistance is assumed.
    pub driver_path_resistance_ohm: f64,
    /// Explicit scenario loss declaration, not a measured or worst-case law.
    /// None withholds total source results rather than assuming zero losses.
    pub additional_driver_loss_w: Option<f64>,
    /// Explicit stiff DC-link source assumption. No capacitor transient model.
    pub source_accepts_regeneration: bool,
    /// Native routed designs use individual R, full L and reciprocal forces.
    /// None retains the scalar model for analytic limiting tests.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub phase_model: Option<PhaseDomainModel>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub loss_model: Option<DeclaredLossModel>,
    /// Actual settings supplied by the native adapter, not a loss declaration.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub loss_operating_point: Option<LossOperatingPoint>,
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
    /// Motor terminal-to-neutral command voltages, not switching samples.
    pub required_phase_voltages_v: [f64; 3],
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
    pub losses: Option<LossSample>,
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
    /// Declared model totals are conditional on their input laws, not measured
    /// hardware demand or a guaranteed upper bound. Legacy models remain partial.
    pub source_model_scope: String,
    pub profile: MoveProfile,
    pub electrical: MoveElectricalModel,
    pub actual_time_step_s: f64,
    /// Necessary sampled envelope checks only, not controller qualification.
    /// Legacy field name: physical model/voltage compatibility only, never
    /// design-goal compliance or proof of achieved hardware motion.
    pub feasible: bool,
    pub limiting_factors: Vec<String>,
    pub missing_inputs: Vec<String>,
    pub requested_distance_m: f64,
    pub sampled_requested_peak_speed_m_s: f64,
    pub sampled_requested_positive_acceleration_m_s2: f64,
    pub sampled_requested_negative_acceleration_m_s2: f64,
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
    pub source_balance_residual_j: Option<f64>,
    pub loss_energy: Option<LossEnergy>,
    pub accounted_loss_energy_j: f64,
    pub phase_rms_including_declared_ripple_a: Option<[f64; 3]>,
    pub sampled_phase_peak_including_declared_ripple_a: Option<f64>,
    /// Required demand, independent of design goals and tracking feasibility.
    /// Withheld only for unsupported motion/source physics or unknown losses.
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
        return Err("Move power supports only balanced star sinusoidal phase currents".into());
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
            p.coulomb_friction_n,
            p.damping_n_s_per_m,
            e.phase_resistance_hot_ohm,
            e.effective_phase_inductance_h,
            e.driver_path_resistance_ohm,
        ]
        .into_iter()
        .all(nonnegative)
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
    if let Some(ph) = &e.phase_model {
        if ph.phase_names.iter().any(|s| s.trim().is_empty())
            || (0..3).any(|i| (i + 1..3).any(|j| ph.phase_names[i] == ph.phase_names[j]))
            || !ph.resistance_hot_ohm.into_iter().all(nonnegative)
            || !ph.inductance_h.into_iter().flatten().all(f64::is_finite)
            || ph.force_map.len() < 2
            || ph.force_map.iter().any(|v| {
                !v.position_m.is_finite() || !v.force_n_per_a.into_iter().all(f64::is_finite)
            })
            || ph
                .force_map
                .windows(2)
                .any(|w| w[0].position_m >= w[1].position_m)
        {
            return Err("Invalid per-phase electrical parameters or force map".into());
        }
        let l = nalgebra::Matrix3::from_fn(|i, j| ph.inductance_h[i][j]);
        let scale = l.norm().max(1e-15);
        if (l - l.transpose()).norm() > 1e-10 * scale
            || l.symmetric_eigen().eigenvalues.min() < -1e-10 * scale
        {
            return Err("Phase inductance matrix must be symmetric positive semidefinite".into());
        }
    }
    if let Some(losses) = &e.loss_model {
        losses.validate(e)?;
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

fn phase_force_at(map: &[PhaseForcePoint], x: f64) -> Result<[f64; 3], String> {
    if x < map[0].position_m - 1e-12 || x > map.last().unwrap().position_m + 1e-12 {
        return Err("Requested trajectory leaves the per-phase force-map interval; extrapolation is not supported".into());
    }
    let hi = map
        .partition_point(|p| p.position_m < x)
        .clamp(1, map.len() - 1);
    let (a, b) = (&map[hi - 1], &map[hi]);
    let u = ((x - a.position_m) / (b.position_m - a.position_m)).clamp(0.0, 1.0);
    Ok(std::array::from_fn(|i| {
        a.force_n_per_a[i] + u * (b.force_n_per_a[i] - a.force_n_per_a[i])
    }))
}

fn dot(a: [f64; 3], b: [f64; 3]) -> f64 {
    a.into_iter().zip(b).map(|(a, b)| a * b).sum()
}

fn multiply(m: [[f64; 3]; 3], v: [f64; 3]) -> [f64; 3] {
    std::array::from_fn(|i| dot(m[i], v))
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
    evaluate_move_with_cancel(p, e, &|| false)
}

/// Cancellation is checked during both passes; no partial result is returned.
pub fn evaluate_move_with_cancel(
    p: &MoveProfile,
    e: &MoveElectricalModel,
    cancelled: &impl Fn() -> bool,
) -> Result<MovePowerResult, String> {
    let n = validate(p, e)?;
    let dt = p.duration_s / n as f64;
    let mut samples = Vec::with_capacity(n + 1);
    let mut factors = Vec::new();
    let mut source_supported = true;
    let r_dc = e
        .phase_model
        .as_ref()
        .map_or([e.phase_resistance_hot_ohm; 3], |ph| ph.resistance_hot_ohm);
    let inductance = e.phase_model.as_ref().map_or_else(
        || {
            std::array::from_fn(|i| {
                std::array::from_fn(|j| {
                    if i == j {
                        e.effective_phase_inductance_h
                    } else {
                        0.0
                    }
                })
            })
        },
        |ph| ph.inductance_h,
    );
    let ripple_energy = e
        .loss_model
        .as_ref()
        .map_or(0.0, |losses| losses.ripple_stored_energy_j(inductance));
    for i in 0..=n {
        if cancelled() {
            return Err("Move power calculation cancelled".into());
        }
        let (x, v, a) = trajectory(p, i as f64 / n as f64);
        let theta = TAU * x / e.electrical_period_m + e.electrical_angle_at_zero_rad;
        let basis = std::array::from_fn(|j| (theta - TAU * j as f64 / 3.0).sin());
        let kf = if let Some(ph) = &e.phase_model {
            dot(phase_force_at(&ph.force_map, x)?, basis)
        } else {
            kf_at(&e.force_map, x)?
        };
        if !kf.is_finite() || kf <= 1e-12 {
            return Err("Declared balanced-star electrical reference has nonpositive or singular thrust coupling along this move; no current allocation is available".into());
        }
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
        let phase_currents_a = basis.map(|b| current * b);
        let losses = e
            .loss_model
            .as_ref()
            .map(|losses| losses.sample(phase_currents_a, v, r_dc))
            .transpose()?;
        let dc_ripple = losses.as_ref().map_or(0.0, |l| l.winding_dc_ripple_loss_w);
        let mean_square = losses
            .as_ref()
            .map_or(phase_currents_a.map(|i| i * i), |l| {
                l.mean_square_phase_current_a2
            });
        let copper_loss_w = e
            .phase_model
            .as_ref()
            .map_or(1.5 * e.phase_resistance_hot_ohm * current * current, |ph| {
                dot(ph.resistance_hot_ohm, phase_currents_a.map(|i| i * i))
            })
            + dc_ripple;
        let magnetic_energy_j = e.phase_model.as_ref().map_or(
            0.75 * e.effective_phase_inductance_h * current * current,
            |ph| {
                0.5 * dot(
                    phase_currents_a,
                    multiply(ph.inductance_h, phase_currents_a),
                )
            },
        ) + ripple_energy;
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
        source_supported &= factors.is_empty();
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
            required_phase_voltages_v: [0.0; 3],
            mechanical_power_w: force * v,
            copper_loss_w,
            driver_conduction_loss_w: 0.5
                * e.driver_path_resistance_ohm
                * mean_square.into_iter().sum::<f64>(),
            friction_damping_loss_w: friction * v + p.damping_n_s_per_m * v * v,
            external_load_power_w: p.external_load_n * v,
            kinetic_energy_j: 0.5 * p.moving_mass_kg * v * v,
            magnetic_energy_j,
            magnetic_power_w: 0.0,
            partial_dc_link_power_w: 0.0,
            required_source_voltage_v: e.source_voltage_v,
            required_source_current_a: None,
            required_source_power_w: None,
            losses,
        });
    }
    for i in 0..=n {
        if cancelled() {
            return Err("Move power calculation cancelled".into());
        }
        let q = |j: usize| samples[j].q_current_phase_peak_a;
        let di = if i == 0 {
            (-3.0 * q(0) + 4.0 * q(1) - q(2)) / (2.0 * dt)
        } else if i == n {
            (3.0 * q(n) - 4.0 * q(n - 1) + q(n - 2)) / (2.0 * dt)
        } else {
            (q(i + 1) - q(i - 1)) / (2.0 * dt)
        };
        let phase_di = std::array::from_fn(|phase| {
            let q = |j: usize| samples[j].phase_currents_a[phase];
            if i == 0 {
                (-3.0 * q(0) + 4.0 * q(1) - q(2)) / (2.0 * dt)
            } else if i == n {
                (3.0 * q(n) - 4.0 * q(n - 1) + q(n - 2)) / (2.0 * dt)
            } else {
                (q(i + 1) - q(i - 1)) / (2.0 * dt)
            }
        });
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
        let theta = TAU * s.position_m / e.electrical_period_m + e.electrical_angle_at_zero_rad;
        let q_basis: [f64; 3] = std::array::from_fn(|j| (theta - TAU * j as f64 / 3.0).sin());
        let d_basis: [f64; 3] = std::array::from_fn(|j| -(theta - TAU * j as f64 / 3.0).cos());
        s.required_phase_voltages_v = std::array::from_fn(|j| {
            q_basis[j] * s.required_q_voltage_v + d_basis[j] * s.required_d_voltage_v
        });
        if let Some(ph) = &e.phase_model {
            let ldi = multiply(ph.inductance_h, phase_di);
            let emf = phase_force_at(&ph.force_map, s.position_m)?.map(|k| k * s.velocity_m_s);
            s.required_phase_voltages_v = std::array::from_fn(|j| {
                ph.resistance_hot_ohm[j] * s.phase_currents_a[j] + ldi[j] + emf[j]
            });
            s.required_q_voltage_v = 2.0 / 3.0 * dot(q_basis, s.required_phase_voltages_v);
            s.required_d_voltage_v = 2.0 / 3.0 * dot(d_basis, s.required_phase_voltages_v);
            // Floating neutral permits common-mode translation. Centered
            // SVPWM needs the instantaneous max-min phase-command span.
            let command: [f64; 3] = std::array::from_fn(|j| {
                s.required_phase_voltages_v[j]
                    + 0.5 * e.driver_path_resistance_ohm * s.phase_currents_a[j]
            });
            s.required_line_voltage_v = command.into_iter().fold(f64::NEG_INFINITY, f64::max)
                - command.into_iter().fold(f64::INFINITY, f64::min);
            s.magnetic_power_w = dot(s.phase_currents_a, ldi);
        }
        s.partial_dc_link_power_w = s.mechanical_power_w
            + s.copper_loss_w
            + s.magnetic_power_w
            + s.driver_conduction_loss_w;
        if e.phase_model.is_some() {
            s.partial_dc_link_power_w = dot(s.required_phase_voltages_v, s.phase_currents_a)
                + s.driver_conduction_loss_w
                + s.losses
                    .as_ref()
                    .map_or(0.0, |l| l.winding_dc_ripple_loss_w);
        }
        if let Some(loss_model) = &e.loss_model {
            let additional_v = loss_model.fundamental_voltage_drop_v(s.phase_currents_a);
            s.required_phase_voltages_v =
                std::array::from_fn(|j| s.required_phase_voltages_v[j] + additional_v[j]);
            s.required_q_voltage_v = 2.0 / 3.0 * dot(q_basis, s.required_phase_voltages_v);
            s.required_d_voltage_v = 2.0 / 3.0 * dot(d_basis, s.required_phase_voltages_v);
            let command: [f64; 3] = std::array::from_fn(|j| {
                s.required_phase_voltages_v[j]
                    + 0.5 * e.driver_path_resistance_ohm * s.phase_currents_a[j]
            });
            s.required_line_voltage_v = command.into_iter().fold(f64::NEG_INFINITY, f64::max)
                - command.into_iter().fold(f64::INFINITY, f64::min);
        }
        s.required_source_power_w = s
            .losses
            .as_ref()
            .map(|l| s.partial_dc_link_power_w + l.additional_power_w())
            .or_else(|| {
                e.additional_driver_loss_w
                    .map(|loss| s.partial_dc_link_power_w + loss)
            });
        s.required_source_current_a = s
            .required_source_power_w
            .map(|power| power / e.source_voltage_v);
        limit(
            &mut factors,
            s.required_line_voltage_v > e.source_voltage_v + 1e-12,
            "Required line voltage exceeds the physical DC-link voltage; demand is calculated for imposed motion, not achieved tracking",
        );
        limit(
            &mut factors,
            !e.source_accepts_regeneration && s.required_source_power_w.is_some_and(|p| p < -1e-12),
            "Source cannot absorb returned energy; DC-link transient or brake model is required",
        );
        source_supported &=
            e.source_accepts_regeneration || !s.required_source_power_w.is_some_and(|p| p < -1e-12);
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
    let loss_energy = e.loss_model.as_ref().map(|_| LossEnergy {
        winding_dc_ripple_energy_j: integral(&samples, |s| {
            s.losses.as_ref().unwrap().winding_dc_ripple_loss_w
        }),
        winding_ac_energy_j: integral(&samples, |s| s.losses.as_ref().unwrap().winding_ac_loss_w),
        external_series_energy_j: integral(&samples, |s| {
            s.losses.as_ref().unwrap().external_series_loss_w
        }),
        external_core_energy_j: integral(&samples, |s| {
            s.losses.as_ref().unwrap().external_core_loss_w
        }),
        switching_energy_j: integral(&samples, |s| s.losses.as_ref().unwrap().switching_loss_w),
        deadtime_energy_j: integral(&samples, |s| s.losses.as_ref().unwrap().deadtime_loss_w),
        controller_energy_j: integral(&samples, |s| s.losses.as_ref().unwrap().controller_loss_w),
        other_dc_link_energy_j: integral(&samples, |s| {
            s.losses.as_ref().unwrap().other_dc_link_loss_w
        }),
    });
    let accounted_losses = copper
        + conduction
        + loss_energy
            .as_ref()
            .map_or(0.0, LossEnergy::additional_energy_j)
        + e.additional_driver_loss_w.unwrap_or(0.0) * p.duration_s;
    let source_known = e.loss_model.is_some() || e.additional_driver_loss_w.is_some();
    let source_balance = source_known.then(|| {
        integral(&samples, |s| s.required_source_power_w.unwrap())
            - mechanical_work
            - accounted_losses
            - magnetic_delta
    });
    let source = if source_supported && source_known {
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
        model_version: MODEL_VERSION.into(), source_model_scope: if e.loss_model.as_ref().is_some_and(DeclaredLossModel::supplies_declared_totals) { "declared_loss_model" } else if e.loss_model.as_ref().is_some_and(DeclaredLossModel::is_engineering_estimate) { "engineering_estimate" } else { "partial_declared_scenario" }.into(),
        profile: p.clone(), electrical: e.clone(), actual_time_step_s: dt,
        feasible: factors.is_empty(), limiting_factors: factors,
        missing_inputs: if let Some(losses) = &e.loss_model { losses.omitted_losses.iter().map(|s| format!("Declared omitted loss: {s}")).collect() }
            else if e.additional_driver_loss_w.is_none() { vec!["Additional switching/dead-time/control loss declaration required for total source demand".into()] } else { vec![] },
        requested_distance_m: p.end_m-p.start_m,
        sampled_requested_peak_speed_m_s: samples.iter().map(|s| s.velocity_m_s.abs()).fold(0.0, f64::max),
        sampled_requested_positive_acceleration_m_s2: samples.iter().map(|s| s.acceleration_m_s2).fold(0.0, f64::max),
        sampled_requested_negative_acceleration_m_s2: samples.iter().map(|s| s.acceleration_m_s2).fold(0.0, f64::min),
        achieved_distance_m: None,
        sampled_phase_peak_a: samples.iter().flat_map(|s| s.phase_currents_a).map(f64::abs).fold(0.0, f64::max),
        phase_rms_a: std::array::from_fn(|j| (integral(&samples, |s| s.phase_currents_a[j].powi(2))/p.duration_s).sqrt()),
        copper_energy_j: copper, conduction_energy_j: conduction, mechanical_work_j: mechanical_work,
        friction_damping_energy_j: friction_energy, external_load_work_j: load_work,
        kinetic_energy_change_j: kinetic_delta, magnetic_energy_change_j: magnetic_delta,
        capacitor_energy_change_j: 0.0,
        mechanical_balance_residual_j: mechanical_work-friction_energy-load_work-kinetic_delta,
        electrical_balance_residual_j: partial_energy-mechanical_work-copper-conduction-magnetic_delta,
        source_balance_residual_j: source_balance, accounted_loss_energy_j: accounted_losses,
        phase_rms_including_declared_ripple_a: e.loss_model.as_ref().map(|_| std::array::from_fn(|j|
            (integral(&samples, |s| s.losses.as_ref().unwrap().mean_square_phase_current_a2[j])/p.duration_s).sqrt())),
        sampled_phase_peak_including_declared_ripple_a: e.loss_model.as_ref().map(|_| samples.iter()
            .flat_map(|s| s.losses.as_ref().unwrap().phase_peak_envelope_a).fold(0.0, f64::max)),
        loss_energy,
        source,
        notes: vec![
            "Required imposed quintic motion, not force/mass-integrated achieved motion. Design goals for speed, acceleration, phase current and voltage margin do not affect or suppress calculated demand. Physical tracking findings do not turn required demand into achieved hardware performance.".into(),
            "PWM-cycle-averaged scenario samples; no analytical or switching-resolved ripple. Sampled peaks are not guaranteed worst-case maxima.".into(),
            "Boundary: explicitly stiff source directly at the DC link, constant voltage; capacitor energy change is zero. Positive P=VI draws power; negative returns it.".into(),
            "Interval [0, duration] only. No preceding current startup, subsequent shutdown, idle, settling or repetition model. Endpoint magnetic/kinetic energy is recorded.".into(),
            "Each move must be monotonic. A reversal requires separate forward and reverse moves; a Coulomb-friction sign jump is not treated as a finite-voltage current transient.".into(),
            "Balanced sinusoidal FOC id=0, Ke=2Kf/3 phase peak. Constant synchronous plus external inductance; no saliency, eddy/core/AC copper or external-inductor losses. Production integration must reject designs needing omitted losses.".into(),
            "Driver conduction assumes equal high/low on-resistance. Additional constant driver loss is a declared scenario input, not a validated bound or measured data.".into(),
        ], samples,
    };
    let mut result = result;
    if e.phase_model.is_some() {
        result
            .notes
            .retain(|note| !note.starts_with("Balanced sinusoidal FOC id=0"));
        result.notes.push("Native phase-domain model: signed terminal force/EMF reciprocity, individual hot resistance, full constant self/mutual plus external inductance. Balanced sinusoidal currents are explicitly commanded, not inferred from the static preview. Required voltage is instantaneous phase-command span including conduction. No eddy/core/AC copper, external-inductor loss or switching ripple model.".into());
    }
    if let Some(losses) = &e.loss_model {
        result.notes.retain(|s| {
            !s.starts_with("PWM-cycle-averaged scenario samples")
                && !s.starts_with("Driver conduction assumes")
                && !s.starts_with("Native phase-domain model:")
                && !s.starts_with("Balanced sinusoidal FOC id=0")
        });
        result.notes.push("Declared cycle-average loss model: native hot DC winding R plus separate fundamental/ripple AC increments, external series resistance/core watts, driver conduction, whole-inverter switching/dead-time energy per PWM cycle, controller and other DC-link watts. No term is counted twice.".into());
        result.notes.push("Phase currents/voltages remain cycle means. Declared zero-mean ripple covariance adds RMS heating and constant stored magnetic energy. The supplied peak envelope is reported without comparison to design goals. No switching waveform or switching-resolution source peak is synthesized.".into());
        result.notes.push(format!("Loss parameters reference: {}. Ripple reference: {}. Applicability is restricted to the declared driver, bus voltage, PWM, temperature, current and speed domain; no extrapolation. These are conditional model results, not measured hardware totals or guaranteed maxima.", losses.reference, losses.ripple.reference));
        result.notes.push("Mean phase voltages include fundamental AC and external-series IR drops. Dead-time energy is a declared averaged loss law, not a switching/compensation simulation. Imposed tracking is an assumption, not controller qualification. Required demand remains available even when voltage exceeds the physical bus.".into());
        if !losses.supplies_declared_totals() {
            result.missing_inputs.push("Idealized basis, zero-ripple assumption or named omissions keep total source demand Unknown; only partial modeled values are available".into());
        }
    }
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
        r.accounted_loss_energy_j,
    ];
    summary.into_iter().chain(r.phase_rms_a).all(f64::is_finite)
        && r.loss_energy.as_ref().map_or(true, LossEnergy::is_finite)
        && r.source_balance_residual_j.into_iter().all(f64::is_finite)
        && r.phase_rms_including_declared_ripple_a
            .into_iter()
            .flatten()
            .all(f64::is_finite)
        && r.sampled_phase_peak_including_declared_ripple_a
            .into_iter()
            .all(f64::is_finite)
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
            s.losses.as_ref().map_or(true, LossSample::is_finite)
                && [
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
                .chain(s.required_phase_voltages_v)
                .chain(s.required_source_power_w)
                .chain(s.required_source_current_a)
                .all(f64::is_finite)
        })
}

#[cfg(test)]
mod tests;

pub mod losses;
pub mod routed;
