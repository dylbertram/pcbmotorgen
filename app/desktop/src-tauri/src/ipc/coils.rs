//! IPC coil-geometry DTOs (`CoilSegmentIpc` / `PhaseCoilIpc` / `CoilPathIpc`)
//! and their core `PhaseCoil` → IPC converters.

use serde::{Deserialize, Serialize};

use pcbmotorgen_routing::{
    CoilSegment as CoreCoilSegment, PhaseBandWidth as CorePhaseBandWidth,
    PhaseCoil as CorePhaseCoil, PoleRegion as CorePoleRegion,
    RoutingDimensions as CoreRoutingDimensions,
};

const MM_TO_M: f64 = 1e-3;

// ===========================================================================
// Coil path (generate_coils)
// ===========================================================================

/// One straight segment of a coil path. `start`/`end` are `(x, y)` [m].
/// `is_active` distinguishes active vertical conductors from end-turn
/// connectors (PRODUCT_GOALS.md §5) for SVG colour-coding.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CoilSegmentIpc {
    pub start: [f64; 2],
    pub end: [f64; 2],
    pub is_active: bool,
}

/// One rounded corner / curve of a coil path — a quadratic Bézier
/// `(start, mid, end)` matching KiCad's `(arc ...)` primitive. `mid` is the
/// control point on the arc.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CoilArcIpc {
    pub start: [f64; 2],
    pub mid: [f64; 2],
    pub end: [f64; 2],
    pub is_active: bool,
}

/// A via's exact barrel span. Coordinates are metres, like the preview traces.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CoilViaIpc {
    pub position: [f64; 2],
    pub from_layer: u32,
    pub to_layer: u32,
}

/// A single phase coil on a single PCB layer.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PhaseCoilIpc {
    pub phase_idx: u32,
    pub layer_idx: u32,
    pub phase_name: String,
    pub pattern_id: String,
    pub segments: Vec<CoilSegmentIpc>,
    /// Rounded corners / curves (empty for straight-line-only patterns).
    #[serde(default)]
    pub corner_arcs: Vec<CoilArcIpc>,
    /// Center positions of inter-layer vias on this coil's layer+net, `(x, y)` [m].
    #[serde(default)]
    pub via_positions: Vec<[f64; 2]>,
    /// Authoritative physical spans when present, including an empty list.
    /// Absent only for legacy coils that supply positions without spans.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub routed_vias: Option<Vec<CoilViaIpc>>,
    pub total_length_m: f64,
    pub active_length_m: f64,
    pub end_turn_length_m: f64,
    pub active_conductor_count: u32,
    /// `[min_x, min_y, max_x, max_y]` [m].
    pub bounding_box: [f64; 4],
    pub terminal_start: [f64; 2],
    pub terminal_end: [f64; 2],
}

/// One active trace bundle's calculated effective phase-band width.
///
/// Lengths are metres and `angle_rad` is relative to the direction of travel.
/// `margin_m < 0` means the bundle is wider than the phase band allowed by the
/// pole pitch; the backend reports that condition and does not alter geometry.
///
/// This is the full coil-side conductor bundle width (a phase band), NOT a
/// single-slot width: a slot houses one active leg. The single-leg track
/// width is reported separately as `slot_width_m`.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PhaseBandWidthIpc {
    pub layer: u32,
    pub net: String,
    pub trace_count: u32,
    pub trace_width_m: f64,
    pub trace_spacing_m: f64,
    pub angle_rad: f64,
    pub band_width_m: f64,
    /// Width of the track space housing ONE active leg of this band
    /// (`w_t / sin(theta)` for a single-trace leg). Distinct from the bundle
    /// width `band_width_m`.
    pub slot_width_m: Option<f64>,
    pub max_band_width_m: Option<f64>,
    pub margin_m: Option<f64>,
}

/// Pole/phase dimensions returned with `generate_coils`.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct RoutingDimensionsIpc {
    pub active_area_length_m: f64,
    pub total_routing_length_m: f64,
    pub board_width_m: f64,
    pub phases: u32,
    /// Full mover magnet-array span, when supplied by the config.
    pub magnet_array_span_m: Option<f64>,
    /// Centre-to-centre distance between adjacent north/south poles.
    pub pole_pitch_m: Option<f64>,
    pub period_pitch_m: Option<f64>,
    pub period_count: Option<u32>,
    /// Ideal phase-band pitch (pole_pitch_m / phases, spacing_ratio = 1.0).
    pub phase_band_pitch_m: Option<f64>,
    pub phase_clearance_m: f64,
    pub max_phase_band_width_m: Option<f64>,
    /// Total active leg slots declared by the pattern's leg grid, when known.
    pub slot_count: Option<u32>,
    /// True slot pitch `tau_s = active_area_length_m / slot_count` from the
    /// declared leg grid. Distinct from `phase_band_pitch_m`.
    pub slot_pitch_m: Option<f64>,
    /// Effective leg pitch of braided/slotless patterns:
    /// `pole_pitch_m / (phases x strands)`. Braided patterns have no physical
    /// slots — this is the equivalent leg-pitch model.
    pub interleave_step_m: Option<f64>,
    pub phase_band_widths: Vec<PhaseBandWidthIpc>,
    #[serde(default)]
    pub pole_regions: Vec<PoleRegionIpc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PoleRegionIpc {
    pub phase: String,
    pub pole_index: u32,
    pub start: [f64; 2],
    pub end: [f64; 2],
}

