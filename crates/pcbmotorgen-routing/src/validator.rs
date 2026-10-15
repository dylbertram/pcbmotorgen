//! Strict-shape validation gate.
//!
//! Every [`RoutingResult`] from any source (bundled, Rust plugin, Python
//! runner) passes through [`Validator::validate`]. It rejects malformed shapes
//! with field-level errors; a result is never silently sanitised.

use crate::context::RoutingContext;
use crate::error::{RoutingError, RoutingErrorKind};
use crate::io::IoPadKind;
use crate::model::{Point, RoutingResult, FORMAT_VERSION};

/// The single validation gate.
pub struct Validator;

/// Routing-domain bounds shared by the geometric checks.
#[derive(Clone, Copy)]
struct Bounds {
    x_max: f64,
    board_width: f64,
    eps: f64,
    /// Skip the board-width (y) check — used for inactive lead conductors.
    y_unbounded: bool,
}

impl Validator {
    /// Validate `result` against `ctx`. Returns `Ok(())` or the first
    /// [`RoutingError`].
    pub fn validate(
        result: &RoutingResult,
        ctx: &RoutingContext,
        expect_continuous: bool,
    ) -> Result<(), RoutingError> {
        if result.format_version != FORMAT_VERSION {
            return Err(RoutingError::new(
                0,
                "format_version",
                RoutingErrorKind::Malformed,
                format!(
                    "routing result format_version {} is unsupported; this crate requires version {} (millimetre geometry)",
                    result.format_version, FORMAT_VERSION
                ),
            ));
        }
        if result.is_empty() {
            return Err(RoutingError::new(
                0,
                "result",
                RoutingErrorKind::Missing,
                "the routing pattern produced no segments, curves, or vias",
            ));
        }

        // The routing domain EQUALS the active area — there is no end padding.
        // The epsilon lets coordinates sitting exactly on the boundary pass.
        let bounds = Bounds {
            x_max: ctx.active_area_length_mm,
            board_width: ctx.board_width_mm,
            eps: 1e-6,
            y_unbounded: false,
        };

        validate_segments(result, ctx, &bounds)?;
        validate_curves(result, ctx, &bounds)?;
        validate_vias(result, ctx, &bounds)?;
        for (i, spline) in result.splines.iter().enumerate() {
            spline.validate().map_err(|message| {
                RoutingError::new(
                    i + 1,
                    format!("splines[{i}]"),
                    RoutingErrorKind::Malformed,
                    message,
                )
            })?;
            check_layer(
                spline.layer,
                ctx.num_layers,
                &format!("splines[{i}].layer"),
                i + 1,
            )?;
            check_net(&spline.net, &format!("splines[{i}].net"), i + 1)?;
            for p in &spline.control_points {
                check_point(p, &bounds, &format!("splines[{i}].control_points"), i + 1)?;
            }
        }
        validate_pole_regions(result, &bounds)?;
        validate_phase_bands(result, ctx, &bounds)?;
        validate_io_pads(result, ctx, &bounds)?;
        validate_io_traces(result, ctx, &bounds)?;

        // Continuity (per layer+net chain).
        if expect_continuous {
            validate_continuity(result, ctx, bounds.eps)?;
        }

        Ok(())
    }
}

fn validate_segments(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    // Inactive conductors (end turns, terminal leads) may run past either
    // board-width edge to reach the winding's terminals; they stay within the
    // travel extent. Thrust-producing conductors must stay on the board.
    let lead_bounds = Bounds {
        y_unbounded: true,
        ..*bounds
    };
    for (i, s) in result.segments.iter().enumerate() {
        let idx = i + 1;
        let b = if s.is_active { bounds } else { &lead_bounds };
        check_point(&s.start, b, &format!("segments[{i}].start"), idx)?;
        check_point(&s.end, b, &format!("segments[{i}].end"), idx)?;
        let len = length(s.start, s.end);
        if !len.is_finite() || len <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("segments[{i}]"),
                RoutingErrorKind::Degenerate,
                format!(
                    "zero-length segment {} ↦ {} — a conductor cannot have zero length",
                    fmt_pt(s.start),
                    fmt_pt(s.end)
                ),
            ));
        }
        check_layer(
            s.layer,
            ctx.num_layers,
            &format!("segments[{i}].layer"),
            idx,
        )?;
        check_net(&s.net, &format!("segments[{i}].net"), idx)?;
    }
    Ok(())
}

