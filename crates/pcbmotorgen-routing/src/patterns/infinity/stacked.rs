//! Even-layer star/wye stack. Only the opening moves between pairs, by one
//! complete braid period per pair from the driver side toward the neutral.
//! The XY braid itself is copied without translation or terminal reversal.

use super::{BraidGeometry, Connection};
use crate::{Point, RouteSegment, RoutingContext, RoutingError, RoutingErrorKind, Via};

pub(super) fn stack_and_terminate(
    geometry: &mut BraidGeometry,
    ends: &[(String, Point, Point)],
    connection: Connection,
    period: f64,
    periods: i64,
    ctx: &RoutingContext,
) -> Result<(), RoutingError> {
    let pairs = ctx.num_layers / 2;
    if connection != Connection::Closed && pairs as i64 > periods {
        return Err(RoutingError::new(0, "num_layers", RoutingErrorKind::Generation,
            "the staggered star openings need at least one braid period per layer pair; increase active length or reduce layer count"));
    }
    let base_segments = std::mem::take(&mut geometry.segments);
    let base_vias = std::mem::take(&mut geometry.vias);
    let base_bands = std::mem::take(&mut geometry.phase_bands);
    let shifted = |p: Point, stage: u32| Point::new(p.x + stage as f64 * period, p.y);
    for pair in 0..pairs {
        let stage = pairs - 1 - pair;
        geometry.segments.extend(base_segments.iter().map(|s| {
            let mut s = s.clone();
            s.layer += 2 * pair;
            s
        }));
        geometry.phase_bands.extend(base_bands.iter().map(|b| {
            let mut b = b.clone();
            b.layer += 2 * pair;
            b
        }));
        let mut vias = base_vias.clone();
        if connection != Connection::Closed && stage != 0 {
            // Restore the first-period cut before opening this pair at its
            // own period. Leaving both out splits a winding into two pieces.
            for (net, brk, _) in ends {
                vias.push(Via { position: *brk, from_layer: 0, to_layer: 1, net: net.clone() });
                let target = shifted(*brk, stage);
                let before = vias.len();
                vias.retain(|v| v.net != *net || v.position.distance_to(target) > 1e-9);
                if vias.len() + 1 != before {
                    return Err(RoutingError::new(0, "series_opening", RoutingErrorKind::Generation,
                        "could not locate exactly one braid via at the staggered opening"));
                }
            }
        }
        geometry.vias.extend(vias.into_iter().map(|mut v| {
            v.from_layer += 2 * pair;
            v.to_layer += 2 * pair;
            v
        }));
    }
    if connection == Connection::Closed { return Ok(()); }
    debug_assert_eq!(connection, Connection::Star);

    let pad = ctx.via_pad_diameter_mm.unwrap_or(0.0);
    if !pad.is_finite() || pad < 0.0 || ctx.via_pad_diameter_mm == Some(0.0) {
        return Err(RoutingError::new(0, "via_pad_diameter_mm", RoutingErrorKind::Generation,
            "via pad diameter must be finite and positive when supplied"));
    }
    // Continue the projected braid edge angle without capping its slope.
    // Match the actual via-row Y interval, not trace/pad DFM sizes. Use the
    // shortest consecutive interval because the two-strand braid has no
    // intermediate upper crossing row, only lower crossing rows and distant
    // end-turn vias at the board centre.
    // The user chose exact geometry plus DFM warnings, never an automatic
    // change of angle or row pitch to hide a clearance violation.
    let mut via_ys: Vec<_> = geometry.vias.iter().map(|v| v.position.y).collect();
    via_ys.sort_by(f64::total_cmp);
    via_ys.dedup_by(|a, b| (*a - *b).abs() < 1e-9);
    let row_pitch = via_ys.windows(2).map(|w| w[1] - w[0])
        .filter(|d| *d > 1e-9).min_by(f64::total_cmp)
        .ok_or_else(|| RoutingError::new(0, "lead_pitch", RoutingErrorKind::Generation,
            "cannot resolve the braid's top-to-next-via Y pitch"))?;
    let extend = |p: Point, dx_dy: f64, y: f64| Point::new(p.x + dx_dy * (y - p.y), y);
    let last = ctx.num_layers - 1;
    for (i, (net, brk, outward)) in ends.iter().enumerate() {
        let k = (outward.x / outward.y).abs();
        let y = brk.y + (i + 1) as f64 * row_pitch;
        // Driver trace bends left on the top layer. Each series step bends
        // right on the outgoing even layer, then reaches the next opening
        // along the following odd layer. No full barrel shares another step.
        let driver = extend(*brk, -k, y);
        trace(geometry, net, last, *brk, driver);
        trace(geometry, net, last, driver, Point::new(0.0, y));
        for stage in 0..pairs - 1 {
            let from = shifted(*brk, stage);
            let to = shifted(*brk, stage + 1);
            let join = extend(from, k, y);
            let corner = extend(to, -k, y);
            if join.x >= corner.x {
                return Err(RoutingError::new(0, "series_leads", RoutingErrorKind::Generation,
                    "series fan-outs cannot fit between consecutive openings; reduce via/trace size or increase pole pitch"));
            }
            let layer = ctx.num_layers - 2 - 2 * stage;
            trace(geometry, net, layer, from, join);
            trace(geometry, net, layer - 1, to, corner);
            trace(geometry, net, layer - 1, corner, join);
            geometry.vias.push(Via { position: join, from_layer: 0, to_layer: last, net: net.clone() });
        }
        let end = shifted(*brk, pairs - 1);
        let neutral = Point::new(end.x, end.y + row_pitch);
        trace(geometry, net, 0, end, neutral);
        if i + 1 < ends.len() {
            let next = shifted(ends[i + 1].1, pairs - 1);
            let owner = if i == 0 { net } else { &ends[i + 1].0 };
            trace(geometry, owner, 0, neutral, Point::new(next.x, neutral.y));
        }
    }
    Ok(())
}

fn trace(g: &mut BraidGeometry, net: &str, layer: u32, start: Point, end: Point) {
    g.segments.push(RouteSegment { start, end, layer, net: net.into(), is_active: false });
}
