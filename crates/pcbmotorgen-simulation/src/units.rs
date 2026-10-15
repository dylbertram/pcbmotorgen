//! Unit conversion helpers. All internal calculations use SI (metres, Tesla,
//! Amperes, Ohms, Watts).


// --- Physical constants ---

/// Electrical resistivity of annealed copper at 20 °C [Ω·m].
pub const RHO_CU: f64 = 1.724e-8;
/// Magnetic permeability of free space [H/m].
pub const MU_0: f64 = 4.0 * std::f64::consts::PI * 1e-7;
/// Nominal copper thickness for 1 oz/ft² [m].
pub const CU_1OZ_M: f64 = 35.0e-6;

// --- Length conversions ---

/// Convert millimetres → metres.
pub fn mm(value: f64) -> f64 {
    value * 1e-3
}
/// Convert mils (thou, 1/1000 inch) → metres.
pub fn mils_to_m(value: f64) -> f64 {
    value * 25.4e-6
}
/// Convert metres → millimetres.
pub fn m_to_mm(value: f64) -> f64 {
    value * 1e3
}

// --- Magnetic flux density ---

/// Convert millitesla → tesla.
pub fn mt_to_t(value: f64) -> f64 {
    value * 1e-3
}

// --- Copper weight / thickness ---

/// Convert PCB copper weight (oz/ft²) → nominal thickness [m].
pub fn oz_to_m(oz: f64) -> f64 {
    oz * CU_1OZ_M
}
/// Convert copper thickness [m] → equivalent weight [oz/ft²].
pub fn m_to_oz(thickness_m: f64) -> f64 {
    thickness_m / CU_1OZ_M
}

// --- KiCad IPC unit conversion ---

/// Convert metres → KiCad IPC nanometres (int64).
pub fn m_to_nm(metres: f64) -> i64 {
    (metres * 1_000_000_000.0) as i64
}
/// Convert KiCad IPC nanometres → metres.
pub fn nm_to_m(nanometres: i64) -> f64 {
    nanometres as f64 / 1_000_000_000.0
}

// --- Electrical / physics helpers ---

/// Skin depth δ = sqrt(ρ / (π·f·µ_r·µ_0)) [m].
pub fn skin_depth_m(frequency_hz: f64, rho: f64, mu_r: f64) -> f64 {
    (rho / (std::f64::consts::PI * frequency_hz * mu_r * MU_0)).sqrt()
}

/// DC resistance per unit length of rectangular trace [Ω/m]: ρ / (w·t).
pub fn cu_resistance_per_length(width_m: f64, thickness_m: f64, rho: f64) -> f64 {
    rho / (width_m * thickness_m)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mm() {
        assert!((mm(10.0) - 0.01).abs() < 1e-12);
        assert!((mm(0.127) - 0.000127).abs() < 1e-12);
    }

    #[test]
    fn test_mils_to_m() {
        assert!((mils_to_m(5.0) - 0.000127).abs() < 1e-8);
    }

    #[test]
    fn test_m_to_mm() {
        assert!((m_to_mm(0.01) - 10.0).abs() < 1e-12);
    }

    #[test]
    fn test_oz_to_m() {
        assert!((oz_to_m(1.0) - 35e-6).abs() < 1e-12);
        assert!((oz_to_m(2.0) - 70e-6).abs() < 1e-12);
    }

    #[test]
    fn test_m_to_oz() {
        assert!((m_to_oz(35e-6) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn test_m_to_nm() {
        assert_eq!(m_to_nm(0.000127), 127000);
        assert_eq!(m_to_nm(0.02), 20000000);
    }

    #[test]
    fn test_nm_to_m() {
        assert!((nm_to_m(127000) - 0.000127).abs() < 1e-12);
    }

    #[test]
    fn test_skin_depth_1mhz() {
        let delta = skin_depth_m(1e6, RHO_CU, 1.0);
        assert!((delta * 1e6 - 66.1).abs() < 0.5); // ≈ 66.1 µm
    }

    #[test]
    fn test_cu_resistance_per_length() {
        let r = cu_resistance_per_length(0.2e-3, oz_to_m(1.0), RHO_CU);
        assert!((r - 2.463).abs() < 0.01);
    }

    #[test]
    fn test_mt_to_t() {
        assert!((mt_to_t(500.0) - 0.5).abs() < 1e-12);
    }
}