fn validate_curves(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    for (i, c) in result.curves.iter().enumerate() {
        let idx = i + 1;
        check_point(&c.start, bounds, &format!("curves[{i}].start"), idx)?;
        check_point(&c.mid, bounds, &format!("curves[{i}].mid"), idx)?;
        check_point(&c.end, bounds, &format!("curves[{i}].end"), idx)?;
        // Degenerate arc: any two of start/mid/end coincide (radius ~ 0).
        if length(c.start, c.mid) <= bounds.eps || length(c.mid, c.end) <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("curves[{i}]"),
                RoutingErrorKind::Degenerate,
                "degenerate arc — start, mid, and end must not collapse to a point",
            ));
        }
        check_layer(c.layer, ctx.num_layers, &format!("curves[{i}].layer"), idx)?;
        check_net(&c.net, &format!("curves[{i}].net"), idx)?;
    }
    Ok(())
}

fn validate_vias(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    // A via that ends an inactive conductor (a terminal joint on a lead) may
    // sit past the board-width edges with that lead.
    let lead_bounds = Bounds {
        y_unbounded: true,
        ..*bounds
    };
    let ends_a_lead = |p: Point| {
        result.segments.iter().any(|s| {
            !s.is_active
                && (length(s.start, p) <= bounds.eps || length(s.end, p) <= bounds.eps)
        })
    };
    for (i, v) in result.vias.iter().enumerate() {
        let idx = i + 1;
        let b = if ends_a_lead(v.position) { &lead_bounds } else { bounds };
        check_point(&v.position, b, &format!("vias[{i}].position"), idx)?;
        check_layer(
            v.from_layer,
            ctx.num_layers,
            &format!("vias[{i}].from_layer"),
            idx,
        )?;
        check_layer(
            v.to_layer,
            ctx.num_layers,
            &format!("vias[{i}].to_layer"),
            idx,
        )?;
        if v.from_layer == v.to_layer {
            return Err(RoutingError::new(
                idx,
                format!("vias[{i}]"),
                RoutingErrorKind::Malformed,
                format!(
                    "via routes layer {} to itself — from_layer must differ from to_layer",
                    v.from_layer
                ),
            ));
        }
        check_net(&v.net, &format!("vias[{i}].net"), idx)?;
    }
    Ok(())
}

fn validate_pole_regions(result: &RoutingResult, bounds: &Bounds) -> Result<(), RoutingError> {
    for (i, region) in result.pole_regions.iter().enumerate() {
        let idx = i + 1;
        check_point(
            &region.start,
            bounds,
            &format!("pole_regions[{i}].start"),
            idx,
        )?;
        check_point(&region.end, bounds, &format!("pole_regions[{i}].end"), idx)?;
        if length(region.start, region.end) <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("pole_regions[{i}]"),
                RoutingErrorKind::Degenerate,
                "zero-length pole region — start and end must differ",
            ));
        }
        check_net(&region.phase, &format!("pole_regions[{i}].phase"), idx)?;
    }
    Ok(())
}

