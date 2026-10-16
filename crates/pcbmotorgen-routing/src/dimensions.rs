//! Board-to-magnet dimensions reported alongside generated routing geometry.
//!
//! A [`RoutingResult`] deliberately contains only raw
//! geometry.  Consumers that need to place or evaluate the mover also need the
//! dimensions that gave that geometry meaning: the centre-to-centre pole pitch
//! and the width of each active conductor band (phase band).  This module owns those
//! calculations so the application, Python runners, and native plugins all use
//! the same equations.
//!
//! Alongside the phase-band quantities, patterns that declare a
//! [`LegGrid`](crate::model::LegGrid) on their result get true per-slot
//! metrics: the single-leg slot width, the slot pitch
//! `tau_s = L_stator / N_slots`, and the braided-pattern interleave step
//! `tau_p / (phases × strands)`. A slot houses ONE active leg — never a whole
//! coil bundle (glossary "Slot").
//!
//! All lengths are millimetres.  `angle_rad` is measured from the direction of
//! motion (the x axis).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::context::RoutingContext;
use crate::error::{RoutingError, RoutingErrorKind};
use crate::model::{Layer, PhaseBand, PhaseBandShape, Point, PoleRegion, RoutingResult};

const EPS: f64 = 1e-12;

/// A calculated active-conductor band for one `(layer, net)` group.
///
/// The band width is calculated from the perpendicular bundle thickness and
/// the trace angle:
///
/// `band_width = (N * trace_width + (N - 1) * trace_spacing) / sin(theta)`
///
/// `max_band_width_mm` is the top-down phase-band limit when a pole pitch is
/// available.  A negative `margin_mm` means the trace bundle does not fit in the
/// available phase band; geometry is never silently shortened to make it fit.
///
/// Alongside the band (bundle) width, each record reports the glossary-exact
/// `slot_width_mm`: the along-travel width of the track space housing **one
/// active leg**, which is a different quantity from the bundle width (a slot
/// houses a single leg, never the whole coil bundle).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PhaseBandWidth {
    /// Copper layer carrying this band.
    pub layer: Layer,
    /// Phase/net label carrying this band.
    pub net: String,
    /// Number of parallel strands (conductors) in the coil-side bundle (`N`).
    pub trace_count: u32,
    /// Width of one trace (`w_t`) [mm].
    pub trace_width_mm: f64,
    /// Clearance between adjacent traces (`s`) [mm].
    pub trace_spacing_mm: f64,
    /// Trace angle relative to the x/travel axis (`theta`) [rad].
    pub angle_rad: f64,
    /// Effective band width measured along the travel axis (`w_s`) [mm].
    pub band_width_mm: f64,
    /// Width of the track space housing one active leg of this band [mm].
    ///
    /// Glossary "Slot Width": for a single-trace leg this is
    /// `w_t / sin(theta)` (`slot_width_from_leg_geometry_mm` with `k = 1`).
    /// When a pattern's leg bundles `k` parallel strands into one leg, the leg
    /// width is `(k * w_t + (k - 1) * s) / sin(theta)` — use
    /// [`slot_width_from_leg_geometry_mm`] with the pattern's `k` in that case.
    /// This record always reports the single-trace leg width.
    #[serde(default)]
    pub slot_width_mm: Option<f64>,
    /// Maximum width allowed by the pole pitch and phase count [mm].
    #[serde(default)]
    pub max_band_width_mm: Option<f64>,
    /// `max_band_width_mm - band_width_mm`, when a pole pitch is known [mm].
    #[serde(default)]
    pub margin_mm: Option<f64>,
}

/// One resolved phase-band record in the [`RoutingDimensions`] sidecar.
///
/// Either the pattern's declared [`PhaseBand`] (copied verbatim,
/// `derived = false`) or a host-derived band built from the ideal phase-band
/// pitch `tau_p / phases` (`derived = true`) when the pattern declares none.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResolvedPhaseBand {
    /// The band geometry (declaration or host derivation).
    #[serde(flatten)]
    pub band: PhaseBand,
    /// True when the host derived this band from the ideal phase-band pitch
    /// because the pattern declared no bands.
    #[serde(default)]
    pub derived: bool,
}

