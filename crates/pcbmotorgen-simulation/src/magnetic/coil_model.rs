//! `CoilCurrentModel` — converts `PhaseCoil` objects into sampled conductor
//! segments for Lorentz force integration.
//!
//! ## Conductor modelling
//!
//! Each *active conductor* segment (vertical traces perpendicular to travel)
//! is subdivided into `meshing` sub-segments for the Lorentz-force integration.
//! End-turn segments are excluded by default (their net X thrust cancels out
//! and they roughly double computation time).
//!
//! ## Current sign convention
//!
//! The current sign is applied directly to the Lorentz force integral
//! `F = I · Σ(dLᵢ × Bᵢ)`. The serpentine vertex ordering handles the
//! alternating conductor direction automatically:
//! - Even-indexed active conductors go from `(x, 0)` to `(x, W)` — current +Y
//! - Odd-indexed go from `(x, W)` to `(x, 0)` — current -Y

use pcbmotorgen_routing::PhaseCoil;

const MM_TO_M: f64 = 1e-3;

/// Default meshing density for sub-segment force integration.
/// Each active segment (~20 mm long) is divided into this many sub-segments.
/// 20 gives sub-mm resolution.
pub const DEFAULT_MESHING: usize = 20;

/// A sub-segment sample point for Lorentz force integration.
///
/// `midpoint_3d`: 3D midpoint of the sub-segment [m]
/// `dl_3d`: direction vector × sub-segment length [m] (the `dL` in `dL × B`)
#[derive(Debug, Clone, Copy)]
pub struct ConductorSample {
    /// 3D midpoint of this sub-segment [m]
    pub midpoint_3d: [f64; 3],
    /// Direction × length of sub-segment [m] — the dL vector
    pub dl_3d: [f64; 3],
}

/// Converts `PhaseCoil` objects into sampled conductor sub-segments for
/// Lorentz force integration.
///
/// This is the Rust equivalent of Python's `CoilCurrentModel`. Instead of
/// building `magpylib.current.Polyline` objects, it directly produces
/// `ConductorSample` records (midpoint + dL) that the `ForceEvaluator`
/// feeds into `F = I · Σ(dLᵢ × Bᵢ)`.
#[derive(Debug, Clone)]
pub struct CoilCurrentModel {
    /// Number of sub-segments per conductor for force integration.
    pub meshing: usize,
    /// If `true`, end-turn segments are also converted to samples.
    pub include_end_turns: bool,
    /// Z coordinate of the conductor plane [m]. 0 = PCB top surface.
    pub layer_z_m: f64,
}

impl Default for CoilCurrentModel {
    fn default() -> Self {
        Self {
            meshing: DEFAULT_MESHING,
            include_end_turns: false,
            layer_z_m: 0.0,
        }
    }
}

impl CoilCurrentModel {
    /// Create a new `CoilCurrentModel`.
    ///
    /// # Panics
    /// Panics if `meshing < 1`.
    pub fn new(meshing: usize, include_end_turns: bool, layer_z_m: f64) -> Self {
        assert!(meshing >= 1, "meshing must be >= 1, got {meshing}");
        Self {
            meshing,
            include_end_turns,
            layer_z_m,
        }
    }

    /// Build conductor samples for a single phase coil.
    ///
    /// Returns a `Vec<ConductorSample>` with one entry per sub-segment.
    /// The caller applies the current multiplier when computing force.
    pub fn build_phase_samples(&self, coil: &PhaseCoil) -> Vec<ConductorSample> {
        let segments: Vec<_> = if self.include_end_turns {
            coil.segments.iter().collect()
        } else {
            coil.active_segments().into_iter().collect()
        };

        let mut samples = Vec::with_capacity(segments.len() * self.meshing);
        for seg in segments {
            self.segment_to_samples(seg.start, seg.end, &mut samples);
        }
        samples
    }

    /// Convert one segment to sub-segment samples (midpoint + dL).
    ///
    /// Appends `meshing` samples to `out`.
    fn segment_to_samples(
        &self,
        start: (f64, f64),
        end: (f64, f64),
        out: &mut Vec<ConductorSample>,
    ) {
        let n = self.meshing as f64;
        // The routing crate owns geometry in millimetres; the physics model
        // and magba operate in metres.
        let start_x_m = start.0 * MM_TO_M;
        let start_y_m = start.1 * MM_TO_M;
        let end_x_m = end.0 * MM_TO_M;
        let end_y_m = end.1 * MM_TO_M;
        let dx_total = end_x_m - start_x_m;
        let dy_total = end_y_m - start_y_m;
        // Sub-segment dL (full 3D, with z=0 in the conductor plane)
        let dl_x = dx_total / n;
        let dl_y = dy_total / n;
        let dl_z = 0.0;

        for i in 0..self.meshing {
            let t_mid = (i as f64 + 0.5) / n;
            let mx = start_x_m + t_mid * dx_total;
            let my = start_y_m + t_mid * dy_total;
            out.push(ConductorSample {
                midpoint_3d: [mx, my, self.layer_z_m],
                dl_3d: [dl_x, dl_y, dl_z],
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::CoilSegment;

    fn make_test_coil() -> PhaseCoil {
        PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            phase_name: "A".to_string(),
            pattern_id: "infinity-braid".to_string(),
            layer_pair: None,
            center_via_positions: vec![],
            routed_vias: vec![],
            corner_arcs: vec![],
            segments: vec![
                CoilSegment { start: (0.0, 0.0), end: (0.0, 20.0), is_active: true },
                CoilSegment { start: (0.0, 20.0), end: (12.0, 20.0), is_active: false },
                CoilSegment { start: (12.0, 20.0), end: (12.0, 0.0), is_active: true },
            ],
        }
    }

    #[test]
    fn test_build_phase_samples_active_only() {
        let model = CoilCurrentModel::new(5, false, 0.0);
        let coil = make_test_coil();
        let samples = model.build_phase_samples(&coil);
        // 2 active segments × 5 sub-segments = 10
        assert_eq!(samples.len(), 10);
    }

    #[test]
    fn test_build_phase_samples_with_end_turns() {
        let model = CoilCurrentModel::new(5, true, 0.0);
        let coil = make_test_coil();
        let samples = model.build_phase_samples(&coil);
        // 3 segments × 5 sub-segments = 15
        assert_eq!(samples.len(), 15);
    }

    #[test]
    fn test_subsegment_midpoints_and_dl() {
        let model = CoilCurrentModel::new(2, false, 0.001);
        let coil = make_test_coil();
        let samples = model.build_phase_samples(&coil);
        // First active segment: (0,0) → (0, 0.020), meshing=2
        // Sub 0 midpoint: (0, 0.005, 0.001), dl: (0, 0.010, 0)
        // Sub 1 midpoint: (0, 0.015, 0.001), dl: (0, 0.010, 0)
        assert_eq!(samples[0].midpoint_3d, [0.0, 0.005, 0.001]);
        assert_eq!(samples[0].dl_3d, [0.0, 0.010, 0.0]);
        assert_eq!(samples[1].midpoint_3d, [0.0, 0.015, 0.001]);
        assert_eq!(samples[1].dl_3d, [0.0, 0.010, 0.0]);
    }

    #[test]
    #[should_panic(expected = "meshing must be >= 1")]
    fn test_meshing_zero_panics() {
        CoilCurrentModel::new(0, false, 0.0);
    }
}
