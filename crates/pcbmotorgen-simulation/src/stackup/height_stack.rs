//! Height stack calculator.

use crate::params::{HeightStackResult, SimulationInput};
use crate::units::oz_to_m;

/// Nominal LPI solder mask thickness [m].
const SOLDER_MASK_M: f64 = 20e-6;
/// Default assembly tolerance [m].
const DEFAULT_TOLERANCE_M: f64 = 3e-4;

/// Compute the physical height stack for a linear mover assembly.
#[derive(Debug, Clone)]
pub struct HeightStackCalculator {
    /// Outer-layer copper weight [oz/ft²].
    pub outer_copper_oz: f64,
    /// Assembly tolerance / adhesive fillet margin [m].
    pub tolerance_m: f64,
}

impl Default for HeightStackCalculator {
    fn default() -> Self {
        Self {
            outer_copper_oz: 1.0,
            tolerance_m: DEFAULT_TOLERANCE_M,
        }
    }
}

impl HeightStackCalculator {
    /// Return the full height stack for `config`.
    pub fn calculate(&self, config: &SimulationInput) -> HeightStackResult {
        HeightStackResult {
            pcb_thickness_m: config.pcb_thickness_m,
            cu_protrusion_m: oz_to_m(self.outer_copper_oz),
            solder_mask_m: SOLDER_MASK_M,
            air_gap_m: config.air_gap_m,
            magnet_height_m: config.magnet_dims_m[2],
            tolerance_m: self.tolerance_m,
            backplane_m: config.backplane.as_ref().map_or(0.0, |b| b.stack_thickness_m()),
            housing_gap_m: config.backplane.as_ref().map_or(0.0, |b| b.housing_gap_m()),
            housing_m: config.backplane.as_ref().map_or(0.0, |b| b.housing_thickness_m()),
            backplane_analysis: config.backplane.as_ref().map(|b| b.analyze(config)),
        }
    }

    /// True if the stack fits within `budget_m`.
    pub fn fits_in_budget(&self, config: &SimulationInput, budget_m: f64) -> bool {
        self.calculate(config).fits_in_budget(budget_m)
    }

    /// Remaining height margin [m] (negative = over budget).
    pub fn headroom_m(&self, config: &SimulationInput, budget_m: f64) -> f64 {
        self.calculate(config).headroom_m(budget_m)
    }

    /// Maximum air gap that fits within `budget_m` [m].
    pub fn max_air_gap_for_budget(
        &self,
        config: &SimulationInput,
        budget_m: f64,
    ) -> f64 {
        let result = self.calculate(config);
        let other = result.total_height_m() - result.air_gap_m;
        (budget_m - other).max(0.0)
    }

    /// Fractional change in Bz per mm of additional air gap (negative).
    /// s = -π/τ × 1e-3 [per mm]
    pub fn field_sensitivity_per_mm(config: &SimulationInput) -> f64 {
        let tau = config.pole_pitch_m();
        -(std::f64::consts::PI / tau) * 1e-3
    }

    /// Estimate peak Bz [T] at a given air gap using the 1st harmonic.
    /// Bz ≈ (4/π) Br (1 - exp(-π tm/τ)) exp(-π h/τ)
    pub fn field_at_gap(config: &SimulationInput, air_gap_m: f64) -> f64 {
        let br = config.magnet_remanence_t;
        let tau = config.pole_pitch_m();
        let tm = config.magnet_dims_m[2];
        (4.0 / std::f64::consts::PI)
            * br
            * (1.0 - (-std::f64::consts::PI * tm / tau).exp())
            * (-std::f64::consts::PI * air_gap_m / tau).exp()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::units::mm;

    fn default_config() -> SimulationInput {
        SimulationInput {
            active_area_length_m: mm(195.0),
            magnet_dims_m: [mm(10.0), mm(10.0), mm(4.0)],
            magnet_count: 10,
            magnet_pitch_m: mm(12.0),
            phases: 3,
            target_force_n: 0.5,
            max_current_a: 1.0,
            board_width_m: mm(20.0),
            air_gap_m: mm(0.5),
            ..SimulationInput::default()
        }
    }

    #[test]
    fn test_calculate_total_height() {
        let calc = HeightStackCalculator::default();
        let cfg = default_config();
        let hs = calc.calculate(&cfg);
        let expected = 0.0016 + 35e-6 + 20e-6 + 0.0005 + 0.004 + 0.0003;
        assert!((hs.total_height_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_fits_in_budget() {
        let calc = HeightStackCalculator::default();
        let cfg = default_config();
        assert!(calc.fits_in_budget(&cfg, 0.010));
        assert!(!calc.fits_in_budget(&cfg, 0.001));
    }

    #[test]
    fn test_headroom() {
        let calc = HeightStackCalculator::default();
        let cfg = default_config();
        let hs = calc.calculate(&cfg);
        let expected = 0.010 - hs.total_height_m();
        assert!((calc.headroom_m(&cfg, 0.010) - expected).abs() < 1e-12);
    }

    #[test]
    fn test_max_air_gap_for_budget() {
        let calc = HeightStackCalculator::default();
        let cfg = default_config();
        let gap = calc.max_air_gap_for_budget(&cfg, 0.010);
        assert!(gap > 0.0);
        // If we set the air gap to this value, it should fit exactly
        let mut cfg2 = cfg.clone();
        cfg2.air_gap_m = gap;
        assert!(calc.fits_in_budget(&cfg2, 0.010));
    }

    #[test]
    fn test_field_sensitivity_negative() {
        let cfg = default_config();
        let s = HeightStackCalculator::field_sensitivity_per_mm(&cfg);
        assert!(s < 0.0);
        // For 12 mm pole pitch: -π/0.012 * 1e-3 ≈ -0.262
        assert!((s - (-std::f64::consts::PI / 0.012 * 1e-3)).abs() < 1e-6);
    }

    #[test]
    fn test_field_at_gap_positive() {
        let cfg = default_config();
        let bz = HeightStackCalculator::field_at_gap(&cfg, 0.0005);
        assert!(bz > 0.0);
        assert!(bz < cfg.magnet_remanence_t);
    }

    #[test]
    fn test_field_decreases_with_gap() {
        let cfg = default_config();
        let bz1 = HeightStackCalculator::field_at_gap(&cfg, 0.0005);
        let bz2 = HeightStackCalculator::field_at_gap(&cfg, 0.002);
        assert!(bz2 < bz1);
    }
}