/// Dimensions needed to hand generated traces off to magnet-pattern and
/// analysis code.
///
/// `pole_pitch_mm` is the centre-to-centre distance between adjacent north and
/// south poles (`tau_p` in the design equation).  `phase_band_pitch_mm` is the
/// ideal phase-band pitch `tau_p / phases`; it is intentionally separate from
/// the calculated conductor-band width in [`PhaseBandWidth::band_width_mm`].
///
/// Alongside the phase-band metrics, the optional pattern-declared
/// [`LegGrid`](crate::model::LegGrid) (see `RoutingResult::leg_grid`) drives
/// the true per-slot quantities: `slot_count`, `slot_pitch_mm`
/// (`tau_s = L_stator / N_slots`), and the braided-pattern effective leg pitch
/// `interleave_step_mm = tau_p / (phases × strands)`. They are `None` when the
/// pattern does not declare a leg grid.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RoutingDimensions {
    /// Active-area length supplied by the board context [mm].
    pub active_area_length_mm: f64,
    /// Total routable length [mm]. The routing domain equals the active
    /// area — there is no end padding.
    pub total_routing_length_mm: f64,
    /// Board width perpendicular to travel [mm].
    pub board_width_mm: f64,
    /// Full mover magnet-array span supplied by the core [mm], when known.
    /// Together with `pole_pitch_mm` this lets a consumer recover the number of
    /// pole intervals without reaching back into the application config.
    #[serde(default)]
    pub magnet_array_span_mm: Option<f64>,
    /// Number of electrical phases used for the phase-band calculation.
    pub phases: u32,
    /// Centre-to-centre adjacent-pole distance (`tau_p`) [mm].
    #[serde(default)]
    pub pole_pitch_mm: Option<f64>,
    /// Repeating routing period [mm].  For the magnet-aware infinity braid this
    /// equals `pole_pitch_mm`; it is optional for patterns without a repeating
    /// unit.
    #[serde(default)]
    pub period_pitch_mm: Option<f64>,
    /// Number of complete repeating periods emitted by a pattern, when known.
    #[serde(default)]
    pub period_count: Option<u32>,
    /// Ideal phase-band pitch (pole_pitch / phases, i.e. spacing_ratio = 1.0) [mm].
    ///
    /// Distinct from the true slot pitch `slot_pitch_mm`: `tau_p / phases`
    /// equals `tau_s` only for uniform 1-slot-per-pole-per-phase windings.
    #[serde(default)]
    pub phase_band_pitch_mm: Option<f64>,
    /// Inter-phase clearance `g_phase` used for `max_phase_band_width_mm` [mm].
    ///
    /// Resolved from `RoutingContext.phase_clearance_mm`; when the context
    /// does not set it, the context's `min_space_mm` is used as a documented
    /// fallback (docs/API.md §10.1).
    pub phase_clearance_mm: f64,
    /// Maximum phase-band width (pole_pitch / phases − g_phase) [mm].
    #[serde(default)]
    pub max_phase_band_width_mm: Option<f64>,
    /// Total number of active leg slots declared by the pattern's leg grid
    /// (`N_slots`), when the pattern declares one [mm-independent].
    #[serde(default)]
    pub slot_count: Option<u32>,
    /// True slot pitch `tau_s = L_stator / N_slots` from the declared leg grid
    /// [mm].  Glossary "Slot Pitch": the centreline distance between
    /// consecutive conductor slots along the stator track.  For braided
    /// slotless patterns see also `interleave_step_mm`.
    #[serde(default)]
    pub slot_pitch_mm: Option<f64>,
    /// Effective leg pitch of braided/slotless patterns:
    /// `tau_p / (phases × strands)` from the declared leg grid [mm].
    ///
    /// Braided slotless patterns have no physical slots — this is the
    /// equivalent leg-pitch model of their interleaved trace layout (glossary
    /// "Slot Pitch", disambiguation).
    #[serde(default)]
    pub interleave_step_mm: Option<f64>,
    /// One calculated band for each active `(layer, net)` group.
    #[serde(default)]
    pub phase_band_widths: Vec<PhaseBandWidth>,
    /// Pattern-defined pole regions copied from the canonical result.
    #[serde(default)]
    pub pole_regions: Vec<PoleRegion>,
    /// Resolved per-`(layer, net)` phase-band geometry (kata hzs2): the
    /// pattern's declared bands, or host-derived bands from the ideal
    /// phase-band pitch `tau_p / phases` when the pattern declares none
    /// (those are marked `derived`). Empty when there is no pole pitch and
    /// no declaration.
    #[serde(default)]
    pub phase_bands: Vec<ResolvedPhaseBand>,
}

impl Default for RoutingDimensions {
    fn default() -> Self {
        Self {
            active_area_length_mm: 0.0,
            total_routing_length_mm: 0.0,
            board_width_mm: 0.0,
            magnet_array_span_mm: None,
            phases: 0,
            pole_pitch_mm: None,
            period_pitch_mm: None,
            period_count: None,
            phase_band_pitch_mm: None,
            phase_clearance_mm: 0.0,
            max_phase_band_width_mm: None,
            slot_count: None,
            slot_pitch_mm: None,
            interleave_step_mm: None,
            phase_band_widths: Vec::new(),
            pole_regions: Vec::new(),
            phase_bands: Vec::new(),
        }
    }
}

impl RoutingDimensions {
    /// Calculate dimensions from a generic routing result.
    ///
    /// Generic patterns may expose a `num_strands` or `trace_count` parameter.
    /// The first present value is used as the trace count for the returned
    /// phase-band width records; otherwise one trace is reported.  (Whole-coil
    /// winding counts such as `turns` are deliberately NOT accepted: they are
    /// not per-bundle strand counts and feeding them into
    /// the width equation silently reported wrong bands.)  A pattern that has
    /// no pole pitch still gets the bottom-up phase-band width calculation,
    /// but no top-down maximum can be reported.  Slot metrics
    /// (`slot_count` / `slot_pitch_mm` / `interleave_step_mm`) require the
    /// pattern to declare a leg grid on the result; without one they stay
    /// `None`.
    pub fn from_result(result: &RoutingResult, ctx: &RoutingContext) -> Result<Self, RoutingError> {
        let trace_count = trace_count_hint(ctx);
        Self::from_result_with_options(result, ctx, trace_count, None, None, None)
    }

    /// Build the dimensions for the bundled infinity braid.
    ///
    /// The diamond edge angle is known from the board width and the repeating
    /// period, so it is not estimated from an arbitrary crossing segment.  If
    /// a magnet layout is present, the period is the pole pitch exactly.
    pub fn for_infinity(
        result: &RoutingResult,
        ctx: &RoutingContext,
        trace_count: u32,
        period_pitch_mm: Option<f64>,
        period_count: Option<u32>,
    ) -> Result<Self, RoutingError> {
        let angle = period_pitch_mm.map(|period| (ctx.board_width_mm / period).atan());
        Self::from_result_with_options(
            result,
            ctx,
            trace_count,
            angle,
            period_pitch_mm,
            period_count,
        )
    }

    /// Return true when every calculated phase band fits.
    pub fn all_phase_bands_fit(&self) -> bool {
        self.phase_band_widths
            .iter()
            .all(|band| band.margin_mm.map(|margin| margin >= -EPS).unwrap_or(true))
    }

    /// Centre-to-centre adjacent North/South pole distance, using the motor
    /// design terminology requested by magnet-pattern consumers.
    pub fn pole_to_pole_pitch_mm(&self) -> Option<f64> {
        self.pole_pitch_mm
    }

