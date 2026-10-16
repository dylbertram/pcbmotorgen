//! Track + corner-arc emission for [`super::coils_to_board_items`].
//!
//! Converts each [`pcbmotorgen_routing::CoilSegment`] into a [`Track`] proto
//! and each corner arc into an [`Arc`] proto, applying the centering x-offset
//! and the per-coil layer / net. The packed `Any` items are appended to the
//! caller's item list.

use prost_types::Any;

use pcbmotorgen_routing::PhaseCoil;

use super::any_pack::pack_any;
use crate::layer_map::mm_to_nm;
use crate::proto::board::types::BoardLayer;
use crate::{Arc, Distance, Kiid, LockedState, Net, Track, Vector2};

/// Emit one [`Track`] per `CoilSegment` and one [`Arc`] per corner arc for
/// `coil`, appending the packed `Any` items to `items`.
///
/// `layer` is the KiCad [`BoardLayer`] the whole coil sits on (derived from
/// `coil.layer_idx` and the *actual* board layer count — see the layer
/// comment in [`super::coils_to_board_items`]). `x_offset_nm` shifts every x
/// coordinate so the coil set straddles x = 0.
pub(crate) fn emit_tracks_and_arcs(
    items: &mut Vec<Any>,
    coil: &PhaseCoil,
    layer: BoardLayer,
    net: Net,
    trace_width_nm: i64,
    x_offset_nm: i64,
) {
    // --- Tracks: one per CoilSegment ---
    for seg in &coil.segments {
        let track = Track {
            id: Some(Kiid { value: String::new() }),
            start: Some(Vector2 {
                x_nm: mm_to_nm(seg.start.0) - x_offset_nm,
                y_nm: mm_to_nm(seg.start.1),
            }),
            end: Some(Vector2 {
                x_nm: mm_to_nm(seg.end.0) - x_offset_nm,
                y_nm: mm_to_nm(seg.end.1),
            }),
            width: Some(Distance { value_nm: trace_width_nm }),
            locked: LockedState::LsUnlocked as i32,
            layer: layer as i32,
            net: Some(net.clone()),
        };
        items.push(pack_any("kiapi.board.types.Track", &track));
    }

    // --- Arcs: one per CoilArc (rounded corners) ---
    for arc in &coil.corner_arcs {
        let ki_arc = Arc {
            id: Some(Kiid { value: String::new() }),
            start: Some(Vector2 {
                x_nm: mm_to_nm(arc.start.0) - x_offset_nm,
                y_nm: mm_to_nm(arc.start.1),
            }),
            mid: Some(Vector2 {
                x_nm: mm_to_nm(arc.mid.0) - x_offset_nm,
                y_nm: mm_to_nm(arc.mid.1),
            }),
            end: Some(Vector2 {
                x_nm: mm_to_nm(arc.end.0) - x_offset_nm,
                y_nm: mm_to_nm(arc.end.1),
            }),
            width: Some(Distance { value_nm: trace_width_nm }),
            locked: LockedState::LsUnlocked as i32,
            layer: layer as i32,
            net: Some(net.clone()),
        };
        items.push(pack_any("kiapi.board.types.Arc", &ki_arc));
    }
}

// ---------------------------------------------------------------------------
// Tests (tracks + arcs)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_dfm::DesignRules;
    use pcbmotorgen_routing::{generate_coils_from_context, PhaseCoil, RoutingContext};
    use prost::Message;
    use std::collections::HashMap;

    use crate::writer::coils_to_board_items;

    /// Millimetres (routing crate's native unit).
    fn mm(v: f64) -> f64 {
        v
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

    /// Active area used by the braid structural tests.
    const BRAID_ACTIVE_AREA_MM: f64 = 600.0;

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

    #[test]
    fn test_track_coordinates_in_nanometres() {
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);

        // Decode the first item back to a Track and verify coordinate scaling.
        // Coils are centered on x = 0, so the wire x_nm = (mm * 1e6) - offset_nm.
        let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
        let seg0 = &coils.iter().next().unwrap().segments[0];
        let offset_nm = mm_to_nm(active / 2.0);
        let expected_start_x = (seg0.start.0 * 1e6).round() as i64 - offset_nm;
        assert_eq!(track.start.unwrap().x_nm, expected_start_x);
    }

    #[test]
    fn test_track_width_matches_config() {
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);
        let expected = (rules.trace_width_mm * 1e6).round() as i64;
        let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
        assert_eq!(track.width.unwrap().value_nm, expected);
    }

    #[test]
    fn nominal_trace_width_drives_written_tracks_not_the_floor() {
        // The floor and the written width are independent: raising the
        // minimum must not widen the copper, and the nominal width (not the
        // floor) is what lands on the board.
        let (coils, layers, mut rules, active) = braid_scene(2);
        rules.min_trace_mm = 0.1;
        rules.trace_width_mm = 0.3;
        let items = coils_to_board_items(&coils, layers, &rules, active);
        let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
        assert_eq!(track.width.unwrap().value_nm, 300_000);
        assert_ne!(track.width.unwrap().value_nm, 100_000);
    }

    #[test]
    fn test_braid_layer_assignment() {
        // On a 2-layer board the braid's layers 0 and 1 map to B.Cu and
        // F.Cu. Assert tracks appear on layer 0 (B.Cu) and layer 1 (F.Cu).
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);

        let mut layers_on_board: std::collections::BTreeSet<i32> = std::collections::BTreeSet::new();
        for any in &items {
            if !any.type_url.ends_with("kiapi.board.types.Track") {
                continue;
            }
            let t: Track = Track::decode(any.value.as_slice()).expect("decode Track");
            layers_on_board.insert(t.layer);
        }
        // Layer 0 → B.Cu (BlBCu = 34), layer 1 → F.Cu (BlFCu = 3) on a
        // 2-layer board.
        assert!(layers_on_board.contains(&(BoardLayer::BlBCu as i32)),
            "braid must emit tracks on B.Cu; got {:?}", layers_on_board);
        assert!(layers_on_board.contains(&(BoardLayer::BlFCu as i32)),
            "braid must emit tracks on F.Cu; got {:?}", layers_on_board);
    }
}
