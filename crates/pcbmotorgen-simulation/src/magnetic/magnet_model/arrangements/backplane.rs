//! Image magnets for the backplane and housing (method of images).
//!
//! The real array is mirrored across the PCB bottom face. Each image keeps
//! the size and polarity of its magnet, scaled by the composite reflection
//! `R` of the stack and housing. For a thick μ→∞ plate (`R = 1`) the image
//! is exact. Otherwise it applies the fundamental's `R` to every harmonic
//! (see [`crate::backplane`]).

use super::super::MagnetArray;
use crate::physics;

impl<'a> MagnetArray<'a> {
    /// Mirror the alternating array across the PCB bottom, `z = −t_pcb`, with
    /// strength `image_strength`.
    pub(crate) fn build_backplane_images(
        &self,
        mover_position_m: f64,
        image_strength: f64,
    ) -> Vec<physics::MagbaCuboidMagnet> {
        let cfg = self.config;
        let z_center = cfg.air_gap_m + cfg.magnet_dims_m[2] / 2.0;
        // z' = 2·plane − z with plane = −t_pcb.
        let z_image = -2.0 * cfg.pcb_thickness_m - z_center;
        self.magnet_row(
            mover_position_m,
            z_image,
            image_strength * cfg.magnet_remanence_t,
        )
    }
}