impl Default for RoutingDimensionsIpc {
    fn default() -> Self {
        Self {
            active_area_length_m: 0.0,
            total_routing_length_m: 0.0,
            board_width_m: 0.0,
            phases: 0,
            magnet_array_span_m: None,
            pole_pitch_m: None,
            period_pitch_m: None,
            period_count: None,
            phase_band_pitch_m: None,
            phase_clearance_m: 0.0,
            max_phase_band_width_m: None,
            slot_count: None,
            slot_pitch_m: None,
            interleave_step_m: None,
            phase_band_widths: Vec::new(),
            pole_regions: Vec::new(),
        }
    }
}

/// Complete coil geometry for all phases/layers.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CoilPathIpc {
    pub phases: Vec<PhaseCoilIpc>,
    pub layer_count: u32,
    /// Design dimensions calculated from the same context as the geometry.
    /// This is additive so existing consumers can continue using `phases` and
    /// `layer_count` alone.
    #[serde(default)]
    pub routing_dimensions: RoutingDimensionsIpc,
}

// ===========================================================================
// Geometry conversions (core PhaseCoil → IPC)
// ===========================================================================

#[allow(dead_code)]
impl CoilSegmentIpc {
    /// Convert a core `CoilSegment` (array coords) to the IPC form.
    /// Both already use `[f64; 2]` — this is a 1:1 passthrough.
    pub fn from_core(s: &CoreCoilSegment) -> Self {
        Self {
            start: [s.start.0 * MM_TO_M, s.start.1 * MM_TO_M],
            end: [s.end.0 * MM_TO_M, s.end.1 * MM_TO_M],
            is_active: s.is_active,
        }
    }
}

#[allow(dead_code)]
impl CoilArcIpc {
    /// Convert a core `CoilArc` (tuple coords) to the IPC form.
    pub fn from_core(a: &pcbmotorgen_routing::CoilArc) -> Self {
        Self {
            start: [a.start.0 * MM_TO_M, a.start.1 * MM_TO_M],
            mid: [a.mid.0 * MM_TO_M, a.mid.1 * MM_TO_M],
            end: [a.end.0 * MM_TO_M, a.end.1 * MM_TO_M],
            is_active: a.is_active,
        }
    }
}

#[allow(dead_code)]
impl PhaseCoilIpc {
    /// Convert a core `PhaseCoil` to the IPC wire format.
    pub fn from_core(coil: &CorePhaseCoil) -> Self {
        let segments: Vec<CoilSegmentIpc> =
            coil.segments.iter().map(CoilSegmentIpc::from_core).collect();
        let corner_arcs: Vec<CoilArcIpc> =
            coil.corner_arcs.iter().map(CoilArcIpc::from_core).collect();
        let via_positions: Vec<[f64; 2]> = coil
            .center_via_positions
            .iter()
            .map(|&(x, y)| [x * MM_TO_M, y * MM_TO_M])
            .collect();
        let bbox = coil.bounding_box();
        let routed_vias = (!coil.routed_vias.is_empty() || coil.center_via_positions.is_empty()).then(||
            coil.routed_vias.iter().map(|v| CoilViaIpc {
                position: [v.position.x * MM_TO_M, v.position.y * MM_TO_M],
                from_layer: v.from_layer,
                to_layer: v.to_layer,
            }).collect());
        let terminal_start = coil
            .segments
            .first()
            .map(|s| [s.start.0 * MM_TO_M, s.start.1 * MM_TO_M])
            .unwrap_or([0.0, 0.0]);
        let terminal_end = coil
            .segments
            .last()
            .map(|s| [s.end.0 * MM_TO_M, s.end.1 * MM_TO_M])
            .unwrap_or([0.0, 0.0]);
        Self {
            phase_idx: coil.phase_idx,
            layer_idx: coil.layer_idx,
            phase_name: coil.phase_name.clone(),
            pattern_id: coil.pattern_id.clone(),
            segments,
            corner_arcs,
            via_positions,
            routed_vias,
            total_length_m: coil.total_length_mm() * MM_TO_M,
            active_length_m: coil.active_length_mm() * MM_TO_M,
            end_turn_length_m: coil.end_turn_length_mm() * MM_TO_M,
            active_conductor_count: coil.active_conductor_count() as u32,
            bounding_box: [
                bbox.0 * MM_TO_M,
                bbox.1 * MM_TO_M,
                bbox.2 * MM_TO_M,
                bbox.3 * MM_TO_M,
            ],
            terminal_start,
            terminal_end,
        }
    }
}

