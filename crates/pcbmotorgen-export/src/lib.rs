//! # pcbmotorgen-export
//!
//! Concrete exporters for the routing crate's generic coil geometry.
//!
//! This crate combines what were previously two separate crates into one
//! public API surface:
//!
//! - [`routing_result_to_dxf`] / [`phase_coils_to_dxf`] — pure DXF R12 ASCII
//!   export (`LINE` / `ARC` / `CIRCLE`) for mechanical CAD / CAM import.
//!   Supporting renderers live in [`entities`], [`sections`], [`groups`] and
//!   [`helpers`].
//! - [`KiCadClient`] — KiCad 10 IPC adapter over an NNG `req0` socket,
//!   including the protobuf API tree ([`proto`]), atomic commits ([`Commit`]),
//!   board item production ([`coils_to_board_items`], and the additive
//!   [`io_elements_to_board_items`] for IO pads / fanout traces), high-level
//!   board operations ([`BoardHandle`]) and diagnostics / preview
//!   ([`get_board_diagnostics`] — live edge-cut bounding box + net classes
//!   in use, [`validate_write_preconditions`], [`preview_coils`]).
//!
//! Both exporters consume [`pcbmotorgen_routing`] types ([`PhaseCoil`],
//! [`RoutingResult`]) and the [`pcbmotorgen_dfm`] DFM sizing snapshot
//! ([`DesignRules`]), and use **millimetres** as the canonical unit.
//!
//! ## Submodules
//!
//! | Module                  | Origin   | Contents                                                                   |
//! |-------------------------|----------|----------------------------------------------------------------------------|
//! | [`entities`]            | DXF      | `LINE` / `ARC` / `CIRCLE` entity emitters                                   |
//! | [`sections`]            | DXF      | `HEADER` / `TABLES` sections                                                |
//! | [`groups`]              | DXF      | DXF group-code / value codec                                                |
//! | [`helpers`]             | DXF      | unit + three-point circle helpers                                           |
//! | [`proto`]               | KiCad    | prost-generated KiCad 10 IPC protobuf types (`common`, `board`, `schematic`)|
//! | [`client`]              | KiCad    | [`KiCadClient`], [`KicadTransport`] trait, [`MockTransport`], transports     |
//! | [`errors`]              | KiCad    | [`KiCadError`]                                                              |
//! | [`layer_map`]           | KiCad    | layer-index → [`BoardLayer`] mapping + unit conversion                       |
//! | [`writer`]              | KiCad    | pure `coils_to_board_items()` converter                                     |
//! | [`commit`]              | KiCad    | [`Commit`] atomic commit handle                                              |
//! | [`board`]               | KiCad    | [`BoardHandle`] high-level board operations                                 |
//! | [`diagnostics`]         | KiCad    | board-diagnostics + pre-write validation + dry-run preview                  |
//!
//! ## DXF mapping
//!
//! | Routing element  | DXF entity | Notes                                               |
//! |------------------|------------|-----------------------------------------------------|
//! | `RouteSegment`   | `LINE`     | Straight trace segment                              |
//! | `RouteCurve`     | `ARC`      | Three-point (start/mid/end) → centre/radius/angles  |
//! | `Via`            | `CIRCLE`   | Pad diameter from design rules                      |
//! | `IoTrace`        | `LINE`     | IO fanout traces emit as normal tracks              |
//! | `IoPad`          | `CIRCLE` / `LINE`×4 | `IO_Pad` layer; circle for round pads, closed rectangle outline for rectangular pads |
//!
//! Payloads without IO elements produce byte-identical output to previous
//! releases (the IO emission loops are no-ops when the additive fields are
//! empty); a golden test pins this in `tests/golden_compat.rs`.
//!
//! ## Layer naming (DXF)
//!
//! - Segments and curves: `L<layer_idx>_<net>` (e.g. `L0_A`, `L1_B`)
//! - Vias: `Via` (one layer for all vias)
//!
//! ## Usage — DXF
//!
//! ```rust,ignore
//! use pcbmotorgen_export::routing_result_to_dxf;
//! use pcbmotorgen_dfm::DesignRules;
//!
//! let dxf_string = routing_result_to_dxf(
//!     &routing_result,
//!     &DesignRules::default(),
//!     /* active_area_length_mm = */ 48.0,
//!     /* centre_x = */ true,
//! );
//! std::fs::write("coils.dxf", dxf_string)?;
//! ```
//!
//! ## Usage — KiCad
//!
//! ```rust,ignore
//! use pcbmotorgen_export::{BoardHandle, KiCadClient, DocumentSpecifier};
//!
//! let mut client = KiCadClient::new(None, None, 2000);
//! client.connect()?;
//! // ... resolve an open PCB `DocumentSpecifier` via GetOpenDocuments ...
//! let mut board = BoardHandle::new(&mut client, document);
//! board.write_coils(&coils, num_layers, &rules, active_area_length_mm)?;
//! // IO elements (pads + fanout traces) go through the additive writer:
//! // board.write_io_elements(&result, num_layers, &rules, active_area_length_mm)?;
//! ```

