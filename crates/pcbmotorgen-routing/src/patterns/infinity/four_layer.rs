//! Four-layer series stack following the supplied star_4-layer copper.
//!
//! Layers 2/3 repeat the active XY braid on 0/1. The open ends on 1 and 2
//! join at a raised via row. The outer ends on 0 and 3 fan away from that
//! row, so a through barrel cannot short either winding pair. Star joins
//! layer-0 ends and brings the three line terminals out on layer 3.

use super::{BraidGeometry, Connection};
use crate::{Point, RouteSegment, Via};

pub(super) fn stack_and_terminate(
    geometry: &mut BraidGeometry,
    ends: &[(String, Point, Point)],
    connection: Connection,
    pitch: f64,
) {
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
        return;
    }

    let extend = |brk: Point, direction: Point, y: f64| {
        Point::new(brk.x + direction.x * (y - brk.y) / direction.y, y)
    };
    let neutral_y = ends[0].1.y + 2.0 * pitch;
    let neutral: Vec<_> = ends.iter().map(|(_, brk, outward)|
        extend(*brk, *outward, neutral_y)).collect();
    // The opposite-layer trace leaves the break in the mirrored direction.
    // Continuing that line upward/right avoids the series via above the break.
    let line: Vec<_> = ends.iter().enumerate().map(|(i, (_, brk, outward))|
        extend(*brk, Point::new(-outward.x, outward.y), brk.y + (i + 2) as f64 * pitch)).collect();
    let mut trace = |net: &str, layer: u32, start: Point, end: Point| {
        geometry.segments.push(RouteSegment {
            start, end, layer, net: net.into(), is_active: false,
        });
    };
    for (i, (net, brk, outward)) in ends.iter().enumerate() {
        let join = Point::new(brk.x, brk.y + pitch);
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
}
