//! Golden byte-identity tests (kata htcq).
//!
//! Acceptance for the additive IO schema requires that **existing exports
//! stay byte-identical for payloads without IO elements**. The goldens below
//! were captured from the pre-htcq implementation (commit 285ce97) for a
//! fixed scene; any change to the legacy emission paths that alters a single
//! byte fails here.
//!
//! Both goldens use the same rules: 0.1 mm trace/space, 0.2 mm via drill,
//! 0.1 mm annular ring; active area 48.0 mm; centring on.

use pcbmotorgen_export::{coils_to_board_items, routing_result_to_dxf};
use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{
    CoilSegment, PhaseCoil, Point, RouteCurve, RouteSegment, RoutingResult, Via,
};

fn rules() -> DesignRules {
    DesignRules {
        min_trace_mm: 0.1,
        trace_width_mm: 0.1,
        min_space_mm: 0.1,
        min_via_drill_mm: 0.2,
        min_via_annular_ring_mm: 0.1,
    }
}

/// The fixed legacy scene: two segments, one curve, one via.
fn legacy_result() -> RoutingResult {
    RoutingResult {
        segments: vec![
            RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(0.0, 20.0),
                layer: 0,
                net: "A".into(),
                is_active: true,
            },
            RouteSegment {
                start: Point::new(0.0, 20.0),
                end: Point::new(10.0, 20.0),
                layer: 0,
                net: "A".into(),
                is_active: false,
            },
        ],
        curves: vec![RouteCurve {
            start: Point::new(10.0, 0.0),
            mid: Point::new(10.7, 0.7),
            end: Point::new(11.0, 1.4),
            layer: 1,
            net: "B".into(),
            is_active: false,
        }],
        vias: vec![Via {
            position: Point::new(1.0, 2.0),
            from_layer: 0,
            to_layer: 1,
            net: "A".into(),
        }],
        ..RoutingResult::default()
    }
}

/// The complete DXF R12 ASCII output for [`legacy_result`], captured verbatim
/// from the pre-htcq implementation.
const GOLDEN_DXF: &str = "0
SECTION
2
HEADER
9
$INSUNITS
70
4
0
ENDSEC
0
SECTION
2
TABLES
0
TABLE
2
LAYER
70
3
0
LAYER
2
L0_A
70
0
62
1
6
CONTINUOUS
0
LAYER
2
L1_B
70
0
62
2
6
CONTINUOUS
0
LAYER
2
Via
70
0
62
3
6
CONTINUOUS
0
ENDTAB
0
ENDSEC
0
SECTION
2
ENTITIES
0
LINE
8
L0_A
10
-24.000000
20
0.000000
11
-24.000000
21
20.000000
0
LINE
8
L0_A
10
-24.000000
20
20.000000
11
-14.000000
21
20.000000
0
ARC
8
L1_B
10
-15.250000
20
1.950000
40
2.316247
50
302.660913
51
346.263732
0
CIRCLE
8
Via
10
-23.000000
20
2.000000
40
0.200000
0
ENDSEC
0
END-OF-FILE
";

#[test]
fn dxf_output_is_byte_identical_for_legacy_payloads() {
    let dxf = routing_result_to_dxf(&legacy_result(), &rules(), 48.0, true);
    // The golden stores the DXF EOF marker as END-OF-FILE to keep the file
    // heredoc-safe; the real output ends with the "0\nEOF\n" pair.
    assert_eq!(dxf, GOLDEN_DXF.replace("END-OF-FILE", "EOF"));
}

/// Hex-encoded `Any.value` bytes of `coils_to_board_items` for a one-coil
/// scene (one segment + one via), captured from the pre-htcq implementation.
const GOLDEN_KICAD_ITEMS: &[&str] = &[
    // Track
    "0a00120b088094c7f4ffffffffff011a10088094c7f4ffffffffff011080dac409220408a08d06280130223a0412022f41",
    // Via
    "0a00120f08c09884f5ffffffffff011080897a1a300801120222031a14080310221a0808c09a0c10c09a0c20012802300220012a10080310011a080880b5181080b518400120012a0412022f413001",
];

#[test]
fn kicad_items_are_byte_identical_for_legacy_payloads() {
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
    let items = coils_to_board_items(&[coil], 2, &rules(), 48.0);
    assert_eq!(items.len(), GOLDEN_KICAD_ITEMS.len());
    for (any, expected_hex) in items.iter().zip(GOLDEN_KICAD_ITEMS) {
        let hex: String = any.value.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(
            hex, *expected_hex,
            "KiCad item bytes changed for a payload without IO elements (type_url: {})",
            any.type_url
        );
    }
}

#[test]
fn legacy_payload_round_trip_without_io_fields_and_export_identically() {
    // A JSON payload produced before htcq (no `io_pads` / `io_traces` keys)
    // deserializes unchanged, and its export matches an identically-built
    // in-memory result byte for byte.
    let json = r#"{
        "format_version": 2,
        "segments": [
            {"start": {"x": 0.0, "y": 0.0}, "end": {"x": 0.0, "y": 20.0},
             "layer": 0, "net": "A", "is_active": true}
        ],
        "curves": [],
        "vias": [
            {"position": {"x": 1.0, "y": 2.0}, "from_layer": 0, "to_layer": 1, "net": "A"}
        ]
    }"#;
    let parsed: RoutingResult = serde_json::from_str(json).expect("legacy JSON");
    assert!(parsed.io_pads.is_empty());
    assert!(parsed.io_traces.is_empty());
    assert_eq!(parsed.format_version, 2, "no format_version bump");

    let from_json_dxf = routing_result_to_dxf(&parsed, &rules(), 48.0, true);
    let built = RoutingResult {
        segments: vec![RouteSegment {
            start: Point::new(0.0, 0.0),
            end: Point::new(0.0, 20.0),
            layer: 0,
            net: "A".into(),
            is_active: true,
        }],
        vias: vec![Via {
            position: Point::new(1.0, 2.0),
            from_layer: 0,
            to_layer: 1,
            net: "A".into(),
        }],
        ..RoutingResult::default()
    };
    let from_built_dxf = routing_result_to_dxf(&built, &rules(), 48.0, true);
    assert_eq!(from_json_dxf, from_built_dxf);
}
