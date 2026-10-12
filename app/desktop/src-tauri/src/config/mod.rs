//! Configuration structs and result types (serde-serializable).
//!
//! The parent (Tauri app) owns exactly one config: [`LinearMotorConfig`] plus
//! its validation error [`ConfigError`] and the orchestration/derived-method
//! helpers. All physics and shared result types have moved into the leaf
//! crates — [`SimulationInput`](pcbmotorgen_simulation::params::SimulationInput),
//! `StackupResult`/`HeightStackResult`/`FrictionBudget`/`PowerBudget` live in
//! `pcbmotorgen_simulation::params`; `RoutingContext` lives in
//! `pcbmotorgen_routing` and `DesignRules` in `pcbmotorgen-dfm` (kata 0rgs).
//! The parent delegates derived arithmetic to the
//! simulation crate instead of duplicating it.
//!
//! All quantities in SI units: metres, Tesla, Amperes, Ohms, Watts.
//! Use [`pcbmotorgen_simulation::units`] helpers (mm, mils_to_m, oz_to_m).
//!
//! ## Module layout
//!
//! The `LinearMotorConfig` API is split across sibling submodules, all of
//! which `impl` the struct defined here:
//! - [`validation`] — `new()` / `validate()` (field-invariant checks).
//! - [`derived`] — derived geometry methods + `summary()`.
//! - [`bridges`] — conversions to the leaf crates (`routing_context`,
//!   `design_rules`, `to_simulation`, `generate_coils_for_board`,
//!   `routing_pattern_id`, `sync_magnet_grade`).

use serde::{Deserialize, Serialize};

pub mod bridges;
pub mod derived;
pub mod validation;

/// Default value for `num_layers` when the field is absent during serde
/// deserialisation (e.g. legacy JSON payloads from before the field was
/// added). Chosen to match the UI's typical 4-layer selection so the
/// validator does not spuriously fire on a 4-layer board.
fn default_num_layers() -> u32 {
    4
}

/// Default value for `strands_per_phase` when the field is absent during
/// serde deserialisation. 1 = the historical single-strand behaviour
/// (Round 8 and earlier). Round 9 introduces multi-strand; the default
/// preserves backward compatibility for existing JSON payloads.
fn default_strands_per_phase() -> u32 {
    1
}

fn default_routing_pattern() -> String {
    "infinity-braid".to_string()
}

// ---------------------------------------------------------------------------
// LinearMotorConfig
// ---------------------------------------------------------------------------