pub mod board;
pub mod cad_dxf;
pub mod client;
pub mod commit;
pub mod diagnostics;
pub mod entities;
pub mod errors;
pub mod groups;
pub mod helpers;
pub mod layer_map;
pub mod sections;
pub mod writer;

/// Raw generated protobuf modules for the KiCad IPC API.
///
/// The `include!` pulls in `OUT_DIR/kiapi.rs`, which prost-build emits as the
/// top-level umbrella module for the `kiapi.*` package tree. Organised by
/// KiCad package:
///
/// - `proto::common` — `ApiRequest`, `ApiResponse`, `ApiStatusCode`, headers
/// - `proto::common::types` — `Vector2`, `Distance`, `Kiid`, `DocumentSpecifier`,
///   `ItemHeader`, `KiCadVersion`, `LockedState`, ...
/// - `proto::common::commands` — `BeginCommit`, `EndCommit`, `CreateItems`,
///   `CreateItemsResponse`, `GetItems`, `Ping`, `GetVersion`, ...
/// - `proto::board` — `BoardStackup`, `BoardSettings`, `BoardDesignRules`
/// - `proto::board::types` — `Track`, `Via`, `Net`, `BoardLayer`, `PadStack`, ...
/// - `proto::board::commands` — board-level commands
/// - `proto::schematic::types` — schematic-level types
pub mod proto {
    include!(concat!(env!("OUT_DIR"), "/kiapi.rs"));
}

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{PhaseCoil, RoutingResult};

// ===========================================================================
// DXF exporter
// ===========================================================================

