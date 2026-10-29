//! Explicit cycle-average loss laws. Never infer PWM waveforms, driver
//! efficiency, material losses or measured provenance from these parameters.

use super::{dot, nonnegative, positive, MoveElectricalModel};
use nalgebra::Matrix3;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum LossBasis {
    DeclaredParameters,
    Idealized,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LossOperatingPoint {
    pub driver_name: String,
    pub pwm_hz: f64,
    pub winding_temp_c: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LossDomain {
    pub driver_name: String,
    pub source_voltage_v: f64,
    pub pwm_hz: f64,
    pub winding_temp_c: f64,
    pub driver_path_resistance_ohm: f64,
    /// Includes the declared ripple peak-deviation bound, not only mean current.
    pub max_phase_peak_a: f64,
    pub max_speed_m_s: f64,
}

/// Energy for the WHOLE inverter per configured PWM cycle, not per FET or edge.
/// Coefficients apply to sum(abs(mean phase I)) and sum(mean(I²)), respectively.
/// They describe a declared/calibrated averaged law; RMS does not reconstruct
/// switching-event current or dead-time diode conduction.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CycleLossLaw {
    pub constant_j: f64,
    pub abs_mean_current_j_per_a: f64,
    pub mean_square_current_j_per_a2: f64,
}

impl CycleLossLaw {
    fn valid(&self) -> bool {
        [
            self.constant_j,
            self.abs_mean_current_j_per_a,
            self.mean_square_current_j_per_a2,
        ]
        .into_iter()
        .all(nonnegative)
    }

    fn power_w(&self, mean: [f64; 3], mean_square: [f64; 3], pwm_hz: f64) -> f64 {
        pwm_hz
            * (self.constant_j
                + self.abs_mean_current_j_per_a * mean.into_iter().map(f64::abs).sum::<f64>()
                + self.mean_square_current_j_per_a2 * mean_square.into_iter().sum::<f64>())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeclaredRipple {
    /// Constant zero-mean cycle-average covariance in the declared phase order.
    /// These are supplied statistics, never generated switching samples.
    pub covariance_a2: [[f64; 3]; 3],
    pub peak_deviation_a: [f64; 3],
    pub reference: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeclaredLossModel {
    pub basis: LossBasis,
    /// Origin and applicability of the supplied laws, including explicit zeros.
    pub reference: String,
    pub domain: LossDomain,
    pub phase_names: [String; 3],
    /// Increment ABOVE the native hot DC winding resistance for mean current.
    pub winding_fundamental_ac_increment_ohm: [f64; 3],
    /// Increment ABOVE native hot DC R for the supplied ripple variance.
    pub winding_ripple_ac_increment_ohm: [f64; 3],
    pub external_series_resistance_ohm: [f64; 3],
    /// Declared constant core loss per external inductor over this domain.
    pub external_core_loss_w: [f64; 3],
    pub ripple: DeclaredRipple,
    pub switching: CycleLossLaw,
    pub deadtime: CycleLossLaw,
    pub controller_power_w: f64,
    pub other_dc_link_power_w: f64,
    pub omitted_losses: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LossSample {
    pub mean_square_phase_current_a2: [f64; 3],
    pub phase_peak_envelope_a: [f64; 3],
    /// Already part of copper_loss_w, not an extra term in the source ledger.
    pub winding_dc_ripple_loss_w: f64,
    pub winding_ac_loss_w: f64,
    pub external_series_loss_w: f64,
    pub external_core_loss_w: f64,
    pub switching_loss_w: f64,
    pub deadtime_loss_w: f64,
    pub controller_loss_w: f64,
    pub other_dc_link_loss_w: f64,
}

impl LossSample {
    pub fn additional_power_w(&self) -> f64 {
        self.winding_ac_loss_w
            + self.external_series_loss_w
            + self.external_core_loss_w
            + self.switching_loss_w
            + self.deadtime_loss_w
            + self.controller_loss_w
            + self.other_dc_link_loss_w
    }

    pub fn is_finite(&self) -> bool {
        [
            self.winding_dc_ripple_loss_w,
            self.winding_ac_loss_w,
            self.external_series_loss_w,
            self.external_core_loss_w,
            self.switching_loss_w,
            self.deadtime_loss_w,
            self.controller_loss_w,
            self.other_dc_link_loss_w,
            self.additional_power_w(),
        ]
        .into_iter()
        .chain(self.mean_square_phase_current_a2)
        .chain(self.phase_peak_envelope_a)
        .all(nonnegative)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LossEnergy {
    /// Included in the winding copper energy, not counted twice in total losses.
    pub winding_dc_ripple_energy_j: f64,
    pub winding_ac_energy_j: f64,
    pub external_series_energy_j: f64,
    pub external_core_energy_j: f64,
    pub switching_energy_j: f64,
    pub deadtime_energy_j: f64,
    pub controller_energy_j: f64,
    pub other_dc_link_energy_j: f64,
}

impl LossEnergy {
    pub fn additional_energy_j(&self) -> f64 {
        self.winding_ac_energy_j
            + self.external_series_energy_j
            + self.external_core_energy_j
            + self.switching_energy_j
            + self.deadtime_energy_j
            + self.controller_energy_j
            + self.other_dc_link_energy_j
    }

    pub fn is_finite(&self) -> bool {
        [
            self.winding_dc_ripple_energy_j,
            self.winding_ac_energy_j,
            self.external_series_energy_j,
            self.external_core_energy_j,
            self.switching_energy_j,
            self.deadtime_energy_j,
            self.controller_energy_j,
            self.other_dc_link_energy_j,
            self.additional_energy_j(),
        ]
        .into_iter()
        .all(nonnegative)
    }
}

fn same(a: f64, b: f64) -> bool {
    a.is_finite() && b.is_finite() && (a - b).abs() <= 1e-9 * a.abs().max(b.abs()).max(1e-12)
}

impl DeclaredLossModel {
    pub fn validate(&self, e: &MoveElectricalModel) -> Result<(), String> {
        if e.additional_driver_loss_w.is_some() {
            return Err("Set legacy additional_driver_loss_w to null when using loss_model; double-counting driver losses is not allowed".into());
        }
        if self.reference.trim().is_empty()
            || self.ripple.reference.trim().is_empty()
            || self.omitted_losses.iter().any(|s| s.trim().is_empty())
        {
            return Err(
                "Loss model and ripple require explicit references; every omission must be named"
                    .into(),
            );
        }
        let d = &self.domain;
        let context = e
            .loss_operating_point
            .as_ref()
            .ok_or("Loss model requires the actual driver/PWM/temperature operating point")?;
        if d.driver_name.trim().is_empty()
            || d.driver_name != context.driver_name
            || !same(d.source_voltage_v, e.source_voltage_v)
            || !same(d.pwm_hz, context.pwm_hz)
            || !same(d.winding_temp_c, context.winding_temp_c)
            || !same(d.driver_path_resistance_ohm, e.driver_path_resistance_ohm)
        {
            return Err("Loss-model driver, voltage, PWM, temperature or conduction resistance does not match the active design; no extrapolation is supported".into());
        }
        if !positive(d.pwm_hz)
            || !positive(d.source_voltage_v)
            || !nonnegative(d.max_phase_peak_a)
            || !nonnegative(d.max_speed_m_s)
            || !self.switching.valid()
            || !self.deadtime.valid()
            || ![self.controller_power_w, self.other_dc_link_power_w]
                .into_iter()
                .all(nonnegative)
            || !self
                .winding_fundamental_ac_increment_ohm
                .into_iter()
                .chain(self.winding_ripple_ac_increment_ohm)
                .chain(self.external_series_resistance_ohm)
                .chain(self.external_core_loss_w)
                .chain(self.ripple.peak_deviation_a)
                .all(nonnegative)
        {
            return Err("Declared loss coefficients, ripple bounds and applicability limits must be finite and nonnegative".into());
        }
        if self.phase_names.iter().any(|s| s.trim().is_empty())
            || (0..3).any(|i| (i + 1..3).any(|j| self.phase_names[i] == self.phase_names[j]))
            || e.phase_model
                .as_ref()
                .is_some_and(|ph| self.phase_names != ph.phase_names)
        {
            return Err(
                "Loss-model phase order does not match the actual electrical networks".into(),
            );
        }
        let q = Matrix3::from_fn(|i, j| self.ripple.covariance_a2[i][j]);
        let scale = q.norm().max(1e-15);
        if !q.iter().all(|v| v.is_finite())
            || !scale.is_finite()
            || (q - q.transpose()).norm() > 1e-10 * scale
            || q.symmetric_eigen().eigenvalues.min() < -1e-10 * scale
            || (0..3).any(|i| q.row(i).sum().abs() > 1e-10 * scale)
            || (0..3).any(|i| {
                !nonnegative(q[(i, i)])
                    || !self.ripple.peak_deviation_a[i].powi(2).is_finite()
                    || q[(i, i)] > self.ripple.peak_deviation_a[i].powi(2) + 1e-10 * scale
            })
        {
            return Err("Ripple covariance must be finite, symmetric, passive and star-balanced, with variance no greater than its squared peak-deviation bound".into());
        }
        Ok(())
    }

    pub fn supplies_declared_totals(&self) -> bool {
        self.basis == LossBasis::DeclaredParameters
            && self.omitted_losses.is_empty()
            && (0..3).any(|i| self.ripple.covariance_a2[i][i] > 0.0)
    }

    pub fn fundamental_voltage_drop_v(&self, mean: [f64; 3]) -> [f64; 3] {
        std::array::from_fn(|i| {
            (self.winding_fundamental_ac_increment_ohm[i] + self.external_series_resistance_ohm[i])
                * mean[i]
        })
    }

    pub fn ripple_stored_energy_j(&self, inductance: [[f64; 3]; 3]) -> f64 {
        0.5 * (0..3)
            .flat_map(|i| (0..3).map(move |j| inductance[i][j] * self.ripple.covariance_a2[j][i]))
            .sum::<f64>()
    }

    pub fn sample(&self, mean: [f64; 3], speed: f64, r_dc: [f64; 3]) -> Result<LossSample, String> {
        let variance = std::array::from_fn(|i| self.ripple.covariance_a2[i][i]);
        let squares = mean.map(|i| i * i);
        let total = std::array::from_fn(|i| squares[i] + variance[i]);
        let peak: [f64; 3] =
            std::array::from_fn(|i| mean[i].abs() + self.ripple.peak_deviation_a[i]);
        if speed.abs() > self.domain.max_speed_m_s + 1e-12
            || peak
                .into_iter()
                .any(|i| i > self.domain.max_phase_peak_a + 1e-12)
        {
            return Err("Requested speed or phase current including declared ripple leaves the loss-model domain; no loss extrapolation or source result is available".into());
        }
        let result = LossSample {
            mean_square_phase_current_a2: total,
            phase_peak_envelope_a: peak,
            winding_dc_ripple_loss_w: dot(r_dc, variance),
            winding_ac_loss_w: dot(self.winding_fundamental_ac_increment_ohm, squares)
                + dot(self.winding_ripple_ac_increment_ohm, variance),
            external_series_loss_w: dot(self.external_series_resistance_ohm, total),
            external_core_loss_w: self.external_core_loss_w.into_iter().sum(),
            switching_loss_w: self.switching.power_w(mean, total, self.domain.pwm_hz),
            deadtime_loss_w: self.deadtime.power_w(mean, total, self.domain.pwm_hz),
            controller_loss_w: self.controller_power_w,
            other_dc_link_loss_w: self.other_dc_link_power_w,
        };
        if !result.is_finite() {
            return Err("Declared loss model overflowed; no source result is available".into());
        }
        Ok(result)
    }
}
