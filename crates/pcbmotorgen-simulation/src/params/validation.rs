//! `SimulationInput` construction and the full validation check cascade.

use super::{SimulationError, SimulationInput};

impl SimulationInput {
    /// Create a validated config, checking all invariants.
    pub fn new(self) -> Result<Self, SimulationError> {
        self.validate()?;
        Ok(self)
    }

    /// Validate all fields.
    pub fn validate(&self) -> Result<(), SimulationError> {
        self.validate_with_design_goals(true)
    }

    /// Validate physical inputs without requiring design-goal relationships.
    pub fn validate_for_move(&self) -> Result<(), SimulationError> {
        self.validate_with_design_goals(false)
    }

    /// Preserve geometry/material checks without enforcing performance goals.
    pub fn validate_for_simulation(&self) -> Result<(), SimulationError> {
        self.validate_with_design_goals(false)
    }

    fn validate_with_design_goals(&self, check_goals: bool) -> Result<(), SimulationError> {
        if let Some(stack) = &self.pcb_stackup {
            stack.validate(self.num_layers, self.pcb_thickness_m).map_err(SimulationError)?;
        }
        if let Some(stack) = &self.backplane {
            stack.validate().map_err(SimulationError)?;
        }
        if self.magnet_dims_m.len() != 3 {
            return Err(SimulationError(
                "magnet_dims_m must be a 3-tuple (width, length, height)".into(),
            ));
        }
        if self.magnet_dims_m.iter().any(|&d| !d.is_finite() || d <= 0.0) {
            return Err(SimulationError(format!(
                "All magnet dimensions must be positive, got {:?}",
                self.magnet_dims_m
            )));
        }
        if self.magnet_count < 2 {
            return Err(SimulationError(format!(
                "magnet_count must be ≥ 2, got {}",
                self.magnet_count
            )));
        }
        if self.magnet_count > super::MAX_MAGNET_COUNT {
            return Err(SimulationError(format!("magnet_count must be ≤ {}, got {}", super::MAX_MAGNET_COUNT, self.magnet_count)));
        }
        if !self.magnet_pitch_m.is_finite() || self.magnet_pitch_m <= 0.0 {
            return Err(SimulationError(format!(
                "magnet_pitch_m must be positive, got {}",
                self.magnet_pitch_m
            )));
        }
        let assembly_gap = self.magnet_pitch_m - self.magnet_dims_m[0];
        if assembly_gap < 0.0 {
            return Err(SimulationError(format!(
                "magnet_pitch_m ({:.3} mm) must be ≥ magnet width ({:.3} mm) — \
                 inter-magnet gap cannot be negative (current gap: {:.3} mm)",
                self.magnet_pitch_m * 1e3,
                self.magnet_dims_m[0] * 1e3,
                assembly_gap * 1e3
            )));
        }
        if self.magnet_remanence_t <= 0.0 || self.magnet_remanence_t > 2.5 {
            return Err(SimulationError(format!(
                "magnet_remanence_t must be in (0, 2.5] T, got {}",
                self.magnet_remanence_t
            )));
        }
        if self.phases < 1 {
            return Err(SimulationError(format!(
                "phases must be ≥ 1, got {}",
                self.phases
            )));
        }
        if self.balanced_three_phase_drive && self.phases != 3 {
            return Err(SimulationError("Balanced A/B/C drive requires exactly three phases".into()));
        }
        if self.spacing_ratio <= 0.0 || self.spacing_ratio > 2.0 {
            return Err(SimulationError(format!(
                "spacing_ratio must be in (0.0, 2.0], got {}",
                self.spacing_ratio
            )));
        }
        if check_goals && self.max_current_a <= 0.0 {
            return Err(SimulationError(format!(
                "max_current_a must be positive, got {}",
                self.max_current_a
            )));
        }
        if self.supply_voltage_v <= 0.0 {
            return Err(SimulationError(format!(
                "supply_voltage_v must be positive, got {}",
                self.supply_voltage_v
            )));
        }
        if self.min_trace_m <= 0.0 {
            return Err(SimulationError(format!(
                "min_trace_m must be positive, got {}",
                self.min_trace_m
            )));
        }
        if self.min_space_m <= 0.0 {
            return Err(SimulationError(format!(
                "min_space_m must be positive, got {}",
                self.min_space_m
            )));
        }
        if self.min_via_drill_m <= 0.0 {
            return Err(SimulationError(format!(
                "min_via_drill_m must be positive, got {}",
                self.min_via_drill_m
            )));
        }
        if self.min_via_annular_ring_m <= 0.0 {
            return Err(SimulationError(format!(
                "min_via_annular_ring_m must be positive, got {}",
                self.min_via_annular_ring_m
            )));
        }
        if self.air_gap_m < 0.0 {
            return Err(SimulationError(format!(
                "air_gap_m must be ≥ 0, got {}",
                self.air_gap_m
            )));
        }
        if self.max_layers < 2 || self.max_layers % 2 != 0 {
            return Err(SimulationError(format!(
                "max_layers must be an even number ≥ 2, got {}",
                self.max_layers
            )));
        }
        if self.max_layers > super::MAX_PCB_LAYERS || self.num_layers > super::MAX_PCB_LAYERS {
            return Err(SimulationError(format!("PCB copper layer count and max_layers must be ≤ {}", super::MAX_PCB_LAYERS)));
        }
        if self.num_layers < 2 || self.num_layers % 2 != 0 {
            return Err(SimulationError(format!(
                "num_layers must be an even number ≥ 2, got {}",
                self.num_layers
            )));
        }
        if self.num_layers > self.max_layers {
            return Err(SimulationError(format!(
                "num_layers ({}) must be ≤ max_layers ({})",
                self.num_layers, self.max_layers
            )));
        }
        if self.drive_frequency_hz <= 0.0 {
            return Err(SimulationError(format!(
                "drive_frequency_hz must be positive, got {}",
                self.drive_frequency_hz
            )));
        }
        if check_goals && self.max_temperature_rise_c <= 0.0 {
            return Err(SimulationError(format!(
                "max_temperature_rise_c must be positive, got {}",
                self.max_temperature_rise_c
            )));
        }

        if self.active_area_length_m <= 0.0 {
            return Err(SimulationError(format!(
                "active_area_length_m must be positive, got {}",
                self.active_area_length_m
            )));
        }
        if self.active_area_length_m <= self.magnet_array_span_m() {
            return Err(SimulationError(format!(
                "active_area_length_m ({:.1} mm) must be greater than the magnet \
                 array span ({:.1} mm = {} magnets × {:.1} mm) — travel would be \
                 zero or negative",
                self.active_area_length_m * 1e3,
                self.magnet_array_span_m() * 1e3,
                self.magnet_count,
                self.magnet_pitch_m * 1e3
            )));
        }
        if self.board_width_m <= 0.0 {
            return Err(SimulationError(format!(
                "board_width_m must be positive, got {}",
                self.board_width_m
            )));
        }
        if self.pcb_thickness_m <= 0.0 {
            return Err(SimulationError(format!(
                "pcb_thickness_m must be positive, got {}",
                self.pcb_thickness_m
            )));
        }
        if self.strands_per_phase < 1 {
            return Err(SimulationError(format!(
                "strands_per_phase must be ≥ 1, got {}",
                self.strands_per_phase
            )));
        }
        if self.strands_per_phase > 1 {
            let strand_height = self.board_width_m / self.strands_per_phase as f64;
            let min_strand_height = self.min_trace_m + self.min_space_m;
            if strand_height < min_strand_height {
                return Err(SimulationError(format!(
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
        if check_goals && self.target_force_n <= 0.0 {
            return Err(SimulationError(format!(
                "target_force_n must be positive, got {}",
                self.target_force_n
            )));
        }
        if check_goals && self.peak_force_n < self.target_force_n {
            return Err(SimulationError(format!(
                "peak_force_n ({:.3} N) must be ≥ target_force_n ({:.3} N)",
                self.peak_force_n, self.target_force_n
            )));
        }
        if self.friction_n < 0.0 {
            return Err(SimulationError(format!(
                "friction_n must be ≥ 0, got {}",
                self.friction_n
            )));
        }
        if self.carriage_mass_kg <= 0.0 {
            return Err(SimulationError(format!(
                "carriage_mass_kg must be positive, got {}",
                self.carriage_mass_kg
            )));
        }
        if check_goals && self.max_accel_m_s2 <= 0.0 {
            return Err(SimulationError(format!(
                "max_accel_m_s2 must be positive, got {}",
                self.max_accel_m_s2
            )));
        }
        if self.capacitor_bank_uf <= 0.0 {
            return Err(SimulationError(format!(
                "capacitor_bank_uf must be positive, got {}",
                self.capacitor_bank_uf
            )));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn magnet_length_cannot_exceed_one_finite_pole_pitch() {
        for pitch in [0.0, -0.006, f64::NAN, f64::INFINITY] {
            let cfg = SimulationInput { magnet_pitch_m: pitch, ..Default::default() };
            assert!(cfg.validate_for_simulation().is_err());
            assert!(cfg.validate_for_move().is_err());
        }
        for width in [0.006 + 1e-12, f64::NAN, f64::INFINITY] {
            let cfg = SimulationInput { magnet_pitch_m: 0.006, magnet_dims_m: [width, 0.005, 0.003], ..Default::default() };
            assert!(cfg.validate_for_simulation().is_err());
            assert!(cfg.validate_for_move().is_err());
        }
        let cfg = SimulationInput { magnet_pitch_m: 0.006, magnet_dims_m: [0.006, 0.005, 0.003], ..Default::default() };
        assert!(cfg.validate_for_simulation().is_ok(), "exactly one pole, zero assembly gap, is not an electrical mismatch");
    }

    #[test]
    fn coreless_magnet_and_pcb_layer_upper_bounds() {
        let mut input = SimulationInput { magnet_count: 12, max_layers: 16, num_layers: 16, ..SimulationInput::default() };
        assert!(input.validate().is_ok());
        input.magnet_count = 13;
        assert!(input.validate().unwrap_err().to_string().contains("≤ 12"));
        input.magnet_count = 12; input.max_layers = 18; input.num_layers = 18;
        assert!(input.validate().unwrap_err().to_string().contains("≤ 16"));
    }

    #[test]
    fn explicit_conductor_depth_json_round_trips_without_one_ulp_normalization() {
        let raw = "[-0.0048000000000000004,-0.0032,-0.0016,0.0]";
        let depths: Vec<f64> = serde_json::from_str(raw).unwrap();
        assert_eq!(depths[0].to_bits(), (-0.0048000000000000004_f64).to_bits());
        let restored: Vec<f64> = serde_json::from_str(&serde_json::to_string(&depths).unwrap()).unwrap();
        assert_eq!(depths.iter().map(|v| v.to_bits()).collect::<Vec<_>>(), restored.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
    }

    #[test]
    fn test_default_validates() {
        assert!(SimulationInput::default().validate().is_ok());
    }

    #[test]
    fn odd_and_even_magnet_counts_validate() {
        for magnet_count in [2, 3, 5, 8, 9] {
            let input = SimulationInput { magnet_count, ..SimulationInput::default() };
            assert!(input.new().is_ok(), "Rejected {magnet_count} magnets");
        }
    }

    #[test]
    fn fewer_than_two_magnets_are_rejected() {
        for magnet_count in [0, 1] {
            let input = SimulationInput { magnet_count, ..SimulationInput::default() };
            assert!(input.validate().unwrap_err().to_string().contains("magnet_count must be ≥ 2"));
        }
    }
}
