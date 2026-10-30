//! Dry-run coil preview.
//!
//! `preview_coils` is a pure dry-run that returns the [`CoilPreview`] — the
//! per-layer summary of the coil set that `write_coils_to_board` would
//! write. Used by the UI to confirm placement before clicking the real
//! "Write to Board" button.

use pcbmotorgen_routing::PhaseCoil;

// ---------------------------------------------------------------------------
// CoilPreview
// ---------------------------------------------------------------------------

/// Per-layer breakdown of the coils that would be written.
#[derive(Debug, Clone, PartialEq)]
pub struct CoilPreviewLayer {
    /// Zero-based layer index in the writer's iteration (`0..num_layers`).
    pub layer_idx: u32,
    /// KiCad `BoardLayer` enum value as `i32` (mirrors the wire format). For
    /// example, `0` bottom = `BL_BCU`, top = `BL_FCU`. The Tauri command
    /// serialises this directly so the UI can render layer-aware previews.
    pub board_layer: i32,
    /// Number of (phase, layer) coil groups on this layer. A phase coil
    /// spans multiple layers; there is one record per (layer, net) pair.
    pub phase_count: u32,
    /// Number of track segments (sum of `segments.len()` across phases).
    pub segment_count: u32,
    /// Number of inter-layer vias (sum of `center_via_positions.len()`).
    pub via_count: u32,
}

/// Dry-run summary of what `write_coils_to_board` would produce.
///
/// Returned by [`preview_coils`]. Contains the full list of `PhaseCoil`
/// objects (so the UI can render the geometry) and a per-layer tally for the
/// at-a-glance "50 tracks + 12 vias across 4 layers" summary the user
/// wants to see before clicking "Write to Board".
#[derive(Debug, Clone)]
pub struct CoilPreview {
    /// Number of layers the writer would iterate over.
    pub num_layers: u32,
    /// Routing pattern id that produced the coil set (e.g.
    /// "infinity-braid"). Distinct from construction topology
    /// (slotted/slotless/coreless).
    pub pattern_id: String,
    /// Per-layer breakdown.
    pub layers: Vec<CoilPreviewLayer>,
    /// Total track segments across all layers.
    pub total_tracks: u32,
    /// Total vias across all layers.
    pub total_vias: u32,
    /// Full phase-coil geometry. The Tauri command converts these to the
    /// `CoilPathIpc` wire format for the UI.
    pub coils: Vec<PhaseCoil>,
}

// ---------------------------------------------------------------------------
// preview_coils
// ---------------------------------------------------------------------------

