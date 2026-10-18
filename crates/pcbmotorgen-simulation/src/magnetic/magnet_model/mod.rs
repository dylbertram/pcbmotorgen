//! `MagnetArray` — builds and manages the magnet source assembly.
//!
//! ## Arrangement
//!
//! The mover uses a single fixed arrangement: **simple alternating ±Z
//! poles** (Halbach and back-iron variants were removed from the product
//! scope to keep the app and simulation simple).
//!
//! ## Module layout
//! - [`arrangements`](self::arrangements) — the alternating builder impl

use crate::params::SimulationInput;
use crate::physics;

mod arrangements;

/// One B-field sample on the X–Z flux-viz grid.
///
/// `x`, `z` are the observer position in SI metres; `bx`, `by`, `bz` are the
/// B-field vector components in Tesla, in the lab frame (Bx = along travel,
/// By = across board, Bz = vertical). Y is fixed at the board centre-line
/// (`board_width_m / 2`) for every sample.
///
/// `BFieldSample2D` is the core equivalent of the IPC `BFieldSampleIpc`
/// (in `app/src-tauri/src/ipc.rs`); the IPC DTO adds a precomputed magnitude
/// `mag_t = sqrt(bx² + by² + bz²)` for the Svelte renderer's convenience.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BFieldSample2D {
    pub x: f64,
    pub z: f64,
    pub bx: f64,
    pub by: f64,
    pub bz: f64,
}

/// Builds and manages the magnet source assembly.
///
/// The array is always the base Z-polarised alternating array: even-indexed
/// magnets polarised +Z, odd-indexed −Z.
pub struct MagnetArray<'a> {
    config: &'a SimulationInput,
}

impl<'a> MagnetArray<'a> {
    /// Create a new `MagnetArray` bound to the given config.
    pub fn new(config: &'a SimulationInput) -> Self {
        Self { config }
    }

    /// Build a `SourceAssembly` for the plain alternating array at the given
    /// mover position.
    /// With a magnetic backplane or housing configured, the mirror image of
    /// the array across the PCB bottom is appended. Without one, the
    /// assembly is unchanged.
    pub fn build_assembly(&self, mover_position_m: f64) -> physics::MagbaSourceAssembly {
        let mut magnets = self.build_alternating(mover_position_m);
        if let Some(stack) = &self.config.backplane {
            let strength = stack.image_strength(self.config);
            if strength > 0.0 {
                magnets.extend(self.build_backplane_images(mover_position_m, strength));
            }
        }
        physics::make_source_assembly(magnets)
    }

    // ------------------------------------------------------------------
    // Geometry accessors
    // ------------------------------------------------------------------

    /// Z position of main magnet centres above PCB [m].
    pub fn magnet_z_center_m(&self) -> f64 {
        self.config.air_gap_m + self.config.magnet_dims_m[2] / 2.0
    }

    /// X positions of all main magnet centres [m].
    pub fn magnet_x_centers_m(&self, mover_position_m: f64) -> Vec<f64> {
        (0..self.config.magnet_count)
            .map(|k| mover_position_m + k as f64 * self.config.magnet_pitch_m)
            .collect()
    }

    // ------------------------------------------------------------------
    // B-field sampling
    // ------------------------------------------------------------------

    /// Sample B along the board centre-line at the PCB surface.
    ///
    /// - `x_sample`: X positions [m]
    /// - `mover_position_m`: mover position [m]
    /// - `z_observer`: Z of observation plane [m] (default 0 = PCB surface)
    ///
    /// Returns `Vec<[f64; 3]>` of B vectors [T], one per x_sample.
    pub fn bfield_at_pcb_surface(
        &self,
        x_sample: &[f64],
        mover_position_m: f64,
        z_observer: f64,
    ) -> Vec<[f64; 3]> {
        let y_center = self.config.board_width_m / 2.0;
        let observers: Vec<nalgebra::Point3<f64>> = x_sample
            .iter()
            .map(|&x| nalgebra::Point3::new(x, y_center, z_observer))
            .collect();

        let assembly = self.build_assembly(mover_position_m);
        let b_vec = physics::compute_b_batch_parallel(&assembly, &observers);

        b_vec.into_iter().map(|b| [b.x, b.y, b.z]).collect()
    }

