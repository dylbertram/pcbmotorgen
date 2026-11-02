//! IPC DTOs for the KiCad bridge: board diagnostics, write preconditions, and
//! coil preview, with their core `pcbmotorgen_export` converters.

use serde::{Deserialize, Serialize};

use super::enums::PreconditionLevelIpc;

// ===========================================================================
// Board diagnostics (get_board_diagnostics / validate_write_preconditions)
// ===========================================================================

/// Snapshot of the open KiCad board — IPC wire format.
///
/// Mirrors `pcbmotorgen_export::BoardDiagnostics`. Board bounds and effective
/// net classes are queried from the open board; individual fields fall back
/// to zero or empty values when their backing query fails.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct BoardDiagnosticsIpc {
    pub board_name: String,
    pub copper_layer_count: u32,
    /// Bounding box of the board edge cuts, in mm; zero when unavailable.
    pub board_x_min_mm: f64,
    pub board_x_max_mm: f64,
    pub board_y_min_mm: f64,
    pub board_y_max_mm: f64,
    pub available_net_classes: Vec<String>,
}

impl BoardDiagnosticsIpc {
    /// Convert a core `BoardDiagnostics` to the IPC wire format.
    pub fn from_core(b: &pcbmotorgen_export::BoardDiagnostics) -> Self {
        Self {
            board_name: b.board_name.clone(),
            copper_layer_count: b.copper_layer_count,
            board_x_min_mm: b.board_x_min_mm,
            board_x_max_mm: b.board_x_max_mm,
            board_y_min_mm: b.board_y_min_mm,
            board_y_max_mm: b.board_y_max_mm,
            available_net_classes: b.available_net_classes.clone(),
        }
    }
}

/// One warning or recommendation about the (config, board) pair.
///
/// Produced by `validate_write_preconditions`. The UI is expected to render
/// `message` verbatim and colour-code by `level`. `field` is an optional
/// machine-readable key (`"num_layers"`, `"active_area_length_m"`, …) the
/// UI can use to highlight the offending input control.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PreconditionWarningIpc {
    pub level: PreconditionLevelIpc,
    pub field: Option<String>,
    pub message: String,
}

impl PreconditionWarningIpc {
    /// Convert a core `PreconditionWarning` to the IPC wire format.
    pub fn from_core(w: &pcbmotorgen_export::PreconditionWarning) -> Self {
        let level = match w.level {
            pcbmotorgen_export::PreconditionLevel::Info => PreconditionLevelIpc::Info,
            pcbmotorgen_export::PreconditionLevel::Warning => {
                PreconditionLevelIpc::Warning
            }
            pcbmotorgen_export::PreconditionLevel::Error => PreconditionLevelIpc::Error,
        };
        Self {
            level,
            field: w.field.clone(),
            message: w.message.clone(),
        }
    }
}

// ===========================================================================
// Coil preview (preview_coils)
// ===========================================================================

/// Per-layer breakdown of the coils that would be written.
///
/// Mirrors `pcbmotorgen_export::CoilPreviewLayer` minus `board_layer` —
/// the UI infers the layer assignment from `layer_idx` (the writer maps
/// `layer_idx == 0` → B.Cu, `layer_idx == num_layers-1` → F.Cu).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CoilPreviewLayerIpc {
    pub layer_idx: u32,
    pub phase_count: u32,
    pub segment_count: u32,
    pub via_count: u32,
}

/// Dry-run summary of what `write_coils_to_board` would produce.
///
/// Returned by `preview_coils`. Contains the per-layer tally and the
/// routing-pattern id that produced the coil set. Pre-condition warnings
/// are *not* included here — the UI calls `validate_write_preconditions`
/// separately for those. The full `PhaseCoil` geometry is *not* carried on
/// the wire here either — the UI calls `generate_coils` separately if it
/// needs the raw segments.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CoilPreviewIpc {
    pub num_layers: u32,
    /// Routing pattern id that produced the coil set (e.g.
    /// `"infinity-braid"`). Mirrors the export crate's `CoilPreview`
    /// `pattern_id` (formerly `topology`).
    pub pattern_id: String,
    pub layers: Vec<CoilPreviewLayerIpc>,
    pub total_tracks: u32,
    pub total_vias: u32,
}

impl CoilPreviewIpc {
    /// Convert a core `CoilPreview` to the IPC wire format.
    ///
    /// Note: `p.pattern_id` is already a `String` (the resolved routing
    /// pattern id), so we just clone it — no enum match needed.
    /// The core's `CoilPreview` does not carry a `warnings` field; the UI
    /// calls `validate_write_preconditions` separately for those.
    pub fn from_core(p: &pcbmotorgen_export::CoilPreview) -> Self {
        let layers = p
            .layers
            .iter()
            .map(|l| CoilPreviewLayerIpc {
                layer_idx: l.layer_idx,
                phase_count: l.phase_count,
                segment_count: l.segment_count,
                via_count: l.via_count,
            })
            .collect();
        Self {
            num_layers: p.num_layers,
            pattern_id: p.pattern_id.clone(),
            layers,
            total_tracks: p.total_tracks,
            total_vias: p.total_vias,
        }
    }
}