/// Validate the pattern-declared phase bands (kata hzs2): finite scalars,
/// in-bounds x/y extents and centerline, non-degenerate extents, valid layer
/// and net. Same rejection policy as the geometry: never sanitised.
fn validate_phase_bands(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    for (i, band) in result.phase_bands.iter().enumerate() {
        let idx = i + 1;
        for (name, x) in [
            ("centerline_x_mm", band.centerline_x_mm),
            ("start_x_mm", band.start_x_mm),
            ("end_x_mm", band.end_x_mm),
        ] {
            if !x.is_finite() {
                return Err(RoutingError::new(
                    idx,
                    format!("phase_bands[{i}].{name}"),
                    RoutingErrorKind::Malformed,
                    format!("non-finite coordinate {x} — NaN/Inf is not a valid position"),
                ));
            }
            if x < -bounds.eps || x > bounds.x_max + bounds.eps {
                return Err(RoutingError::new(
                    idx,
                    format!("phase_bands[{i}].{name}"),
                    RoutingErrorKind::OutOfBounds,
                    format!(
                        "x = {x:.3} mm outside the routing area [0, {:.3} mm] — the routing domain equals the active area; fix the pattern",
                        bounds.x_max
                    ),
                ));
            }
        }
        for (name, y) in [("y_min_mm", band.y_min_mm), ("y_max_mm", band.y_max_mm)] {
            if !y.is_finite() {
                return Err(RoutingError::new(
                    idx,
                    format!("phase_bands[{i}].{name}"),
                    RoutingErrorKind::Malformed,
                    format!("non-finite coordinate {y} — NaN/Inf is not a valid position"),
                ));
            }
            if y < -bounds.eps || y > bounds.board_width + bounds.eps {
                return Err(RoutingError::new(
                    idx,
                    format!("phase_bands[{i}].{name}"),
                    RoutingErrorKind::OutOfBounds,
                    format!(
                        "y = {y:.3} mm outside the board width [0, {:.3} mm]",
                        bounds.board_width
                    ),
                ));
            }
        }
        if band.end_x_mm - band.start_x_mm <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("phase_bands[{i}]"),
                RoutingErrorKind::Degenerate,
                format!(
                    "degenerate along-travel extent {} ↦ {} mm — start_x_mm and end_x_mm must differ",
                    band.start_x_mm,
                    band.end_x_mm
                ),
            ));
        }
        if band.y_max_mm - band.y_min_mm <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("phase_bands[{i}]"),
                RoutingErrorKind::Degenerate,
                format!(
                    "degenerate y-extent {} ↦ {} mm — y_min_mm and y_max_mm must differ",
                    band.y_min_mm, band.y_max_mm
                ),
            ));
        }
        check_layer(
            band.layer,
            ctx.num_layers,
            &format!("phase_bands[{i}].layer"),
            idx,
        )?;
        check_net(&band.net, &format!("phase_bands[{i}].net"), idx)?;
    }
    Ok(())
}

/// Validate the additive IO pad elements (`io_pads[]`).
///
/// Same geometric domain as every other element (the routing domain equals
/// the active area; the epsilon lets pads sitting exactly on a boundary —
/// e.g. board-edge connector pads — pass). Pad-stack integrity: sizes must
/// be finite and positive; THT pads require a positive `drill_mm`, surface
/// pads (SMD / board-edge) reject one.
fn validate_io_pads(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    for (i, pad) in result.io_pads.iter().enumerate() {
        let idx = i + 1;
        check_point(
            &pad.position,
            bounds,
            &format!("io_pads[{i}].position"),
            idx,
        )?;
        if !pad.size.x.is_finite()
            || !pad.size.y.is_finite()
            || pad.size.x <= 0.0
            || pad.size.y <= 0.0
        {
            return Err(RoutingError::new(
                idx,
                format!("io_pads[{i}].size"),
                RoutingErrorKind::Malformed,
                format!(
                    "pad size {:.3}×{:.3} mm — pad dimensions must be finite and positive",
                    pad.size.x, pad.size.y
                ),
            ));
        }
        if let Some(drill) = pad.drill_mm {
            if !drill.is_finite() || drill <= 0.0 {
                return Err(RoutingError::new(
                    idx,
                    format!("io_pads[{i}].drill_mm"),
                    RoutingErrorKind::Malformed,
                    format!("drill_mm = {drill} — drill diameters must be finite and positive"),
                ));
            }
        }
        match pad.kind {
            IoPadKind::Tht if pad.drill_mm.is_none() => {
                return Err(RoutingError::new(
                    idx,
                    format!("io_pads[{i}]"),
                    RoutingErrorKind::Missing,
                    "THT IO pad without drill_mm — a plated through-hole pad must declare its drill diameter",
                ));
            }
            IoPadKind::Smd | IoPadKind::BoardEdge if pad.drill_mm.is_some() => {
                return Err(RoutingError::new(
                    idx,
                    format!("io_pads[{i}]"),
                    RoutingErrorKind::Malformed,
                    format!(
                        "{:?} IO pad with drill_mm — surface pads have no drill; use kind \"tht\" for plated pads",
                        pad.kind
                    ),
                ));
            }
            _ => {}
        }
        for (j, &layer) in pad.layers.iter().enumerate() {
            check_layer(
                layer,
                ctx.num_layers,
                &format!("io_pads[{i}].layers[{j}]"),
                idx,
            )?;
        }
        check_net(&pad.net, &format!("io_pads[{i}].net"), idx)?;
    }
    Ok(())
}