/// Linear PCB coreless motor configuration (flying mover).
///
/// All quantities in SI units. `active_area_length_m` is the primary INPUT;
/// `travel` is derived: `active_area_length - magnet_array_span`.
///
/// Ports Python `BaseMotorConfig` + `LinearMotorConfig` as a single flat struct
/// (Rust has no dataclass inheritance).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinearMotorConfig {
    // --- Magnet parameters ---
    /// (width_travel, width_cross, height) of one magnet [m].
    pub magnet_dims_m: [f64; 3],
    /// Number of magnets in the array (≥ 2; odd and even counts are supported).
    pub magnet_count: u32,
    /// Centre-to-centre magnet spacing = pole pitch [m].
    pub magnet_pitch_m: f64,
    /// Remnant flux density Br at 20 °C [T].
    pub magnet_remanence_t: f64,
    /// Standard NdFeB grade name (N35–N52) or "Custom".
    pub magnet_grade: String,

    // --- Geometry ---
    /// Physical length of the stator copper trace region [m]. PRIMARY INPUT.
    pub active_area_length_m: f64,
    /// PCB dimension perpendicular to the travel axis [m].
    pub board_width_m: f64,
    /// PCB substrate thickness [m].
    pub pcb_thickness_m: f64,
    /// Magnet face to PCB copper clearance [m].
    pub air_gap_m: f64,
    /// Number of parallel serpentine paths per phase on the same layer
    /// ("strands", stacked in the y direction within the board_width).
    /// Each strand uses `board_width_m / strands_per_phase` of the
    /// vertical board space. The strands are offset in x by
    /// `phase_band_pitch / strands_per_phase` so their end-turns and active
    /// conductors interleave without collision. Default 1 (single strand,
    /// the historical single-layer serpentine).
    ///
    /// Round 9 motivation: with 1 strand per phase, the user's 3-phase /
    /// 4-layer / 195 mm board only had 33 segments per phase, 132
    /// total. With `strands_per_phase = 2` the same config produces 66
    /// segments per phase × 3 phases = 198 segments (50% more copper per
    /// phase), with the two strands interleaved so they don't cross each
    /// other and the end turns routed within the active area (the braid's
    /// end turns are part of the pattern — there is no end padding).
    #[serde(default = "default_strands_per_phase")]
    pub strands_per_phase: u32,

    // --- Coil ---
    /// Extensible routing-pattern plugin id (see the `pcbmotorgen-routing`
    /// crate and `docs/adr/0009`). Defaults to the bundled `infinity-braid`.
    #[serde(default = "default_routing_pattern")]
    pub routing_pattern: String,
    /// User-editable parameters for the selected routing pattern (keyed by the
    /// pattern's declared [`PatternParameter`] keys, e.g. `num_strands`). Board
    /// -derived quantities (amplitude, total length) are computed by the
    /// pattern and never appear here. Defaults to empty = use pattern defaults.
    #[serde(default)]
    pub routing_params: std::collections::HashMap<String, f64>,
    /// Number of electrical phases.
    pub phases: u32,
    /// Vernier phase-band pitch spacing ratio. 1.0 = standard 1:1.
    pub spacing_ratio: f64,

    // --- Drive electronics ---
    /// Peak phase current [A].
    pub max_current_a: f64,
    /// Drive electronics supply voltage [V].
    pub supply_voltage_v: f64,

    // --- DFM rules ---
    /// Minimum manufacturable trace width [m].
    pub min_trace_m: f64,
    /// Minimum trace-to-trace clearance [m].
    pub min_space_m: f64,
    /// Minimum via drill diameter [m].
    pub min_via_drill_m: f64,
    /// Minimum via annular ring width [m].
    pub min_via_annular_ring_m: f64,
    /// Maximum copper layer count (must be even).
    pub max_layers: u32,
    /// User-selected copper layer count (UI-controlled). Defaults to
    /// `max_layers` when the caller does not specify it (e.g. when
    /// deserialising configs that pre-date this field). The user may choose
    /// a value ≤ `max_layers` to use fewer copper layers than the DFM upper
    /// limit (e.g. a 4-layer user selection on a 12-layer-capable board).
    ///
    /// This is the value the `validate_write_preconditions` checks against
    /// the live board's `copper_layer_count` — NOT `max_layers`, which is
    /// the DFM upper bound, not the actual write target.
    #[serde(default = "default_num_layers")]
    pub num_layers: u32,
    /// Nominal electrical drive frequency for skin-depth [Hz].
    pub drive_frequency_hz: f64,
    /// Maximum acceptable PCB temperature rise [°C].
    pub max_temperature_rise_c: f64,

    // --- Force / motion targets ---
    /// Minimum continuous thrust [N].
    pub target_force_n: f64,
    /// Burst thrust target [N] (must be ≥ target_force_n).
    pub peak_force_n: f64,
    /// Estimated total mechanical friction [N].
    pub friction_n: f64,
    /// Moving carriage mass [kg].
    pub carriage_mass_kg: f64,
    /// Maximum carriage acceleration [m/s²].
    pub max_accel_m_s2: f64,
    /// Burst-current capacitor bank size [µF].
    pub capacitor_bank_uf: f64,

    // --- Metadata ---
    /// Optional human-readable label.
    pub name: Option<String>,
}

