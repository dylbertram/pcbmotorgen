//! Force sweep results and their statistics.

use serde::{Deserialize, Serialize};

use super::CommutationMode;

/// Force sweep results across the mover travel range.
///
/// All force values are **mover** forces (Newton's Third Law corrected).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForceResult {
    /// Absolute first-magnet-center positions at which force was evaluated [m].
    /// Physical array edges, not magnet centers, define the sweep limits.
    pub positions_m: Vec<f64>,
    /// Total X (thrust) force at each position [N].
    pub force_x_n: Vec<f64>,
    /// Total Y (lateral) force at each position [N].
    pub force_y_n: Vec<f64>,
    /// Total Z (normal, magnet-attraction) force at each position [N].
    pub force_z_n: Vec<f64>,
    /// Per-phase X thrust [N] — flat vec of `n_positions × n_phases`.
    pub per_phase_force_x: Vec<f64>,
    /// Number of phases.
    pub n_phases: usize,
    /// The commutation mode used for this result.
    pub commutation: CommutationMode,
    /// Applied peak current [A].
    pub current_a: f64,
}

impl ForceResult {
    /// Mean X thrust force over the sweep [N].
    pub fn mean_thrust_n(&self) -> f64 {
        if self.force_x_n.is_empty() {
            return 0.0;
        }
        self.force_x_n.iter().sum::<f64>() / self.force_x_n.len() as f64
    }

    /// Peak X thrust force [N].
    pub fn peak_thrust_n(&self) -> f64 {
        self.force_x_n.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
    }

    /// Minimum X thrust force [N].
    pub fn min_thrust_n(&self) -> f64 {
        self.force_x_n.iter().cloned().fold(f64::INFINITY, f64::min)
    }

    /// Peak-to-peak force ripple as a percentage of mean thrust.
    ///
    /// `Ripple % = (F_max - F_min) / |F_mean| × 100`
    pub fn ripple_pct(&self) -> f64 {
        let mean = self.mean_thrust_n();
        if mean.abs() < 1e-12 {
            return 0.0;
        }
        (self.peak_thrust_n() - self.min_thrust_n()) / mean.abs() * 100.0
    }

    /// Number of sweep positions.
    pub fn n_positions(&self) -> usize {
        self.positions_m.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ripple_pct() {
        let result = ForceResult {
            positions_m: vec![0.0, 0.01, 0.02],
            force_x_n: vec![10.0, 12.0, 8.0],
            force_y_n: vec![0.0, 0.0, 0.0],
            force_z_n: vec![0.0, 0.0, 0.0],
            per_phase_force_x: vec![0.0; 3],
            n_phases: 1,
            commutation: CommutationMode::MaxThrust,
            current_a: 1.0,
        };
        // mean = 10, max = 12, min = 8, ripple = (12-8)/10 * 100 = 40%
        assert!((result.ripple_pct() - 40.0).abs() < 1e-9);
        assert!((result.mean_thrust_n() - 10.0).abs() < 1e-9);
    }

    #[test]
    fn test_ripple_zero_mean() {
        let result = ForceResult {
            positions_m: vec![0.0],
            force_x_n: vec![0.0],
            force_y_n: vec![0.0],
            force_z_n: vec![0.0],
            per_phase_force_x: vec![],
            n_phases: 0,
            commutation: CommutationMode::MaxThrust,
            current_a: 1.0,
        };
        assert!(result.ripple_pct() == 0.0);
    }
}
