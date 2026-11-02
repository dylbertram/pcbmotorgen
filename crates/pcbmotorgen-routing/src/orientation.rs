//! Host-side reflections, shared by every generated-copper consumer.

use serde::{Deserialize, Serialize};
use crate::{IoPadKind, PhaseBand, Point, RoutingDimensions, RoutingResult};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RoutingOrientation {
    pub mirror_x: bool,
    pub mirror_y: bool,
    pub reverse_layers: bool,
}

impl RoutingOrientation {
    pub fn point(self, point: &mut Point, length: f64, width: f64) {
        if self.mirror_x { point.x = length - point.x; }
        if self.mirror_y { point.y = width - point.y; }
    }

    pub fn layer(self, layer: u32, count: u32) -> u32 {
        if self.reverse_layers { count - 1 - layer } else { layer }
    }

    fn band(self, band: &mut PhaseBand, length: f64, width: f64, layers: u32) {
        band.layer = self.layer(band.layer, layers);
        if self.mirror_x {
            band.centerline_x_mm = length - band.centerline_x_mm;
            (band.start_x_mm, band.end_x_mm) = (length - band.end_x_mm, length - band.start_x_mm);
        }
        if self.mirror_y {
            (band.y_min_mm, band.y_max_mm) = (width - band.y_max_mm, width - band.y_min_mm);
        }
    }

    pub fn apply(self, result: &mut RoutingResult, length: f64, width: f64, layers: u32) {
        for segment in &mut result.segments {
            self.point(&mut segment.start, length, width);
            self.point(&mut segment.end, length, width);
            segment.layer = self.layer(segment.layer, layers);
        }
        for curve in &mut result.curves {
            self.point(&mut curve.start, length, width);
            self.point(&mut curve.mid, length, width);
            self.point(&mut curve.end, length, width);
            curve.layer = self.layer(curve.layer, layers);
        }
        for spline in &mut result.splines {
            for point in &mut spline.control_points { self.point(point, length, width); }
            spline.layer = self.layer(spline.layer, layers);
        }
        for via in &mut result.vias {
            self.point(&mut via.position, length, width);
            via.from_layer = self.layer(via.from_layer, layers);
            via.to_layer = self.layer(via.to_layer, layers);
        }
        for region in &mut result.pole_regions {
            self.point(&mut region.start, length, width);
            self.point(&mut region.end, length, width);
        }
        for band in &mut result.phase_bands { self.band(band, length, width, layers); }
        for pad in &mut result.io_pads {
            self.point(&mut pad.position, length, width);
            if self.reverse_layers && pad.layers.is_empty() && pad.kind != IoPadKind::Tht {
                pad.layers.push(layers - 1);
            } else {
                for layer in &mut pad.layers { *layer = self.layer(*layer, layers); }
            }
        }
        for trace in &mut result.io_traces {
            self.point(&mut trace.start, length, width);
            self.point(&mut trace.end, length, width);
            trace.layer = self.layer(trace.layer, layers);
        }
    }

    pub fn dimensions(self, dimensions: &mut RoutingDimensions, layers: u32) {
        let length = dimensions.total_routing_length_mm;
        let width = dimensions.board_width_mm;
        for band in &mut dimensions.phase_band_widths { band.layer = self.layer(band.layer, layers); }
        for band in &mut dimensions.phase_bands { self.band(&mut band.band, length, width, layers); }
        for region in &mut dimensions.pole_regions {
            self.point(&mut region.start, length, width);
            self.point(&mut region.end, length, width);
        }
    }
}

#[cfg(test)]
#[path = "orientation_tests.rs"]
mod tests;
