//! Coil presentation model (`CoilSegment`, `CoilArc`, `PhaseCoil`).
//!
//! This module defines the geometry *presentation* the writer, preview, and
//! simulation/force model consume. It contains no routing algorithms — all
//! geometry is produced by a routing pattern via [`generate`](crate::generate).
//!
//! Coordinate system: X = travel axis, Y = perpendicular (board width). All [mm].

use serde::{Deserialize, Serialize};

/// Standard phase name labels (A, B, C, D, E, F).
pub const PHASE_NAMES: &[&str] = &["A", "B", "C", "D", "E", "F"];

/// One straight trace segment in a coil path.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CoilSegment {
    pub start: (f64, f64),
    pub end: (f64, f64),
    pub is_active: bool,
}

/// One rounded corner in a coil path — an arc with start, midpoint, and end
/// points (matching KiCad's `(arc ...)` s-expression primitive).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CoilArc {
    pub start: (f64, f64),
    pub mid: (f64, f64),
    pub end: (f64, f64),
    /// Active force-producing curve (`true`) vs end-turn connector (`false`).
    #[serde(default)]
    pub is_active: bool,
}

impl CoilSegment {
    /// Euclidean length [mm].
    pub fn length_mm(&self) -> f64 {
        let dx = self.end.0 - self.start.0;
        let dy = self.end.1 - self.start.1;
        (dx * dx + dy * dy).sqrt()
    }

    /// Midpoint of the segment.
    pub fn midpoint(&self) -> (f64, f64) {
        (
            (self.start.0 + self.end.0) / 2.0,
            (self.start.1 + self.end.1) / 2.0,
        )
    }

}

/// Complete coil path for one (phase, layer) group of a routing result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseCoil {
    pub phase_idx: u32,
    pub layer_idx: u32,
    /// Straight-line segments.
    pub segments: Vec<CoilSegment>,
    /// Rounded corners / curves (may be empty for patterns without curves).
    #[serde(default)]
    pub corner_arcs: Vec<CoilArc>,
    pub phase_name: String,
    /// The routing pattern id that produced this coil.
    #[serde(default = "default_pattern_id")]
    pub pattern_id: String,
    #[serde(default)]
    pub layer_pair: Option<(u32, u32)>,
    #[serde(default)]
    pub center_via_positions: Vec<(f64, f64)>,
    /// Exact barrel spans, including mixed pair and full-stack connections.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub routed_vias: Vec<crate::Via>,
}

fn default_pattern_id() -> String {
    "infinity-braid".to_string()
}

impl PhaseCoil {
    /// Ordered list of all waypoints along the coil path (len = segments + 1).
    pub fn polyline(&self) -> Vec<(f64, f64)> {
        if self.segments.is_empty() {
            return vec![];
        }
        let mut pts = vec![self.segments[0].start];
        for seg in &self.segments {
            pts.push(seg.end);
        }
        pts
    }

    /// All active conductor segments.
    pub fn active_segments(&self) -> Vec<&CoilSegment> {
        self.segments.iter().filter(|s| s.is_active).collect()
    }

    /// All end-turn segments.
    pub fn end_turn_segments(&self) -> Vec<&CoilSegment> {
        self.segments.iter().filter(|s| !s.is_active).collect()
    }

    /// Number of active conductors.
    pub fn active_conductor_count(&self) -> usize {
        self.segments.iter().filter(|s| s.is_active).count()
    }

