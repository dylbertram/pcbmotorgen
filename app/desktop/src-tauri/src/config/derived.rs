//! Derived geometry methods on [`LinearMotorConfig`](super::LinearMotorConfig)
//! (delegated to the simulation crate) + `summary()` and their tests.

use super::LinearMotorConfig;

// The following methods form the config API. In the binary these are partly
// exercised via `cargo test` (inline `#[cfg(test)]`) while the shipped runtime
// path builds the config straight from the IPC DTO's `to_core()`, so keep the
// API available without dead-code noise in release builds.
#[allow(dead_code)]
impl LinearMotorConfig {
    // --- Derived geometry (single source of truth lives in the simulation
    // crate — the parent delegates, it does not duplicate the arithmetic) ---

    /// Mover magnet-array span [m]: magnet_count × magnet_pitch.
    pub fn magnet_array_span_m(&self) -> f64 {
        self.to_simulation().magnet_array_span_m()
    }

    /// Derived center-to-center travel [m]:
    /// `active_area_length - magnet_array_span`.
    pub fn travel_m(&self) -> f64 {
        self.to_simulation().travel_m()
    }

    /// Minimum PCB length required [m] (= active_area_length_m).
    pub fn active_length_m(&self) -> f64 {
        self.to_simulation().active_length_m()
    }

    /// Magnet pole pitch [m] (= magnet_pitch for alternating arrays).
    pub fn pole_pitch_m(&self) -> f64 {
        self.to_simulation().pole_pitch_m()
    }

    /// Vernier-adjusted phase-band pitch = (pole_pitch / phases) × spacing_ratio [m].
    pub fn phase_band_pitch_m(&self) -> f64 {
        self.to_simulation().phase_band_pitch_m()
    }

    /// Vernier rest offset: phase offset between a coil center and the
    /// nearest pole center [m]. Clamped to `[0, pole_pitch]`.
    pub fn rest_offset_m(&self) -> f64 {
        self.to_simulation().rest_offset_m()
    }

    /// Gap between adjacent magnets [m]: `magnet_pitch - magnet_width`.
    pub fn magnet_gap_m(&self) -> f64 {
        self.to_simulation().magnet_gap_m()
    }

    /// Minimum via pad diameter [m] = drill + 2 × annular ring.
    pub fn min_via_pad_m(&self) -> f64 {
        self.to_simulation().min_via_pad_m()
    }

    /// Peak inertial force [N] = `carriage_mass × max_accel`.
    pub fn acceleration_force_n(&self) -> f64 {
        self.to_simulation().acceleration_force_n()
    }

    /// Minimum motor force to overcome friction with safety margin [N].
    pub fn minimum_drive_force_n(&self) -> f64 {
        self.to_simulation().minimum_drive_force_n()
    }

    /// Compact human-readable summary.
    pub fn summary(&self) -> String {
        let topo_label = if self.routing_pattern.trim().is_empty() {
            "(none)".to_string()
        } else {
            self.routing_pattern.clone()
        };
        let name = self.name.as_deref().unwrap_or("(unnamed)");
        format!(
            "LinearMotorConfig: {name}\n\
             \x20 Active area len:  {active:.1} mm\n\
             \x20 Travel (derived): {travel:.1} mm\n\
             \x20 Magnet arr. span: {span:.1} mm\n\
             \x20 Magnet:          {count}× {w:.0}×{l:.0}×{h:.0} mm  Br={br:.2} T\n\
             \x20 Arrangement:     alternating poles\n\
             \x20 Coil topology:   {topo}\n\
             \x20 Pole pitch:      {pp:.1} mm\n\
             \x20 Phase-band pitch: {sp:.2} mm  ({phases}-phase)\n\
             \x20 Air gap:         {ag:.2} mm\n\
             \x20 Board width:     {bw:.1} mm\n\
             \x20 Target force:    {tf:.0} mN / {pk:.0} mN peak\n\
             \x20 Friction est.:   {fr:.0} mN (min drive: {md:.0} mN)\n\
             \x20 Accel. budget:   {af:.0} mN ({mass:.0} g × {accel:.1} m/s²)\n\
             \x20 Current:         {curr:.1} A @ {volt:.1} V\n\
             \x20 Cap. bank:       {cap:.0} µF\n\
             \x20 Min trace/space: {mt:.3} / {ms:.3} mm\n\
             \x20 Via drill/ring:  {vd:.2} / {vr:.2} mm\n\
             \x20 Drive freq:      {df:.0} Hz\n\
             \x20 Max ΔT:          {dt:.0} °C",
            name = name,
            active = self.active_area_length_m * 1e3,
            travel = self.travel_m() * 1e3,
            span = self.magnet_array_span_m() * 1e3,
            count = self.magnet_count,
            w = self.magnet_dims_m[0] * 1e3,
            l = self.magnet_dims_m[1] * 1e3,
            h = self.magnet_dims_m[2] * 1e3,
            br = self.magnet_remanence_t,
            topo = topo_label,
            pp = self.pole_pitch_m() * 1e3,
            sp = self.phase_band_pitch_m() * 1e3,
            phases = self.phases,
            ag = self.air_gap_m * 1e3,
            bw = self.board_width_m * 1e3,
            tf = self.target_force_n * 1e3,
            pk = self.peak_force_n * 1e3,
            fr = self.friction_n * 1e3,
            md = self.minimum_drive_force_n() * 1e3,
            af = self.acceleration_force_n() * 1e3,
            mass = self.carriage_mass_kg * 1e3,
            accel = self.max_accel_m_s2,
            curr = self.max_current_a,
            volt = self.supply_voltage_v,
            cap = self.capacitor_bank_uf,
            mt = self.min_trace_m * 1e3,
            ms = self.min_space_m * 1e3,
            vd = self.min_via_drill_m * 1e3,
            vr = self.min_via_annular_ring_m * 1e3,
            df = self.drive_frequency_hz,
            dt = self.max_temperature_rise_c,
        )
    }
}

