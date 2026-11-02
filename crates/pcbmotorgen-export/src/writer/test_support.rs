use std::collections::HashMap;

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{generate_coils_from_context, PhaseCoil, RoutingContext};

const BRAID_ACTIVE_AREA_MM: f64 = 600.0;
pub(super) const TEST_ACTIVE_AREA_MM: f64 = 48.0;

pub(super) fn test_rules() -> DesignRules {
    DesignRules {
        min_trace_mm: 5.0 * 0.0254,
        trace_width_mm: 5.0 * 0.0254,
        min_space_mm: 5.0 * 0.0254,
        min_via_drill_mm: 0.2,
        min_via_annular_ring_mm: 0.1,
    }
}

pub(super) fn braid_coils(num_layers: u32) -> Vec<PhaseCoil> {
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

pub(super) fn braid_scene(layers: u32) -> (Vec<PhaseCoil>, u32, DesignRules, f64) {
    let rules = DesignRules {
        min_trace_mm: 0.1,
        trace_width_mm: 0.1,
        min_space_mm: 0.1,
        min_via_drill_mm: 0.2,
        min_via_annular_ring_mm: 0.1,
    };
    (braid_coils(layers), layers, rules, BRAID_ACTIVE_AREA_MM)
}

pub(super) fn hand_scene() -> (DesignRules, f64) {
    (test_rules(), TEST_ACTIVE_AREA_MM)
}
