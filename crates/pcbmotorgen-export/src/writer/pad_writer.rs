//! IO-pad + IO-fanout emission for the KiCad writer.
//!
//! Converts the additive [`RoutingResult`](pcbmotorgen_routing::RoutingResult)
//! IO elements into KiCad board items:
//!
//! - one [`FootprintInstance`] per [`IoPad`], carrying a one-pad [`Footprint`]
//!   whose single item is a [`Pad`] with a [`PadStack`] (the protos were
//!   already vendored; this is their first pad emitter);
//! - one [`Track`] per [`IoTrace`] — IO fanout traces are emitted as normal
//!   tracks, sized from the [`DesignRules`] (the sizing authority — this
//!   writer only reads the declared pad sizes and rule-derived trace width,
//!   it never decides dimensions).
//!
//! The KiCad `PCB_VIA` unpacker constraints documented in
//! [`super::via_writer`] apply to pad padstacks too (singular enums must be
//! real variants; `PstNormal` padstacks carry exactly one `PadStackLayer`
//! with `layer = BlFCu` = C++ `ALL_LAYERS`), so this module mirrors the same
//! conventions.

use prost_types::Any;

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{IoPad, IoPadKind, IoTrace, RoutingResult};

use super::any_pack::pack_any;
use super::via_writer::through_drill;
use crate::layer_map::{layer_idx_to_board_layer, mm_to_nm};
use crate::proto::board::types::{
    BoardLayer, Footprint, FootprintAttributes, FootprintInstance, FootprintMountingStyle, Pad,
    PadStack, PadStackLayer, PadStackShape, PadStackType, PadType, UnconnectedLayerRemoval,
};
use crate::{Distance, Kiid, LibraryIdentifier, LockedState, Net, Track, Vector2};

/// Emit the IO elements of `result` (pads + fanout traces) as packed `Any`
/// items, appending them to `items`.
///
/// `trace_width_nm` is the design-rule trace width the fanout tracks are
/// emitted with; `x_offset_nm` applies the same centering shift as
/// [`super::coils_to_board_items`]. `num_layers` is the *actual* board layer
/// count used to map routing layer indices onto KiCad layers.
pub(crate) fn emit_io_elements(
    items: &mut Vec<Any>,
    result: &RoutingResult,
    num_layers: u32,
    rules: &DesignRules,
    x_offset_nm: i64,
) {
    // --- IO fanout traces: one Track each (normal tracks, rule-sized) ------
    let trace_width_nm = mm_to_nm(rules.trace_width_mm);
    for trace in &result.io_traces {
        items.push(pack_any(
            "kiapi.board.types.Track",
            &io_trace_track(trace, num_layers, trace_width_nm, x_offset_nm),
        ));
    }

    // --- IO pads: one FootprintInstance each -------------------------------
    for (i, pad) in result.io_pads.iter().enumerate() {
        items.push(pack_any(
            "kiapi.board.types.FootprintInstance",
            &io_pad_footprint(pad, i, num_layers, x_offset_nm),
        ));
    }
}

/// Convenience wrapper used by [`super::io_elements_to_board_items`].
///
/// Kept `pub(crate)` so the entry point owns the public signature.
pub(crate) fn io_elements_to_board_items(
    result: &RoutingResult,
    num_layers: u32,
    rules: &DesignRules,
    active_area_length_mm: f64,
) -> Vec<Any> {
    let x_offset_nm = mm_to_nm(active_area_length_mm / 2.0);
    let mut items = Vec::new();
    emit_io_elements(&mut items, result, num_layers, rules, x_offset_nm);
    items
}

/// Build the [`Track`] for one [`IoTrace`] — a normal track on the trace's
/// layer with the trace's net (slash-prefixed like every coil net).
fn io_trace_track(
    trace: &IoTrace,
    num_layers: u32,
    trace_width_nm: i64,
    x_offset_nm: i64,
) -> Track {
    Track {
        id: Some(Kiid { value: String::new() }),
        start: Some(Vector2 {
            x_nm: mm_to_nm(trace.start.x) - x_offset_nm,
            y_nm: mm_to_nm(trace.start.y),
        }),
        end: Some(Vector2 {
            x_nm: mm_to_nm(trace.end.x) - x_offset_nm,
            y_nm: mm_to_nm(trace.end.y),
        }),
        width: Some(Distance { value_nm: trace_width_nm }),
        locked: LockedState::LsUnlocked as i32,
        layer: layer_idx_to_board_layer(trace.layer, num_layers) as i32,
        net: Some(Net {
            code: None,
            name: format!("/{}", trace.net),
        }),
    }
}

