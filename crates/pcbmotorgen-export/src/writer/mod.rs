//! Pure conversion of coil geometry into KiCad board items (Tracks + Vias).
//!
//! The core function [`coils_to_board_items`] is **pure** — it does not touch
//! any socket or client. This makes it trivially testable offline.
//!
//! ## Output
//! Each [`pcbmotorgen_routing::PhaseCoil`] is converted into:
//! - one [`Track`] proto per [`pcbmotorgen_routing::CoilSegment`],
//! - one [`Arc`] proto per corner arc, and
//! - one [`Via`] proto per `center_via_positions` entry.
//!
//! All items are packed into `google.protobuf.Any` messages ready for
//! `CreateItems`.
//!
//! ## Submodules
//! - [`any_pack`] — `google.protobuf.Any` packing helper.
//! - [`track_writer`] — track + corner-arc emission.
//! - [`via_writer`] — through-via construction + via layer-set building.
//! - [`pad_writer`] — IO pad (`FootprintInstance`/`Pad`) + IO fanout-track
//!   emission from the additive [`RoutingResult`](pcbmotorgen_routing::RoutingResult)
//!   IO elements.

use prost_types::Any;

use crate::layer_map::{layer_idx_to_board_layer, mm_to_nm, via_pad_diameter_nm};
use crate::Net;
use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{PhaseCoil, RoutingResult, SensorGeometry};

mod any_pack;
mod pad_writer;
mod track_writer;
mod via_writer;

/// Type URL prefix used when packing items into `google.protobuf.Any`.
pub(crate) const TYPE_URL_PREFIX: &str = "type.googleapis.com";

/// Convert coil geometry into KiCad board items (Tracks and Vias).
///
/// Each `CoilSegment` becomes a [`Track`] proto message. Each
/// `center_via_position` becomes a [`Via`] proto message. All coordinates are
/// converted from millimetres to nanometres. Phase nets are named `"/A"`, `"/B"`,
/// `"/C"`, etc.
///
/// ## Centering
/// The coil generators emit geometry with x = 0 at the start of the active
/// area (i.e. extending from 0 to `active_area_length_mm`). A typical KiCad
/// board is centered on the origin, so writing those coordinates verbatim
/// pushes the right half of the coil set off-board. To avoid that we
/// subtract `active_area_length_mm / 2` from every x coordinate so the
/// coils straddle x = 0 (active area runs from
/// `-active_area_length_mm / 2` to `+active_area_length_mm / 2`). Y coordinates
/// are passed through unchanged — the board is already centered on y = 0,
/// and the coil set spans the full board width, y ∈
/// `[-board_width_mm / 2, +board_width_mm / 2]`.
///
/// This is a **pure function** — no socket I/O. It produces a list of
/// `google.protobuf.Any`-wrapped items ready for `CreateItems`.
pub fn coils_to_board_items(
    coils: &[PhaseCoil],
    num_layers: u32,
    rules: &DesignRules,
    active_area_length_mm: f64,
) -> Vec<Any> {
    let trace_width_nm = mm_to_nm(rules.min_trace_mm);
    let drill_nm = mm_to_nm(rules.min_via_drill_mm);
    let pad_diameter_nm =
        via_pad_diameter_nm(rules.min_via_drill_mm, rules.min_via_annular_ring_mm);

    // Centering offset: shift the whole active area so it sits symmetrically
    // about x = 0. Coils are generated starting at x = 0; we move them to
    // x ∈ [-active_area_length_mm/2, +active_area_length_mm/2] so a centered
    // KiCad board shows the full coil set instead of only the leftmost half.
    let x_offset_mm = active_area_length_mm / 2.0;
    let x_offset_nm = mm_to_nm(x_offset_mm);

    // For a through via, the `PadStack.layers` field is the set of copper
    // layers the via passes through. The set must match the layers the
    // *board actually has* (see `via_writer::via_board_layers` for the full
    // rationale and the KiCad rejection it prevents).
    let board_layers = via_writer::via_board_layers(num_layers);

    let mut items: Vec<Any> = Vec::new();

    for coil in coils {
        // The track's `layer` MUST be derived from `num_layers` (the actual
        // board being written to), not `max_layers` (the DFM ceiling): on a
        // 4-layer board with `max_layers = 12`, a top-layer coil
        // (`layer_idx = 3`) would otherwise map to `In3_Cu` — a layer the
        // live board does not have — and KiCad's `UnpackLayerSet` rejects
        // every item whose layer set is not a subset of the board's actual
        // layer set ("attempted to add item with no overlapping layers with
        // the board", `ISC_INVALID_DATA`). Using `num_layers` maps
        // `layer_idx == num_layers - 1` to the board's real top layer
        // (`F_Cu`) via `layer_idx_to_board_layer`.
        let layer = layer_idx_to_board_layer(coil.layer_idx, num_layers);
        let net_name = format!("/{}", coil.phase_name);
        let net = Net {
            code: None,
            name: net_name,
        };

        track_writer::emit_tracks_and_arcs(
            &mut items,
            coil,
            layer,
            net.clone(),
            trace_width_nm,
            x_offset_nm,
        );
        via_writer::emit_vias(
            &mut items,
            coil,
            net.clone(),
            drill_nm,
            pad_diameter_nm,
            x_offset_mm,
            &board_layers,
        );
    }

    items
}

