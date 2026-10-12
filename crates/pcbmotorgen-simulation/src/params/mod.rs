//! Simulation input parameters and shared result types (serde-serializable).
//!
//! This crate is parent-free; all configuration it needs lives here rather
//! than in a monolithic `config` module. Quantities are in SI units: metres,
//! Tesla, Amperes, Ohms, Watts. Use [`crate::units`] helpers (mm, mils_to_m,
//! oz_to_m) for human-readable input.
//!
//! Mirrors the fields the simulation modules consumed from the old
//! `LinearMotorConfig`: the subset that `magnetic::*` and `stackup::*` read.
//!
//! ## Module layout
//! - [`validation`](self::validation) — `SimulationInput::new` / `validate`
//! - [`derived`](self::derived) — derived-geometry accessors
//! - [`stackup_result`] — `StackupResult`
//! - [`height_stack_result`] — `HeightStackResult`
//! - [`friction_budget`] — `FrictionBudget`
//! - [`power_budget`] — `PowerBudget`

use serde::{Deserialize, Serialize};

mod derived;
mod friction_budget;
mod height_stack_result;
mod power_budget;
mod phase_band;
mod stackup_result;
mod validation;

pub use friction_budget::FrictionBudget;
pub use height_stack_result::HeightStackResult;
pub use phase_band::{phase_bands_from_routing, PhaseBandPosition};
pub use power_budget::PowerBudget;
pub use stackup_result::StackupResult;

/// Safety margin for minimum drive force calculation.
pub(crate) const SAFETY_MARGIN: f64 = 1.3;

/// Default value for `num_layers` when the field is absent during serde
/// deserialisation (e.g. legacy JSON payloads from before the field was
/// added).
fn default_num_layers() -> u32 {
    4
}

/// Default value for `strands_per_phase` when the field is absent during
/// serde deserialisation. 1 = the historical single-strand behaviour.
fn default_strands_per_phase() -> u32 {
    1
}

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

/// Mover linear bearing / guide type.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BearingType {
    PlasticChannel,
    /// PTFE (Teflon)-lined bearing surface.
    PtfeLined,
    BallBearing,
}

// ---------------------------------------------------------------------------
// SimulationInput
// ---------------------------------------------------------------------------

/// Simulation inputs for a coreless linear PCB motor (flying mover).
///
/// All quantities in SI units. `active_area_length_m` is the primary INPUT;
/// `travel` is derived: `active_area_length − magnet array span`.
///
/// This is the standalone-crate counterpart of the old monolithic
/// `LinearMotorConfig`, restricted to exactly the fields the simulation
/// modules (`magnetic::*`, `stackup::*`) consume.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulationInput {
    // --- Magnet parameters ---
    /// (width_travel, width_cross, height) of one magnet [m].
    pub magnet_dims_m: [f64; 3],
    /// Number of magnets in the array (≥ 2; odd and even counts are supported).
    pub magnet_count: u32,
    /// Centre-to-centre magnet spacing = pole pitch [m].
    pub magnet_pitch_m: f64,
    /// Remnant flux density Br at 20 °C [T].
    pub magnet_remanence_t: f64,

    // --- Geometry ---
    /// Physical length of the stator copper trace region [m]. PRIMARY INPUT.
    pub active_area_length_m: f64,
    /// PCB dimension perpendicular to the travel axis [m].
    pub board_width_m: f64,
    /// PCB substrate thickness [m].
    pub pcb_thickness_m: f64,
    /// Magnet face to PCB copper clearance [m].
    pub air_gap_m: f64,
    /// Number of parallel strands (serpentine paths) per phase on the same
    /// layer. Distinct from a winding: a winding (coil) is one complete
    /// conductive loop.
    #[serde(default = "default_strands_per_phase")]
    pub strands_per_phase: u32,

    // --- Coil ---
    /// Number of electrical phases.
    pub phases: u32,
    /// Vernier phase-band spacing ratio (applied phase-band pitch / ideal
    /// phase-band pitch τ_p/phases). 1.0 = standard 1:1.
    pub spacing_ratio: f64,

    // --- Drive electronics ---
    /// Peak phase current [A]. The power model derives
    /// `I_rms = I_peak/√2` from this for continuous (thermal) loss;
    /// burst loss and capacitor sizing remain peak-referenced.
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
    /// User-selected copper layer count (UI-controlled).
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

    // --- Declared phase bands (kata hzs2) ---
    /// Pattern-declared phase-band positions [m], converted from the routing
    /// contract's resolved `phase_bands` sidecar. When present, commutation
    /// derives the per-coil electrical offsets from the declared band
    /// centerlines (matched by phase label) and the equilibrium helpers can
    /// anchor the copper region to the declared extents. Empty by default
    /// (serde default): the analytic `spacing_ratio · tau_p/phases` offsets
    /// and the context copper region remain the fallback.
    #[serde(default)]
    pub phase_bands: Vec<PhaseBandPosition>,
}