/// Build a single-pad [`FootprintInstance`] for one [`IoPad`].
///
/// The footprint origin sits at the pad centre (with the writer's centering
/// shift applied), so the [`Pad`]'s position relative to the footprint origin
/// is always `(0, 0)`. The footprint is placed on `F.Cu` and marked
/// `not_in_schematic` / excluded from the BOM — these are generated board
/// artifacts, not schematic-driven components.
fn io_pad_footprint(pad: &IoPad, index: usize, num_layers: u32, x_offset_nm: i64) -> FootprintInstance {
    let pad_number = pad
        .number
        .clone()
        .unwrap_or_else(|| (index + 1).to_string());
    let ki_pad = Pad {
        id: Some(Kiid { value: String::new() }),
        locked: LockedState::LsUnlocked as i32,
        number: pad_number,
        net: Some(Net {
            code: None,
            name: format!("/{}", pad.net),
        }),
        r#type: pad_type(pad.kind) as i32,
        pad_stack: Some(io_pad_stack(pad, num_layers)),
        // Pad positions are always relative to the footprint origin.
        position: Some(Vector2 { x_nm: 0, y_nm: 0 }),
        copper_clearance_override: None,
        pad_to_die_length: None,
        symbol_pin: None,
        pad_to_die_delay: None,
    };
    let definition = Footprint {
        id: Some(LibraryIdentifier {
            library_nickname: "pcbmotorgen".to_string(),
            entry_name: format!("io_pad_{}_{}", pad.net, index + 1),
        }),
        anchor: Some(Vector2 { x_nm: 0, y_nm: 0 }),
        attributes: Some(FootprintAttributes {
            description: String::new(),
            keywords: String::new(),
            not_in_schematic: true,
            exclude_from_position_files: false,
            exclude_from_bill_of_materials: true,
            exempt_from_courtyard_requirement: true,
            do_not_populate: false,
            mounting_style: mounting_style(pad.kind) as i32,
            allow_soldermask_bridges: false,
        }),
        overrides: None,
        net_ties: Vec::new(),
        private_layers: Vec::new(),
        reference_field: None,
        value_field: None,
        datasheet_field: None,
        description_field: None,
        items: vec![pack_any("kiapi.board.types.Pad", &ki_pad)],
        jumpers: None,
    };
    FootprintInstance {
        id: Some(Kiid { value: String::new() }),
        position: Some(Vector2 {
            x_nm: mm_to_nm(pad.position.x) - x_offset_nm,
            y_nm: mm_to_nm(pad.position.y),
        }),
        orientation: None,
        layer: BoardLayer::BlFCu as i32,
        locked: LockedState::LsUnlocked as i32,
        definition: Some(definition),
        reference_field: None,
        value_field: None,
        datasheet_field: None,
        description_field: None,
        attributes: None,
        overrides: None,
        symbol_path: None,
        symbol_sheet_name: String::new(),
        symbol_sheet_filename: String::new(),
        symbol_footprint_filters: String::new(),
    }
}

/// Map an [`IoPadKind`] onto KiCad's `PadType`.
fn pad_type(kind: IoPadKind) -> PadType {
    match kind {
        IoPadKind::Smd => PadType::PtSmd,
        IoPadKind::Tht => PadType::PtPth,
        IoPadKind::BoardEdge => PadType::PtEdgeConnector,
    }
}

/// Map an [`IoPadKind`] onto KiCad's `FootprintMountingStyle`.
fn mounting_style(kind: IoPadKind) -> FootprintMountingStyle {
    match kind {
        IoPadKind::Smd => FootprintMountingStyle::FmsSmd,
        IoPadKind::Tht => FootprintMountingStyle::FmsThroughHole,
        IoPadKind::BoardEdge => FootprintMountingStyle::FmsUnspecified,
    }
}

