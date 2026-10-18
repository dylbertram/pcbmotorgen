//! Base Z-polarised alternating magnet array.

use nalgebra::UnitQuaternion;

use super::super::MagnetArray;
use crate::physics;

impl<'a> MagnetArray<'a> {
    /// Build the base Z-polarised alternating magnet list.
    pub(crate) fn build_alternating(&self, mover_position_m: f64) -> Vec<physics::MagbaCuboidMagnet> {
        let cfg = self.config;
        let z_center = cfg.air_gap_m + cfg.magnet_dims_m[2] / 2.0;
        self.magnet_row(mover_position_m, z_center, cfg.magnet_remanence_t)
    }

    /// `magnet_count` cuboids centred at `z_center`, polarised `±polarization_t`
    /// along z, alternating from `+` at the mover position.
    pub(crate) fn magnet_row(
        &self,
        mover_position_m: f64,
        z_center: f64,
        polarization_t: f64,
    ) -> Vec<physics::MagbaCuboidMagnet> {
        let cfg = self.config;
        let y_center = cfg.board_width_m / 2.0;

        (0..cfg.magnet_count)
            .map(|k| {
                let x = mover_position_m + k as f64 * cfg.magnet_pitch_m;
                let pol_z = polarization_t * if k % 2 == 0 { 1.0 } else { -1.0 };
                physics::make_cuboid_magnet(
                    [x, y_center, z_center],
                    UnitQuaternion::identity(),
                    [0.0, 0.0, pol_z],
                    cfg.magnet_dims_m,
                )
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::params::SimulationInput;

    #[test]
    fn test_alternating_magnet_count() {
        let cfg = SimulationInput::default();
        let arr = MagnetArray::new(&cfg);
        let assembly = arr.build_assembly(0.0);
        // 10 main magnets — the array is always plain alternating.
        assert_eq!(assembly.iter().count(), 10);
    }
}