#[allow(dead_code)]
impl CoilPathIpc {
    /// Build the IPC coil path and include the dimensions produced by the
    /// routing report.
    pub fn from_core_with_dimensions(
        coils: &[CorePhaseCoil],
        layer_count: u32,
        dimensions: &CoreRoutingDimensions,
    ) -> Self {
        Self {
            phases: coils.iter().map(PhaseCoilIpc::from_core).collect(),
            layer_count,
            routing_dimensions: RoutingDimensionsIpc::from_core(dimensions),
        }
    }
}

impl PhaseBandWidthIpc {
    fn from_core(band: &CorePhaseBandWidth) -> Self {
        Self {
            layer: band.layer,
            net: band.net.clone(),
            trace_count: band.trace_count,
            trace_width_m: band.trace_width_mm * MM_TO_M,
            trace_spacing_m: band.trace_spacing_mm * MM_TO_M,
            angle_rad: band.angle_rad,
            band_width_m: band.band_width_mm * MM_TO_M,
            slot_width_m: band.slot_width_mm.map(|v| v * MM_TO_M),
            max_band_width_m: band.max_band_width_mm.map(|v| v * MM_TO_M),
            margin_m: band.margin_mm.map(|v| v * MM_TO_M),
        }
    }
}

impl RoutingDimensionsIpc {
    fn from_core(dimensions: &CoreRoutingDimensions) -> Self {
        Self {
            active_area_length_m: dimensions.active_area_length_mm * MM_TO_M,
            total_routing_length_m: dimensions.total_routing_length_mm * MM_TO_M,
            board_width_m: dimensions.board_width_mm * MM_TO_M,
            phases: dimensions.phases,
            magnet_array_span_m: dimensions.magnet_array_span_mm.map(|v| v * MM_TO_M),
            pole_pitch_m: dimensions.pole_pitch_mm.map(|v| v * MM_TO_M),
            period_pitch_m: dimensions.period_pitch_mm.map(|v| v * MM_TO_M),
            period_count: dimensions.period_count,
            phase_band_pitch_m: dimensions.phase_band_pitch_mm.map(|v| v * MM_TO_M),
            phase_clearance_m: dimensions.phase_clearance_mm * MM_TO_M,
            max_phase_band_width_m: dimensions.max_phase_band_width_mm.map(|v| v * MM_TO_M),
            slot_count: dimensions.slot_count,
            slot_pitch_m: dimensions.slot_pitch_mm.map(|v| v * MM_TO_M),
            interleave_step_m: dimensions.interleave_step_mm.map(|v| v * MM_TO_M),
            phase_band_widths: dimensions
                .phase_band_widths
                .iter()
                .map(PhaseBandWidthIpc::from_core)
                .collect(),
            pole_regions: dimensions
                .pole_regions
                .iter()
                .map(PoleRegionIpc::from_core)
                .collect(),
        }
    }
}

