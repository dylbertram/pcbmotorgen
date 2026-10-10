//! Canonical output shape for routing patterns.
//!
//! Every routing pattern — bundled, Rust crate plugin, or Python runner — must
//! ultimately produce one [`RoutingResult`] conforming to this strict serde
//! model. Units are millimetres, x = travel axis, y = across board width.
//!
//! # Contract versioning
//!
//! `RoutingResult.format_version` identifies the wire contract that produced
//! the document. It defaults to [`FORMAT_VERSION`] when absent for runners
//! authored against the current millimetre contract.
//! Adding fields to this model is non-breaking (additive); removing or
//! reinterpreting a field, or changing the coordinate/unit conventions, is
//! breaking and MUST bump `FORMAT_VERSION`. See `docs/routing-pattern-handoff.md`.

//! IO (connector/IC pads + terminal fanout traces) is one such additive
//! extension — see [`crate::io`].

use crate::io::{IoPad, IoTrace};
use serde::{Deserialize, Serialize};

/// The current routing handoff contract version (see `model.rs` docs).
pub const FORMAT_VERSION: u32 = 2;

fn default_format_version() -> u32 {
    FORMAT_VERSION
}

/// A 2D point in millimetres.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    /// Euclidean distance to another point [mm].
    pub fn distance_to(&self, other: Point) -> f64 {
        let dx = other.x - self.x;
        let dy = other.y - self.y;
        (dx * dx + dy * dy).sqrt()
    }
}

/// Index into the board's copper stack `[0, num_layers)`.
pub type Layer = u32;

/// A phase net label (e.g. `"A"`, `"B"`, `"C"`). The writer prefixes `/`.
pub type Net = String;

/// One straight trace element.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RouteSegment {
    pub start: Point,
    pub end: Point,
    pub layer: Layer,
    pub net: Net,
    /// Active force-producing conductor (`true`) vs end-turn (`false`).
    pub is_active: bool,
}

/// One arc (rounded corner / curve) — maps to KiCad's `(arc start mid end)`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RouteCurve {
    pub start: Point,
    pub mid: Point,
    pub end: Point,
    pub layer: Layer,
    pub net: Net,
    pub is_active: bool,
}

/// One via / inter-layer connection.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Via {
    pub position: Point,
    pub from_layer: Layer,
    pub to_layer: Layer,
    pub net: Net,
}

/// One pole-pitch region assigned by a routing pattern to a phase.
///
/// These boundaries are pattern-owned: different routing algorithms may use
/// completely different geometry to determine where a phase's pole region
/// starts and ends. Coordinates are in millimetres.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PoleRegion {
    /// Phase/net label associated with this region.
    pub phase: Net,
    /// Zero-based pole-pitch index within the phase.
    pub pole_index: u32,
    pub start: Point,
    pub end: Point,
}

/// Pattern-declared leg grid: the equivalent slot model of the pattern's
/// generated active legs (glossary "Slot" — a slot houses ONE active leg).
///
/// Patterns whose active legs populate a regular grid declare it here so the
/// host can report true per-slot quantities (`slot_count`, `slot_pitch_mm`,
/// `interleave_step_mm`) alongside the phase-band metrics. The declaration is
/// optional metadata; a pattern without a regular leg grid (or a legacy
/// payload) omits it and the derived slot fields stay `None`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LegGrid {
    /// Total number of active leg slots the pattern declares along the stator
    /// track (`N_slots` in `tau_s = L_stator / N_slots`).
    pub slot_count: u32,
    /// Number of parallel strands the pattern interleaves per leg-grid
    /// position (the braid's `num_strands`). Used to derive the effective leg
    /// pitch `interleave_step_mm = tau_p / (phases × strands_per_leg)`. For
    /// braided slotless patterns each strand is its own active leg, so the
    /// per-record `slot_width_mm` stays the single-trace width.
    #[serde(default)]
    pub strands_per_leg: Option<u32>,
}