    fn from_result_with_options(
        result: &RoutingResult,
        ctx: &RoutingContext,
        trace_count: u32,
        angle_override_rad: Option<f64>,
        period_pitch_mm: Option<f64>,
        period_count: Option<u32>,
    ) -> Result<Self, RoutingError> {
        validate_context_dimensions(ctx)?;
        if trace_count == 0 {
            return Err(dimension_error(
                "dimensions.trace_count",
                "trace count N must be at least 1",
            ));
        }

        let phases = ctx.phases.max(1);
        let pole_pitch_mm = resolved_pole_pitch_mm(ctx)?;
        let phase_band_pitch_mm = pole_pitch_mm.map(|pitch| pitch / phases as f64);
        // Explicit inter-phase clearance `g_phase`. When the context does not
        // set `phase_clearance_mm`, the trace-to-trace clearance is used as a
        // documented compatibility fallback (docs/API.md §10.1) — this keeps
        // legacy contexts byte-identical while making the reuse visible here.
        let phase_clearance_mm = ctx.phase_clearance_mm.unwrap_or(ctx.min_space_mm);
        let max_phase_band_width_mm = phase_band_pitch_mm.map(|pitch| pitch - phase_clearance_mm);

        let (slot_count, slot_pitch_mm, interleave_step_mm) =
            declared_slot_metrics(result, ctx, pole_pitch_mm, phases);

        let groups = collect_active_paths(result);
        let phase_bands =
            resolve_phase_bands(result, &groups, phase_band_pitch_mm, ctx.board_width_mm);
        let phase_band_widths = phase_band_records(
            groups,
            ctx,
            trace_count,
            angle_override_rad,
            max_phase_band_width_mm,
        )?;

        Ok(Self {
            active_area_length_mm: ctx.active_area_length_mm,
            total_routing_length_mm: ctx.active_area_length_mm,
            board_width_mm: ctx.board_width_mm,
            magnet_array_span_mm: ctx.magnet_array_span(),
            phases,
            pole_pitch_mm,
            period_pitch_mm,
            period_count,
            phase_band_pitch_mm,
            phase_clearance_mm,
            max_phase_band_width_mm,
            slot_count,
            slot_pitch_mm,
            interleave_step_mm,
            phase_band_widths,
            pole_regions: result.pole_regions.clone(),
            phase_bands,
        })
    }
}

/// Resolve the sidecar phase-band records for a result.
///
/// Declared bands (`RoutingResult.phase_bands`) are copied verbatim and
/// marked `derived = false`. When the pattern declares none, the host derives
/// one band per active `(layer, net)` group from the ideal phase-band pitch
/// `tau_band = tau_p / phases` (glossary "Phase Band"): the group's net takes
/// phase slot `p` — its index among the distinct active nets — with extent
/// `[p · tau_band, (p + 1) · tau_band]`, centerline `p · tau_band + tau_band / 2`,
/// the full board width as y-extent, and a linear shape. Derived records are
/// marked `derived = true`. Without a pole pitch there is nothing to derive
/// from and the sidecar stays empty.
fn resolve_phase_bands(
    result: &RoutingResult,
    groups: &BTreeMap<(Layer, String), Vec<(Point, Point)>>,
    phase_band_pitch_mm: Option<f64>,
    board_width_mm: f64,
) -> Vec<ResolvedPhaseBand> {
    if !result.phase_bands.is_empty() {
        return result
            .phase_bands
            .iter()
            .map(|band| ResolvedPhaseBand {
                band: band.clone(),
                derived: false,
            })
            .collect();
    }
    let Some(pitch) = phase_band_pitch_mm else {
        return Vec::new();
    };
    let nets: Vec<&str> = {
        let mut sorted: Vec<&str> = groups.keys().map(|(_, net)| net.as_str()).collect();
        sorted.sort_unstable();
        sorted.dedup();
        sorted
    };
    groups
        .keys()
        .map(|(layer, net)| {
            let slot = nets.iter().position(|candidate| *candidate == net.as_str()).unwrap_or(0);
            let start_x = slot as f64 * pitch;
            ResolvedPhaseBand {
                band: PhaseBand {
                    layer: *layer,
                    net: net.clone(),
                    centerline_x_mm: start_x + pitch / 2.0,
                    start_x_mm: start_x,
                    end_x_mm: start_x + pitch,
                    y_min_mm: 0.0,
                    y_max_mm: board_width_mm,
                    shape: PhaseBandShape::Linear,
                },
                derived: true,
            }
        })
        .collect()
}

/// Validated pole pitch from the context: `None` when the context carries no
/// magnet layout, an error when the pitch is present but not finite/positive.
fn resolved_pole_pitch_mm(ctx: &RoutingContext) -> Result<Option<f64>, RoutingError> {
    match ctx.magnet_pitch_mm {
        Some(pitch) if pitch.is_finite() && pitch > 0.0 => Ok(Some(pitch)),
        Some(_) => Err(dimension_error(
            "context.magnet_pitch_mm",
            "pole pitch must be finite and greater than zero",
        )),
        None => Ok(None),
    }
}

/// Slot metrics derived from the pattern-declared leg grid: `(slot_count,
/// slot_pitch_mm, interleave_step_mm)`.
///
/// Without a declaration — or with a malformed one (zero slot count / strand
/// count) — these degrade to `None` instead of failing generation, because
/// the grid is optional metadata.
fn declared_slot_metrics(
    result: &RoutingResult,
    ctx: &RoutingContext,
    pole_pitch_mm: Option<f64>,
    phases: u32,
) -> (Option<u32>, Option<f64>, Option<f64>) {
    let leg_grid = result.leg_grid.as_ref();
    let slot_count = leg_grid.map(|grid| grid.slot_count);
    let slot_pitch_mm = slot_count
        .and_then(|slots| slot_pitch_from_leg_grid_mm(ctx.active_area_length_mm, slots).ok());
    let interleave_step_mm = leg_grid
        .and_then(|grid| grid.strands_per_leg)
        .filter(|strands| *strands >= 1)
        .and_then(|strands| {
            pole_pitch_mm.map(|pitch| pitch / (phases as f64 * strands as f64))
        });
    (slot_count, slot_pitch_mm, interleave_step_mm)
}