/// Build the [`PadStack`] for one [`IoPad`].
///
/// A `PstNormal` (= C++ `PADSTACK::MODE::NORMAL`) padstack: exactly one
/// `PadStackLayer` carrying `layer = BlFCu` (= C++ `ALL_LAYERS`, the only
/// value the C++ unpacker accepts for `MODE::NORMAL`), shaped as a circle for
/// equal x/y sizes and a rectangle otherwise. `PadStack.layers` is the pad's
/// copper layer set — the pad's declared `layers` mapped onto the board, or
/// the pad kind's default set when the pattern left it empty (all copper
/// layers for THT, the top layer for surface pads) — which must stay a subset
/// of the live board's layers or KiCad's `UnpackLayerSet` rejects the item.
fn io_pad_stack(pad: &IoPad, num_layers: u32) -> PadStack {
    let shape = if pad.size.is_round(1e-9) {
        PadStackShape::PssCircle
    } else {
        PadStackShape::PssRectangle
    };
    let layers = if pad.layers.is_empty() {
        default_pad_layers(pad.kind, num_layers)
    } else {
        pad.layers
            .iter()
            .map(|&idx| layer_idx_to_board_layer(idx, num_layers) as i32)
            .collect()
    };
    PadStack {
        r#type: PadStackType::PstNormal as i32,
        layers,
        drill: pad.drill_mm.map(|d| through_drill(mm_to_nm(d))),
        // ULR_KEEP = 1 ("Keep annular rings on all layers"). ULR_UNKNOWN (0)
        // is the proto's "not set" sentinel and KiCad's IPC rejects it.
        unconnected_layer_removal: UnconnectedLayerRemoval::UlrKeep as i32,
        // Exactly one entry for `MODE::NORMAL` — see [`io_pad_stack`].
        copper_layers: vec![PadStackLayer {
            layer: BoardLayer::BlFCu as i32,
            shape: shape as i32,
            size: Some(Vector2 {
                x_nm: mm_to_nm(pad.size.x),
                y_nm: mm_to_nm(pad.size.y),
            }),
            corner_rounding_ratio: 0.0,
            chamfer_ratio: 0.0,
            chamfered_corners: None,
            custom_shapes: Vec::new(),
            custom_anchor_shape: shape as i32,
            zone_settings: None,
            trapezoid_delta: None,
            offset: None,
        }],
        angle: None,
        front_outer_layers: None,
        back_outer_layers: None,
        zone_settings: None,
        secondary_drill: None,
        tertiary_drill: None,
        front_post_machining: None,
        back_post_machining: None,
    }
}

/// The default copper layer set for a pad whose pattern declared no explicit
/// `layers`: all copper layers for a through-hole pad, the top layer for
/// surface pads.
fn default_pad_layers(kind: IoPadKind, num_layers: u32) -> Vec<i32> {
    match kind {
        IoPadKind::Tht => (0..num_layers)
            .map(|idx| layer_idx_to_board_layer(idx, num_layers) as i32)
            .collect(),
        IoPadKind::Smd | IoPadKind::BoardEdge => vec![BoardLayer::BlFCu as i32],
    }
}

