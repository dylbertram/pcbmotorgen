//! IPC physics-result DTOs: force sweep, height stack, friction
//! budget, and travel envelope.

use serde::{Deserialize, Serialize};

use super::enums::CommutationModeIpc;

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
    /// Backplane layer thickness below the PCB [m] (t707).
    pub backplane_m: f64,
    /// Air gap between the backplane and the housing [m] (t707).
    pub housing_gap_m: f64,
    /// Housing wall thickness below the backplane [m] (t707).
    pub housing_m: f64,
    /// Backplane image, attraction and saturation estimates; `None` without a
    /// backplane (t707).
    pub backplane_analysis: Option<pcbmotorgen_simulation::backplane::BackplaneAnalysis>,
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