/// Validate the additive IO fanout trace elements (`io_traces[]`).
fn validate_io_traces(
    result: &RoutingResult,
    ctx: &RoutingContext,
    bounds: &Bounds,
) -> Result<(), RoutingError> {
    for (i, t) in result.io_traces.iter().enumerate() {
        let idx = i + 1;
        check_point(&t.start, bounds, &format!("io_traces[{i}].start"), idx)?;
        check_point(&t.end, bounds, &format!("io_traces[{i}].end"), idx)?;
        let len = length(t.start, t.end);
        if !len.is_finite() || len <= bounds.eps {
            return Err(RoutingError::new(
                idx,
                format!("io_traces[{i}]"),
                RoutingErrorKind::Degenerate,
                format!(
                    "zero-length IO trace {} ↦ {} — a fanout trace cannot have zero length",
                    fmt_pt(t.start),
                    fmt_pt(t.end)
                ),
            ));
        }
        check_layer(
            t.layer,
            ctx.num_layers,
            &format!("io_traces[{i}].layer"),
            idx,
        )?;
        check_net(&t.net, &format!("io_traces[{i}].net"), idx)?;
    }
    Ok(())
}

fn check_point(p: &Point, bounds: &Bounds, field: &str, index: usize) -> Result<(), RoutingError> {
    if !p.x.is_finite() || !p.y.is_finite() {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::Malformed,
            format!(
                "non-finite coordinate {},{} — NaN/Inf is not a valid position",
                p.x, p.y
            ),
        ));
    }
    if p.x < -bounds.eps || p.x > bounds.x_max + bounds.eps {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::OutOfBounds,
            format!(
                "x = {:.3} mm outside the routing area [0, {:.3} mm] — the routing domain equals the active area; fix the pattern",
                p.x,
                bounds.x_max
            ),
        ));
    }
    if !bounds.y_unbounded && (p.y < -bounds.eps || p.y > bounds.board_width + bounds.eps) {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::OutOfBounds,
            format!(
                "y = {:.3} mm outside the board width [0, {:.3} mm]",
                p.y, bounds.board_width
            ),
        ));
    }
    Ok(())
}

fn check_layer(layer: u32, num_layers: u32, field: &str, index: usize) -> Result<(), RoutingError> {
    if layer >= num_layers {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::BadLayer,
            format!(
                "layer = {} but the board has only {} copper layers (0..{})",
                layer,
                num_layers,
                num_layers.saturating_sub(1)
            ),
        ));
    }
    Ok(())
}

fn check_net(net: &str, field: &str, index: usize) -> Result<(), RoutingError> {
    if net.is_empty() {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::BadNet,
            "empty net label — every conductor/via must belong to a named phase net",
        ));
    }
    if !net.is_ascii() {
        return Err(RoutingError::new(
            index,
            field,
            RoutingErrorKind::BadNet,
            format!("net label \"{net}\" is not ASCII — use plain phase labels like \"A\", \"B\", \"C\""),
        ));
    }
    Ok(())
}