/// Group active segments and curves by `(layer, net)`, preserving per-group
/// emission order.
fn collect_active_paths(
    result: &RoutingResult,
) -> BTreeMap<(Layer, String), Vec<(Point, Point)>> {
    let mut groups: BTreeMap<(Layer, String), Vec<(Point, Point)>> = BTreeMap::new();
    for segment in result.segments.iter().filter(|segment| segment.is_active) {
        groups
            .entry((segment.layer, segment.net.clone()))
            .or_default()
            .push((segment.start, segment.end));
    }
    for curve in result.curves.iter().filter(|curve| curve.is_active) {
        groups
            .entry((curve.layer, curve.net.clone()))
            .or_default()
            .push((curve.start, curve.end));
    }
    groups
}

/// One [`PhaseBandWidth`] per `(layer, net)` group.
///
/// The trace angle comes from the override or the first path that yields one;
/// geometry parallel to the travel axis is an error because its projected
/// band width is undefined (division by `sin(theta)`).
fn phase_band_records(
    groups: BTreeMap<(Layer, String), Vec<(Point, Point)>>,
    ctx: &RoutingContext,
    trace_count: u32,
    angle_override_rad: Option<f64>,
    max_phase_band_width_mm: Option<f64>,
) -> Result<Vec<PhaseBandWidth>, RoutingError> {
    let mut records = Vec::with_capacity(groups.len());
    for ((layer, net), paths) in groups {
        let angle_rad = angle_override_rad
            .or_else(|| paths.iter().find_map(|(start, end)| path_angle(*start, *end)))
            .ok_or_else(|| {
                dimension_error(
                    "dimensions.phase_band_widths.angle_rad",
                    format!(
                        "cannot calculate a trace angle for layer {} net {}: active geometry is parallel to the travel axis",
                        layer, net
                    ),
                )
            })?;
        let band_width_mm = phase_band_width_from_trace_geometry_mm(
            trace_count,
            ctx.trace_width(),
            ctx.min_space_mm,
            angle_rad,
        )
        .map_err(|message| dimension_error("dimensions.phase_band_widths.band_width_mm", message))?;
        // Glossary-exact per-slot width: a slot houses ONE active leg. The
        // record reports the single-trace leg width (`k = 1`); callers
        // whose legs bundle `k` parallel strands use
        // `slot_width_from_leg_geometry_mm(k, ...)` directly.
        let slot_width_mm =
            slot_width_from_leg_geometry_mm(1, ctx.trace_width(), ctx.min_space_mm, angle_rad)
                .map_err(|message| {
                    dimension_error("dimensions.phase_band_widths.slot_width_mm", message)
                })?;
        let margin_mm = max_phase_band_width_mm.map(|max| max - band_width_mm);
        records.push(PhaseBandWidth {
            layer,
            net,
            trace_count,
            trace_width_mm: ctx.trace_width(),
            trace_spacing_mm: ctx.min_space_mm,
            angle_rad,
            band_width_mm,
            slot_width_mm: Some(slot_width_mm),
            max_band_width_mm: max_phase_band_width_mm,
            margin_mm,
        });
    }
    Ok(records)
}

/// Bottom-up phase-band width equation.
///
/// `theta_rad` is the angle between the trace and the direction of motion.
/// The function rejects an angle parallel to the motion because its projected
/// band width is undefined (division by `sin(theta)`).
pub fn phase_band_width_from_trace_geometry_mm(
    trace_count: u32,
    trace_width_mm: f64,
    trace_spacing_mm: f64,
    theta_rad: f64,
) -> Result<f64, String> {
    if trace_count == 0 {
        return Err("trace count N must be at least 1".to_string());
    }
    if !trace_width_mm.is_finite() || trace_width_mm <= 0.0 {
        return Err("trace width w_t must be finite and greater than zero".to_string());
    }
    if !trace_spacing_mm.is_finite() || trace_spacing_mm < 0.0 {
        return Err("trace spacing s must be finite and non-negative".to_string());
    }
    if !theta_rad.is_finite() {
        return Err("trace angle theta must be finite".to_string());
    }

    let sin_theta = theta_rad.sin().abs();
    if sin_theta <= EPS {
        return Err(
            "trace angle theta must not be parallel to the travel axis (sin(theta) is zero)"
                .to_string(),
        );
    }

    let perpendicular_bundle_width = trace_count as f64 * trace_width_mm
        + (trace_count.saturating_sub(1) as f64) * trace_spacing_mm;
    Ok(perpendicular_bundle_width / sin_theta)
}

/// Top-down maximum phase-band width equation:
///
/// `max_phase_band_width = pole_pitch / phases - phase_clearance`.
pub fn max_phase_band_width_from_pole_pitch_mm(
    pole_pitch_mm: f64,
    phases: u32,
    phase_clearance_mm: f64,
) -> Result<f64, String> {
    if !pole_pitch_mm.is_finite() || pole_pitch_mm <= 0.0 {
        return Err("pole pitch tau_p must be finite and greater than zero".to_string());
    }
    if phases == 0 {
        return Err("phase count m must be at least 1".to_string());
    }
    if !phase_clearance_mm.is_finite() || phase_clearance_mm < 0.0 {
        return Err("phase clearance g_phase must be finite and non-negative".to_string());
    }
    Ok(pole_pitch_mm / phases as f64 - phase_clearance_mm)
}

