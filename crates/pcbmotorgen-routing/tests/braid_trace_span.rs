//! Pins the infinity braid's ACTUAL trace X-extent for the app's reference
//! defaults. The braid routes whole diamond periods after reserving the
//! phase/strand interleave step, so the routed span is intentionally SHORTER
//! than the nominal routing domain (which equals the active area — there is
//! no end padding) by up to one period of slack at the right-hand end.
//! Consumers (desktop previews, readouts) must therefore measure the
//! returned segments instead of trusting the configured domain — this test
//! documents the expected drift.

use pcbmotorgen_routing::{generate_routing_report, RoutingContext};
use std::collections::HashMap;

/// App reference defaults: 147 mm active area (the whole routing domain),
/// τ_p = 6 mm pole pitch, 72 mm magnet-array span, 3 phases, 4 layers.
fn reference_context() -> RoutingContext {
    RoutingContext {
        active_area_length_mm: 147.0,
        board_width_mm: 20.0,
        num_layers: 4,
        phases: 3,
        min_trace_mm: 0.127,
        trace_width_mm: 0.127,
        via_pad_diameter_mm: None,
        min_space_mm: 0.127,
        expects_continuous: true,
        params: HashMap::new(), // pattern defaults (num_strands = 5; 2 is only the minimum)
        magnet_pitch_mm: Some(6.0),
        magnet_array_span_mm: Some(72.0),
        // No explicit inter-phase clearance: the documented min_space_mm
        // fallback applies.
        phase_clearance_mm: None,
    }
}

#[test]
fn braid_traces_start_at_the_domain_origin() {
    let report = generate_routing_report(&reference_context(), "infinity-braid")
        .expect("braid generates");
    let min_x = report
        .result
        .segments
        .iter()
        .map(|s| s.start.x.min(s.end.x))
        .fold(f64::INFINITY, f64::min);
    assert!((min_x - 0.0).abs() < 1e-6, "min_x = {min_x}");
}

#[test]
fn braid_span_is_shorter_than_the_nominal_domain_by_sub_period_slack() {
    let report = generate_routing_report(&reference_context(), "infinity-braid")
        .expect("braid generates");
    let max_x = report
        .result
        .segments
        .iter()
        .map(|s| s.start.x.max(s.end.x))
        .fold(f64::NEG_INFINITY, f64::max);
    let domain = 147.0; // the active area IS the routing domain
    let span = max_x - 0.0;
    // Measured 143.6 mm for the reference defaults: the last partial period
    // (147 is not a whole multiple of the pitched+interleave unit) is left
    // unrouted. Pin with a tolerant band so unrelated geometry churn does
    // not flake, but catch accidental full-domain fills or large losses.
    assert!(
        span > domain - 6.0 && span < domain - 1.0,
        "span {span:.3} mm should be ~3–6 mm short of the {domain} mm domain"
    );
    // The declared routable length still equals the nominal domain.
    assert!((report.dimensions.total_routing_length_mm - domain).abs() < 1e-6);
}
