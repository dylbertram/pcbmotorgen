//! IPC physics-result DTOs: B-field grid, force sweep, height stack, friction
//! budget, and travel envelope.

use serde::{Deserialize, Serialize};

use super::enums::CommutationModeIpc;

// ===========================================================================
// B-field grid (sample_b_field) — WP4 / WP5 flux-viz backend
// ===========================================================================

/// One B-field sample on the X–Z flux-viz grid.
///
/// All units SI: positions in metres, B-field in Tesla. `mag_t` is the
/// precomputed `sqrt(bx² + by² + bz²)` — the Svelte renderer uses it to
/// colour-code arrows by magnitude without recomputing.
///
/// Field naming on the wire: every field has an explicit `#[serde(rename)]`
/// so the unit suffix (`_m`, `_t`) is preserved end-to-end and stable
/// across Rust → JSON → TypeScript.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BFieldSampleIpc {
    #[serde(rename = "x_m")]
    pub x_m: f64,
    #[serde(rename = "z_m")]
    pub z_m: f64,
    #[serde(rename = "bx_t")]
    pub bx_t: f64,
    #[serde(rename = "by_t")]
    pub by_t: f64,
    #[serde(rename = "bz_t")]
    pub bz_t: f64,
    #[serde(rename = "mag_t")]
    pub mag_t: f64,
}

impl BFieldSampleIpc {
    /// Convert a core `pcbmotorgen_simulation::magnetic::BFieldSample2D` to the
    /// IPC wire form, computing the magnitude on the way out.
    pub fn from_core(s: &pcbmotorgen_simulation::magnetic::BFieldSample2D) -> Self {
        Self {
            x_m: s.x,
            z_m: s.z,
            bx_t: s.bx,
            by_t: s.by,
            bz_t: s.bz,
            mag_t: (s.bx * s.bx + s.by * s.by + s.bz * s.bz).sqrt(),
        }
    }
}

/// Full 2D B-field grid response for the `sample_b_field` Tauri command.
///
/// `samples` is **row-major** with Z as the slow axis:
/// `samples[i_z * n_x + i_x]`. The Svelte `FluxDiagram` reshapes the flat
/// `samples` into a 2D `n_z × n_x` arrow grid using `x_extent_m` /
/// `z_extent_m` to recover the physical axes.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct BFieldGridIpc {
    pub samples: Vec<BFieldSampleIpc>,
    /// `[x_min, x_max]` over which the grid was sampled [m].
    pub x_extent_m: [f64; 2],
    /// `[z_min, z_max]` over which the grid was sampled [m].
    pub z_extent_m: [f64; 2],
}

// ===========================================================================
// Force sweep (evaluate_force_sweep)
// ===========================================================================

/// Force vs mover position along the travel axis.
///
/// Per PRODUCT_GOALS §4.C the sign convention is `F_mover = -F_stator`;
/// `force_x_n` already reflects the mover's reference frame.
/// Ripple % = `(F_max - F_min) / |F_mean| × 100` (§4.A).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ForceSweepResultIpc {
    pub positions_m: Vec<f64>,
    pub force_x_n: Vec<f64>,
    pub force_y_n: Vec<f64>,
    pub force_z_n: Vec<f64>,
    /// Per-phase x-force at each position: `[position][phase]`.
    pub per_phase_force_x: Vec<Vec<f64>>,
    pub commutation: CommutationModeIpc,
    pub current_a: f64,
    pub mean_thrust_n: f64,
    pub peak_thrust_n: f64,
    pub min_thrust_n: f64,
    pub ripple_pct: f64,
    pub n_positions: u32,
}

// ===========================================================================
// Height / friction (compute_*)
// ===========================================================================

/// Explicit vertical stack from PCB bottom to magnet top.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct HeightStackResultIpc {
    pub pcb_thickness_m: f64,
    pub cu_protrusion_m: f64,
    pub solder_mask_m: f64,
    pub air_gap_m: f64,
    pub magnet_height_m: f64,
    pub tolerance_m: f64,
    pub total_height_m: f64,
}

/// Mechanical friction breakdown.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct FrictionBudgetIpc {
    pub bearing_friction_n: f64,
    pub cable_drag_n: f64,
    pub wiper_contact_n: f64,
    /// Coreless motor → zero cogging (PRODUCT_GOALS §4.A).
    pub cogging_n: f64,
    pub total_n: f64,
    pub minimum_drive_force_n: f64,
}

/// Stable-equilibrium travel envelope of the mover array centre: the
/// charge-based electromagnetic endpoints (kata k5r5) clamped into the
/// span-aware flush limits (kata 5c7r). Every stable rest centre satisfies
/// `rest_phase_m ≡ x (mod electrical_period_m)`; the slider range endpoints
/// are the travel limits, not the rests.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct TravelEnvelopeIpc {
    /// First stable rest position of the array centre [m].
    pub min_position_m: f64,
    /// Last stable rest position of the array centre [m] (≥ min).
    pub max_position_m: f64,
    /// Rest phase φ [m].
    pub rest_phase_m: f64,
    /// Electrical period P_e = 2 × pole pitch (one full 360° electrical cycle) [m].
    pub electrical_period_m: f64,
}

impl From<pcbmotorgen_simulation::equilibrium::TravelEnvelope> for TravelEnvelopeIpc {
    fn from(env: pcbmotorgen_simulation::equilibrium::TravelEnvelope) -> Self {
        Self {
            min_position_m: env.min_position_m,
            max_position_m: env.max_position_m,
            rest_phase_m: env.rest_phase_m,
            electrical_period_m: env.electrical_period_m,
        }
    }
}