/// Bottom-up single-leg slot width equation (glossary "Slot Width").
///
/// `k` is the number of parallel strands bundled in one active leg (`k = 1` is
/// a single trace), `w_t` the trace width, `s` the clearance between bundled
/// strands, and `theta_rad` the leg angle from the travel direction:
///
/// `slot_width = (k * w_t + (k - 1) * s) / sin(theta)`
///
/// A slot houses ONE active leg — never the full phase band, the electrical
/// period, or the slot pitch. The function rejects `k = 0`, non-finite
/// inputs, and an angle parallel to the motion because the projected width is
/// undefined (division by `sin(theta)`).
pub fn slot_width_from_leg_geometry_mm(
    k: u32,
    trace_width_mm: f64,
    trace_spacing_mm: f64,
    theta_rad: f64,
) -> Result<f64, String> {
    if k == 0 {
        return Err("leg strand count k must be at least 1".to_string());
    }
    if !trace_width_mm.is_finite() || trace_width_mm <= 0.0 {
        return Err("trace width w_t must be finite and greater than zero".to_string());
    }
    if !trace_spacing_mm.is_finite() || trace_spacing_mm < 0.0 {
        return Err("trace spacing s must be finite and non-negative".to_string());
    }
    if !theta_rad.is_finite() {
        return Err("trace angle theta must be finite".to_string());
    }

    let sin_theta = theta_rad.sin().abs();
    if sin_theta <= EPS {
        return Err(
            "trace angle theta must not be parallel to the travel axis (sin(theta) is zero)"
                .to_string(),
        );
    }

    let leg_width = k as f64 * trace_width_mm
        + (k.saturating_sub(1) as f64) * trace_spacing_mm;
    Ok(leg_width / sin_theta)
}

/// True slot pitch equation (glossary "Slot Pitch"):
///
/// `tau_s = L_stator / N_slots`
///
/// `L_stator` is the stator track length populated by active conductor legs
/// (the context's active-area length) and `N_slots` the total number of
/// active leg slots declared by the pattern's leg grid. The function rejects
/// a non-positive / non-finite stator length and `n_slots = 0`.
pub fn slot_pitch_from_leg_grid_mm(l_stator_mm: f64, n_slots: u32) -> Result<f64, String> {
    if !l_stator_mm.is_finite() || l_stator_mm <= 0.0 {
        return Err("stator track length L_stator must be finite and greater than zero".to_string());
    }
    if n_slots == 0 {
        return Err("slot count N_slots must be at least 1".to_string());
    }
    Ok(l_stator_mm / n_slots as f64)
}

fn validate_context_dimensions(ctx: &RoutingContext) -> Result<(), RoutingError> {
    if !ctx.active_area_length_mm.is_finite() || ctx.active_area_length_mm <= 0.0 {
        return Err(dimension_error(
            "context.active_area_length_mm",
            "active-area length must be finite and greater than zero",
        ));
    }
    if !ctx.board_width_mm.is_finite() || ctx.board_width_mm <= 0.0 {
        return Err(dimension_error(
            "context.board_width_mm",
            "board width must be finite and greater than zero",
        ));
    }
    if !ctx.min_trace_mm.is_finite() || ctx.min_trace_mm <= 0.0 {
        return Err(dimension_error(
            "context.min_trace_mm",
            "trace width must be finite and greater than zero",
        ));
    }
    if !ctx.min_space_mm.is_finite() || ctx.min_space_mm < 0.0 {
        return Err(dimension_error(
            "context.min_space_mm",
            "trace/phase clearance must be finite and non-negative",
        ));
    }
    if let Some(g_phase) = ctx.phase_clearance_mm {
        if !g_phase.is_finite() || g_phase < 0.0 {
            return Err(dimension_error(
                "context.phase_clearance_mm",
                "explicit phase clearance g_phase must be finite and non-negative",
            ));
        }
    }
    Ok(())
}

fn path_angle(start: Point, end: Point) -> Option<f64> {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    if !dx.is_finite() || !dy.is_finite() || (dx.abs() <= EPS && dy.abs() <= EPS) {
        return None;
    }
    let angle = dy.abs().atan2(dx.abs());
    if angle <= EPS {
        None
    } else {
        Some(angle)
    }
}

/// Per-bundle strand-count hint from the context parameters.
///
/// Only per-bundle strand counts are accepted: `num_strands` wins over
/// `trace_count` when both are present. Whole-coil winding counts (`turns`)
/// are deliberately NOT consulted — they count coil
/// windings, not parallel strands in one bundle, and previously fed the width
/// equation with silently wrong numbers.
fn trace_count_hint(ctx: &RoutingContext) -> u32 {
    ["num_strands", "trace_count"]
        .iter()
        .find_map(|key| {
            let value = ctx.params.get(*key).copied()?;
            if value.is_finite() && value >= 1.0 {
                Some(value.round() as u32)
            } else {
                None
            }
        })
        .unwrap_or(1)
}