/// How a declared phase band occupies its across-travel (y) extent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PhaseBandShape {
    /// Straight band: active legs cross the y-extent at a fixed angle
    /// (e.g. a serpentine winding).
    Linear,
    /// Braided weave: the band's strands cross each other over the y-extent
    /// (e.g. the infinity braid's diamonds).
    Braided,
}

/// Pattern-declared phase-band geometry for one `(layer, net)` group (kata
/// hzs2): the first-class position + shape contract that simulation
/// commutation and equilibrium read.
///
/// This is the position/shape counterpart of the host-calculated
/// [`PhaseBandWidth`](crate::dimensions::PhaseBandWidth) budget record: the
/// pattern declares WHERE its phase band sits, the host derives how wide the
/// conductor bundle is. Declaring is optional metadata; a pattern without a
/// declaration gets host-derived bands in the dimension sidecar
/// (`RoutingDimensions.phase_bands`, marked `derived`), built from the ideal
/// phase-band pitch `tau_p / phases`.
///
/// All coordinates are millimetres, x = travel axis.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PhaseBand {
    /// Copper layer carrying this band.
    pub layer: Layer,
    /// Phase/net label carrying this band.
    pub net: Net,
    /// Centerline x of the band's first repeating instance [mm] — the phase
    /// reference position. Consumers derive the per-phase electrical offsets
    /// from the centerline distances to the reference phase (glossary
    /// "Commutation": offset = pi · dx / tau_p). For a band laid out as a
    /// single instance this is the band's own centerline.
    pub centerline_x_mm: f64,
    /// Along-travel extent start [mm], as the pattern lays the band out.
    /// For a repeating layout this spans all repeats of the band.
    pub start_x_mm: f64,
    /// Along-travel extent end [mm]; must be greater than `start_x_mm`.
    pub end_x_mm: f64,
    /// Across-travel extent lower bound [mm].
    pub y_min_mm: f64,
    /// Across-travel extent upper bound [mm]; must be greater than `y_min_mm`.
    pub y_max_mm: f64,
    /// How the band occupies its y-extent.
    pub shape: PhaseBandShape,
}

/// The complete geometry a routing pattern produces for a board.
///
/// All elements carry their own `layer` and `net` — the pattern owns layer
/// semantics.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoutingResult {
    /// Wire-contract version (see module docs). Defaults to [`FORMAT_VERSION`]
    /// when the field is absent in serialized JSON.
    #[serde(default = "default_format_version")]
    pub format_version: u32,
    pub segments: Vec<RouteSegment>,
    pub curves: Vec<RouteCurve>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub splines: Vec<crate::RouteSpline>,
    pub vias: Vec<Via>,
    /// Pattern-defined pole regions, one entry per phase and pole pitch.
    #[serde(default)]
    pub pole_regions: Vec<PoleRegion>,
    /// Optional pattern-declared leg grid (equivalent slot model of the
    /// generated active legs). Additive; absent for legacy payloads.
    #[serde(default)]
    pub leg_grid: Option<LegGrid>,
    /// Pattern-declared phase-band geometry, one record per `(layer, net)`
    /// band (kata hzs2). Additive; absent for legacy payloads. When empty,
    /// the host derives bands from the ideal phase-band pitch and marks them
    /// as derived in the dimension sidecar.
    #[serde(default)]
    pub phase_bands: Vec<PhaseBand>,
    /// Connector/IC pads the pattern declares for IO routing (additive;
    /// empty for legacy payloads and non-IO patterns). See [`IoPad`].
    #[serde(default)]
    pub io_pads: Vec<IoPad>,
    /// IO fanout traces connecting coil terminals to IO pads (additive;
    /// empty for legacy payloads and non-IO patterns). See [`IoTrace`].
    #[serde(default)]
    pub io_traces: Vec<IoTrace>,
}

impl Default for RoutingResult {
    fn default() -> Self {
        Self {
            format_version: FORMAT_VERSION,
            segments: Vec::new(),
            curves: Vec::new(),
            splines: Vec::new(),
            vias: Vec::new(),
            pole_regions: Vec::new(),
            leg_grid: None,
            phase_bands: Vec::new(),
            io_pads: Vec::new(),
            io_traces: Vec::new(),
        }
    }
}