/// Convert the **IO elements** of a [`RoutingResult`](pcbmotorgen_routing::RoutingResult)
/// (connector/IC pads and terminal fanout traces) into KiCad board items —
/// the additive counterpart of [`coils_to_board_items`].
///
/// - One `FootprintInstance` per `io_pads[]` entry, each carrying a
///   single-pad `Footprint` with a full `PadStack` (emitted by the
///   `pad_writer` submodule).
/// - One `Track` proto per `io_traces[]` entry — IO fanout traces are
///   emitted as normal tracks sized from `rules.min_trace_mm` (the sizing
///   authority; this writer reads sizes, never decides them).
///
/// The centering shift and layer mapping match [`coils_to_board_items`].
/// This is a **pure function** — no socket I/O.
pub fn io_elements_to_board_items(
    result: &RoutingResult,
    num_layers: u32,
    rules: &DesignRules,
    active_area_length_mm: f64,
) -> Vec<Any> {
    pad_writer::io_elements_to_board_items(result, num_layers, rules, active_area_length_mm)
}

/// Convert native induction-sensor routes into tracks and through-vias.
/// The sensor's layer IDs are F.Cu=0/B.Cu=1, while the shared writer uses
/// board indices B.Cu=0/F.Cu=1, so this adapter explicitly reverses them.
/// Per-net trace widths are retained and terminal markers are deliberately
/// omitted (the prototype does not define physical footprints or pads).
pub fn sensor_geometry_to_board_items(geometry: &SensorGeometry, rules: &DesignRules) -> Vec<Any> {
    let mut items = Vec::new();
    for net in &geometry.nets {
        let net_rules = DesignRules {
            min_trace_mm: net.trace_width_mm,
            min_space_mm: rules.min_space_mm,
            min_via_drill_mm: rules.min_via_drill_mm.min(net.via_size_mm / 2.0),
            min_via_annular_ring_mm: (net.via_size_mm
                - rules.min_via_drill_mm.min(net.via_size_mm / 2.0))
                / 2.0,
        };
        for board_layer in 0..2 {
            let sensor_layer = 1 - board_layer;
            let coil = PhaseCoil {
                phase_idx: 0,
                layer_idx: board_layer,
                segments: net
                    .segments
                    .iter()
                    .filter(|segment| segment.layer == sensor_layer)
                    .map(|segment| pcbmotorgen_routing::CoilSegment {
                        start: (segment.start.x, segment.start.y),
                        end: (segment.end.x, segment.end.y),
                        is_active: segment.is_active,
                    })
                    .collect(),
                corner_arcs: Vec::new(),
                phase_name: net.name.clone(),
                pattern_id: "induction-position-sensor".into(),
                layer_pair: Some((0, 1)),
                // Emit each net's vias exactly once, along with its B.Cu path.
                center_via_positions: if board_layer == 0 {
                    net.vias
                        .iter()
                        .map(|via| (via.position.x, via.position.y))
                        .collect()
                } else {
                    Vec::new()
                },
            };
            items.extend(coils_to_board_items(&[coil], 2, &net_rules, 0.0));
        }
    }
    items
}

