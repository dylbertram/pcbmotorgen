//! Through-via construction for [`super::coils_to_board_items`].
//!
//! Builds the [`Via`] proto for each `center_via_position`, including the
//! [`PadStack`] layer set matching the real board's copper layers
//! ([`via_board_layers`]) and the enum values KiCad's IPC requires,
//! documented on [`build_through_via`].

use prost_types::Any;

use pcbmotorgen_routing::PhaseCoil;

use super::any_pack::pack_any;
use crate::layer_map::{layer_idx_to_board_layer, mm_to_nm};
use crate::proto::board::types::{
    DrillProperties, DrillShape, PadStack, PadStackLayer, PadStackShape, PadStackType,
    UnconnectedLayerRemoval, ViaDrillCappingMode, ViaDrillFillingMode, ViaType,
};
use crate::{BoardLayer, Kiid, LockedState, Net, Vector2, Via};

/// The set of copper layers a through via passes through — i.e. every copper
/// layer the board actually has.
///
/// KiCad's own `PCB_VIA::GetLayerSet()` returns
/// `LSET::AllCuMask(copper_layer_count)` for a through via, so we mirror
/// that here. The set is used by KiCad to know which layers the via's
/// annular rings may appear on, so an incomplete set could produce a via
/// that doesn't show up on inner copper layers. See `PadStack.layers`
/// validation in `api_pcb_utils.cpp::UnpackLayerSet`.
///
/// **IMPORTANT:** This list MUST match the layers the *board actually
/// has*, not the DFM upper limit. `num_layers` is the user's actual layer
/// selection (e.g. 4 on a 4-layer board). If we populated `board_layers`
/// from a larger ceiling, the emitted via's `PadStack.layers` would
/// include entries like `In3_Cu..In11_Cu` that the live board does not
/// have. KiCad's `CreateItems` validator (`UnpackLayerSet`) rejects any
/// item whose layer set is not a subset of the board's actual layer set
/// with `ISC_INVALID_DATA` (code 7) and the message "attempted to add
/// item with no overlapping layers with the board". We therefore use
/// `num_layers` here so the emitted set always matches the live board.
pub(crate) fn via_board_layers(num_layers: u32) -> Vec<i32> {
    (0..num_layers)
        .map(|idx| layer_idx_to_board_layer(idx, num_layers) as i32)
        .collect()
}

/// Emit one [`Via`] per `center_via_position`, packed and appended to `items`.
///
/// Each via is centered at `(pos.0 - x_offset_mm, pos.1)` (millimetres) to apply
/// the same centering shift as the tracks — see
/// [`super::coils_to_board_items`].
pub(crate) fn emit_vias(
    items: &mut Vec<Any>,
    coil: &PhaseCoil,
    net: Net,
    drill_nm: i64,
    pad_diameter_nm: i64,
    x_offset_mm: f64,
    board_layers: &[i32],
) {
    // --- Vias: one per center_via_position ---
    for &pos in &coil.center_via_positions {
        let via = build_through_via(
            (pos.0 - x_offset_mm, pos.1),
            drill_nm,
            pad_diameter_nm,
            net.clone(),
            board_layers,
        );
        items.push(pack_any("kiapi.board.types.Via", &via));
    }
}