    /// Sample the B-field on a 2D X–Z grid at the board centre-line
    /// (`y = board_width_m / 2`).
    ///
    /// This is the WP4 / WP5 flux-viz sampler: a 24×12 arrow grid that the
    /// `FluxDiagram` Svelte component renders. It composes the existing
    /// 1D [`Self::bfield_at_pcb_surface`] at each Z row — no magba plumbing
    /// is duplicated. The 1D sampler routes through
    /// `pcbmotorgen_simulation::physics::compute_b_batch_parallel` (the magba
    /// adapter) and [`Self::build_assembly`] always builds the plain
    /// alternating array.
    ///
    /// - `x_sample`: X positions along the travel axis [m]
    /// - `z_sample`: Z rows of the grid [m] (e.g. PCB surface, magnet
    ///   midplane, 2 mm above magnet top)
    /// - `mover_position_m`: mover X position [m]
    ///
    /// Returns one [`BFieldSample2D`] per `(x, z)` pair, **row-major** with
    /// Z as the slow axis: `samples[i_z * n_x + i_x]`. Total length is
    /// `x_sample.len() * z_sample.len()`. B is in Tesla, in the lab frame
    /// (Bx = along travel, By = across board, Bz = vertical).
    pub fn bfield_grid(
        &self,
        x_sample: &[f64],
        z_sample: &[f64],
        mover_position_m: f64,
    ) -> Vec<BFieldSample2D> {
        let n_x = x_sample.len();
        let n_z = z_sample.len();
        let mut samples = Vec::with_capacity(n_x * n_z);

        for &z in z_sample {
            // Reuse the 1D sampler at this Z row — it owns the magba
            // adapter call and the assembly construction.
            let row = self.bfield_at_pcb_surface(x_sample, mover_position_m, z);
            for (i, b) in row.iter().enumerate() {
                samples.push(BFieldSample2D {
                    x: x_sample[i],
                    z,
                    bx: b[0],
                    by: b[1],
                    bz: b[2],
                });
            }
        }
        samples
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> SimulationInput {
        SimulationInput::default()
    }

    #[test]
    fn test_magnet_z_center() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        // air_gap + height/2 = 0.0005 + 0.002 = 0.0025
        assert!((arr.magnet_z_center_m() - 0.0025).abs() < 1e-9);
    }