    /// (min_x, min_y, max_x, max_y) bounding box — includes corner arcs.
    pub fn bounding_box(&self) -> (f64, f64, f64, f64) {
        let pts = self.polyline();
        if pts.is_empty() && self.corner_arcs.is_empty() {
            return (0.0, 0.0, 0.0, 0.0);
        }
        let (mut min_x, mut min_y) = (f64::INFINITY, f64::INFINITY);
        let (mut max_x, mut max_y) = (f64::NEG_INFINITY, f64::NEG_INFINITY);
        for &(x, y) in &pts {
            if x < min_x { min_x = x; }
            if y < min_y { min_y = y; }
            if x > max_x { max_x = x; }
            if y > max_y { max_y = y; }
        }
        for arc in &self.corner_arcs {
            for &(x, y) in &[arc.start, arc.mid, arc.end] {
                if x < min_x { min_x = x; }
                if y < min_y { min_y = y; }
                if x > max_x { max_x = x; }
                if y > max_y { max_y = y; }
            }
        }
        (min_x, min_y, max_x, max_y)
    }

    /// Electrical input terminal (first waypoint).
    pub fn terminal_start(&self) -> (f64, f64) {
        if self.segments.is_empty() {
            (0.0, 0.0)
        } else {
            self.segments[0].start
        }
    }

    /// Electrical output terminal (last waypoint).
    pub fn terminal_end(&self) -> (f64, f64) {
        if self.segments.is_empty() {
            (0.0, 0.0)
        } else {
            self.segments[self.segments.len() - 1].end
        }
    }

    /// Total copper trace length [mm].
    pub fn total_length_mm(&self) -> f64 {
        self.segments.iter().map(|s| s.length_mm()).sum()
    }

    /// Total length of active conductor segments [mm].
    pub fn active_length_mm(&self) -> f64 {
        self.segments
            .iter()
            .filter(|s| s.is_active)
            .map(|s| s.length_mm())
            .sum()
    }

    /// Total length of end-turn segments [mm].
    pub fn end_turn_length_mm(&self) -> f64 {
        self.segments
            .iter()
            .filter(|s| !s.is_active)
            .map(|s| s.length_mm())
            .sum()
    }

    /// Return true if every segment starts where the previous ends.
    pub fn is_continuous(&self, tol: f64) -> bool {
        for i in 0..self.segments.len().saturating_sub(1) {
            let ex = self.segments[i].end.0;
            let ey = self.segments[i].end.1;
            let sx = self.segments[i + 1].start.0;
            let sy = self.segments[i + 1].start.1;
            if (ex - sx).abs() > tol || (ey - sy).abs() > tol {
                return false;
            }
        }
        true
    }
}

impl Default for PhaseCoil {
    fn default() -> Self {
        Self {
            phase_idx: 0,
            layer_idx: 0,
            segments: vec![],
            corner_arcs: vec![],
            phase_name: "A".into(),
            pattern_id: "infinity-braid".into(),
            layer_pair: None,
            center_via_positions: vec![],
            routed_vias: vec![],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_length_vertical() {
        let seg = CoilSegment { start: (0.0, 0.0), end: (0.0, 20.0), is_active: true };
        assert!((seg.length_mm() - 20.0).abs() < 1e-12);
    }

    #[test]
    fn test_polyline_length() {
        let coil = PhaseCoil {
            segments: vec![
                CoilSegment { start: (0.0, 0.0), end: (0.0, 20.0), is_active: true },
                CoilSegment { start: (0.0, 20.0), end: (10.0, 20.0), is_active: false },
            ],
            ..PhaseCoil::default()
        };
        assert_eq!(coil.polyline().len(), 3);
        assert_eq!(coil.active_conductor_count(), 1);
        assert_eq!(coil.end_turn_segments().len(), 1);
    }

    #[test]
    fn test_is_continuous() {
        let coil = PhaseCoil {
            segments: vec![
                CoilSegment { start: (0.0, 0.0), end: (0.0, 20.0), is_active: true },
                CoilSegment { start: (0.0, 20.0), end: (10.0, 20.0), is_active: false },
            ],
            ..PhaseCoil::default()
        };
        assert!(coil.is_continuous(1e-6));
    }

    #[test]
    fn test_default_pattern_id() {
        assert_eq!(PhaseCoil::default().pattern_id, "infinity-braid");
    }
}