impl Default for LinearMotorConfig {
    fn default() -> Self {
        use pcbmotorgen_simulation::units::{mm, mils_to_m};
        Self {
            magnet_dims_m: [mm(10.0), mm(10.0), mm(4.0)],
            magnet_count: 10,
            magnet_pitch_m: mm(12.0),
            magnet_remanence_t: 1.35,
            magnet_grade: "N44".to_string(),
            active_area_length_m: mm(195.0),
            board_width_m: mm(20.0),
            pcb_thickness_m: 0.0016,
            air_gap_m: mm(0.5),
            // Round 9: multi-strand defaults that the production code
            // path uses for the MagneticFader reference design. With
            // `strands_per_phase = 2`:
            //
            // - Each phase gets 2 parallel serpentine paths on its
            //   assigned layer (stacked in y, interleaved in x by
            //   `phase_band_pitch / 2`).
            // - The multi-strand design is single-layer per phase, so
            //   no inter-layer connections, no through-vias, no
            //   buried vias — directly addresses the Bug 17 through-via
            //   short-circuit symptom the user reported in Round 8.
            //
            // Tests that exercise the single-strand case (e.g. the
            // Round 8 regression tests) override these fields
            // explicitly to keep their assertions stable.
            strands_per_phase: 2,
            routing_pattern: "infinity-braid".to_string(),
            routing_params: std::collections::HashMap::new(),
            phases: 3,
            spacing_ratio: 1.0,
            max_current_a: 1.0,
            supply_voltage_v: 5.0,
            min_trace_m: mils_to_m(5.0),
            min_space_m: mils_to_m(5.0),
            min_via_drill_m: mm(0.2),
            min_via_annular_ring_m: mm(0.1),
            max_layers: 12,
            // User's actual layer selection. Default to the UI's typical
            // 4-layer choice rather than the DFM upper limit so that
            // `validate_write_preconditions` does not warn against a
            // 4-layer board when the user has not yet narrowed the field.
            num_layers: 4,
            drive_frequency_hz: 500.0,
            max_temperature_rise_c: 20.0,
            target_force_n: 0.5,
            peak_force_n: 1.0,
            friction_n: 0.05,
            carriage_mass_kg: 0.015,
            max_accel_m_s2: 2.0,
            capacitor_bank_uf: 1000.0,
            name: None,
        }
    }
}

/// Configuration validation error.
#[derive(Debug, Clone, PartialEq)]
pub struct ConfigError(pub String);

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for ConfigError {}