// ---------------------------------------------------------------------------
// Tests (IO pads + fanout traces)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use prost::Message;

    use super::*;
    use pcbmotorgen_routing::{IoTraceRole, PadSize, Point};

    fn rules() -> DesignRules {
        DesignRules {
            min_trace_mm: 0.1,
            trace_width_mm: 0.1,
            min_space_mm: 0.1,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.1,
        }
    }

    fn smd_pad() -> IoPad {
        IoPad {
            position: Point::new(48.0, 2.0),
            size: PadSize { x: 0.6, y: 0.6 },
            drill_mm: None,
            layers: vec![1],
            kind: IoPadKind::Smd,
            net: "A".into(),
            number: Some("1".into()),
        }
    }

    fn tht_pad() -> IoPad {
        IoPad {
            position: Point::new(0.0, 18.0),
            size: PadSize { x: 0.4, y: 0.4 },
            drill_mm: Some(0.2),
            layers: vec![],
            kind: IoPadKind::Tht,
            net: "B".into(),
            number: None,
        }
    }

    fn result_with(pads: Vec<IoPad>, traces: Vec<IoTrace>) -> RoutingResult {
        RoutingResult {
            io_pads: pads,
            io_traces: traces,
            ..RoutingResult::default()
        }
    }

    #[test]
    fn smd_pad_becomes_footprint_instance_with_pad() {
        let items = io_elements_to_board_items(&result_with(vec![smd_pad()], vec![]), 2, &rules(), 48.0);
        assert_eq!(items.len(), 1, "one pad → one FootprintInstance");
        assert!(items[0].type_url.ends_with("kiapi.board.types.FootprintInstance"));

        let fp: FootprintInstance =
            FootprintInstance::decode(items[0].value.as_slice()).expect("decode FootprintInstance");
        // Position: x = 48 mm - 24 mm offset = 24 mm, y = 2 mm (in nm).
        let pos = fp.position.expect("position");
        assert_eq!(pos.x_nm, 24_000_000);
        assert_eq!(pos.y_nm, 2_000_000);
        assert_eq!(fp.layer, BoardLayer::BlFCu as i32);

        let definition = fp.definition.expect("definition");
        let lib_id = definition.id.expect("lib id");
        assert_eq!(lib_id.library_nickname, "pcbmotorgen");
        assert_eq!(lib_id.entry_name, "io_pad_A_1");
        let attrs = definition.attributes.expect("attributes");
        assert_eq!(attrs.mounting_style, FootprintMountingStyle::FmsSmd as i32);
        assert!(attrs.not_in_schematic);
        assert!(attrs.exclude_from_bill_of_materials);
        assert_eq!(definition.items.len(), 1, "one pad item");
        assert!(definition.items[0].type_url.ends_with("kiapi.board.types.Pad"));

        let pad: Pad = Pad::decode(definition.items[0].value.as_slice()).expect("decode Pad");
        assert_eq!(pad.number, "1");
        assert_eq!(pad.net.expect("net").name, "/A");
        assert_eq!(pad.r#type, PadType::PtSmd as i32);
        assert_eq!(pad.position.expect("pad position").x_nm, 0);

        let ps = pad.pad_stack.expect("pad stack");
        assert_eq!(ps.r#type, PadStackType::PstNormal as i32);
        assert!(ps.drill.is_none(), "SMD pad has no drill");
        // Layer index 1 is the TOP layer of a 2-layer board → F_Cu.
        assert_eq!(ps.layers, vec![BoardLayer::BlFCu as i32], "declared layer 1 → F_Cu on a 2-layer board");
        assert_eq!(ps.copper_layers.len(), 1, "PstNormal must have exactly one PadStackLayer");
        let layer = &ps.copper_layers[0];
        assert_eq!(layer.layer, BoardLayer::BlFCu as i32, "PstNormal PadStackLayer.layer must be ALL_LAYERS");
        assert_eq!(layer.shape, PadStackShape::PssCircle as i32);
        assert_eq!(layer.custom_anchor_shape, PadStackShape::PssCircle as i32);
        let size = layer.size.expect("size");
        assert_eq!(size.x_nm, 600_000);
        assert_eq!(size.y_nm, 600_000);
        assert_eq!(
            ps.unconnected_layer_removal,
            UnconnectedLayerRemoval::UlrKeep as i32,
            "ULR must not be the rejected UlrUnknown sentinel"
        );
    }

    #[test]
    fn tht_pad_defaults_to_full_copper_layer_set_and_carries_drill() {
        let items = io_elements_to_board_items(&result_with(vec![tht_pad()], vec![]), 4, &rules(), 48.0);
        let fp: FootprintInstance =
            FootprintInstance::decode(items[0].value.as_slice()).expect("decode FootprintInstance");
        let definition = fp.definition.expect("definition");
        let pad: Pad = Pad::decode(definition.items[0].value.as_slice()).expect("decode Pad");
        assert_eq!(pad.r#type, PadType::PtPth as i32);
        // No declared pad number → positional fallback ("1").
        assert_eq!(pad.number, "1");
        assert_eq!(pad.net.expect("net").name, "/B");

        let ps = pad.pad_stack.expect("pad stack");
        let drill = ps.drill.expect("THT pad must carry a drill");
        assert_eq!(drill.shape, crate::proto::board::types::DrillShape::DsCircle as i32);
        assert_eq!(drill.diameter.expect("drill diameter").x_nm, 200_000);
        assert_eq!(ps.layers.len(), 4, "THT default layer set = all board copper layers");
        assert_eq!(
            ps.layers,
            vec![
                BoardLayer::BlBCu as i32,
                BoardLayer::BlIn1Cu as i32,
                BoardLayer::BlIn2Cu as i32,
                BoardLayer::BlFCu as i32,
            ]
        );
        let attrs = definition.attributes.expect("attributes");
        assert_eq!(attrs.mounting_style, FootprintMountingStyle::FmsThroughHole as i32);
    }

    #[test]
    fn rectangular_pad_uses_rectangle_shape() {
        let mut pad = smd_pad();
        pad.size = PadSize { x: 1.0, y: 0.6 };
        let items = io_elements_to_board_items(&result_with(vec![pad], vec![]), 2, &rules(), 0.0);
        let fp: FootprintInstance =
            FootprintInstance::decode(items[0].value.as_slice()).expect("decode");
        let definition = fp.definition.expect("definition");
        let pad: Pad = Pad::decode(definition.items[0].value.as_slice()).expect("decode Pad");
        let layer = &pad.pad_stack.expect("pad stack").copper_layers[0];
        assert_eq!(layer.shape, PadStackShape::PssRectangle as i32);
        assert_eq!(layer.custom_anchor_shape, PadStackShape::PssRectangle as i32);
        let size = layer.size.expect("size");
        assert_eq!(size.x_nm, 1_000_000);
        assert_eq!(size.y_nm, 600_000);
    }

    #[test]
    fn io_traces_become_normal_rule_sized_tracks() {
        let trace = IoTrace {
            start: Point::new(0.0, 10.0),
            end: Point::new(47.0, 2.0),
            layer: 0,
            net: "A".into(),
            role: IoTraceRole::Fanout,
        };
        let items =
            io_elements_to_board_items(&result_with(vec![], vec![trace]), 2, &rules(), 48.0);
        assert_eq!(items.len(), 1);
        assert!(items[0].type_url.ends_with("kiapi.board.types.Track"));

        let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
        // Width comes from the design rules (the sizing authority), not from
        // the writer.
        assert_eq!(track.width.expect("width").value_nm, 100_000);
        assert_eq!(track.layer, BoardLayer::BlBCu as i32, "routing layer 0 → B_Cu");
        assert_eq!(track.net.expect("net").name, "/A");
        let start = track.start.expect("start");
        assert_eq!(start.x_nm, mm_to_nm(0.0) - mm_to_nm(24.0));
        assert_eq!(start.y_nm, 10_000_000);
        let end = track.end.expect("end");
        assert_eq!(end.x_nm, mm_to_nm(47.0) - mm_to_nm(24.0));
        assert_eq!(end.y_nm, 2_000_000);
    }

    #[test]
    fn empty_io_result_produces_no_items() {
        let items = io_elements_to_board_items(&result_with(vec![], vec![]), 2, &rules(), 48.0);
        assert!(items.is_empty());
    }

    #[test]
    fn io_pad_footprint_proto_round_trips() {
        let fp = io_pad_footprint(&tht_pad(), 0, 4, 0);
        let mut buf = Vec::new();
        fp.encode(&mut buf).expect("encode FootprintInstance");
        let back = FootprintInstance::decode(buf.as_slice()).expect("decode");
        assert_eq!(back.locked, LockedState::LsUnlocked as i32);
        let pad: Pad =
            Pad::decode(back.definition.expect("definition").items[0].value.as_slice())
                .expect("decode Pad");
        assert_eq!(pad.r#type, PadType::PtPth as i32);
    }
}
