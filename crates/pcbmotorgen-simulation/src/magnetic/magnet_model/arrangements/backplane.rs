//! Image magnets for the backplane and housing (method of images).
//!
//! Each real magnet is mirrored across each boundary plane. The image keeps
//! the same size and polarity, scaled by the boundary's image strength. For
//! μ→∞ the image is exact. For finite μ it is an approximation (see
//! [`crate::backplane`]).

use super::super::MagnetArray;
use crate::backplane::BackplaneAnalysis;
use crate::physics;
use nalgebra::UnitQuaternion;

impl<'a> MagnetArray<'a> {
    /// Mirror the alternating array across the backplane and housing planes.
    /// Returns nothing when there is no backplane or its strength is zero.
    pub(crate) fn build_backplane_images(
        &self,
        mover_position_m: f64,
        analysis: &BackplaneAnalysis,
    ) -> Vec<physics::MagbaCuboidMagnet> {
        let cfg = self.config;
        let z_center = cfg.air_gap_m + cfg.magnet_dims_m[2] / 2.0;
        let y_center = cfg.board_width_m / 2.0;
        let br = cfg.magnet_remanence_t;

        let planes = [
            (analysis.image_strength, Some(analysis.image_plane_z_m)),
            (analysis.housing_image_strength, analysis.housing_plane_z_m),
        ];

        let mut images = Vec::new();
        for (strength, plane) in planes {
            let Some(plane_z) = plane else { continue };
            if strength <= 0.0 {
                continue;
            }
            for k in 0..cfg.magnet_count {
                let x = mover_position_m + k as f64 * cfg.magnet_pitch_m;
                let pol_z = strength * br * if k % 2 == 0 { 1.0 } else { -1.0 };
                // Mirror across z = plane_z: z' = 2·plane − z.
                let z_image = 2.0 * plane_z - z_center;
                images.push(physics::make_cuboid_magnet(
                    [x, y_center, z_image],
                    UnitQuaternion::identity(),
                    [0.0, 0.0, pol_z],
                    cfg.magnet_dims_m,
                ));
            }
        }
        images
    }
}