/// Check that consecutive elements sharing a (layer, net) chain connect
/// end→start. Chains are built from segments and curves in emitted order.
fn validate_continuity(
    result: &RoutingResult,
    ctx: &RoutingContext,
    eps: f64,
) -> Result<(), RoutingError> {
    use std::collections::HashMap;

    struct El {
        start: Point,
        end: Point,
        idx: usize,
    }

    // Chain keyed by (layer, net), preserving emitted order.
    let mut chains: HashMap<(u32, String), Vec<El>> = HashMap::new();

    let elems = result
        .segments
        .iter()
        .map(|s| (s.layer, s.net.clone(), s.start, s.end, 0))
        .chain(
            result
                .curves
                .iter()
                .map(|c| (c.layer, c.net.clone(), c.start, c.end, 0)),
        )
        .enumerate();

    for (k, (layer, net, start, end, _)) in elems {
        chains
            .entry((layer, net))
            .or_default()
            .push(El { start, end, idx: k });
    }

    for ((layer, net), chain) in &chains {
        if chain.len() < 2 {
            continue;
        }
        for w in 0..chain.len() - 1 {
            let a = &chain[w];
            let b = &chain[w + 1];
            let gap = length(a.end, b.start);
            // Allow the discontinuity to be at most a small multiple of the
            // min trace (corner clearance); larger gaps mean stranded copper.
            let tol = (ctx.min_trace_mm * 2.0).max(eps);
            if gap > tol {
                return Err(RoutingError::new(
                    b.idx,
                    format!("chain layer {layer} net {net}"),
                    RoutingErrorKind::Malformed,
                    format!(
                        "discontinuity in the {} net path on layer {}: gap of {:.3} mm between elements — the pattern declares continuous copper but elements do not connect end→start",
                        net,
                        layer,
                        gap
                    ),
                ));
            }
        }
    }

    Ok(())
}

fn length(a: Point, b: Point) -> f64 {
    let dx = b.x - a.x;
    let dy = b.y - a.y;
    (dx * dx + dy * dy).sqrt()
}

