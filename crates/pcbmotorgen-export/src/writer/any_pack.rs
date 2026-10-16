//! `google.protobuf.Any` packing for KiCad board items.
//!
//! The packed items are consumed by `CreateItems`, so every emitted `Any`
//! carries the `type.googleapis.com/...` URL prefix defined in
//! [`super::TYPE_URL_PREFIX`].

use prost::Message;
use prost_types::Any;

use super::TYPE_URL_PREFIX;

/// Pack a prost message into a `google.protobuf.Any` with the given short
/// protobuf type name (e.g. `"kiapi.board.types.Track"`).
pub(crate) fn pack_any<T: Message>(full_name: &str, msg: &T) -> Any {
    let mut buf = Vec::new();
    msg.encode(&mut buf)
        .expect("encoding a KiCad board item should never fail");
    Any {
        type_url: format!("{TYPE_URL_PREFIX}/{full_name}"),
        value: buf,
    }
}

// ---------------------------------------------------------------------------
// Tests (Any packing)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use pcbmotorgen_dfm::DesignRules;
    use pcbmotorgen_routing::{generate_coils_from_context, PhaseCoil, RoutingContext};
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
    fn test_items_are_track_arc_or_via() {
        let (coils, layers, rules, active) = braid_scene(2);
        let items = coils_to_board_items(&coils, layers, &rules, active);
        assert!(!items.is_empty());
        for any in &items {
            assert!(
                any.type_url.ends_with("kiapi.board.types.Track")
                    || any.type_url.ends_with("kiapi.board.types.Arc")
                    || any.type_url.ends_with("kiapi.board.types.Via"),
                "expected Track, Arc, or Via, got: {}",
                any.type_url
            );
        }
    }
}