impl Default for SimulationInput {
    fn default() -> Self {
        use crate::units::{mm, mils_to_m};
        Self {
            magnet_dims_m: [mm(10.0), mm(10.0), mm(4.0)],
            magnet_count: 10,
            magnet_pitch_m: mm(12.0),
            magnet_remanence_t: 1.35,
            active_area_length_m: mm(195.0),
            board_width_m: mm(20.0),
            pcb_thickness_m: 0.0016,
            air_gap_m: mm(0.5),
            strands_per_phase: 2,
            phases: 3,
            spacing_ratio: 1.0,
            max_current_a: 1.0,
            supply_voltage_v: 5.0,
            min_trace_m: mils_to_m(5.0),
            min_space_m: mils_to_m(5.0),
            min_via_drill_m: mm(0.2),
            min_via_annular_ring_m: mm(0.1),
            max_layers: 12,
            num_layers: 4,
            drive_frequency_hz: 500.0,
            max_temperature_rise_c: 20.0,
            target_force_n: 0.5,
            peak_force_n: 1.0,
            friction_n: 0.05,
            carriage_mass_kg: 0.015,
            max_accel_m_s2: 2.0,
            capacitor_bank_uf: 1000.0,
            phase_bands: Vec::new(),
        }
    }
}

/// Simulation error.
#[derive(Debug, Clone, PartialEq)]
pub struct SimulationError(pub String);

impl std::fmt::Display for SimulationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for SimulationError {}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_config() -> SimulationInput {
        SimulationInput::default()
    }

    #[test]
    fn test_serde_round_trip() {
        let cfg = default_config();
        let json = serde_json::to_string(&cfg).unwrap();
        let cfg2: SimulationInput = serde_json::from_str(&json).unwrap();
        assert_eq!(cfg.active_area_length_m, cfg2.active_area_length_m);
        assert_eq!(cfg.phases, cfg2.phases);
        assert_eq!(cfg.num_layers, cfg2.num_layers);
    }

    #[test]
    fn test_serde_default_num_layers() {
        let json = r#"{
            "active_area_length_m": 0.195,
            "magnet_dims_m": [0.010, 0.010, 0.004],
            "magnet_count": 10,
            "magnet_pitch_m": 0.012,
            "magnet_remanence_t": 1.35,
            "board_width_m": 0.020,
            "pcb_thickness_m": 0.0016,
            "air_gap_m": 0.0005,
            "phases": 3,
            "spacing_ratio": 1.0,
            "max_current_a": 1.0,
            "supply_voltage_v": 5.0,
            "min_trace_m": 0.000127,
            "min_space_m": 0.000127,
            "min_via_drill_m": 0.0002,
            "min_via_annular_ring_m": 0.0001,
            "max_layers": 12,
            "drive_frequency_hz": 500.0,
            "max_temperature_rise_c": 20.0,
            "target_force_n": 0.5,
            "peak_force_n": 1.0,
            "friction_n": 0.05,
            "carriage_mass_kg": 0.015,
            "max_accel_m_s2": 2.0,
            "capacitor_bank_uf": 1000.0
        }"#;
        let cfg: SimulationInput = serde_json::from_str(json).expect("deserialize");
        assert_eq!(cfg.num_layers, 4, "num_layers must default to 4 when absent");
        assert!(cfg.strands_per_phase >= 1);
        assert!(
            cfg.phase_bands.is_empty(),
            "declared phase bands must default to empty for legacy payloads"
        );
    }

    #[test]
    fn test_serde_round_trip_with_declared_phase_bands() {
        let cfg = SimulationInput {
            phase_bands: vec![PhaseBandPosition {
                phase: "A".to_string(),
                centerline_m: 0.002,
                start_m: 0.0,
                end_m: 0.004,
            }],
            ..SimulationInput::default()
        };
        let json = serde_json::to_string(&cfg).unwrap();
        let back: SimulationInput = serde_json::from_str(&json).unwrap();
        assert_eq!(back.phase_bands, cfg.phase_bands);
    }
}