// ---------------------------------------------------------------------------
// Tests (entry point)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::{
        generate_coils_from_context, CoilSegment, RoutingContext, SensorConfig,
    };
    use prost::Message;
    use std::collections::HashMap;

    use crate::proto::board::types::BoardLayer;
    use crate::Track;

    /// Millimetres (routing crate's native unit).
    fn mm(v: f64) -> f64 {
        v
    }

    /// mil → millimetres (1 mil = 0.0254 mm).
    fn mils_to_mm(v: f64) -> f64 {
        v * 0.0254
    }

    /// `DesignRules` matching the old `braid_test_config` helper.
    fn braid_rules() -> DesignRules {
        DesignRules {
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            min_via_drill_mm: mm(0.2),
            min_via_annular_ring_mm: mm(0.1),
        }
    }

    /// `DesignRules` matching the old `test_config` helper (48 mm active
    /// area, 5 mil trace/space, 0.2 mm via drill, 0.1 mm annular ring).
    fn test_rules() -> DesignRules {
        DesignRules {
            min_trace_mm: mils_to_mm(5.0),
            min_space_mm: mils_to_mm(5.0),
            min_via_drill_mm: mm(0.2),
            min_via_annular_ring_mm: mm(0.1),
        }
    }

    /// Active area used by the braid structural tests (matches the old
    /// `braid_test_config.active_area_length_mm = 600.0`).
    const BRAID_ACTIVE_AREA_MM: f64 = 600.0;

    /// Active area used by the hand-built proto tests (matches the old
    /// `test_config.active_area_length_mm = mm(48.0)`).
    const TEST_ACTIVE_AREA_MM: f64 = 48.0;

    /// Generate the bundled infinity-braid coil set for a board of
    /// `num_layers` layers. Mirrors the old `generate_coils_for_board`.
    fn braid_coils(num_layers: u32) -> Vec<PhaseCoil> {
        let mut params = HashMap::new();
        params.insert("num_strands".to_string(), 5.0);
        params.insert("n_periods".to_string(), 4.0);
        let ctx = RoutingContext {
            active_area_length_mm: BRAID_ACTIVE_AREA_MM,
            board_width_mm: 20.0,
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

    /// Convenience: braid coil scene → (coils, num_layers, rules, active_area).
    fn braid_scene(layers: u32) -> (Vec<PhaseCoil>, u32, DesignRules, f64) {
        (
            braid_coils(layers),
            layers,
            braid_rules(),
            BRAID_ACTIVE_AREA_MM,
        )
    }

    /// Convenience: a 4-layer hand-built coil scene (rules + active area).
    fn hand_scene() -> (DesignRules, f64) {
        (test_rules(), TEST_ACTIVE_AREA_MM)
    }

    /// Structural assertions for the infinity-braid routing pattern:
    /// non-empty coils, exactly the 3 phase nets (A/B/C), segments on at
    /// least layers 0 and 1, at least one via per phase, and a non-empty
    /// board-item set from `coils_to_board_items`.
    #[test]
    fn test_infinity_braid_coils_structure() {
        let (coils, layers, rules, active) = braid_scene(2);

        assert!(
            !coils.is_empty(),
            "infinity-braid must produce non-empty coils"
        );

        // 3 distinct phase nets (A/B/C).
        let nets: std::collections::BTreeSet<&str> =
            coils.iter().map(|c| c.phase_name.as_str()).collect();
        assert_eq!(
            nets,
            std::collections::BTreeSet::from(["A", "B", "C"]),
            "infinity-braid must produce exactly the 3 phase nets; got {:?}",
            nets
        );

        // Segments on at least layers 0 and 1.
        let layers_used: std::collections::BTreeSet<u32> =
            coils.iter().map(|c| c.layer_idx).collect();
        assert!(
            layers_used.contains(&0) && layers_used.contains(&1),
            "infinity-braid must place segments on at least layers 0 and 1; got {:?}",
            layers_used
        );

        // At least one via per phase (vias are attached to the layer-0 coils).
        for phase in ["A", "B", "C"] {
            let via_count: usize = coils
                .iter()
                .filter(|c| c.phase_name == phase)
                .map(|c| c.center_via_positions.len())
                .sum();
            assert!(
                via_count > 0,
                "phase {phase} must own at least one via; got 0"
            );
        }

        // The writer converts the coil set into a non-empty item list.
        let items = coils_to_board_items(&coils, layers, &rules, active);
        assert!(
            !items.is_empty(),
            "coils_to_board_items must produce non-empty items"
        );
    }

    #[test]
    fn test_default_config_braid_coils_structure() {
        // A 4-layer board must also produce the 2-layer braid with 3 nets.
        let coils = braid_coils(4);
        assert!(!coils.is_empty());
        let nets: std::collections::BTreeSet<&str> =
            coils.iter().map(|c| c.phase_name.as_str()).collect();
        assert_eq!(nets, std::collections::BTreeSet::from(["A", "B", "C"]));
        let layers: std::collections::BTreeSet<u32> = coils.iter().map(|c| c.layer_idx).collect();
        assert!(layers.contains(&0) && layers.contains(&1));
    }

    #[test]
    fn test_braid_rejects_single_layer_config() {
        // The infinity-braid requires num_layers >= 2; a 1-layer board
        // produces no coils (the pattern rejects it during generation).
        let coils = braid_coils(1);
        assert!(
            coils.is_empty(),
            "1-layer board must produce no braid coils"
        );
    }

    #[test]
    fn test_item_count_matches_segments_arcs_and_vias() {
        // Each coil item is a Track (one per segment), an Arc (one per
        // corner_arc), or a Via (one per center_via_position).
        let (coils, layers, rules, active) = braid_scene(2);
        let expected: usize = coils
            .iter()
            .map(|c| c.segments.len() + c.corner_arcs.len() + c.center_via_positions.len())
            .sum();
        let items = coils_to_board_items(&coils, layers, &rules, active);
        assert_eq!(
            items.len(),
            expected,
            "items = {} (expected {} tracks + {} arcs + {} vias)",
            items.len(),
            coils.iter().map(|c| c.segments.len()).sum::<usize>(),
            coils.iter().map(|c| c.corner_arcs.len()).sum::<usize>(),
            coils
                .iter()
                .map(|c| c.center_via_positions.len())
                .sum::<usize>(),
        );
    }

    #[test]
    fn test_net_names_are_slash_prefixed_distinct() {
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);

        // Collect the distinct net names across all Track items.
        let mut nets: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
        for any in &items {
            if !any.type_url.ends_with("kiapi.board.types.Track") {
                continue;
            }
            let t: Track = Track::decode(any.value.as_slice()).expect("decode Track");
            nets.insert(t.net.expect("Track must carry a net").name);
        }
        let expected: std::collections::BTreeSet<String> =
            ["/A".to_string(), "/B".to_string(), "/C".to_string()]
                .into_iter()
                .collect();
        assert_eq!(
            nets, expected,
            "distinct track nets must be {{/A, /B, /C}}; got {:?}",
            nets
        );
    }

    /// Regression: the track's `Track.layer` field must be derived from the
    /// actual layer count (`num_layers`) so a top-layer coil is mapped to
    /// `F_Cu` (the top of the real board).
    #[test]
    fn test_track_layer_uses_num_layers() {
        // (num_layers, expected layer set the top-layer track may land on).
        let cases: &[(u32, &[BoardLayer])] = &[
            (
                4,
                &[
                    BoardLayer::BlBCu,
                    BoardLayer::BlIn1Cu,
                    BoardLayer::BlIn2Cu,
                    BoardLayer::BlFCu,
                ],
            ),
            (2, &[BoardLayer::BlBCu, BoardLayer::BlFCu]),
            (
                6,
                &[
                    BoardLayer::BlBCu,
                    BoardLayer::BlIn1Cu,
                    BoardLayer::BlIn2Cu,
                    BoardLayer::BlIn3Cu,
                    BoardLayer::BlIn4Cu,
                    BoardLayer::BlFCu,
                ],
            ),
        ];

        let (rules, active) = hand_scene();
        for &(num_layers, expected_layers) in cases {
            // Build a minimal coil with a top-layer segment.
            let coil = PhaseCoil {
                phase_idx: 0,
                layer_idx: num_layers - 1, // top layer of the live board
                segments: vec![CoilSegment {
                    start: (0.0, 0.0),
                    end: (0.0, 20.0),
                    is_active: true,
                }],
                phase_name: "A".into(),
                center_via_positions: Vec::new(),
                ..PhaseCoil::default()
            };
            let items = coils_to_board_items(&[coil], num_layers, &rules, active);
            let track_any = items
                .iter()
                .find(|a| a.type_url.ends_with("kiapi.board.types.Track"))
                .unwrap_or_else(|| {
                    panic!("expected a Track in items for num_layers={}", num_layers)
                });
            let track: Track = Track::decode(track_any.value.as_slice()).expect("decode Track");

            // The top-layer track must map to F_Cu (the top of the board).
            assert_eq!(
                track.layer,
                BoardLayer::BlFCu as i32,
                "num_layers={}: top-layer track MUST be F_Cu (the top of the live board), \
                 not In{}_Cu",
                num_layers,
                num_layers - 1
            );
            // And it must be one of the board's valid layers.
            let valid_layers: Vec<i32> = expected_layers.iter().map(|l| *l as i32).collect();
            assert!(
                valid_layers.contains(&track.layer),
                "num_layers={}: track must land on a layer the board has (one of {:?}); got {}",
                num_layers,
                valid_layers,
                track.layer
            );
        }
    }

    #[test]
    fn sensor_writer_preserves_receiver_and_transmitter_widths_and_skips_terminals() {
        let mut config = SensorConfig::default();
        config.tx_trace_width_mm = 0.3;
        config.tx_via_size_mm = 0.8;
        let geometry = pcbmotorgen_routing::generate_sensor(&config).unwrap();
        let items = sensor_geometry_to_board_items(&geometry, &DesignRules::default());
        let expected_segments: usize = geometry.nets.iter().map(|net| net.segments.len()).sum();
        let expected_vias: usize = geometry.nets.iter().map(|net| net.vias.len()).sum();
        let tracks: Vec<Track> = items
            .iter()
            .filter(|item| item.type_url.ends_with("kiapi.board.types.Track"))
            .map(|item| Track::decode(item.value.as_slice()).expect("decode Track"))
            .collect();
        let vias: Vec<crate::Via> = items
            .iter()
            .filter(|item| item.type_url.ends_with("kiapi.board.types.Via"))
            .map(|item| crate::Via::decode(item.value.as_slice()).expect("decode Via"))
            .collect();

        assert_eq!(tracks.len(), expected_segments);
        assert_eq!(vias.len(), expected_vias);
        assert_eq!(items.len(), expected_segments + expected_vias);
        assert_eq!(
            tracks
                .iter()
                .map(|track| track.net.as_ref().unwrap().name.as_str())
                .collect::<std::collections::BTreeSet<_>>(),
            std::collections::BTreeSet::from(["/CL1", "/CL2", "/OSC"])
        );

        for track in &tracks {
            let net_name = track.net.as_ref().unwrap().name.trim_start_matches('/');
            let net = geometry
                .nets
                .iter()
                .find(|net| net.name == net_name)
                .unwrap();
            assert_eq!(
                track.width.as_ref().unwrap().value_nm,
                crate::layer_map::mm_to_nm(net.trace_width_mm),
                "{} track width must be preserved",
                net_name
            );
            assert!(
                track.layer == BoardLayer::BlBCu as i32 || track.layer == BoardLayer::BlFCu as i32,
                "sensor routes must stay on the two outer copper layers"
            );
        }
        for via in &vias {
            let net_name = via.net.as_ref().unwrap().name.trim_start_matches('/');
            let net = geometry
                .nets
                .iter()
                .find(|net| net.name == net_name)
                .unwrap();
            let pad_stack = via.pad_stack.as_ref().unwrap();
            let copper_pad = &pad_stack.copper_layers[0];
            assert_eq!(
                copper_pad.size.as_ref().unwrap().x_nm,
                crate::layer_map::mm_to_nm(net.via_size_mm),
                "{} via diameter must be preserved",
                net_name
            );
        }
        // The two prototype terminal coordinates are visual/reference
        // markers only; they must not become footprints or pads.
        assert_eq!(geometry.terminal_markers.len(), 2);
        assert!(items.iter().all(|item| {
            !item
                .type_url
                .ends_with("kiapi.board.types.FootprintInstance")
                && !item.type_url.ends_with("kiapi.board.types.Pad")
        }));
    }
}