/// Build the full DXF file string from a complete geometry set.
///
/// This is the main DXF public API. It produces a self-contained DXF R12
/// ASCII file with HEADER, TABLES (layer definitions), ENTITIES (geometry),
/// and EOF.
///
/// # Arguments
///
/// * `result` — The routing geometry from any pattern plugin.
/// * `rules`  — Design rules; used for via circle diameter.
/// * `active_area_length_mm` — Length of the active area; passed through if
///   the caller wants to centre coordinates (set to 0.0 for no centring).
/// * `centre_x` — If `true`, shift x coordinates by `-active_area_length_mm / 2`
///   so the coil set is centred on x = 0 (matches the KiCad writer behaviour).
pub fn routing_result_to_dxf(
    result: &RoutingResult,
    rules: &DesignRules,
    active_area_length_mm: f64,
    centre_x: bool,
) -> String {
    let x_offset_mm = if centre_x {
        active_area_length_mm / 2.0
    } else {
        0.0
    };

    let via_radius_mm = (rules.min_via_drill_mm + 2.0 * rules.min_via_annular_ring_mm) / 2.0;

    // Collect unique layer names for the TABLES section.
    let mut layer_names: Vec<String> = Vec::new();

    for seg in &result.segments {
        let name = format!("L{}_{}", seg.layer, seg.net);
        if !layer_names.contains(&name) {
            layer_names.push(name);
        }
    }
    for curve in &result.curves {
        let name = format!("L{}_{}", curve.layer, curve.net);
        if !layer_names.contains(&name) {
            layer_names.push(name);
        }
    }
    if !result.vias.is_empty() && !layer_names.contains(&"Via".to_string()) {
        layer_names.push("Via".to_string());
    }
    // IO fanout traces share the segment layer naming; IO pads get one
    // dedicated `IO_Pad` layer.
    for trace in &result.io_traces {
        let name = format!("L{}_{}", trace.layer, trace.net);
        if !layer_names.contains(&name) {
            layer_names.push(name);
        }
    }
    if !result.io_pads.is_empty() && !layer_names.contains(&"IO_Pad".to_string()) {
        layer_names.push("IO_Pad".to_string());
    }

    // Sort for deterministic output.
    layer_names.sort();

    // Accumulate "code\nvalue" pairs, joined with newlines at the end.
    let mut fragments: Vec<String> = Vec::new();

    // -----------------------------------------------------------------------
    // HEADER section
    // -----------------------------------------------------------------------
    sections::write_header(&mut fragments);

    // -----------------------------------------------------------------------
    // TABLES section — layer definitions
    // -----------------------------------------------------------------------
    sections::write_tables(&mut fragments, &layer_names);

    // -----------------------------------------------------------------------
    // ENTITIES section
    // -----------------------------------------------------------------------
    groups::dxf_group(&mut fragments, 0, "SECTION");
    groups::dxf_group(&mut fragments, 2, "ENTITIES");

    // --- LINE entities (segments) ---
    for seg in &result.segments {
        entities::write_line(
            &mut fragments,
            &format!("L{}_{}", seg.layer, seg.net),
            seg.start.x - x_offset_mm,
            seg.start.y,
            seg.end.x - x_offset_mm,
            seg.end.y,
        );
    }

    // --- ARC entities (curves) ---
    for curve in &result.curves {
        entities::write_arc(
            &mut fragments,
            &format!("L{}_{}", curve.layer, curve.net),
            (curve.start.x - x_offset_mm, curve.start.y),
            (curve.mid.x - x_offset_mm, curve.mid.y),
            (curve.end.x - x_offset_mm, curve.end.y),
        );
    }

    // --- CIRCLE entities (vias) ---
    for via in &result.vias {
        entities::write_circle(
            &mut fragments,
            "Via",
            via.position.x - x_offset_mm,
            via.position.y,
            via_radius_mm,
        );
    }

    // --- LINE entities (IO fanout traces — normal tracks) ---
    for trace in &result.io_traces {
        entities::write_line(
            &mut fragments,
            &format!("L{}_{}", trace.layer, trace.net),
            trace.start.x - x_offset_mm,
            trace.start.y,
            trace.end.x - x_offset_mm,
            trace.end.y,
        );
    }

    // --- CIRCLE / rectangle-outline entities (IO pads) ---
    for pad in &result.io_pads {
        entities::write_pad(
            &mut fragments,
            "IO_Pad",
            pad.position.x - x_offset_mm,
            pad.position.y,
            pad.size.x,
            pad.size.y,
        );
    }

    groups::dxf_group(&mut fragments, 0, "ENDSEC");

    // -----------------------------------------------------------------------
    // EOF
    // -----------------------------------------------------------------------
    groups::dxf_group(&mut fragments, 0, "EOF");

    let mut out = fragments.join("\n");
    out.push('\n');
    out
}

