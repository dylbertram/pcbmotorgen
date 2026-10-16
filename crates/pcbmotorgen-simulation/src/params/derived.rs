//! Derived-geometry accessors on [`SimulationInput`].

use super::{SAFETY_MARGIN, SimulationInput};

impl SimulationInput {
    // --- Derived geometry ---

    /// Physical outer-edge span of the mover magnet array [m].
    pub fn magnet_array_span_m(&self) -> f64 {
        self.magnet_count.saturating_sub(1) as f64 * self.magnet_pitch_m
            + self.magnet_dims_m[0]
    }

    /// Edge-aligned translation distance [m]: `active_area_length − physical array span`.
    pub fn travel_m(&self) -> f64 {
        self.active_area_length_m - self.magnet_array_span_m()
    }

    /// First-magnet-center limits that keep both physical array edges inside
    /// the active area. Vernier phase offsets do not move mechanical limits.
    pub fn sweep_center_limits_m(&self) -> (f64, f64) {
        let start = self.magnet_dims_m[0] / 2.0;
        (start, start + self.travel_m())
    }

    /// Minimum PCB length required [m] (= active_area_length_m).
    pub fn active_length_m(&self) -> f64 {
        self.active_area_length_m
    }

    /// Magnet pole pitch [m] (= magnet_pitch for alternating arrays).
    pub fn pole_pitch_m(&self) -> f64 {
        self.magnet_pitch_m
    }

    /// Vernier-adjusted phase-band pitch [m]: `(pole_pitch / phases) × spacing_ratio`.
    /// With `spacing_ratio = 1.0` this is the ideal phase-band pitch
    /// `τ_p/phases`; the glossary's slot pitch `τ_s = L_stator/N_slots`
    /// coincides only for uniform 1-slot-per-pole-per-phase windings.
    pub fn phase_band_pitch_m(&self) -> f64 {
        (self.pole_pitch_m() / self.phases as f64) * self.spacing_ratio
    }

    /// Vernier rest offset: phase offset between a coil center and the
    /// nearest pole center [m]. Clamped to `[0, pole_pitch]`.
    pub fn rest_offset_m(&self) -> f64 {
        ((self.pole_pitch_m() / self.phases as f64) * (1.0 - self.spacing_ratio))
            .clamp(0.0, self.pole_pitch_m())
    }

    /// Inter-magnet gap along the travel axis [m]: `magnet_pitch − magnet_width`.
    /// Distinct from the motor air gap `air_gap_m` (stator-to-mover clearance).
    pub fn magnet_gap_m(&self) -> f64 {
        self.magnet_pitch_m - self.magnet_dims_m[0]
    }

    /// Minimum via pad diameter [m] = drill + 2 × annular ring.
    pub fn min_via_pad_m(&self) -> f64 {
        self.min_via_drill_m + 2.0 * self.min_via_annular_ring_m
    }

    /// Peak inertial force [N] = `carriage_mass × max_accel`.
    pub fn acceleration_force_n(&self) -> f64 {
        self.carriage_mass_kg * self.max_accel_m_s2
    }

    /// Minimum motor force to overcome friction with safety margin [N].
    pub fn minimum_drive_force_n(&self) -> f64 {
        self.friction_n * SAFETY_MARGIN
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_config() -> SimulationInput {
        SimulationInput::default()
    }

    #[test]
    fn sweep_limits_contain_physical_array_for_gaps_and_vernier_ratios() {
        for count in [1, 2, 10] {
            for width in [0.006, 0.012] {
                for ratio in [0.8, 1.0, 1.2] {
                    let mut cfg = default_config();
                    cfg.magnet_count = count;
                    cfg.magnet_dims_m[0] = width;
                    cfg.spacing_ratio = ratio;
                    let (start, end) = cfg.sweep_center_limits_m();
                    let last_center_offset = count.saturating_sub(1) as f64 * cfg.magnet_pitch_m;
                    assert!((start - width / 2.0).abs() < 1e-12);
                    assert!((end + last_center_offset + width / 2.0 - cfg.active_area_length_m).abs() < 1e-12);
                    assert!((end - start - cfg.travel_m()).abs() < 1e-12);
                }
            }
        }
    }

    #[test]
    fn test_derived_values() {
        let cfg = default_config();
        assert!((cfg.magnet_array_span_m() - 118e-3).abs() < 1e-12);
        assert!((cfg.travel_m() - 77e-3).abs() < 1e-12);
        assert!((cfg.phase_band_pitch_m() - 4e-3).abs() < 1e-12);
        assert_eq!(cfg.rest_offset_m(), 0.0);
        assert!((cfg.magnet_gap_m() - 2e-3).abs() < 1e-12);
        assert!((cfg.min_via_pad_m() - 0.4e-3).abs() < 1e-12);
        assert!((cfg.acceleration_force_n() - 0.03).abs() < 1e-12);
        assert!((cfg.minimum_drive_force_n() - 0.065).abs() < 1e-12);
    }
}