fn fmt_pt(p: Point) -> String {
    format!("({:.3}, {:.3}) mm", p.x, p.y)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{RouteSegment, Via};
    use std::collections::HashMap;

    fn ctx() -> RoutingContext {
        RoutingContext {
            active_area_length_mm: 100.0,
            board_width_mm: 20.0,
            num_layers: 2,
            phases: 3,
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            expects_continuous: false,
            params: HashMap::new(),
            ..RoutingContext::default()
        }
    }

    fn seg(x1: f64, y1: f64, x2: f64, y2: f64, layer: u32, net: &str) -> RouteSegment {
        RouteSegment {
            start: Point::new(x1, y1),
            end: Point::new(x2, y2),
            layer,
            net: net.into(),
            is_active: true,
        }
    }

    fn result_with(segments: Vec<RouteSegment>) -> RoutingResult {
        RoutingResult {
            segments,
            curves: vec![],
            vias: vec![],
            ..Default::default()
        }
    }

    #[test]
    fn accepts_valid_single_segment() {
        let r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        assert!(Validator::validate(&r, &ctx(), false).is_ok());
    }

    #[test]
    fn rejects_meter_contract_version() {
        let mut r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        r.format_version = 1;
        let error = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(error.field, "format_version");
        assert!(error.message.contains("millimetre"));
    }

    #[test]
    fn rejects_nan() {
        let r = result_with(vec![seg(f64::NAN, 0.0, 0.0, 20.0, 0, "A")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Malformed);
        assert!(e.field.contains("segments[0].start"));
    }

    #[test]
    fn rejects_out_of_bounds_x() {
        let r = result_with(vec![seg(200.0, 0.0, 0.0, 20.0, 0, "A")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::OutOfBounds);
    }

    #[test]
    fn rejects_out_of_bounds_y() {
        let r = result_with(vec![seg(0.0, 50.0, 0.0, 20.0, 0, "A")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::OutOfBounds);
    }

    #[test]
    fn rejects_bad_layer() {
        let r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 5, "A")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::BadLayer);
        assert!(e.message.contains("2 copper layers"));
    }

    #[test]
    fn rejects_degenerate_segment() {
        let r = result_with(vec![seg(0.0, 0.0, 0.0, 0.0, 0, "A")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Degenerate);
    }

    #[test]
    fn rejects_empty_net() {
        let r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "")]);
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::BadNet);
    }

    #[test]
    fn rejects_empty_result() {
        let r = RoutingResult::default();
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Missing);
    }

    #[test]
    fn rejects_via_same_layer() {
        let r = RoutingResult {
            segments: vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")],
            curves: vec![],
            vias: vec![Via {
                position: Point::new(0.0, 10.0),
                from_layer: 0,
                to_layer: 0,
                net: "A".into(),
            }],
            ..Default::default()
        };
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Malformed);
    }

    #[test]
    fn rejects_discontinuous_path_when_expected() {
        // Two segments on the same layer+net with a big gap between them.
        let r = result_with(vec![
            seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
            seg(50.0, 20.0, 60.0, 20.0, 0, "A"),
        ]);
        let e = Validator::validate(&r, &ctx(), true).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Malformed);
        assert!(e.message.contains("continuity") || e.message.contains("discontinuity"));
    }

    #[test]
    fn accepts_continuous_path_when_expected() {
        let r = result_with(vec![
            seg(0.0, 0.0, 10.0, 0.0, 0, "A"),
            seg(10.0, 0.0, 20.0, 0.0, 0, "A"),
        ]);
        assert!(Validator::validate(&r, &ctx(), true).is_ok());
    }

    #[test]
    fn accepts_valid_phase_band_and_legacy_results_still_pass() {
        // Legacy payload without bands: unchanged.
        let r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        assert!(Validator::validate(&r, &ctx(), false).is_ok());

        let mut r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        r.phase_bands = vec![crate::model::PhaseBand {
            layer: 0,
            net: "A".into(),
            centerline_x_mm: 2.0,
            start_x_mm: 0.0,
            end_x_mm: 4.0,
            y_min_mm: 0.0,
            y_max_mm: 20.0,
            shape: crate::model::PhaseBandShape::Linear,
        }];
        assert!(Validator::validate(&r, &ctx(), false).is_ok());
    }

    #[test]
    fn rejects_phase_band_out_of_bounds() {
        let mut r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        r.phase_bands = vec![crate::model::PhaseBand {
            layer: 0,
            net: "A".into(),
            centerline_x_mm: 2.0,
            start_x_mm: 0.0,
            end_x_mm: 150.0,
            y_min_mm: 0.0,
            y_max_mm: 20.0,
            shape: crate::model::PhaseBandShape::Linear,
        }];
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::OutOfBounds);
        assert!(
            e.field.contains("phase_bands[0].end_x_mm"),
            "field: {}",
            e.field
        );
    }

    #[test]
    fn rejects_phase_band_non_finite_and_degenerate() {
        let mut r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        r.phase_bands = vec![crate::model::PhaseBand {
            layer: 0,
            net: "A".into(),
            centerline_x_mm: f64::NAN,
            start_x_mm: 0.0,
            end_x_mm: 4.0,
            y_min_mm: 0.0,
            y_max_mm: 20.0,
            shape: crate::model::PhaseBandShape::Linear,
        }];
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Malformed);

        r.phase_bands[0].centerline_x_mm = 2.0;
        r.phase_bands[0].end_x_mm = 0.0;
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Degenerate);

        r.phase_bands[0].end_x_mm = 4.0;
        r.phase_bands[0].y_max_mm = 0.0;
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::Degenerate);
    }

    #[test]
    fn rejects_phase_band_bad_layer_and_net() {
        let mut r = result_with(vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")]);
        r.phase_bands = vec![crate::model::PhaseBand {
            layer: 5,
            net: "A".into(),
            centerline_x_mm: 2.0,
            start_x_mm: 0.0,
            end_x_mm: 4.0,
            y_min_mm: 0.0,
            y_max_mm: 20.0,
            shape: crate::model::PhaseBandShape::Linear,
        }];
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::BadLayer);

        r.phase_bands[0].layer = 0;
        r.phase_bands[0].net = "".into();
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::BadNet);
    }

    #[test]
    fn rejects_empty_net_on_via() {
        let r = RoutingResult {
            segments: vec![seg(0.0, 0.0, 0.0, 20.0, 0, "A")],
            curves: vec![],
            vias: vec![Via {
                position: Point::new(0.0, 10.0),
                from_layer: 0,
                to_layer: 1,
                net: "".into(),
            }],
            ..Default::default()
        };
        let e = Validator::validate(&r, &ctx(), false).unwrap_err();
        assert_eq!(e.kind, RoutingErrorKind::BadNet);
    }
}