// ---------------------------------------------------------------------------
// Tests — derived properties + summary
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_simulation::units::{mm, mils_to_m};

    fn default_config() -> LinearMotorConfig {
        LinearMotorConfig {
            name: Some("test-config".into()),
            active_area_length_m: mm(195.0),
            magnet_dims_m: [mm(10.0), mm(10.0), mm(4.0)],
            magnet_count: 10,
            magnet_pitch_m: mm(12.0),
            phases: 3,
            target_force_n: 0.5,
            max_current_a: 1.0,
            min_trace_m: mils_to_m(5.0),
            min_space_m: mils_to_m(5.0),
            min_via_drill_m: mm(0.2),
            min_via_annular_ring_m: mm(0.1),
            board_width_m: mm(20.0),
            air_gap_m: mm(0.5),
            max_layers: 12,
            drive_frequency_hz: 500.0,
            ..LinearMotorConfig::default()
        }
    }

    // --- Derived properties ---

    #[test]
    fn test_pole_pitch_equals_magnet_pitch() {
        let cfg = default_config();
        assert_eq!(cfg.pole_pitch_m(), cfg.magnet_pitch_m);
    }

    #[test]
    fn test_phase_band_pitch_three_phase() {
        let cfg = default_config();
        let expected = cfg.magnet_pitch_m / 3.0;
        assert!((cfg.phase_band_pitch_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_rest_offset_zero_at_unity_ratio() {
        // spacing_ratio = 1.0 → rest offset is exactly 0.
        let cfg = default_config();
        assert_eq!(cfg.rest_offset_m(), 0.0);
    }

    #[test]
    fn test_rest_offset_vernier_4_5() {
        // 4:5 Vernier (spacing_ratio = 0.8) → offset = 0.2 × (pole_pitch / phases).
        let cfg = LinearMotorConfig {
            spacing_ratio: 0.8,
            ..default_config()
        };
        let expected = 0.2 * (cfg.pole_pitch_m() / cfg.phases as f64);
        assert!((cfg.rest_offset_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_rest_offset_clamped_at_zero() {
        // spacing_ratio > 1.0 → formula goes negative, clamp pins it to 0.
        let cfg = LinearMotorConfig {
            spacing_ratio: 1.5,
            ..default_config()
        };
        assert_eq!(cfg.rest_offset_m(), 0.0);
    }

    #[test]
    fn test_magnet_array_span() {
        let cfg = default_config();
        // Nine centre spacings plus the two outer half-magnet widths.
        let expected = 9.0 * mm(12.0) + mm(10.0);
        assert!((cfg.magnet_array_span_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_travel() {
        let cfg = default_config();
        let expected = cfg.active_area_length_m - cfg.magnet_array_span_m();
        assert!((cfg.travel_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_min_via_pad() {
        let cfg = default_config();
        let expected = cfg.min_via_drill_m + 2.0 * cfg.min_via_annular_ring_m;
        assert!((cfg.min_via_pad_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_active_length_greater_than_travel() {
        let cfg = default_config();
        assert!(cfg.active_length_m() > cfg.travel_m());
    }

    #[test]
    fn test_acceleration_force() {
        let cfg = default_config();
        let expected = cfg.carriage_mass_kg * cfg.max_accel_m_s2;
        assert!((cfg.acceleration_force_n() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_minimum_drive_force() {
        let cfg = default_config();
        let expected = cfg.friction_n * 1.3;
        assert!((cfg.minimum_drive_force_n() - expected).abs() < 1e-12);
    }

    // --- Summary ---

    #[test]
    fn test_summary_is_string() {
        let cfg = default_config();
        let s = cfg.summary();
        assert!(!s.is_empty());
    }

    #[test]
    fn test_summary_contains_travel() {
        let cfg = default_config();
        let s = cfg.summary();
        // Physical span = 9 * 12 + 10 = 118 mm; travel = 195 - 118.
        assert!(s.contains("77"));
    }

    #[test]
    fn test_summary_contains_name() {
        let cfg = LinearMotorConfig {
            name: Some("custom-name".into()),
            ..LinearMotorConfig::default()
        };
        assert!(cfg.summary().contains("custom-name"));
    }

    #[test]
    fn test_summary_unnamed_placeholder() {
        let cfg = LinearMotorConfig::default();
        assert!(cfg.summary().contains("(unnamed)"));
    }
}
