//! IPC wire format for the motor configuration (`LinearMotorConfigIpc`) plus
//! core↔IPC converters.

use serde::{Deserialize, Serialize};

use super::enums::CommutationModeIpc;
use crate::config::LinearMotorConfig as CoreConfig;

/// Default value for `strands_per_phase` when the field is absent during
/// serde deserialisation. Matches the core's `LinearMotorConfig::default()`.
fn default_strands_per_phase() -> u32 {
    1
}

/// Default routing-pattern plugin id.
fn default_routing_pattern() -> String {
    "infinity-braid".to_string()
}

// ===========================================================================
// LinearMotorConfig (IPC wire format — SI units, snake_case)
// ===========================================================================

/// Linear PCB coreless motor configuration — IPC / frontend contract.
///
/// Mirrors `app/src/lib/types.ts` `LinearMotorConfig` **exactly** (field names,
/// order, units). All lengths in metres, electrical in SI. Per PRODUCT_GOALS.md
/// §3: `active_area_length_m` is the primary INPUT; `travel` is DERIVED.
///
/// Magnet axis convention (matches the frontend store):
/// - `magnet_width_m`       — along the travel (x) axis.
/// - `magnet_cross_width_m` — across the stator (y, board-width axis).
/// - `magnet_height_m`      — vertical thickness (z, magnetisation axis).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct LinearMotorConfigIpc {
    pub active_area_length_m: f64,
    pub board_width_m: f64,
    pub pcb_thickness_m: f64,
    /// Number of parallel serpentine paths per phase on the same layer
    /// ("strands", stacked in y). Mirrors `LinearMotorConfig::strands_per_phase`.
    /// Default 1 (the historical single-strand behaviour).
    #[serde(default = "default_strands_per_phase")]
    pub strands_per_phase: u32,

    pub magnet_count: u32,
    pub magnet_width_m: f64,
    pub magnet_cross_width_m: f64,
    pub magnet_height_m: f64,
    /// Gap between adjacent magnets along the travel axis [m]. Derived
    /// (`pitch - width`) but kept on the wire for UI clarity.
    pub magnet_gap_m: f64,
    /// Magnet pitch (mechanical) = magnet_width + magnet_gap [m]. For the
    /// alternating (non-Halbach) array this equals the magnetic pole pitch
    /// τ_p: adjacent magnets are consecutive opposite poles.
    pub magnet_pitch_m: f64,

    pub magnet_remanence_t: f64,
    pub magnet_grade: String,
    pub air_gap_m: f64,

    /// Extensible routing-pattern plugin id (see `docs/adr/0009`). The
    /// frontend selects from `list_routing_patterns`.
    #[serde(default = "default_routing_pattern")]
    pub routing_pattern: String,
    /// User-editable parameters for the selected routing pattern
    /// (e.g. `num_strands`). Empty = pattern defaults.
    #[serde(default)]
    pub routing_params: std::collections::HashMap<String, f64>,
    pub phases: u32,
    /// Vernier spacing ratio as a raw f64 (1.0, 0.8, 0.8333…).
    pub spacing_ratio: f64,

    pub max_current_a: f64,
    pub supply_voltage_v: f64,

    /// Current copper layer count selection (UI-controlled).
    pub num_layers: u32,
    pub min_trace_m: f64,
    pub min_space_m: f64,
    pub min_via_drill_m: f64,
    pub min_via_annular_ring_m: f64,
    /// DFM limit on layer count (must be even).
    pub max_layers: u32,
    pub drive_frequency_hz: f64,
    pub max_temperature_rise_c: f64,

    pub target_force_n: f64,
    pub peak_force_n: f64,
    pub friction_n: f64,
    pub carriage_mass_kg: f64,
    pub max_accel_m_s2: f64,
    pub capacitor_bank_uf: f64,

    pub commutation: CommutationModeIpc,
    pub n_positions: u32,
    pub meshing: u32,

    pub name: Option<String>,
}