/// Build a minimal through-hole [`Via`] proto at `pos` (millimetres) with the given
/// drill and pad diameters (nanometres).
///
/// `board_layers` is the list of copper layers the via passes through, in
/// ascending order (B_Cu first, F_Cu last). It populates `PadStack.layers` to
/// mirror KiCad's own `PCB_VIA::GetLayerSet()`, which returns
/// `LSET::AllCuMask(copper_layer_count)` for a through via.
///
/// KiCad's `PCB_VIA` IPC unpacker is strict in three ways that shape this
/// payload:
///
/// - Every singular proto3 enum field must be a real variant: the
///   `*_UNKNOWN = 0` "not set" sentinels are rejected, so all enums below
///   are set explicitly (`UlrKeep`, `VdcmUncapped`, `VdfmUnfilled`,
///   `PssCircle`).
/// - For `PadStackType::PstNormal` (= C++ `PADSTACK::MODE::NORMAL`),
///   `copper_layers` must be exactly ONE entry with `layer = BlFCu`
///   (= C++ `ALL_LAYERS`, `pcbnew/padstack.h:177`). `PADSTACK::unpackCopperLayer`
///   rejects any other value, failing the whole via decode.
/// - `PadStack.layers` must be a subset of the live board's copper layers or
///   `UnpackLayerSet` rejects the item (`ISC_INVALID_DATA`) — hence the
///   caller passes the actual `num_layers`-sized set, never a DFM ceiling.
fn build_through_via(
    pos: (f64, f64),
    drill_nm: i64,
    pad_diameter_nm: i64,
    net: Net,
    board_layers: &[i32],
) -> Via {
    Via {
        id: Some(Kiid { value: String::new() }),
        position: Some(Vector2 {
            x_nm: mm_to_nm(pos.0),
            y_nm: mm_to_nm(pos.1),
        }),
        pad_stack: Some(through_pad_stack(drill_nm, pad_diameter_nm, board_layers)),
        locked: LockedState::LsUnlocked as i32,
        net: Some(net),
        r#type: ViaType::VtThrough as i32,
    }
}