/// Dry-run: summarise the coil set `write_coils_to_board` would write, but
/// do not touch KiCad.
///
/// `coils` is the pre-generated [`PhaseCoil`] set (built by the caller via
/// [`pcbmotorgen_routing::generate_coils_from_context`]). `num_layers` is the
/// per-call layer count used to map layer indices to KiCad `BoardLayer` enum
/// values via `layer_idx_to_board_layer`.
pub fn preview_coils(coils: &[PhaseCoil], num_layers: u32) -> Result<CoilPreview, String> {
    if num_layers == 0 {
        return Err(
            "num_layers is 0 — nothing to preview. Set at least 2 layers.".to_string(),
        );
    }

    if coils.is_empty() {
        return Err(format!(
            "coil generator produced no coils (num_layers={}). \
             Check that the routing context produces a valid coil set.",
            num_layers,
        ));
    }

    let pattern_id = coils
        .iter()
        .find(|c| !c.pattern_id.is_empty())
        .map(|c| c.pattern_id.clone())
        .unwrap_or_else(|| "infinity-braid".to_string());

    // Report one layer entry per distinct layer index actually present in the
    // coil set (sorted ascending), matching the production write path.
    let mut used_layers: Vec<u32> = coils.iter().map(|c| c.layer_idx).collect::<Vec<u32>>();
    used_layers.sort_unstable();
    used_layers.dedup();

    let mut layers: Vec<CoilPreviewLayer> = Vec::with_capacity(used_layers.len());
    let mut total_tracks: u32 = 0;
    let mut total_vias: u32 = 0;
    for &layer_idx in &used_layers {
        let layer_coils: Vec<&PhaseCoil> =
            coils.iter().filter(|c| c.layer_idx == layer_idx).collect();
        let segment_count: u32 = layer_coils
            .iter()
            .map(|c| c.segments.len() as u32)
            .sum();
        let via_count: u32 = layer_coils
            .iter()
            .map(|c| c.center_via_positions.len() as u32)
            .sum();
        let board_layer = crate::layer_idx_to_board_layer(layer_idx, num_layers.max(1)) as i32;
        total_tracks += segment_count;
        total_vias += via_count;
        layers.push(CoilPreviewLayer {
            layer_idx,
            board_layer,
            phase_count: layer_coils.len() as u32,
            segment_count,
            via_count,
        });
    }

    Ok(CoilPreview {
        num_layers,
        pattern_id,
        layers,
        total_tracks,
        total_vias,
        coils: coils.to_vec(),
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
use super::*;
use pcbmotorgen_routing::{generate_coils_from_context, RoutingContext};
use std::collections::HashMap;

/// Active area used by the braid preview tests [mm].
const ACTIVE_AREA_MM: f64 = 600.0;

/// Board width used by the braid preview tests [mm].
const BOARD_WIDTH_MM: f64 = 20.0;

/// Generate the bundled infinity-braid coil set for `num_layers` layers.
fn braid_coils(num_layers: u32) -> Vec<PhaseCoil> {
    let mut params = HashMap::new();
    params.insert("num_strands".to_string(), 5.0);
    params.insert("n_periods".to_string(), 4.0);
    let ctx = RoutingContext {
        active_area_length_mm: ACTIVE_AREA_MM,
        board_width_mm: BOARD_WIDTH_MM,
        num_layers,
        phases: 3,
        min_trace_mm: 0.1,
        min_space_mm: 0.1,
        expects_continuous: false,
        params,
        ..RoutingContext::default()
    };
    generate_coils_from_context(&ctx, "infinity-braid")
}

// --- preview_coils ---

#[test]
fn test_preview_coils_produces_tracks() {
    // This is the regression test for the "0 of 0" bug: the preview must
    // produce tracks (and at least one coil) for a valid coil set.
    let coils = braid_coils(4);
    let preview = preview_coils(&coils, 4).expect("preview");
    assert!(!preview.coils.is_empty(), "coils must be non-empty");
    assert!(
        preview.total_tracks > 0,
        "coil set must produce at least one track; got {}",
        preview.total_tracks
    );
    // Per-layer tally matches the coils.
    for layer in &preview.layers {
        assert_eq!(
            layer.segment_count as usize,
            preview
                .coils
                .iter()
                .filter(|c| c.layer_idx == layer.layer_idx)
                .map(|c| c.segments.len())
                .sum::<usize>(),
            "layer {} segment_count mismatch",
            layer.layer_idx,
        );
    }
}

#[test]
fn test_preview_coils_per_layer_count_matches_phases() {
    // The four-layer braid populates both pairs, with one presentation coil
    // per (layer, net), three coils per layer on a three-phase board.
    let coils = braid_coils(4);
    let preview = preview_coils(&coils, 4).expect("preview");
    assert_eq!(preview.layers.len(), 4);
    for layer in &preview.layers {
        assert_eq!(
            layer.phase_count, 3,
            "braid layer {} must carry one coil per phase (3); got {}",
            layer.layer_idx, layer.phase_count
        );
    }
}

#[test]
fn test_preview_coils_pattern_id_label() {
    let coils = braid_coils(4);
    let preview = preview_coils(&coils, 4).expect("preview");
    assert_eq!(preview.pattern_id, "infinity-braid");
}

#[test]
fn test_preview_coils_zero_layers_errors() {
    let err = preview_coils(&[], 0).unwrap_err();
    assert!(err.to_lowercase().contains("num_layers"));
}

#[test]
fn test_preview_coils_bottom_layer_uses_bcu() {
    let coils = braid_coils(4);
    let preview = preview_coils(&coils, 4).expect("preview");
    let bottom = &preview.layers[0];
    assert_eq!(
        bottom.board_layer,
        crate::BoardLayer::BlBCu as i32,
        "layer 0 should map to B.Cu"
    );
}

// --- Regression: default config produces coils (the "0 of 0" fix) ---

#[test]
fn test_default_config_generator_produces_coils() {
    // The very assertion the user's bug report was failing: with the default
    // generation parameters the coil generator must produce non-empty coils.
    let coils = braid_coils(4);
    assert!(
        !coils.is_empty(),
        "generator produced 0 coils — writer would emit 0 of 0"
    );
    // The infinity-braid spans layers 0 and 1, one coil per (layer, net)
    // pair, so a 3-phase board yields 2 layers × 3 phases = 6 coils.
    assert!(
        coils.len() >= 3,
        "expected at least one coil per phase, got {}",
        coils.len()
    );
}
}