impl LinearMotorConfigIpc {
    /// Convert to the core SI representation.
    ///
    /// Maps the IPC superset onto the core's compact fields:
    /// - `magnet_dims_m = [magnet_width, magnet_cross_width, magnet_height]`
    /// - `magnet_pitch_m` passed through (core stores pitch, not gap).
    /// - UI-only fields (`num_layers`, `commutation`, `n_positions`,
    ///   `meshing`, `magnet_gap_m`, `magnet_cross_width_m`) are NOT carried
    ///   into the core config — they are consumed directly by the stub
    ///   handlers until Phases C/D/E port the full calculators.
    pub fn to_core(&self) -> CoreConfig {
        CoreConfig {
            magnet_dims_m: [
                self.magnet_width_m,
                self.magnet_cross_width_m,
                self.magnet_height_m,
            ],
            magnet_count: self.magnet_count,
            magnet_pitch_m: self.magnet_pitch_m,
            magnet_remanence_t: self.magnet_remanence_t,
            magnet_grade: self.magnet_grade.clone(),
            active_area_length_m: self.active_area_length_m,
            board_width_m: self.board_width_m,
            pcb_thickness_m: self.pcb_thickness_m,
            // Round 9: multi-strand pass-through to the core.
            strands_per_phase: self.strands_per_phase,
            air_gap_m: self.air_gap_m,
            routing_pattern: self.routing_pattern.clone(),
            routing_params: self.routing_params.clone(),
            phases: self.phases,
            spacing_ratio: self.spacing_ratio,
            max_current_a: self.max_current_a,
            supply_voltage_v: self.supply_voltage_v,
            min_trace_m: self.min_trace_m,
            min_space_m: self.min_space_m,
            min_via_drill_m: self.min_via_drill_m,
            min_via_annular_ring_m: self.min_via_annular_ring_m,
            max_layers: self.max_layers,
            num_layers: self.num_layers,
            drive_frequency_hz: self.drive_frequency_hz,
            max_temperature_rise_c: self.max_temperature_rise_c,
            target_force_n: self.target_force_n,
            peak_force_n: self.peak_force_n,
            friction_n: self.friction_n,
            carriage_mass_kg: self.carriage_mass_kg,
            max_accel_m_s2: self.max_accel_m_s2,
            capacitor_bank_uf: self.capacitor_bank_uf,
            name: self.name.clone(),
        }
    }
}

impl From<&CoreConfig> for LinearMotorConfigIpc {
    fn from(c: &CoreConfig) -> Self {
        LinearMotorConfigIpc {
            active_area_length_m: c.active_area_length_m,
            board_width_m: c.board_width_m,
            pcb_thickness_m: c.pcb_thickness_m,
            // Round 9: pass through the multi-strand field. For configs
            // that pre-date it, the core `Default` gives
            // `strands_per_phase: 1` (single strand), the historical
            // behaviour.
            strands_per_phase: c.strands_per_phase,
            magnet_count: c.magnet_count,
            magnet_width_m: c.magnet_dims_m[0],
            magnet_cross_width_m: c.magnet_dims_m[1],
            magnet_height_m: c.magnet_dims_m[2],
            magnet_gap_m: c.magnet_gap_m(),
            magnet_pitch_m: c.magnet_pitch_m,
            magnet_remanence_t: c.magnet_remanence_t,
            magnet_grade: c.magnet_grade.clone(),
            air_gap_m: c.air_gap_m,
            routing_pattern: c.routing_pattern.clone(),
            routing_params: c.routing_params.clone(),
            phases: c.phases,
            spacing_ratio: c.spacing_ratio,
            max_current_a: c.max_current_a,
            supply_voltage_v: c.supply_voltage_v,
            // The core has no "current layer count" field — default to max.
            num_layers: c.max_layers,
            min_trace_m: c.min_trace_m,
            min_space_m: c.min_space_m,
            min_via_drill_m: c.min_via_drill_m,
            min_via_annular_ring_m: c.min_via_annular_ring_m,
            max_layers: c.max_layers,
            drive_frequency_hz: c.drive_frequency_hz,
            max_temperature_rise_c: c.max_temperature_rise_c,
            target_force_n: c.target_force_n,
            peak_force_n: c.peak_force_n,
            friction_n: c.friction_n,
            carriage_mass_kg: c.carriage_mass_kg,
            max_accel_m_s2: c.max_accel_m_s2,
            capacitor_bank_uf: c.capacitor_bank_uf,
            commutation: CommutationModeIpc::MaxThrust,
            n_positions: 50,
            meshing: 20,
            name: c.name.clone(),
        }
    }
}