// ---------------------------------------------------------------------------
// Tests — struct / Default / serde + leaf-crate result-type sanity checks
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_simulation::units::{mm, mils_to_m, oz_to_m};
    use pcbmotorgen_simulation::params::{
        FrictionBudget, HeightStackResult, PowerBudget, StackupResult,
    };

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

    // --- Construction ---

    #[test]
    fn test_default_config_validates() {
        assert!(default_config().validate().is_ok());
    }

    #[test]
    fn test_name_stored() {
        let cfg = LinearMotorConfig {
            name: Some("my-actuator".into()),
            ..LinearMotorConfig::default()
        };
        assert_eq!(cfg.name.as_deref(), Some("my-actuator"));
    }

    #[test]
    fn test_name_optional() {
        let cfg = LinearMotorConfig::default();
        assert!(cfg.name.is_none());
    }

    #[test]
    fn test_default_phases() {
        assert_eq!(LinearMotorConfig::default().phases, 3);
    }

    #[test]
    fn test_default_magnet_count() {
        assert_eq!(LinearMotorConfig::default().magnet_count, 10);
    }

    #[test]
    fn test_default_max_layers_even() {
        assert!(LinearMotorConfig::default().max_layers % 2 == 0);
    }

    // --- Leaf-crate result types (StackupResult / HeightStackResult /
    // FrictionBudget / PowerBudget) ---

    fn base_4layer() -> StackupResult {
        StackupResult {
            layer_count: 4,
            trace_widths_m: vec![mm(0.15), mm(0.25), mm(0.25), mm(0.15)],
            cu_thickness_m: vec![oz_to_m(1.0), oz_to_m(2.0), oz_to_m(2.0), oz_to_m(1.0)],
            via_drill_m: mm(0.2),
            via_annular_ring_m: mm(0.1),
            via_grid_rows: 2,
            via_grid_cols: 3,
            estimated_force_n: 0.42,
            estimated_dc_resistance_ohm: 3.1,
            notes: vec!["4-layer stackup chosen by test fixture".into()],
        }
    }

    #[test]
    fn test_stackup_4layer_validates() {
        assert!(base_4layer().validate().is_ok());
    }

    #[test]
    fn test_stackup_odd_layer_count_raises() {
        let mut s = base_4layer();
        s.layer_count = 3;
        assert!(s.validate().is_err());
    }

    #[test]
    fn test_stackup_trace_width_count_mismatch() {
        let mut s = base_4layer();
        s.trace_widths_m = vec![mm(0.15), mm(0.25), mm(0.15)];
        assert!(s.validate().is_err());
    }

    #[test]
    fn test_stackup_outer_layer_ids() {
        let s = base_4layer();
        assert_eq!(s.outer_layer_ids(), (0, 3));
    }

    #[test]
    fn test_stackup_inner_layer_ids() {
        let s = base_4layer();
        assert_eq!(s.inner_layer_ids(), vec![1, 2]);
    }

    #[test]
    fn test_stackup_via_pad() {
        let s = base_4layer();
        let expected = mm(0.2) + 2.0 * mm(0.1);
        assert!((s.via_pad_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_stackup_via_grid_count() {
        assert_eq!(base_4layer().via_grid_count(), 6);
    }

    #[test]
    fn test_stackup_summary() {
        let s = base_4layer();
        let summary = s.summary();
        assert!(summary.contains("4 layers"));
    }

    // --- HeightStackResult ---

    #[test]
    fn test_height_stack_total() {
        let hs = HeightStackResult {
            pcb_thickness_m: 0.0016,
            cu_protrusion_m: 35e-6,
            solder_mask_m: 20e-6,
            air_gap_m: 0.0005,
            magnet_height_m: 0.004,
            tolerance_m: 0.0003,
        };
        let expected = 0.0016 + 35e-6 + 20e-6 + 0.0005 + 0.004 + 0.0003;
        assert!((hs.total_height_m() - expected).abs() < 1e-12);
    }

    #[test]
    fn test_height_stack_fits_in_budget() {
        let hs = HeightStackResult {
            pcb_thickness_m: 0.0016,
            cu_protrusion_m: 35e-6,
            solder_mask_m: 20e-6,
            air_gap_m: 0.0005,
            magnet_height_m: 0.004,
            tolerance_m: 0.0003,
        };
        assert!(hs.fits_in_budget(0.010));
        assert!(!hs.fits_in_budget(0.001));
    }

    #[test]
    fn test_height_stack_headroom() {
        let hs = HeightStackResult {
            pcb_thickness_m: 0.0016,
            cu_protrusion_m: 35e-6,
            solder_mask_m: 20e-6,
            air_gap_m: 0.0005,
            magnet_height_m: 0.004,
            tolerance_m: 0.0003,
        };
        let total = hs.total_height_m();
        assert!((hs.headroom_m(0.010) - (0.010 - total)).abs() < 1e-12);
    }

    // --- FrictionBudget ---

    #[test]
    fn test_friction_total() {
        let fb = FrictionBudget {
            bearing_friction_n: 0.03,
            cable_drag_n: 0.52,
            wiper_contact_n: 0.055,
            cogging_n: 0.0,
        };
        assert!((fb.total_n() - 0.605).abs() < 1e-12);
    }

    #[test]
    fn test_friction_minimum_drive_force() {
        let fb = FrictionBudget {
            bearing_friction_n: 0.1,
            cable_drag_n: 0.0,
            wiper_contact_n: 0.0,
            cogging_n: 0.0,
        };
        assert!((fb.minimum_drive_force_n() - 0.13).abs() < 1e-12);
    }

    // --- PowerBudget ---

    #[test]
    fn test_power_budget_summary() {
        let pb = PowerBudget {
            phase_resistance_ohm: 3.1,
            continuous_power_w: 0.5,
            burst_power_w: 1.0,
            temperature_rise_c: 7.5,
            capacitor_required_uf: 500.0,
            efficiency_pct: 5.0,
        };
        let s = pb.summary();
        assert!(s.contains("3.100"));
        assert!(s.contains("500"));
    }

    // --- Serde round-trip ---

    #[test]
    fn test_config_serde_roundtrip() {
        let cfg = default_config();
        let json = serde_json::to_string(&cfg).unwrap();
        let cfg2: LinearMotorConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(cfg2.active_area_length_m, cfg.active_area_length_m);
        assert_eq!(cfg2.magnet_count, cfg.magnet_count);
        assert_eq!(cfg2.routing_pattern, cfg.routing_pattern);
    }

    #[test]
    fn test_routing_pattern_defaults() {
        let cfg = LinearMotorConfig::default();
        assert_eq!(cfg.routing_pattern, "infinity-braid");
    }
}
