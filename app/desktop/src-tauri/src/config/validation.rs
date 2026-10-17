//! `LinearMotorConfig` construction + validation: `new()` and `validate()`
//! plus the full field-invariant test suite.

use super::{ConfigError, LinearMotorConfig};

// The following methods form the config API. In the binary these are partly
// exercised via `cargo test` (inline `#[cfg(test)]`) while the shipped runtime
// path builds the config straight from the IPC DTO's `to_core()`, so keep the
// API available without dead-code noise in release builds.
#[allow(dead_code)]
impl LinearMotorConfig {
    /// Create a validated config, syncing magnet grade and checking all invariants.
    #[allow(clippy::wrong_self_convention)]
    pub fn new(mut self) -> Result<Self, ConfigError> {
        self.sync_magnet_grade();
        self.validate()?;
        Ok(self)
    }

    /// Validate all fields (mirrors Python `_validate_base` + `_validate_linear`).
    pub fn validate(&self) -> Result<(), ConfigError> {
        // --- Base validation ---
        if self.magnet_dims_m.len() != 3 {
            return Err(ConfigError(
                "magnet_dims_m must be a 3-tuple (width, length, height)".into(),
            ));
        }
        if self.magnet_dims_m.iter().any(|&d| d <= 0.0) {
            return Err(ConfigError(format!(
                "All magnet dimensions must be positive, got {:?}",
                self.magnet_dims_m
            )));
        }
        if self.magnet_count < 2 {
            return Err(ConfigError(format!(
                "magnet_count must be ≥ 2, got {}",
                self.magnet_count
            )));
        }
        if self.magnet_pitch_m <= 0.0 {
            return Err(ConfigError(format!(
                "magnet_pitch_m must be positive, got {}",
                self.magnet_pitch_m
            )));
        }
        let assembly_gap = self.magnet_pitch_m - self.magnet_dims_m[0];
        if assembly_gap < -1e-10 {
            return Err(ConfigError(format!(
                "magnet_pitch_m ({:.3} mm) must be ≥ magnet width ({:.3} mm) — \
                 inter-magnet gap cannot be negative (current gap: {:.3} mm)",
                self.magnet_pitch_m * 1e3,
                self.magnet_dims_m[0] * 1e3,
                assembly_gap * 1e3
            )));
        }
        if self.magnet_remanence_t <= 0.0 || self.magnet_remanence_t > 2.5 {
            return Err(ConfigError(format!(
                "magnet_remanence_t must be in (0, 2.5] T, got {}",
                self.magnet_remanence_t
            )));
        }
        if self.phases < 1 {
            return Err(ConfigError(format!(
                "phases must be ≥ 1, got {}",
                self.phases
            )));
        }
        if self.spacing_ratio <= 0.0 || self.spacing_ratio > 2.0 {
            return Err(ConfigError(format!(
                "spacing_ratio must be in (0.0, 2.0], got {}",
                self.spacing_ratio
            )));
        }
        if self.max_current_a <= 0.0 {
            return Err(ConfigError(format!(
                "max_current_a must be positive, got {}",
                self.max_current_a
            )));
        }
        if self.supply_voltage_v <= 0.0 {
            return Err(ConfigError(format!(
                "supply_voltage_v must be positive, got {}",
                self.supply_voltage_v
            )));
        }
        if !self.min_trace_m.is_finite() || self.min_trace_m <= 0.0 {
            return Err(ConfigError(format!(
                "min_trace_m must be positive, got {}",
                self.min_trace_m
            )));
        }
        if !self.trace_width_m.is_finite() || self.trace_width_m <= 0.0 {
            return Err(ConfigError(format!(
                "trace_width_m must be positive, got {}",
                self.trace_width_m
            )));
        }
        if self.trace_width_m < self.min_trace_m {
            return Err(ConfigError(format!(
                "trace_width_m ({}) must be at least the minimum trace width ({})",
                self.trace_width_m, self.min_trace_m
            )));
        }
        if self.min_space_m <= 0.0 {
            return Err(ConfigError(format!(
                "min_space_m must be positive, got {}",
                self.min_space_m
            )));
        }
        if self.min_via_drill_m <= 0.0 {
            return Err(ConfigError(format!(
                "min_via_drill_m must be positive, got {}",
                self.min_via_drill_m
            )));
        }
        if self.min_via_annular_ring_m <= 0.0 {
            return Err(ConfigError(format!(
                "min_via_annular_ring_m must be positive, got {}",
                self.min_via_annular_ring_m
            )));
        }
        if self.air_gap_m < 0.0 {
            return Err(ConfigError(format!(
                "air_gap_m must be ≥ 0, got {}",
                self.air_gap_m
            )));
        }
        if self.max_layers < 2 || self.max_layers % 2 != 0 {
            return Err(ConfigError(format!(
                "max_layers must be an even number ≥ 2, got {}",
                self.max_layers
            )));
        }
        if self.num_layers < 2 || self.num_layers % 2 != 0 {
            return Err(ConfigError(format!(
                "num_layers must be an even number ≥ 2, got {}",
                self.num_layers
            )));
        }
        if self.num_layers > self.max_layers {
            return Err(ConfigError(format!(
                "num_layers ({}) must be ≤ max_layers ({})",
                self.num_layers, self.max_layers
            )));
        }
        if self.drive_frequency_hz <= 0.0 {
            return Err(ConfigError(format!(
                "drive_frequency_hz must be positive, got {}",
                self.drive_frequency_hz
            )));
        }
        if self.max_temperature_rise_c <= 0.0 {
            return Err(ConfigError(format!(
                "max_temperature_rise_c must be positive, got {}",
                self.max_temperature_rise_c
            )));
        }

        // --- Linear validation ---
        if self.active_area_length_m <= 0.0 {
            return Err(ConfigError(format!(
                "active_area_length_m must be positive, got {}",
                self.active_area_length_m
            )));
        }
        if self.active_area_length_m <= self.magnet_array_span_m() {
            return Err(ConfigError(format!(
                "active_area_length_m ({:.1} mm) must be greater than the magnet array \
                 span ({:.1} mm = {} magnets × {:.1} mm) — travel would be zero or negative",
                self.active_area_length_m * 1e3,
                self.magnet_array_span_m() * 1e3,
                self.magnet_count,
                self.magnet_pitch_m * 1e3
            )));
        }
        if self.board_width_m <= 0.0 {
            return Err(ConfigError(format!(
                "board_width_m must be positive, got {}",
                self.board_width_m
            )));
        }
        if self.pcb_thickness_m <= 0.0 {
            return Err(ConfigError(format!(
                "pcb_thickness_m must be positive, got {}",
                self.pcb_thickness_m
            )));
        }
        // Round 9: multi-strand validation.
        if self.strands_per_phase < 1 {
            return Err(ConfigError(format!(
                "strands_per_phase must be ≥ 1, got {}",
                self.strands_per_phase
            )));
        }
        // Each strand needs at least `min_trace_m + min_space_m` of
        // vertical room. Reject configs that try to pack too many
        // strands into the board_width.
        if self.strands_per_phase > 1 {
            let strand_height = self.board_width_m / self.strands_per_phase as f64;
            let min_strand_height = self.min_trace_m + self.min_space_m;
            if strand_height < min_strand_height {
                return Err(ConfigError(format!(
                    "strands_per_phase ({}) requires each strand to be ≥ \
                     {:.3} mm tall (min_trace + min_space); board_width_m / \
                     strands_per_phase = {:.3} mm. Reduce strands_per_phase \
                     or increase board_width_m.",
                    self.strands_per_phase,
                    min_strand_height * 1e3,
                    strand_height * 1e3,
                )));
            }
        }
        if self.target_force_n <= 0.0 {
            return Err(ConfigError(format!(
                "target_force_n must be positive, got {}",
                self.target_force_n
            )));
        }
        if self.peak_force_n < self.target_force_n {
            return Err(ConfigError(format!(
                "peak_force_n ({:.3} N) must be ≥ target_force_n ({:.3} N)",
                self.peak_force_n, self.target_force_n
            )));
        }
        if self.friction_n < 0.0 {
            return Err(ConfigError(format!(
                "friction_n must be ≥ 0, got {}",
                self.friction_n
            )));
        }
        if self.carriage_mass_kg <= 0.0 {
            return Err(ConfigError(format!(
                "carriage_mass_kg must be positive, got {}",
                self.carriage_mass_kg
            )));
        }
        if self.max_accel_m_s2 <= 0.0 {
            return Err(ConfigError(format!(
                "max_accel_m_s2 must be positive, got {}",
                self.max_accel_m_s2
            )));
        }
        if self.capacitor_bank_uf <= 0.0 {
            return Err(ConfigError(format!(
                "capacitor_bank_uf must be positive, got {}",
                self.capacitor_bank_uf
            )));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests — validation
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_simulation::units::mm;

    #[test]
    fn test_nominal_trace_width_below_minimum_raises() {
        let cfg = LinearMotorConfig { trace_width_m: mm(0.05), min_trace_m: mm(0.127), ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_active_area_raises() {
        let cfg = LinearMotorConfig { active_area_length_m: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_negative_active_area_raises() {
        let cfg = LinearMotorConfig { active_area_length_m: -mm(10.0), ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_active_area_le_magnet_array_span_raises() {
        let cfg = LinearMotorConfig {
            active_area_length_m: mm(120.0),
            magnet_count: 10,
            magnet_pitch_m: mm(12.0),
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_magnet_dim_raises() {
        let cfg = LinearMotorConfig {
            magnet_dims_m: [0.0, mm(10.0), mm(4.0)],
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_odd_and_even_magnet_counts_validate() {
        for magnet_count in [2, 3, 5, 8, 9] {
            let cfg = LinearMotorConfig { magnet_count, ..LinearMotorConfig::default() };
            assert!(cfg.validate().is_ok(), "Rejected {magnet_count} magnets");
        }
    }

    #[test]
    fn test_magnet_count_below_two_raises() {
        for magnet_count in [0, 1] {
            let cfg = LinearMotorConfig { magnet_count, ..LinearMotorConfig::default() };
            assert!(cfg.validate().unwrap_err().to_string().contains("magnet_count must be ≥ 2"));
        }
    }

    #[test]
    fn test_pitch_smaller_than_magnet_width_raises() {
        let cfg = LinearMotorConfig {
            magnet_dims_m: [mm(15.0), mm(10.0), mm(4.0)],
            magnet_pitch_m: mm(12.0),
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_unrealistic_remanence_raises() {
        let cfg = LinearMotorConfig {
            magnet_grade: "Custom".into(),
            magnet_remanence_t: 3.0,
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_remanence_raises() {
        let cfg = LinearMotorConfig {
            magnet_grade: "Custom".into(),
            magnet_remanence_t: 0.0,
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_target_force_raises() {
        let cfg = LinearMotorConfig { target_force_n: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_current_raises() {
        let cfg = LinearMotorConfig { max_current_a: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_trace_raises() {
        let cfg = LinearMotorConfig { min_trace_m: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_via_drill_raises() {
        let cfg = LinearMotorConfig { min_via_drill_m: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_negative_air_gap_raises() {
        let cfg = LinearMotorConfig { air_gap_m: -mm(0.1), ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_odd_max_layers_raises() {
        let cfg = LinearMotorConfig { max_layers: 5, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_max_layers_raises() {
        let cfg = LinearMotorConfig { max_layers: 0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_drive_frequency_raises() {
        let cfg = LinearMotorConfig { drive_frequency_hz: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_zero_board_width_raises() {
        let cfg = LinearMotorConfig { board_width_m: 0.0, ..LinearMotorConfig::default() };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_peak_below_target_raises() {
        let cfg = LinearMotorConfig {
            target_force_n: 1.0,
            peak_force_n: 0.5,
            ..LinearMotorConfig::default()
        };
        assert!(cfg.validate().is_err());
    }
}