    #[test]
    fn test_magnet_x_centers() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        let xs = arr.magnet_x_centers_m(0.0);
        assert_eq!(xs.len(), 10);
        assert!((xs[0] - 0.0).abs() < 1e-9);
        assert!((xs[1] - 0.012).abs() < 1e-9);
        assert!((xs[9] - 0.108).abs() < 1e-9);
    }

    #[test]
    fn test_bfield_at_pcb_surface() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        let xs = vec![0.0, 0.006, 0.012, 0.018];
        let b = arr.bfield_at_pcb_surface(&xs, 0.0, 0.0);
        assert_eq!(b.len(), 4);
        // B should be finite and non-trivial
        for bi in &b {
            assert!(bi[0].is_finite());
            assert!(bi[1].is_finite());
            assert!(bi[2].is_finite());
            // |B| should be > 0
            let mag = (bi[0] * bi[0] + bi[1] * bi[1] + bi[2] * bi[2]).sqrt();
            assert!(mag > 1e-6, "B magnitude too small: {}", mag);
        }
        // Bz should alternate sign between magnet centres
        // x=0 is centre of magnet 0 (Z+), x=0.012 is centre of magnet 1 (Z-)
        assert!(b[0][2] > 0.0, "Bz at x=0 should be positive (Z+ pole)");
        assert!(b[1][2] < 0.0, "Bz at x=6mm should be negative (between poles)");
    }

    // --- WP4 2D B-field grid sampler ---

    /// 2D sampler returns one sample per (x, z) in row-major order, with
    /// finite, non-trivial magnitudes.
    #[test]
    fn test_bfield_grid_row_major_and_magnitude() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        let xs = vec![0.0, 0.006, 0.012, 0.018];
        let zs = vec![0.0, 0.002, 0.004, 0.006];
        let grid = arr.bfield_grid(&xs, &zs, 0.0);
        assert_eq!(grid.len(), xs.len() * zs.len());
        // Row-major: samples[0] is (xs[0], zs[0]); samples[1] is (xs[1], zs[0])
        assert!((grid[0].x - xs[0]).abs() < 1e-12);
        assert!((grid[0].z - zs[0]).abs() < 1e-12);
        assert!((grid[1].x - xs[1]).abs() < 1e-12);
        assert!((grid[1].z - zs[0]).abs() < 1e-12);
        // Last row, first column = (xs[0], zs[3])
        let last_row_first = xs.len() * (zs.len() - 1);
        assert!((grid[last_row_first].x - xs[0]).abs() < 1e-12);
        assert!((grid[last_row_first].z - zs[3]).abs() < 1e-12);
        // Every sample must be finite with non-zero |B|.
        for s in &grid {
            assert!(s.bx.is_finite());
            assert!(s.by.is_finite());
            assert!(s.bz.is_finite());
            let mag = (s.bx * s.bx + s.by * s.by + s.bz * s.bz).sqrt();
            assert!(mag > 1e-6, "B magnitude too small at ({}, {}): {}", s.x, s.z, mag);
        }
    }

    /// Bz at the PCB surface (z=0) over magnet 0 centre (x=0) should be
    /// positive (Z+ pole facing the observer).
    #[test]
    fn test_bfield_grid_alternating_pcb_surface_polarity() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        let xs = vec![0.0, 0.012]; // centre of magnet 0 (Z+), centre of magnet 1 (Z-)
        let zs = vec![0.0];        // PCB surface
        let grid = arr.bfield_grid(&xs, &zs, 0.0);
        assert!(grid[0].bz > 0.0, "Bz at x=0,z=0 should be positive (Z+ pole)");
        assert!(grid[1].bz < 0.0, "Bz at x=12mm,z=0 should be negative (Z- pole)");
    }

    /// `bfield_grid` returns a populated grid for the plain alternating
    /// array (i.e. the call goes through `build_assembly`).
    #[test]
    fn test_bfield_grid_produces_grid() {
        let cfg = test_config();
        let ma = MagnetArray::new(&cfg);
        let xs = vec![0.0, 0.012, 0.024];
        let zs = vec![0.0, 0.0025];
        let grid = ma.bfield_grid(&xs, &zs, 0.0);
        assert_eq!(
            grid.len(),
            xs.len() * zs.len(),
            "produced wrong grid length"
        );
        for s in &grid {
            assert!(s.bx.is_finite() && s.by.is_finite() && s.bz.is_finite());
        }
    }

    /// 1D `bfield_at_pcb_surface` signature is unchanged — `bfield_grid` is
    /// a sibling, not a replacement. This test guards the 1D contract.
    #[test]
    fn test_bfield_at_pcb_surface_1d_signature_intact() {
        let cfg = test_config();
        let arr = MagnetArray::new(&cfg);
        // Original 3-arg call form: (x_sample, mover_position_m, z_observer)
        let b = arr.bfield_at_pcb_surface(&[0.0, 0.006], 0.0, 0.0);
        assert_eq!(b.len(), 2);
        // Returns Vec<[f64; 3]>, not Vec<BFieldSample2D>
        assert_eq!(b[0].len(), 3);
    }
}