/// Padstack for a basic through via: `PadStackType::PstNormal`
/// (= C++ `PADSTACK::MODE::NORMAL`) — a single shape applied to all copper
/// layers — carrying the full board copper layer set. The set is consumed by
/// `PADSTACK::Deserialize::SetLayerSet` and immediately reset by
/// `PCB_VIA::Deserialize`, but having it is faithful to KiCad's own output
/// and keeps the padstack correct if the via is later reused.
fn through_pad_stack(drill_nm: i64, pad_diameter_nm: i64, board_layers: &[i32]) -> PadStack {
    PadStack {
        r#type: PadStackType::PstNormal as i32,
        layers: board_layers.to_vec(),
        drill: Some(through_drill(drill_nm)),
        // ULR_KEEP = 1 ("Keep annular rings on all layers"). ULR_UNKNOWN (0)
        // is the proto's "not set" sentinel and KiCad's IPC rejects it.
        unconnected_layer_removal: UnconnectedLayerRemoval::UlrKeep as i32,
        // Exactly one entry for `MODE::NORMAL` — see [`build_through_via`].
        copper_layers: vec![normal_pad_layer(pad_diameter_nm)],
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

/// The single `PadStackLayer` of a `PstNormal` padstack.
///
/// `layer` carries the C++ `ALL_LAYERS` sentinel (`BlFCu`): any other value
/// is rejected by `PADSTACK::unpackCopperLayer` for `MODE::NORMAL`.
/// `custom_anchor_shape` mirrors `shape` because KiCad rejects the
/// `PssUnknown` sentinel here just like it does for the drill enum fields.
fn normal_pad_layer(pad_diameter_nm: i64) -> PadStackLayer {
    PadStackLayer {
        layer: BoardLayer::BlFCu as i32,
        shape: PadStackShape::PssCircle as i32,
        size: Some(Vector2 {
            x_nm: pad_diameter_nm,
            y_nm: pad_diameter_nm,
        }),
        corner_rounding_ratio: 0.0,
        chamfer_ratio: 0.0,
        chamfered_corners: None,
        custom_shapes: Vec::new(),
        custom_anchor_shape: PadStackShape::PssCircle as i32,
        zone_settings: None,
        trapezoid_delta: None,
        offset: None,
    }
}

/// Drill properties for a stock PTH hole: circular, uncapped, unfilled. The
/// proto3 `*_UNKNOWN = 0` sentinels are rejected by KiCad's `PCB_VIA`
/// unpacker, so the modes are set to real variants.
///
/// Shared with the IO-pad writer (`pad_writer`) for plated THT pad stacks.
pub(crate) fn through_drill(drill_nm: i64) -> DrillProperties {
    DrillProperties {
        start_layer: BoardLayer::BlFCu as i32,
        end_layer: BoardLayer::BlBCu as i32,
        diameter: Some(Vector2 {
            x_nm: drill_nm,
            y_nm: drill_nm,
        }),
        shape: DrillShape::DsCircle as i32,
        capped: ViaDrillCappingMode::VdcmUncapped as i32,
        filled: ViaDrillFillingMode::VdfmUnfilled as i32,
    }
}

// ---------------------------------------------------------------------------
// Tests (via + padstack)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_dfm::DesignRules;
    use pcbmotorgen_routing::{generate_coils_from_context, CoilSegment, RoutingContext};
    use prost::Message;
    use std::collections::HashMap;

    use crate::layer_map::via_pad_diameter_nm;
    use crate::writer::coils_to_board_items;

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
            trace_width_mm: 0.1,
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
            trace_width_mm: mils_to_mm(5.0),
            min_space_mm: mils_to_mm(5.0),
            min_via_drill_mm: mm(0.2),
            min_via_annular_ring_mm: mm(0.1),
        }
    }

    /// Active area used by the braid structural tests.
    const BRAID_ACTIVE_AREA_MM: f64 = 600.0;

    /// Active area used by the hand-built proto tests.
    const TEST_ACTIVE_AREA_MM: f64 = 48.0;

    /// Generate the bundled infinity-braid coil set for `num_layers` layers.
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
            trace_width_mm: 0.1,
            min_space_mm: 0.1,
            expects_continuous: false,
            params,
            ..RoutingContext::default()
        };
        generate_coils_from_context(&ctx, "infinity-braid")
    }

    /// Convenience: braid coil scene → (coils, num_layers, rules, active_area).
    fn braid_scene(layers: u32) -> (Vec<PhaseCoil>, u32, DesignRules, f64) {
        (braid_coils(layers), layers, braid_rules(), BRAID_ACTIVE_AREA_MM)
    }

    /// Convenience: a 4-layer hand-built coil scene (rules + active area).
    fn hand_scene() -> (DesignRules, f64) {
        (test_rules(), TEST_ACTIVE_AREA_MM)
    }

    #[test]
    fn test_braid_emits_vias_per_phase() {
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);

        let via_items: Vec<&Any> = items
            .iter()
            .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
            .collect();
        assert!(!via_items.is_empty(), "infinity-braid must emit vias");

        // Each phase net must appear on at least one via.
        let via_nets: std::collections::BTreeSet<String> = via_items
            .iter()
            .map(|a| {
                let v: Via = Via::decode(a.value.as_slice()).expect("decode Via");
                v.net.expect("Via must carry a net").name
            })
            .collect();
        let expected: std::collections::BTreeSet<String> =
            ["/A".to_string(), "/B".to_string(), "/C".to_string()].into_iter().collect();
        assert_eq!(via_nets, expected, "vias must cover all 3 phase nets; got {:?}", via_nets);
    }

    #[test]
    fn test_via_construction() {
        let layers = 4u32;
        let rules = test_rules();
        let active = TEST_ACTIVE_AREA_MM;
        // Note: the via center is offset by the same centering shift as the
        // track x coordinates — see `coils_to_board_items`.
        let x_offset_mm = active / 2.0;
        let coil = PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 20.0),
                is_active: true,
            }],
            phase_name: "A".into(),
            center_via_positions: vec![(1.0, 2.0)],
            ..PhaseCoil::default()
        };
        let items = coils_to_board_items(&[coil], layers, &rules, active);
        // 1 track + 1 via
        assert_eq!(items.len(), 2);
        let via_any = items
            .iter()
            .find(|a| a.type_url.ends_with("kiapi.board.types.Via"))
            .expect("expected a Via");
        let via: Via = Via::decode(via_any.value.as_slice()).expect("decode Via");
        let pos = via.position.unwrap();
        let expected_x_nm = mm_to_nm(1.0 - x_offset_mm);
        assert_eq!(pos.x_nm, expected_x_nm);
        assert_eq!(pos.y_nm, 2_000_000);
        assert_eq!(via.r#type, ViaType::VtThrough as i32);
        let ps = via.pad_stack.unwrap();
        assert_eq!(ps.r#type, PadStackType::PstNormal as i32);
        // A `PstNormal` padstack must have exactly one `PadStackLayer`, with
        // `layer = BlFCu` (= C++ `ALL_LAYERS`): the C++ deserializer rejects
        // any other layer for `MODE::NORMAL`.
        assert_eq!(
            ps.copper_layers.len(),
            1,
            "PstNormal padstack must have exactly one PadStackLayer; got {}",
            ps.copper_layers.len()
        );
        let pad = &ps.copper_layers[0];
        assert_eq!(
            pad.layer,
            BoardLayer::BlFCu as i32,
            "PstNormal PadStackLayer.layer must be BlFCu (= C++ ALL_LAYERS) for KiCad to accept the via"
        );
        assert_eq!(pad.shape, PadStackShape::PssCircle as i32);
        let drill = ps.drill.unwrap();
        assert_eq!(drill.shape, DrillShape::DsCircle as i32);
        let drill_d = drill.diameter.unwrap();
        assert_eq!(drill_d.x_nm, mm_to_nm(rules.min_via_drill_mm));
        // pad diameter = drill + 2*annular = 0.4mm = 400_000 nm
        let size = pad.size.unwrap();
        assert_eq!(size.x_nm, via_pad_diameter_nm(rules.min_via_drill_mm, rules.min_via_annular_ring_mm));
        // For a 4-layer board, PadStack.layers should contain all 4 copper
        // layers (B_Cu, In1_Cu, In2_Cu, F_Cu) — matching what KiCad's own
        // `PCB_VIA::GetLayerSet()` returns for `VIATYPE::THROUGH`.
        assert_eq!(
            ps.layers.len(),
            4,
            "PadStack.layers should contain all 4 copper layers for a 4-layer board; got {:?}",
            ps.layers
        );
    }

    // --- Regression: Via proto round-trips cleanly ---

    /// `build_through_via` must produce a `Via` proto that encodes and
    /// decodes without error and whose singular enum fields are valid
    /// variants. A proto3 `*_UNKNOWN = 0` sentinel in any of them makes
    /// KiCad's IPC reject the via with `could not unpack PCB_VIA from
    /// request` at CreateItems time.
    #[test]
    fn test_via_proto_round_trips() {
        use crate::proto::board::types::{
            UnconnectedLayerRemoval, ViaDrillCappingMode, ViaDrillFillingMode,
        };

        let net = Net {
            code: None,
            name: "/A".to_string(),
        };
        // Pass the copper layer set for a 4-layer board so `PadStack.layers`
        // matches KiCad's own `PCB_VIA::GetLayerSet()` output for a through
        // via.
        let board_layers = vec![
            BoardLayer::BlBCu as i32,
            BoardLayer::BlIn1Cu as i32,
            BoardLayer::BlIn2Cu as i32,
            BoardLayer::BlFCu as i32,
        ];
        let via = build_through_via((0.001, 0.002), 200_000, 400_000, net, &board_layers);
        let mut buf = Vec::new();
        via.encode(&mut buf).expect("encode Via");
        // Round-trip: decode the bytes back into a fresh `Via` proto.
        let via2 = Via::decode(buf.as_slice()).expect("decode Via");
        assert_eq!(via2.r#type, ViaType::VtThrough as i32);
        let ps = via2.pad_stack.expect("pad_stack present");
        // The critical assertion: unconnected_layer_removal must NOT be
        // the proto's `UlrUnknown` sentinel (0), which KiCad rejects.
        assert_eq!(
            ps.unconnected_layer_removal,
            UnconnectedLayerRemoval::UlrKeep as i32,
            "unconnected_layer_removal must be UlrKeep (1) for KiCad to accept the via; got {}",
            ps.unconnected_layer_removal
        );
        assert_ne!(
            ps.unconnected_layer_removal,
            UnconnectedLayerRemoval::UlrUnknown as i32,
            "unconnected_layer_removal must NOT be UlrUnknown (0) — KiCad rejects it"
        );
        // DrillProperties.capped and .filled must also be real, non-sentinel
        // values — KiCad's PCB_VIA unpacker rejects VDCM_UNKNOWN / VDFM_UNKNOWN
        // just like ULR_UNKNOWN.
        let drill = ps.drill.as_ref().expect("drill");
        assert_eq!(
            drill.capped,
            ViaDrillCappingMode::VdcmUncapped as i32,
            "drill.capped must be VdcmUncapped (2); got {} (VdcmUnknown = 0 is the rejected sentinel)",
            drill.capped
        );
        assert_ne!(
            drill.capped,
            ViaDrillCappingMode::VdcmUnknown as i32,
            "drill.capped must NOT be VdcmUnknown (0)"
        );
        assert_eq!(
            drill.filled,
            ViaDrillFillingMode::VdfmUnfilled as i32,
            "drill.filled must be VdfmUnfilled (2); got {} (VdfmUnknown = 0 is the rejected sentinel)",
            drill.filled
        );
        assert_ne!(
            drill.filled,
            ViaDrillFillingMode::VdfmUnknown as i32,
            "drill.filled must NOT be VdfmUnknown (0)"
        );
        // PadStackLayer.custom_anchor_shape must also be a real, non-sentinel
        // value matching the per-layer `shape`.
        for (i, layer) in ps.copper_layers.iter().enumerate() {
            assert_eq!(
                layer.custom_anchor_shape, PadStackShape::PssCircle as i32,
                "copper_layers[{}].custom_anchor_shape must be PssCircle (1); got {} \
                 (PssUnknown = 0 is the rejected sentinel)",
                i, layer.custom_anchor_shape
            );
        }
        // For `PadStackType::PstNormal` (= C++ `PADSTACK::MODE::NORMAL`),
        // `PadStackLayer.layer` must be `BlFCu` (= C++ `ALL_LAYERS`): the C++
        // unpacker rejects any other value for `MODE::NORMAL`, surfacing as
        // "could not unpack PCB_VIA from request".
        assert_eq!(
            ps.copper_layers.len(),
            1,
            "PstNormal padstack must have exactly one PadStackLayer; got {}",
            ps.copper_layers.len()
        );
        assert_eq!(
            ps.copper_layers[0].layer,
            BoardLayer::BlFCu as i32,
            "PstNormal PadStackLayer.layer must be BlFCu (= C++ ALL_LAYERS); got {}",
            ps.copper_layers[0].layer
        );
        // Other enum fields must be valid (regression guard).
        assert_eq!(ps.r#type, PadStackType::PstNormal as i32);
        assert_eq!(ps.drill.as_ref().unwrap().shape, DrillShape::DsCircle as i32);
        assert_eq!(ps.copper_layers[0].shape, PadStackShape::PssCircle as i32);
        // PadStack.layers carries the via's layer set, mirroring KiCad's
        // own `PCB_VIA::GetLayerSet()` for `VIATYPE::THROUGH`.
        assert_eq!(
            ps.layers,
            vec![
                BoardLayer::BlBCu as i32,
                BoardLayer::BlIn1Cu as i32,
                BoardLayer::BlIn2Cu as i32,
                BoardLayer::BlFCu as i32,
            ],
            "PadStack.layers must be the full copper layer set for a through via on a 4-layer board"
        );
        assert_eq!(via2.locked, LockedState::LsUnlocked as i32);
    }

    /// The via `coils_to_board_items` emits for a real coil set must also
    /// round-trip and carry the valid `UlrKeep` value. This is the
    /// end-to-end check — it walks the same path as the failing KiCad
    /// write: encode → decode → verify.
    #[test]
    fn test_coils_to_board_items_via_round_trip() {
        use crate::proto::board::types::{
            UnconnectedLayerRemoval, ViaDrillCappingMode, ViaDrillFillingMode,
        };

        let (rules, active) = hand_scene();
        let layers = 4u32;
        let coil = PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 0.02),
                is_active: true,
            }],
            phase_name: "A".into(),
            center_via_positions: vec![(0.001, 0.002), (0.005, 0.007), (0.01, 0.01)],
            ..PhaseCoil::default()
        };
        let items = coils_to_board_items(&[coil], layers, &rules, active);
        let via_items: Vec<&Any> = items
            .iter()
            .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
            .collect();
        assert_eq!(via_items.len(), 3, "expected 3 vias in this coil");
        for any in &via_items {
            let via = Via::decode(any.value.as_slice()).expect("decode Via via Any");
            let ps = via.pad_stack.as_ref().expect("pad_stack");
            assert_eq!(
                ps.unconnected_layer_removal,
                UnconnectedLayerRemoval::UlrKeep as i32,
                "every via emitted by coils_to_board_items must use UlrKeep"
            );
            // drill.capped / drill.filled must also be real values.
            let drill = ps.drill.as_ref().expect("drill");
            assert_eq!(
                drill.capped,
                ViaDrillCappingMode::VdcmUncapped as i32,
                "every via's drill.capped must be VdcmUncapped; got {}",
                drill.capped
            );
            assert_eq!(
                drill.filled,
                ViaDrillFillingMode::VdfmUnfilled as i32,
                "every via's drill.filled must be VdfmUnfilled; got {}",
                drill.filled
            );
            // copper_layers[*].custom_anchor_shape must be PssCircle.
            for layer in &ps.copper_layers {
                assert_eq!(
                    layer.custom_anchor_shape,
                    PadStackShape::PssCircle as i32,
                    "every PadStackLayer.custom_anchor_shape must be PssCircle; got {}",
                    layer.custom_anchor_shape
                );
            }
            assert_eq!(via.r#type, ViaType::VtThrough as i32);
        }
    }

    /// Regression: every singular proto3 enum field in the
    /// `Via` payload must be a real, non-sentinel variant. KiCad's
    /// `PCB_VIA` unpacker rejects any `*_UNKNOWN = 0` sentinel value.
    /// This test walks every enum field in
    /// the encoded `Via` and asserts no field equals 0.
    #[test]
    fn test_via_proto_has_no_unknown_enum_sentinels() {
        // Check every singular enum field on the Via + PadStack + DrillProperties
        // + PadStackLayer payload. Repeated fields (layers) and message fields
        // (position, diameter, net) are not enums and so not checked here.
        let net = Net {
            code: None,
            name: "/A".to_string(),
        };
        let board_layers = vec![
            BoardLayer::BlBCu as i32,
            BoardLayer::BlFCu as i32,
        ];
        let via = build_through_via((0.001, 0.002), 200_000, 400_000, net, &board_layers);
        let ps = via.pad_stack.as_ref().expect("pad_stack");
        let drill = ps.drill.as_ref().expect("drill");

        // Format (name, value) for a clear diagnostic if a field slips to 0.
        let enum_fields: &[(&str, i32)] = &[
            ("Via.type", via.r#type),
            ("Via.locked", via.locked),
            ("PadStack.type", ps.r#type),
            ("PadStack.unconnected_layer_removal", ps.unconnected_layer_removal),
            ("DrillProperties.start_layer", drill.start_layer),
            ("DrillProperties.end_layer", drill.end_layer),
            ("DrillProperties.shape", drill.shape),
            ("DrillProperties.capped", drill.capped),
            ("DrillProperties.filled", drill.filled),
        ];
        for (name, value) in enum_fields {
            assert_ne!(
                *value, 0,
                "{} = 0 is the *_UNKNOWN proto3 sentinel; KiCad's PCB_VIA unpacker \
                 rejects this. Set the field to a real, non-sentinel variant.",
                name
            );
        }
        for (i, layer) in ps.copper_layers.iter().enumerate() {
            assert_ne!(
                layer.layer, 0,
                "PadStackLayer[{}].layer = 0 is BL_UNKNOWN; KiCad rejects this.",
                i
            );
            assert_ne!(
                layer.shape, 0,
                "PadStackLayer[{}].shape = 0 is PSS_UNKNOWN; KiCad rejects this.",
                i
            );
            assert_ne!(
                layer.custom_anchor_shape, 0,
                "PadStackLayer[{}].custom_anchor_shape = 0 is PSS_UNKNOWN; \
                 KiCad rejects this.",
                i
            );
        }
    }

    /// Regression: for `PadStackType::PstNormal` (= C++
    /// `PADSTACK::MODE::NORMAL`), the `PadStack.copper_layers` field must
    /// contain exactly ONE `PadStackLayer`, and its `layer` must be
    /// `BlFCu` (= C++ `ALL_LAYERS`, the only layer `PADSTACK::unpackCopperLayer`
    /// accepts for `MODE::NORMAL`).
    #[test]
    fn test_via_pst_normal_copper_layers_uses_all_layers_sentinel() {
        let net = Net {
            code: None,
            name: "/A".to_string(),
        };
        // Use a 4-layer board's copper layer set to match the realistic
        // call path from `coils_to_board_items`.
        let board_layers = vec![
            BoardLayer::BlBCu as i32,
            BoardLayer::BlIn1Cu as i32,
            BoardLayer::BlIn2Cu as i32,
            BoardLayer::BlFCu as i32,
        ];
        let via = build_through_via((0.001, 0.002), 200_000, 400_000, net, &board_layers);
        let ps = via.pad_stack.as_ref().expect("pad_stack");

        // The padstack type must be PST_NORMAL for a basic through via.
        assert_eq!(
            ps.r#type,
            PadStackType::PstNormal as i32,
            "precondition: via padstack type must be PstNormal for this test to apply"
        );

        // Exactly one PadStackLayer entry — `MODE::NORMAL` only ever has
        // a single padstack layer (see `PADSTACK::ForEachUniqueLayer` in
        // `pcbnew/padstack.cpp:1241-1246`).
        assert_eq!(
            ps.copper_layers.len(),
            1,
            "PstNormal padstack must have exactly one PadStackLayer; got {} \
             (KiCad's PADSTACK::unpackCopperLayer rejects any extra entries)",
            ps.copper_layers.len()
        );

        // The single entry's `layer` must be `BlFCu` (= C++ `ALL_LAYERS`).
        // `PADSTACK::unpackCopperLayer` returns `false` for any other
        // value when `m_mode == MODE::NORMAL`.
        assert_eq!(
            ps.copper_layers[0].layer,
            BoardLayer::BlFCu as i32,
            "PstNormal PadStackLayer.layer must be BlFCu (= C++ ALL_LAYERS); \
             got {} (any other value causes KiCad's PCB_VIA deserializer \
             to fail with `could not unpack PCB_VIA from request`)",
            ps.copper_layers[0].layer
        );

        // And the size must still be the requested pad diameter.
        let pad = &ps.copper_layers[0];
        let size = pad.size.expect("size present");
        assert_eq!(size.x_nm, 400_000, "pad x size = drill + 2*annular");
        assert_eq!(size.y_nm, 400_000, "pad y size = drill + 2*annular");

        // PadStack.layers must be the full copper layer set, matching
        // what KiCad's own `PCB_VIA::GetLayerSet()` returns for
        // `VIATYPE::THROUGH` (`LSET::AllCuMask(copper_layer_count)`).
        assert_eq!(
            ps.layers, board_layers,
            "PadStack.layers must equal the full board copper layer set for a through via"
        );
    }

    /// End-to-end: every via emitted by `coils_to_board_items`
    /// for a real coil set must satisfy the PstNormal invariants
    /// (single `PadStackLayer` with `layer = BlFCu` and `PadStack.layers`
    /// equal to the full copper layer set).
    ///
    /// The test uses a 4-layer board and asserts `PadStack.layers` has
    /// exactly `num_layers` entries — KiCad's `UnpackLayerSet` rejects any
    /// via whose layer set is not a subset of the live board's actual layer
    /// set with `ISC_INVALID_DATA` (code 7).
    #[test]
    fn test_coils_to_board_items_via_round_trip_pst_normal_invariants() {
        // 4-layer board — `num_layers` is the board's actual layer count.
        let layers = 4u32;
        let (rules, active) = hand_scene();
        let coil = PhaseCoil {
            phase_idx: 0,
            layer_idx: 0,
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 0.02),
                is_active: true,
            }],
            phase_name: "A".into(),
            center_via_positions: vec![(0.001, 0.002), (0.005, 0.007), (0.01, 0.01)],
            ..PhaseCoil::default()
        };
        let items = coils_to_board_items(&[coil], layers, &rules, active);
        let via_items: Vec<&Any> = items
            .iter()
            .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
            .collect();
        assert_eq!(via_items.len(), 3, "expected 3 vias in this coil");

        let expected_board_layers: Vec<i32> = vec![
            BoardLayer::BlBCu as i32,
            BoardLayer::BlIn1Cu as i32,
            BoardLayer::BlIn2Cu as i32,
            BoardLayer::BlFCu as i32,
        ];

        for any in &via_items {
            let via = Via::decode(any.value.as_slice()).expect("decode Via via Any");
            let ps = via.pad_stack.as_ref().expect("pad_stack");
            assert_eq!(
                ps.r#type,
                PadStackType::PstNormal as i32,
                "every via's padstack type must be PstNormal"
            );
            assert_eq!(
                ps.copper_layers.len(),
                1,
                "every PstNormal via must have exactly one PadStackLayer; got {}",
                ps.copper_layers.len()
            );
            assert_eq!(
                ps.copper_layers[0].layer,
                BoardLayer::BlFCu as i32,
                "every PstNormal via's PadStackLayer.layer must be BlFCu (= C++ ALL_LAYERS); got {}",
                ps.copper_layers[0].layer
            );
            // `PadStack.layers` must have exactly `num_layers` entries.
            assert_eq!(
                ps.layers.len(),
                layers as usize,
                "PadStack.layers.len() must equal num_layers ({}); got {} entries: {:?}",
                layers, ps.layers.len(), ps.layers
            );
            assert_eq!(
                ps.layers, expected_board_layers,
                "every via's PadStack.layers must equal the live board's actual copper layer set"
            );
        }
    }

    /// Regression: when building `PadStack.layers`, the writer must use the
    /// actual layer count (`num_layers`) and never a larger DFM ceiling.
    /// `PadStack.layers` must always be exactly the `num_layers`-entry set.
    #[test]
    fn test_pad_stack_layers_reflect_num_layers() {
        // (num_layers, expected_layer_set) — `PadStack.layers` must equal
        // the `num_layers`-entry set in every case.
        let cases: &[(u32, &[BoardLayer])] = &[
            (4, &[
                BoardLayer::BlBCu,
                BoardLayer::BlIn1Cu,
                BoardLayer::BlIn2Cu,
                BoardLayer::BlFCu,
            ]),
            (2, &[
                BoardLayer::BlBCu,
                BoardLayer::BlFCu,
            ]),
            (6, &[
                BoardLayer::BlBCu,
                BoardLayer::BlIn1Cu,
                BoardLayer::BlIn2Cu,
                BoardLayer::BlIn3Cu,
                BoardLayer::BlIn4Cu,
                BoardLayer::BlFCu,
            ]),
        ];

        let (rules, active) = hand_scene();
        for &(num_layers, expected_layers) in cases {
            // Build a minimal coil with exactly one center via so the test
            // can introspect a single `Via` payload.
            let coil = PhaseCoil {
                phase_idx: 0,
                layer_idx: 0,
                segments: vec![CoilSegment {
                    start: (0.0, 0.0),
                    end: (0.0, 0.02),
                    is_active: true,
                }],
                phase_name: "A".into(),
                center_via_positions: vec![(0.001, 0.002)],
                ..PhaseCoil::default()
            };
            let items = coils_to_board_items(&[coil], num_layers, &rules, active);
            let via_any = items
                .iter()
                .find(|a| a.type_url.ends_with("kiapi.board.types.Via"))
                .unwrap_or_else(|| panic!(
                    "expected a Via in items for num_layers={}",
                    num_layers
                ));
            let via = Via::decode(via_any.value.as_slice()).expect("decode Via");
            let ps = via.pad_stack.as_ref().expect("pad_stack");

            // `PadStack.layers` length equals `num_layers`.
            assert_eq!(
                ps.layers.len(),
                num_layers as usize,
                "num_layers={}: PadStack.layers must have exactly num_layers entries, \
                 got {} (full set: {:?})",
                num_layers, ps.layers.len(), ps.layers
            );
            // The contents of `PadStack.layers` must match the expected set.
            let expected: Vec<i32> = expected_layers
                .iter()
                .map(|l| *l as i32)
                .collect();
            assert_eq!(
                ps.layers, expected,
                "num_layers={}: PadStack.layers contents must match the num_layers-entry set, \
                 got {:?}",
                num_layers, ps.layers
            );

            // PstNormal invariants: single PadStackLayer + BlFCu.
            assert_eq!(ps.r#type, PadStackType::PstNormal as i32);
            assert_eq!(ps.copper_layers.len(), 1);
            assert_eq!(ps.copper_layers[0].layer, BoardLayer::BlFCu as i32);
        }
    }
}