impl RoutingResult {
    pub fn is_empty(&self) -> bool {
        self.segments.is_empty()
            && self.curves.is_empty()
            && self.splines.is_empty()
            && self.vias.is_empty()
            && self.io_pads.is_empty()
            && self.io_traces.is_empty()
    }

    /// Total number of geometric elements (segments, curves, vias, IO pads,
    /// and IO traces).
    pub fn element_count(&self) -> usize {
        self.segments.len()
            + self.curves.len()
            + self.splines.len()
            + self.vias.len()
            + self.io_pads.len()
            + self.io_traces.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_result_is_format_version_2() {
        let r = RoutingResult::default();
        assert_eq!(r.format_version, FORMAT_VERSION);
        assert!(r.is_empty());
    }

    #[test]
    fn absent_format_version_defaults_to_current() {
        // Python runners may omit `format_version`; the current contract is
        // selected by the serde default.
        let json = r#"{"segments": [], "curves": [], "vias": []}"#;
        let r: RoutingResult = serde_json::from_str(json).expect("valid result JSON");
        assert_eq!(r.format_version, FORMAT_VERSION);
    }

    #[test]
    fn absent_leg_grid_defaults_to_none_and_declared_grid_round_trips() {
        // Legacy payloads without the additive `leg_grid` field deserialize.
        let json = r#"{"segments": [], "curves": [], "vias": []}"#;
        let r: RoutingResult = serde_json::from_str(json).expect("legacy result JSON");
        assert_eq!(r.leg_grid, None);

        let declared = RoutingResult {
            leg_grid: Some(LegGrid {
                slot_count: 975,
                strands_per_leg: Some(5),
            }),
            ..RoutingResult::default()
        };
        let json = serde_json::to_string(&declared).expect("serialize");
        assert!(json.contains("\"slot_count\":975"));
        let back: RoutingResult = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back, declared);
    }

    #[test]
    fn absent_phase_bands_default_to_empty_and_declared_bands_round_trip() {
        // Legacy payloads without the additive `phase_bands` field.
        let json = r#"{"segments": [], "curves": [], "vias": []}"#;
        let r: RoutingResult = serde_json::from_str(json).expect("legacy result JSON");
        assert!(r.phase_bands.is_empty());

        let declared = RoutingResult {
            phase_bands: vec![
                PhaseBand {
                    layer: 0,
                    net: "A".into(),
                    centerline_x_mm: 2.0,
                    start_x_mm: 0.0,
                    end_x_mm: 4.0,
                    y_min_mm: 0.0,
                    y_max_mm: 20.0,
                    shape: PhaseBandShape::Linear,
                },
                PhaseBand {
                    layer: 0,
                    net: "B".into(),
                    centerline_x_mm: 6.0,
                    start_x_mm: 4.0,
                    end_x_mm: 8.0,
                    y_min_mm: 0.0,
                    y_max_mm: 20.0,
                    shape: PhaseBandShape::Braided,
                },
            ],
            ..RoutingResult::default()
        };
        let json = serde_json::to_string(&declared).expect("serialize");
        assert!(json.contains("\"centerline_x_mm\":2.0"));
        assert!(json.contains("\"shape\":\"braided\""));
        let back: RoutingResult = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back, declared);
    }

    #[test]
    fn format_version_round_trips() {
        let r = RoutingResult::default();
        let json = serde_json::to_string(&r).expect("serialize");
        assert!(json.contains("\"format_version\":2"));
        let back: RoutingResult = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back, r);
    }

    #[test]
    fn arc_serialization_keeps_is_active_with_default() {
        // Arc without is_active (older serialized coil) defaults to false.
        let json = r#"{"start": [0.0, 0.0], "mid": [1.0, 1.0], "end": [2.0, 0.0]}"#;
        let arc: crate::coil::CoilArc = serde_json::from_str(json).expect("valid arc");
        assert!(!arc.is_active);
    }
}
