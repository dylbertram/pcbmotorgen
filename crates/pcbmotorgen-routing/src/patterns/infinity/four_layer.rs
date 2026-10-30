//! Four-layer series stack following the supplied star_4-layer copper.
//!
//! Layers 2/3 repeat the active XY braid on 0/1. The open ends on 1 and 2
//! join at a raised via row. The outer ends on 0 and 3 fan away from that
//! row, so a through barrel cannot short either winding pair. Star joins
//! layer-0 ends and brings the three line terminals out on layer 3.

use super::{BraidGeometry, Connection};
use crate::{Point, RouteSegment, RoutingContext, RoutingError, RoutingErrorKind, Via};

pub(super) fn stack_and_terminate(
    geometry: &mut BraidGeometry,
    ends: &[(String, Point, Point)],
    connection: Connection,
    pitch: f64,
    ctx: &RoutingContext,
) -> Result<(), RoutingError> {
    let copies: Vec<_> = geometry.segments.iter().map(|s| {
        let mut copy = s.clone();
        copy.layer += 2;
        copy
    }).collect();
    geometry.segments.extend(copies);
    let copies: Vec<_> = geometry.vias.iter().map(|v| {
        let mut copy = v.clone();
        copy.from_layer += 2;
        copy.to_layer += 2;
        copy
    }).collect();
    geometry.vias.extend(copies);
    let copies: Vec<_> = geometry.phase_bands.iter().map(|b| {
        let mut copy = b.clone();
        copy.layer += 2;
        copy
    }).collect();
    geometry.phase_bands.extend(copies);
    // Pole regions / leg grid describe XY repeats, not a count of stack copies.
    if connection == Connection::Closed {
        return Ok(());
    }

    let pad = ctx.via_pad_diameter_mm.unwrap_or(0.0);
    if !pad.is_finite() || pad < 0.0 || ctx.via_pad_diameter_mm == Some(0.0) {
        return Err(RoutingError::new(0, "via_pad_diameter_mm", RoutingErrorKind::Generation,
            "via pad diameter must be finite and positive when supplied"));
    }
    let clearance = ctx.min_space_mm.max(ctx.phase_clearance_mm.unwrap_or(ctx.min_space_mm));
    let required_inradius = pad / 2.0 + ctx.trace_width() / 2.0 + clearance;
    // The outer-layer diagonals and their first horizontal run enclose an
    // isosceles triangle. Its incenter, not half its height, maximizes the
    // clearance from all three sides. Reserve an extra pad diameter above
    // the old two-pitch envelope, and grow further when DFM requires it.
    let height = ends.iter().map(|(_, _, direction)| {
        let k = (direction.x / direction.y).abs();
        (2.0 * pitch + pad).max(required_inradius * (1.0 + k.hypot(1.0) / k))
    }).fold(0.0_f64, f64::max);

    let extend = |brk: Point, direction: Point, y: f64| {
        Point::new(brk.x + direction.x * (y - brk.y) / direction.y, y)
    };
    let neutral_y = ends[0].1.y + height;
    let neutral: Vec<_> = ends.iter().map(|(_, brk, outward)|
        extend(*brk, *outward, neutral_y)).collect();
    // The opposite-layer trace leaves the break in the mirrored direction.
    // Continuing that line upward/right avoids the series via above the break.
    let line: Vec<_> = ends.iter().enumerate().map(|(i, (_, brk, outward))|
        extend(*brk, Point::new(-outward.x, outward.y), brk.y + height + i as f64 * pitch)).collect();
    let mut trace = |net: &str, layer: u32, start: Point, end: Point| {
        geometry.segments.push(RouteSegment {
            start, end, layer, net: net.into(), is_active: false,
        });
    };
    let mut joins = Vec::new();
    for (i, (net, brk, outward)) in ends.iter().enumerate() {
        let k = (outward.x / outward.y).abs();
        let inradius = height * k / (k.hypot(1.0) + k);
        let join = Point::new(brk.x, brk.y + height - inradius);
        joins.push((join, net.clone()));
        trace(net, 1, *brk, join);
        trace(net, 2, *brk, join);
        geometry.vias.push(Via {
            position: join, from_layer: 0, to_layer: 3, net: net.clone(),
        });
        trace(net, 3, *brk, line[i]);
        trace(net, 3, line[i], Point::new(0.0, line[i].y));
        match connection {
            Connection::Star => {
                trace(net, 0, *brk, neutral[i]);
                if i + 1 < ends.len() {
                    let owner = if i == 0 { net } else { &ends[i + 1].0 };
                    trace(owner, 0, neutral[i], neutral[i + 1]);
                }
            }
            Connection::Delta => {
                let prev = (i + ends.len() - 1) % ends.len();
                let reach = extend(*brk, *outward, line[prev].y);
                trace(net, 0, *brk, reach);
                trace(net, 0, reach, line[prev]);
                geometry.vias.push(Via {
                    position: line[prev], from_layer: 0, to_layer: 3, net: net.clone(),
                });
            }
            Connection::Closed => unreachable!(),
        }
    }
    // Check other phases as well as the triangle's own sides. If the pads
    // cannot fit at this phase pitch, do not move the active winding to hide it.
    for (join, net) in joins {
        let blocked_trace = geometry.segments.iter().filter(|s| s.layer == 0 || s.layer == 3 || s.net != net)
            .any(|s| point_segment_distance(join, s.start, s.end) + 1e-9 < required_inradius);
        let blocked_via = geometry.vias.iter().any(|v| v.position != join
            && v.position.distance_to(join) + 1e-9 < pad + clearance);
        if blocked_trace || blocked_via {
            return Err(RoutingError::new(0, "four_layer_series_via", RoutingErrorKind::Generation,
                "four-layer series via cannot clear the surrounding copper at this phase pitch; reduce via/trace size or increase pole pitch"));
        }
    }
    Ok(())
}

fn point_segment_distance(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b.x - a.x, b.y - a.y);
    let t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0);
    p.distance_to(Point::new(a.x + t * dx, a.y + t * dy))
}
