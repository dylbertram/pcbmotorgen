//! Application config accessors delegated to the simulation crate.

use super::LinearMotorConfig;

impl LinearMotorConfig {
    /// Physical outer-edge span of the mover magnet array [m].
    pub fn magnet_array_span_m(&self) -> f64 {
        self.to_simulation().magnet_array_span_m()
    }

    /// Edge-aligned travel within the active area [m].
    pub fn travel_m(&self) -> f64 {
        self.to_simulation().travel_m()
    }

    /// Gap between adjacent magnets [m].
    pub fn magnet_gap_m(&self) -> f64 {
        self.to_simulation().magnet_gap_m()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn derived_geometry_uses_configured_magnet_dimensions() {
        let cfg = LinearMotorConfig {
            magnet_dims_m: [0.006, 0.01, 0.004],
            magnet_count: 4,
            magnet_pitch_m: 0.012,
            active_area_length_m: 0.1,
            ..LinearMotorConfig::default()
        };
        assert!((cfg.magnet_array_span_m() - 0.042).abs() < 1e-12);
        assert!((cfg.travel_m() - 0.058).abs() < 1e-12);
        assert!((cfg.magnet_gap_m() - 0.006).abs() < 1e-12);
    }
}