fn dimension_error(field: impl Into<String>, message: impl Into<String>) -> RoutingError {
    RoutingError::new(0, field, RoutingErrorKind::Generation, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{RouteSegment, RoutingResult};
    use std::collections::HashMap;

    fn context() -> RoutingContext {
        RoutingContext {
            active_area_length_mm: 195.0,
            board_width_mm: 20.0,
            num_layers: 2,
            phases: 3,
            min_trace_mm: 0.2,
            min_space_mm: 0.15,
            magnet_pitch_mm: Some(12.0),
            params: HashMap::from([("num_strands".to_string(), 4.0)]),
            ..RoutingContext::default()
        }
    }

    #[test]
    fn bottom_up_equation_matches_reference_example() {
        let width = phase_band_width_from_trace_geometry_mm(4, 0.2, 0.15, 45_f64.to_radians())
            .expect("valid phase-band width inputs");
        assert!((width - 1.76776695).abs() < 1e-8, "width = {width}");
    }

    #[test]
    fn top_down_equation_matches_reference_example() {
        let width = max_phase_band_width_from_pole_pitch_mm(12.0, 3, 0.0).unwrap();
        assert!((width - 4.0).abs() < 1e-12);
    }

    #[test]
    fn rejects_trace_parallel_to_motion() {
        let error = phase_band_width_from_trace_geometry_mm(1, 0.2, 0.15, 0.0).unwrap_err();
        assert!(error.contains("parallel"));
    }

    #[test]
    fn reports_pole_pitch_and_band_widths_per_layer_and_net() {
        let result = RoutingResult {
            segments: vec![
                RouteSegment {
                    start: Point::new(0.0, 0.0),
                    end: Point::new(10.0, 10.0),
                    layer: 0,
                    net: "A".to_string(),
                    is_active: true,
                },
                RouteSegment {
                    start: Point::new(0.0, 10.0),
                    end: Point::new(10.0, 0.0),
                    layer: 1,
                    net: "A".to_string(),
                    is_active: true,
                },
            ],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &context()).unwrap();
        assert_eq!(dimensions.pole_pitch_mm, Some(12.0));
        assert_eq!(dimensions.pole_to_pole_pitch_mm(), Some(12.0));
        assert_eq!(dimensions.magnet_array_span_mm, None);
        assert_eq!(dimensions.phase_band_pitch_mm, Some(4.0));
        assert_eq!(dimensions.phase_band_widths.len(), 2);
        assert!(dimensions.all_phase_bands_fit(), "bands: {:?}", dimensions.phase_band_widths);
        assert_eq!(dimensions.phase_band_widths[0].trace_count, 4);
    }

    #[test]
    fn dimensions_round_trip_as_json() {
        let dimensions = RoutingDimensions::from_result(
            &RoutingResult {
                segments: vec![RouteSegment {
                    start: Point::new(0.0, 0.0),
                    end: Point::new(10.0, 10.0),
                    layer: 0,
                    net: "A".into(),
                    is_active: true,
                }],
                ..RoutingResult::default()
            },
            &context(),
        )
        .unwrap();
        let json = serde_json::to_string(&dimensions).unwrap();
        let back: RoutingDimensions = serde_json::from_str(&json).unwrap();
        assert_eq!(back, dimensions);
    }

    // -----------------------------------------------------------------------
    // Per-slot helpers (glossary "Slot Width" / "Slot Pitch")
    // -----------------------------------------------------------------------

    #[test]
    fn slot_width_reference_examples() {
        // Single-trace leg: w_t / sin(theta) = 0.2 / sin(45°) = 0.28284271.
        let single = slot_width_from_leg_geometry_mm(1, 0.2, 0.15, 45_f64.to_radians())
            .expect("valid single-leg slot width inputs");
        assert!((single - 0.28284271).abs() < 1e-8, "width = {single}");
        // Bundled leg: (4 * 0.2 + 3 * 0.15) / sin(45°) = 1.76776695.
        let bundled = slot_width_from_leg_geometry_mm(4, 0.2, 0.15, 45_f64.to_radians())
            .expect("valid bundled-leg slot width inputs");
        assert!((bundled - 1.76776695).abs() < 1e-8, "width = {bundled}");
    }

    #[test]
    fn slot_width_rejects_invalid_leg_geometry() {
        let err = slot_width_from_leg_geometry_mm(0, 0.2, 0.15, 45_f64.to_radians()).unwrap_err();
        assert!(err.contains("k"), "k = 0 must be rejected: {err}");
        let err = slot_width_from_leg_geometry_mm(1, f64::NAN, 0.15, 45_f64.to_radians()).unwrap_err();
        assert!(err.contains("w_t"), "non-finite w_t must be rejected: {err}");
        let err =
            slot_width_from_leg_geometry_mm(1, 0.2, f64::INFINITY, 45_f64.to_radians()).unwrap_err();
        assert!(err.contains("s"), "non-finite s must be rejected: {err}");
        let err = slot_width_from_leg_geometry_mm(1, 0.2, 0.15, f64::NAN).unwrap_err();
        assert!(err.contains("theta"), "non-finite theta must be rejected: {err}");
        let err = slot_width_from_leg_geometry_mm(1, 0.2, 0.15, 0.0).unwrap_err();
        assert!(err.contains("parallel"), "theta parallel to travel must be rejected: {err}");
    }

    #[test]
    fn slot_pitch_reference_example() {
        // L_stator = 600 mm over the braid reference grid (65 periods x 3
        // phases x 5 strands = 975 slots).
        let pitch = slot_pitch_from_leg_grid_mm(600.0, 975).expect("valid slot pitch inputs");
        assert!((pitch - 600.0 / 975.0).abs() < 1e-12, "pitch = {pitch}");
        let err = slot_pitch_from_leg_grid_mm(600.0, 0).unwrap_err();
        assert!(err.contains("N_slots"), "n_slots = 0 must be rejected: {err}");
        let err = slot_pitch_from_leg_grid_mm(f64::NEG_INFINITY, 10).unwrap_err();
        assert!(err.contains("L_stator"), "non-finite length must be rejected: {err}");
        let err = slot_pitch_from_leg_grid_mm(-1.0, 10).unwrap_err();
        assert!(err.contains("L_stator"), "negative length must be rejected: {err}");
    }

    // -----------------------------------------------------------------------
    // Pattern-declared leg grid -> RoutingDimensions slot fields
    // -----------------------------------------------------------------------

    /// Result with a 45° active segment and a declared leg grid.
    fn gridded_result(slot_count: u32, strands_per_leg: Option<u32>) -> RoutingResult {
        RoutingResult {
            segments: vec![RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(10.0, 10.0),
                layer: 0,
                net: "A".to_string(),
                is_active: true,
            }],
            leg_grid: Some(crate::model::LegGrid {
                slot_count,
                strands_per_leg,
            }),
            ..RoutingResult::default()
        }
    }

    #[test]
    fn declared_leg_grid_produces_slot_metrics() {
        let dimensions =
            RoutingDimensions::from_result(&gridded_result(975, Some(5)), &context()).unwrap();
        assert_eq!(dimensions.slot_count, Some(975));
        // tau_s = L_stator / N_slots = 195 / 975.
        let expected_pitch = 195.0 / 975.0;
        assert_eq!(dimensions.slot_pitch_mm, Some(expected_pitch));
        // Effective leg pitch tau_p / (phases x strands) = 12 / (3 x 5) = 0.8.
        assert_eq!(dimensions.interleave_step_mm, Some(0.8));
        // Phase-band metrics keep working alongside the slot metrics.
        assert_eq!(dimensions.phase_band_pitch_mm, Some(4.0));
        assert_eq!(dimensions.phase_band_widths[0].trace_count, 4);
        // Per-record slot width is the single-leg width: 0.2 / sin(45°).
        let slot_width = dimensions.phase_band_widths[0].slot_width_mm.unwrap();
        assert!((slot_width - 0.2 / 45_f64.to_radians().sin()).abs() < 1e-12);
        // ... and it is narrower than the 4-strand bundle width.
        assert!(slot_width < dimensions.phase_band_widths[0].band_width_mm);
    }

    #[test]
    fn absent_leg_grid_keeps_slot_fields_none_and_phase_band_metrics_unchanged() {
        let result = RoutingResult {
            segments: vec![RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(10.0, 10.0),
                layer: 0,
                net: "A".to_string(),
                is_active: true,
            }],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &context()).unwrap();
        assert_eq!(dimensions.slot_count, None);
        assert_eq!(dimensions.slot_pitch_mm, None);
        assert_eq!(dimensions.interleave_step_mm, None);
        // Phase-band metrics are unaffected by the missing grid ...
        assert_eq!(dimensions.phase_band_pitch_mm, Some(4.0));
        assert_eq!(dimensions.max_phase_band_width_mm, Some(4.0 - 0.15));
        assert_eq!(dimensions.phase_band_widths[0].trace_count, 4);
        let band = dimensions.phase_band_widths[0].band_width_mm;
        assert!((band - 1.76776695).abs() < 1e-8, "band = {band}");
        // ... while the per-record single-leg slot width needs no grid: it is
        // pure geometry (w_t / sin(theta)).
        let slot_width = dimensions.phase_band_widths[0].slot_width_mm.unwrap();
        assert!((slot_width - 0.2 / 45_f64.to_radians().sin()).abs() < 1e-12);
    }

    #[test]
    fn band_record_requires_band_width_mm() {
        // `band_width_mm` is required: silently mapping a payload that lacks
        // it onto the per-record `slot_width_mm` field would misreport the
        // band by a factor of `trace_count`.
        let payload = r#"{
            "active_area_length_mm": 195.0,
            "total_routing_length_mm": 255.0,
            "board_width_mm": 20.0,
            "phases": 3,
            "phase_clearance_mm": 0.127,
            "phase_band_widths": [
                {
                    "layer": 0,
                    "net": "A",
                    "trace_count": 5,
                    "trace_width_mm": 0.127,
                    "trace_spacing_mm": 0.127,
                    "angle_rad": 1.030377,
                    "slot_width_mm": 1.333
                }
            ]
        }"#;
        let result: Result<RoutingDimensions, _> = serde_json::from_str(payload);
        assert!(result.is_err(), "missing band_width_mm must be rejected");
    }

    // -----------------------------------------------------------------------
    // Phase-band geometry (kata hzs2): declared vs derived
    // -----------------------------------------------------------------------

    use crate::model::PhaseBandShape;

    /// Two-band result: one band per net on layer 0 (serpentine-like).
    fn two_band_result() -> RoutingResult {
        RoutingResult {
            segments: vec![RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(10.0, 10.0),
                layer: 0,
                net: "A".to_string(),
                is_active: true,
            }],
            phase_bands: vec![
                crate::model::PhaseBand {
                    layer: 0,
                    net: "A".into(),
                    centerline_x_mm: 2.0,
                    start_x_mm: 0.0,
                    end_x_mm: 4.0,
                    y_min_mm: 0.0,
                    y_max_mm: 20.0,
                    shape: PhaseBandShape::Linear,
                },
                crate::model::PhaseBand {
                    layer: 0,
                    net: "B".into(),
                    centerline_x_mm: 6.0,
                    start_x_mm: 4.0,
                    end_x_mm: 8.0,
                    y_min_mm: 0.5,
                    y_max_mm: 19.5,
                    shape: PhaseBandShape::Braided,
                },
            ],
            ..RoutingResult::default()
        }
    }

    #[test]
    fn declared_phase_bands_pass_through_marked_not_derived() {
        let dimensions = RoutingDimensions::from_result(&two_band_result(), &context()).unwrap();
        assert_eq!(dimensions.phase_bands.len(), 2);
        for (record, expected) in dimensions.phase_bands.iter().zip(two_band_result().phase_bands) {
            assert!(!record.derived, "declared bands must not be marked derived");
            assert_eq!(record.band, expected);
        }
        // The sidecar round-trips as JSON with the flattened band fields.
        let json = serde_json::to_string(&dimensions).unwrap();
        let back: RoutingDimensions = serde_json::from_str(&json).unwrap();
        assert_eq!(back, dimensions);
        assert!(json.contains("\"centerline_x_mm\":6.0"));
        assert!(json.contains("\"derived\":false"));
    }

    #[test]
    fn absent_phase_bands_are_derived_from_the_ideal_phase_band_pitch() {
        // No declaration: the host derives one band per active (layer, net)
        // group from tau_band = tau_p / phases = 4 mm. Two groups on two
        // layers sharing net "A" -> both take phase slot 0.
        let result = RoutingResult {
            segments: vec![
                RouteSegment {
                    start: Point::new(0.0, 0.0),
                    end: Point::new(10.0, 10.0),
                    layer: 0,
                    net: "A".to_string(),
                    is_active: true,
                },
                RouteSegment {
                    start: Point::new(0.0, 10.0),
                    end: Point::new(10.0, 0.0),
                    layer: 1,
                    net: "A".to_string(),
                    is_active: true,
                },
            ],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &context()).unwrap();
        assert_eq!(dimensions.phase_bands.len(), 2);
        for record in &dimensions.phase_bands {
            assert!(record.derived, "fallback bands must be marked derived");
            assert_eq!(record.band.net, "A");
            // Phase slot 0: extent [0, tau_band], centerline tau_band / 2.
            assert_eq!(record.band.start_x_mm, 0.0);
            assert_eq!(record.band.end_x_mm, 4.0);
            assert_eq!(record.band.centerline_x_mm, 2.0);
            assert_eq!(record.band.y_min_mm, 0.0);
            assert_eq!(record.band.y_max_mm, 20.0);
            assert_eq!(record.band.shape, PhaseBandShape::Linear);
        }
        assert_eq!(dimensions.phase_bands[0].band.layer, 0);
        assert_eq!(dimensions.phase_bands[1].band.layer, 1);
    }

    #[test]
    fn derived_phase_bands_slot_nets_in_sorted_order() {
        // Nets B and A on layer 0: sorted net order gives A slot 0, B slot 1.
        let result = RoutingResult {
            segments: vec![
                RouteSegment {
                    start: Point::new(0.0, 0.0),
                    end: Point::new(10.0, 10.0),
                    layer: 0,
                    net: "B".to_string(),
                    is_active: true,
                },
                RouteSegment {
                    start: Point::new(0.0, 10.0),
                    end: Point::new(10.0, 0.0),
                    layer: 0,
                    net: "A".to_string(),
                    is_active: true,
                },
            ],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &context()).unwrap();
        assert_eq!(dimensions.phase_bands.len(), 2);
        let a = dimensions
            .phase_bands
            .iter()
            .find(|record| record.band.net == "A")
            .expect("band for net A");
        let b = dimensions
            .phase_bands
            .iter()
            .find(|record| record.band.net == "B")
            .expect("band for net B");
        // A slot 0: [0, 4]; B slot 1: [4, 8]; adjacent centerlines one
        // phase-band pitch apart.
        assert_eq!(a.band.start_x_mm, 0.0);
        assert_eq!(a.band.end_x_mm, 4.0);
        assert_eq!(b.band.start_x_mm, 4.0);
        assert_eq!(b.band.end_x_mm, 8.0);
        assert_eq!(b.band.centerline_x_mm - a.band.centerline_x_mm, 4.0);
        assert!(a.derived && b.derived);
    }

    #[test]
    fn no_pole_pitch_yields_no_derived_phase_bands() {
        let mut ctx = context();
        ctx.magnet_pitch_mm = None;
        let result = RoutingResult {
            segments: vec![RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(10.0, 10.0),
                layer: 0,
                net: "A".to_string(),
                is_active: true,
            }],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &ctx).unwrap();
        assert!(dimensions.phase_bands.is_empty());
        // ... while a declaration still passes through without a pole pitch.
        let declared = two_band_result();
        let dimensions = RoutingDimensions::from_result(&declared, &ctx).unwrap();
        assert_eq!(dimensions.phase_bands.len(), 2);
        assert!(dimensions.phase_bands.iter().all(|record| !record.derived));
    }

    // -----------------------------------------------------------------------
    // trace_count_hint contract
    // -----------------------------------------------------------------------

    #[test]
    fn turns_and_windings_per_phase_are_no_longer_selected() {
        let mut ctx = context();
        ctx.params = HashMap::from([("turns".to_string(), 7.0)]);
        assert_eq!(trace_count_hint(&ctx), 1, "whole-coil `turns` must be ignored");
        ctx.params = HashMap::from([("windings_per_phase".to_string(), 9.0)]);
        assert_eq!(
            trace_count_hint(&ctx),
            1,
            "whole-coil `windings_per_phase` must be ignored"
        );
    }

    #[test]
    fn num_strands_still_wins_over_trace_count() {
        let mut ctx = context();
        ctx.params = HashMap::from([
            ("num_strands".to_string(), 3.0),
            ("trace_count".to_string(), 5.0),
            ("turns".to_string(), 11.0),
        ]);
        assert_eq!(trace_count_hint(&ctx), 3);
        ctx.params = HashMap::from([("trace_count".to_string(), 5.0)]);
        assert_eq!(trace_count_hint(&ctx), 5);
        ctx.params = HashMap::new();
        assert_eq!(trace_count_hint(&ctx), 1);
    }

    // -----------------------------------------------------------------------
    // Explicit phase clearance contract
    // -----------------------------------------------------------------------

    #[test]
    fn explicit_phase_clearance_overrides_min_space() {
        let mut ctx = context();
        ctx.phase_clearance_mm = Some(0.5);
        let result = RoutingResult {
            segments: vec![RouteSegment {
                start: Point::new(0.0, 0.0),
                end: Point::new(10.0, 10.0),
                layer: 0,
                net: "A".to_string(),
                is_active: true,
            }],
            ..RoutingResult::default()
        };
        let dimensions = RoutingDimensions::from_result(&result, &ctx).unwrap();
        assert_eq!(dimensions.phase_clearance_mm, 0.5);
        assert_eq!(dimensions.max_phase_band_width_mm, Some(4.0 - 0.5));
        assert_eq!(dimensions.phase_band_widths[0].max_band_width_mm, Some(3.5));
        // The bottom-up bundle spacing still uses the trace-to-trace rule.
        assert_eq!(dimensions.phase_band_widths[0].trace_spacing_mm, 0.15);
    }

    #[test]
    fn negative_explicit_phase_clearance_is_rejected() {
        let mut ctx = context();
        ctx.phase_clearance_mm = Some(-0.1);
        let result = RoutingResult::default();
        let err = RoutingDimensions::from_result(&result, &ctx).unwrap_err();
        assert!(err.message.contains("phase clearance"), "err: {err}");
    }
}