/// Convenience: export a set of [`PhaseCoil`]s to DXF.
///
/// This reconstructs the equivalent [`RoutingResult`] from the simplified
/// `PhaseCoil` presentation model (segments + corner_arcs + center_via_positions)
/// and delegates to [`routing_result_to_dxf`].
pub fn phase_coils_to_dxf(
    coils: &[PhaseCoil],
    num_layers: u32,
    rules: &DesignRules,
    active_area_length_mm: f64,
) -> String {
    let mut result = RoutingResult::default();

    for coil in coils {
        let net = coil.phase_name.clone();

        for seg in &coil.segments {
            result.segments.push(pcbmotorgen_routing::RouteSegment {
                start: pcbmotorgen_routing::Point::new(seg.start.0, seg.start.1),
                end: pcbmotorgen_routing::Point::new(seg.end.0, seg.end.1),
                layer: coil.layer_idx,
                net: net.clone(),
                is_active: seg.is_active,
            });
        }

        for arc in &coil.corner_arcs {
            result.curves.push(pcbmotorgen_routing::RouteCurve {
                start: pcbmotorgen_routing::Point::new(arc.start.0, arc.start.1),
                mid: pcbmotorgen_routing::Point::new(arc.mid.0, arc.mid.1),
                end: pcbmotorgen_routing::Point::new(arc.end.0, arc.end.1),
                layer: coil.layer_idx,
                net: net.clone(),
                is_active: arc.is_active,
            });
        }

        for &(x, y) in &coil.center_via_positions {
            let from_layer = 0;
            let to_layer = num_layers.saturating_sub(1);
            result.vias.push(pcbmotorgen_routing::Via {
                position: pcbmotorgen_routing::Point::new(x, y),
                from_layer,
                to_layer,
                net: net.clone(),
            });
        }
    }

    routing_result_to_dxf(&result, rules, active_area_length_mm, true)
}

// ===========================================================================
// KiCad IPC API — re-exports
// ===========================================================================

pub use client::{KiCadClient, KicadTransport, MockTransport};
pub use errors::KiCadError;
pub use proto::common::{
    ApiRequest, ApiRequestHeader, ApiResponse, ApiResponseHeader, ApiResponseStatus, ApiStatusCode,
};
pub use proto::common::commands::{
    BeginCommit, BeginCommitResponse, CommitAction, CreateItems, CreateItemsResponse, EndCommit,
    EndCommitResponse,
};
pub use proto::common::types::{
    AxisAlignment, DocumentSpecifier, DocumentType, Distance, ItemHeader, ItemRequestStatus, Kiid,
    KiCadVersion, LibraryIdentifier, LockedState, ProjectSpecifier, Vector2, Vector3,
};
pub use proto::board::types::{Arc, BoardLayer, Footprint, FootprintInstance, Net, Pad, PadType, Track, Via};
pub use proto::board::commands::BoardOriginType;

// Phase 7 re-exports.
pub use board::{BoardBBoxMm, BoardHandle};
pub use commit::Commit;
pub use diagnostics::{
    get_board_diagnostics, preview_coils, validate_write_preconditions, BoardDiagnostics,
    CoilPreview, CoilPreviewLayer, PreconditionLevel, PreconditionWarning,
};
pub use layer_map::{layer_idx_to_board_layer, mm_to_nm, via_pad_diameter_nm};
pub use writer::{coils_to_board_items, io_elements_to_board_items};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_dfm::DesignRules;

    fn sample_rules() -> DesignRules {
        DesignRules {
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.1,
        }
    }

    #[test]
    fn test_phase_coils_to_dxf_produces_valid_output() {
        use pcbmotorgen_routing::{CoilSegment, PhaseCoil};

        let coils = vec![PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            phase_name: "A".into(),
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 20.0),
                is_active: true,
            }],
            corner_arcs: vec![],
            center_via_positions: vec![(1.0, 2.0)],
            ..PhaseCoil::default()
        }];

        let dxf = phase_coils_to_dxf(&coils, 2, &sample_rules(), 48.0);
        assert!(dxf.contains("LINE"), "should contain LINE from segment");
        assert!(dxf.contains("CIRCLE"), "should contain CIRCLE from via");
        assert!(dxf.contains("EOF"), "should end with EOF");
    }

    #[test]
    fn test_kicad_items_pure_function_smoke() {
        // The KiCad writer path is exercised thoroughly in
        // `tests/kicad_writer.rs`; here we just confirm both halves of the
        // merged crate build and link together.
        use pcbmotorgen_routing::{CoilSegment, PhaseCoil};
        let coil = PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            phase_name: "A".into(),
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 20.0),
                is_active: true,
            }],
            corner_arcs: vec![],
            center_via_positions: Vec::new(),
            ..PhaseCoil::default()
        };
        let items = coils_to_board_items(&[coil], 2, &sample_rules(), 0.0);
        assert_eq!(items.len(), 1, "one segment -> one Track item");
    }
}