impl PoleRegionIpc {
    fn from_core(region: &CorePoleRegion) -> Self {
        Self {
            phase: region.phase.clone(),
            pole_index: region.pole_index,
            start: [region.start.x * MM_TO_M, region.start.y * MM_TO_M],
            end: [region.end.x * MM_TO_M, region.end.y * MM_TO_M],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preview_keeps_exact_spans_and_converts_only_coordinates() {
        let mut coil = CorePhaseCoil::default();
        coil.routed_vias = vec![pcbmotorgen_routing::Via {
            position: pcbmotorgen_routing::Point::new(10.0, 5.0),
            from_layer: 0, to_layer: 7, net: "A".into(),
        }];
        coil.center_via_positions = vec![(10.0, 5.0)];
        let dto = PhaseCoilIpc::from_core(&coil);
        assert_eq!(dto.routed_vias, Some(vec![CoilViaIpc {
            position: [0.01, 0.005], from_layer: 0, to_layer: 7,
        }]));
        let json = serde_json::to_value(&dto).unwrap();
        let restored: PhaseCoilIpc = serde_json::from_value(json.clone()).unwrap();
        assert_eq!(restored.routed_vias, dto.routed_vias);
        let mut legacy = json;
        legacy.as_object_mut().unwrap().remove("routed_vias");
        assert!(serde_json::from_value::<PhaseCoilIpc>(legacy).unwrap().routed_vias.is_none());
        coil.routed_vias.clear();
        assert!(PhaseCoilIpc::from_core(&coil).routed_vias.is_none(), "position-only legacy data must retain the fallback");
        coil.center_via_positions.clear();
        assert_eq!(PhaseCoilIpc::from_core(&coil).routed_vias, Some(vec![]));
    }

    #[test]
    fn every_even_braid_via_survives_the_preview_boundary() {
        for layers in [2, 4, 6, 8] {
            let context = pcbmotorgen_routing::RoutingContext {
                active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: layers, phases: 3,
                min_trace_mm: 0.2, trace_width_mm: 0.2, min_space_mm: 0.127,
                magnet_pitch_mm: Some(6.0),
                params: std::collections::HashMap::from([("num_strands".into(), 3.0), ("connection".into(), 2.0)]),
                ..Default::default()
            };
            let routing = pcbmotorgen_routing::generate_routing_result(&context, "infinity-braid").unwrap();
            let coils = pcbmotorgen_routing::routing_result_to_phase_coils(&routing, "infinity-braid");
            let mut actual: Vec<_> = coils.iter().flat_map(|c| {
                PhaseCoilIpc::from_core(c).routed_vias.unwrap().into_iter().map(|v| (
                    c.phase_name.clone(), v.from_layer, v.to_layer,
                    (v.position[0] * 1e9).round() as i64, (v.position[1] * 1e9).round() as i64,
                ))
            }).collect();
            let mut expected: Vec<_> = routing.vias.iter().map(|v| (
                v.net.clone(), v.from_layer, v.to_layer,
                (v.position.x * 1e6).round() as i64, (v.position.y * 1e6).round() as i64,
            )).collect();
            actual.sort(); expected.sort();
            assert_eq!(actual, expected);
        }
    }

    #[test]
    fn routing_mm_is_converted_to_frontend_si() {
        let segment = CoreCoilSegment {
            start: (10.0, 0.0),
            end: (10.0, 20.0),
            is_active: true,
        };
        let dto = CoilSegmentIpc::from_core(&segment);
        assert_eq!(dto.start, [0.01, 0.0]);
        assert_eq!(dto.end, [0.01, 0.02]);

        let dimensions = CoreRoutingDimensions {
            active_area_length_mm: 195.0,
            total_routing_length_mm: 255.0,
            board_width_mm: 20.0,
            magnet_array_span_mm: Some(120.0),
            phases: 3,
            pole_pitch_mm: Some(12.0),
            period_pitch_mm: Some(12.0),
            period_count: Some(20),
            phase_band_pitch_mm: Some(4.0),
            phase_clearance_mm: 0.127,
            max_phase_band_width_mm: Some(3.873),
            slot_count: Some(975),
            slot_pitch_mm: Some(0.8),
            interleave_step_mm: Some(0.8),
            phase_band_widths: vec![],
            phase_bands: vec![],
            pole_regions: vec![CorePoleRegion {
                phase: "A".to_string(),
                pole_index: 2,
                start: pcbmotorgen_routing::Point::new(0.0, 10.0),
                end: pcbmotorgen_routing::Point::new(12.0, 10.0),
            }],
        };
        // Per-band conversion includes the single-leg slot width (mm -> m).
        let band = CorePhaseBandWidth {
            layer: 0,
            net: "A".to_string(),
            trace_count: 5,
            trace_width_mm: 0.127,
            trace_spacing_mm: 0.127,
            angle_rad: 1.030377,
            band_width_mm: 1.333,
            slot_width_mm: Some(0.148),
            max_band_width_mm: Some(3.873),
            margin_mm: Some(2.54),
        };
        let band_wire = PhaseBandWidthIpc::from_core(&band);
        assert_eq!(band_wire.band_width_m, 0.001333);
        assert_eq!(band_wire.slot_width_m, Some(0.000148));
        assert_eq!(band_wire.margin_m, Some(0.00254));

        let wire = RoutingDimensionsIpc::from_core(&dimensions);
        assert_eq!(wire.active_area_length_m, 0.195);
        assert_eq!(wire.pole_pitch_m, Some(0.012));
        assert_eq!(wire.phase_clearance_m, 0.000127);
        assert_eq!(wire.slot_count, Some(975));
        assert_eq!(wire.slot_pitch_m, Some(0.0008));
        assert_eq!(wire.interleave_step_m, Some(0.0008));
        assert_eq!(wire.pole_regions.len(), 1);
        assert_eq!(wire.pole_regions[0].phase, "A");
        assert_eq!(wire.pole_regions[0].pole_index, 2);
        assert_eq!(wire.pole_regions[0].start, [0.0, 0.01]);
        assert_eq!(wire.pole_regions[0].end, [0.012, 0.01]);
    }
}
