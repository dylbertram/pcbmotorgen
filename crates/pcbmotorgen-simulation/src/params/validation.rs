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
        if self.magnet_dims_m.len() != 3 {
            return Err(SimulationError(
                "magnet_dims_m must be a 3-tuple (width, length, height)".into(),
            ));
        }
        if self.magnet_dims_m.iter().any(|&d| d <= 0.0) {
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
        if self.magnet_pitch_m <= 0.0 {
            return Err(SimulationError(format!(
                "magnet_pitch_m must be positive, got {}",
                self.magnet_pitch_m
            )));
        }
        let assembly_gap = self.magnet_pitch_m - self.magnet_dims_m[0];
        if assembly_gap < -1e-10 {
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
        if self.spacing_ratio <= 0.0 || self.spacing_ratio > 2.0 {
            return Err(SimulationError(format!(
                "spacing_ratio must be in (0.0, 2.0], got {}",
                self.spacing_ratio
            )));
        }
        if self.max_current_a <= 0.0 {
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
        if self.max_temperature_rise_c <= 0.0 {
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
        if self.target_force_n <= 0.0 {
            return Err(SimulationError(format!(
                "target_force_n must be positive, got {}",
                self.target_force_n
            )));
        }
        if self.peak_force_n < self.target_force_n {
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
        if self.max_accel_m_s2 <= 0.0 {
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
