//! Even-layer star/wye stack. Only the opening moves between pairs, by one
//! complete braid period per pair from the driver side toward the neutral.
//! The XY braid itself is copied without translation or terminal reversal.

use super::{BraidGeometry, Connection};
use crate::{Point, RouteSegment, RoutingContext, RoutingError, RoutingErrorKind, Via};

pub(super) fn stack_and_terminate(
    geometry: &mut BraidGeometry,
    ends: &[(String, Point, Point)],
    connection: Connection,
    pitch: f64,
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
    let clearance = ctx.min_space_mm.max(ctx.phase_clearance_mm.unwrap_or(ctx.min_space_mm));
    let required = pad / 2.0 + ctx.trace_width() / 2.0 + clearance;
    // Widen the phase rows for finite pads. Cap the fan-out's horizontal
    // step at phase_pitch/(2*phases), balancing the barrel's clearance from
    // its own mirrored driver riser and the next phase's driver riser.
    // This steepens only the external leads when the original diamond slope
    // would run through a neighbouring phase's pad. Two-layer leads have no
    // series barrels and retain the reference slope/pitch regardless of pad.
    let row_pitch = if pairs == 1 { pitch } else {
        ends.iter().map(|(_, _, d)| {
            let k = (d.x / d.y).abs();
            required * k.hypot(1.0) / (2.0 * k)
        }).fold(pitch.max(required).max(pad + clearance), f64::max)
    };
    let phase_pitch = ends.windows(2).map(|w| (w[1].1.x - w[0].1.x).abs())
        .fold(f64::INFINITY, f64::min);
    let max_step = phase_pitch / (2.0 * ends.len() as f64);
    let slope = |d: Point| {
        let k = (d.x / d.y).abs();
        if pairs == 1 { k } else { k.min(max_step / row_pitch) }
    };
    let extend = |p: Point, dx_dy: f64, y: f64| Point::new(p.x + dx_dy * (y - p.y), y);
    let last = ctx.num_layers - 1;
    let mut joins = Vec::new();
    for (i, (net, brk, outward)) in ends.iter().enumerate() {
        let k = slope(*outward);
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
            joins.push((join, net.clone(), layer - 1, layer));
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
    // A barrel may land only on its two intended layers. Even same-phase
    // copper on another layer would bypass part of the series winding.
    for (join, net, lo, hi) in joins {
        let blocked_trace = geometry.segments.iter()
            .filter(|s| s.net != net || (s.layer != lo && s.layer != hi)
                || (s.start != join && s.end != join))
            .find(|s| point_segment_distance(join, s.start, s.end) + 1e-9 < required);
        let blocked_via = geometry.vias.iter().any(|v| v.position != join
            && v.position.distance_to(join) + 1e-9 < pad + clearance);
        if blocked_trace.is_some() || blocked_via {
            let conflict = blocked_trace.map(|s| format!("trace on layer {} phase {}", s.layer, s.net))
                .unwrap_or_else(|| "another via pad".into());
            return Err(RoutingError::new(0, "series_via", RoutingErrorKind::Generation,
                format!("series via {net} at ({:.4}, {:.4}) cannot clear {conflict}; reduce via/trace size or increase pole pitch", join.x, join.y)));
        }
    }
    Ok(())
}

fn trace(g: &mut BraidGeometry, net: &str, layer: u32, start: Point, end: Point) {
    g.segments.push(RouteSegment { start, end, layer, net: net.into(), is_active: false });
}

fn point_segment_distance(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b.x - a.x, b.y - a.y);
    let t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0);
    p.distance_to(Point::new(a.x + t * dx, a.y + t * dy))
}
