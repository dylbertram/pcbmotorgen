//! HEADER and TABLES section emission.
//!
//! The DXF preamble: a HEADER section declaring the drawing units, and a
//! TABLES section with one LAYER entry per unique layer name. Both writers
//! append `"code\nvalue"` pairs to the shared fragment buffer.

use crate::groups::dxf_group;

/// Emit the HEADER section (units declaration).
///
/// INSUNITS: 4 = Millimetres.
pub(crate) fn write_header(out: &mut Vec<String>) {
    dxf_group(out, 0, "SECTION");
    dxf_group(out, 2, "HEADER");
    dxf_group(out, 9, "$INSUNITS");
    dxf_group(out, 70, "4");
    dxf_group(out, 0, "ENDSEC");
}

/// Emit the TABLES section — one LAYER entry per unique layer name.
///
/// Expects a sorted, de-duplicated list (the caller guarantees this so the
/// output is deterministic). Default colour: white (7). Vias get a different
/// colour for visual distinction.
pub(crate) fn write_tables(out: &mut Vec<String>, layer_names: &[String]) {
    write_tables_version(out, layer_names, false);
}

pub(crate) fn write_tables_version(out: &mut Vec<String>, layer_names: &[String], modern: bool) {
    dxf_group(out, 0, "SECTION");
    dxf_group(out, 2, "TABLES");

    dxf_group(out, 0, "TABLE");
    dxf_group(out, 2, "LAYER");
    if modern { dxf_group(out, 100, "AcDbSymbolTable"); }
    dxf_group(out, 70, &layer_names.len().to_string());

    for (i, name) in layer_names.iter().enumerate() {
        dxf_group(out, 0, "LAYER");
        if modern {
            dxf_group(out, 100, "AcDbSymbolTableRecord");
            dxf_group(out, 100, "AcDbLayerTableRecord");
        }
        dxf_group(out, 2, name);
        dxf_group(out, 70, "0"); // not frozen, not locked
                                 // Default colour: white (7). Vias get a different colour for
                                 // visual distinction.
        let colour = if name == "Via" {
            "3"
        } else {
            &((i % 7 + 1).to_string())
        };
        dxf_group(out, 62, colour);
        dxf_group(out, 6, "CONTINUOUS");
    }

    dxf_group(out, 0, "ENDTAB");
    dxf_group(out, 0, "ENDSEC");
}

#[cfg(test)]
mod tests {
    use crate::routing_result_to_dxf;
    use pcbmotorgen_dfm::DesignRules;
    use pcbmotorgen_routing::{Point, RouteSegment, RoutingResult, Via};

    fn sample_rules() -> DesignRules {
        DesignRules {
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.1,
        }
    }

    fn sample_result() -> RoutingResult {
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
            curves: vec![],
            vias: vec![Via {
                position: Point::new(0.001, 0.002),
                from_layer: 0,
                to_layer: 1,
                net: "A".into(),
            }],
            ..Default::default()
        }
    }

    #[test]
    fn test_dxf_has_required_sections() {
        let result = sample_result();
        let dxf = routing_result_to_dxf(&result, &sample_rules(), 0.048, true);

        assert!(
            dxf.contains("0\nSECTION\n2\nHEADER"),
            "missing HEADER section"
        );
        assert!(
            dxf.contains("0\nSECTION\n2\nTABLES"),
            "missing TABLES section"
        );
        assert!(
            dxf.contains("0\nSECTION\n2\nENTITIES"),
            "missing ENTITIES section"
        );
        assert!(dxf.ends_with("0\nEOF\n"), "must end with EOF section");
    }

    #[test]
    fn test_dxf_has_insunits_mm() {
        let result = sample_result();
        let dxf = routing_result_to_dxf(&result, &sample_rules(), 0.048, true);
        assert!(
            dxf.contains("$INSUNITS"),
            "missing $INSUNITS header variable"
        );
        assert!(dxf.contains("70\n4"), "INSUNITS must be 4 (mm)");
    }

    #[test]
    fn test_layer_names() {
        let result = sample_result();
        let dxf = routing_result_to_dxf(&result, &sample_rules(), 0.048, true);

        // LAYER table entries: "0\nLAYER\n2\n<name>\n"
        assert!(
            dxf.contains("0\nLAYER\n2\nL0_A"),
            "missing L0_A layer definition"
        );
        assert!(
            dxf.contains("0\nLAYER\n2\nVia"),
            "missing Via layer definition"
        );

        // LINE entity references L0_A via group 8.
        assert!(dxf.contains("0\nLINE\n8\nL0_A"), "LINE not on L0_A");
        // CIRCLE entity references Via via group 8.
        assert!(dxf.contains("0\nCIRCLE\n8\nVia"), "CIRCLE not on Via layer");
    }

    #[test]
    fn test_empty_result_produces_valid_dxf() {
        let result = RoutingResult::default();
        let dxf = routing_result_to_dxf(&result, &sample_rules(), 0.0, false);
        assert!(dxf.contains("HEADER"));
        assert!(dxf.contains("TABLES"));
        assert!(dxf.contains("ENTITIES"));
        assert!(dxf.contains("EOF"));
    }
}
