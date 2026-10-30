//! The "infinity" diamond braid routing pattern.
//!
//! Faithful Rust port of `docs/reference/pcbBraid` (after Verbeek & Dehez).
//! Produces a two-layer braid: `top_layer_segments` on layer 0, `bottom_layer_segments`
//! on layer 1, and vias (at every peak/valley/edge endpoint) routing 0 → 1.
//!
//! Pattern-owned layer semantics: this pattern is inherently 2-layer and uses
//! vias at crossing points. It is not constrained by the earlier single-layer
//! ranking.
//!
//! ## Magnet-aware period count
//!
//! When the [`RoutingContext`] carries the magnet layout (`magnet_pitch_mm` +
//! `magnet_array_span_mm`) the braid sizes its repeating diamond period to the pole
//! pitch. Complete periods are used after reserving the interleave span, so the
//! distance between corresponding diamond repeats is **exactly** the
//! centre-to-centre pole pitch. The phase/strand via pitch is
//! `pole_pitch / (phases × strands)` on both layer copies; the period count is
//! reduced when necessary to keep that uniform grid inside the routable length.
//! The selected repeat count is coprime to the strand count so the braid
//! forms one connected ring per phase before its lead cut, not several rings.
//! Contexts built without a magnet layout fall back to the packaged `n_periods`
//! default (kept for backward compatibility with plugin probes and unit tests).
//!
//! Phase starts occupy consecutive strand bundles on the compact interleave
//! grid. Physical bundle pitch is not, by itself, a declaration of terminal
//! polarity or controller electrical phase. Do not spread the bundles to fit
//! a desired force-axis angle; winding polarity/commutation needs its own audit.
//!
//! The geometry is split into three submodules:
//! - [`diamonds`] — the diamond / period geometry engine,
//! - [`peaks_valleys`] — peak / valley / braid-crossing computation,
//! - [`segments`] — the per-layer segment builders.
//!
//! The host-side [`RoutingReport`](crate::RoutingReport) derives the diamond
//! edge angle as `atan(board_width / pole_pitch)` and reports the resulting
//! conductor-band width budget for every active (layer, net) bundle.
//!
//! ## Declared leg grid
//!
//! The braid declares its leg grid on the result
//! (`RoutingResult::leg_grid`): `slot_count = periods × phases × strands`
//! — one slot per phase/strand position per period — and
//! `strands_per_leg = num_strands`. The host derives the true slot pitch
//! `tau_s = L_stator / N_slots` and the effective leg pitch
//! `interleave_step_mm = tau_p / (phases × strands)` from that declaration.
//! Per the glossary the braid is slotless (no physical slots): the declaration
//! is the equivalent leg-pitch model of its interleaved active segments, and
//! each strand remains a single-trace leg for the per-record slot width.
//!
//! ## Declared phase bands
//!
//! The braid also declares its phase bands on the result
//! (`RoutingResult::phase_bands`, kata hzs2): one record per `(layer, net)`
//! with the band's first-repeat centerline taken from its first pole region,
//! the full along-travel span of its pole regions as extent, the full board
//! width as y-extent, and the braided shape. The declaration is consistent
//! with the `pole_regions` emission by construction.
//!
//! ## Winding connection
//!
//! Every phase of the braid is a closed copper ring. The `connection`
//! parameter keeps that ring (`closed`) or opens it into a winding with two
//! ends and brings the ends out as leads:
//!
//! - The ring is opened at the last peak of the first period (the top vertex
//!   of the last strand's first diamond) by omitting the via there. Its
//!   layer-0 and layer-1 traces become the winding's two ends.
//! - The layer-1 end is the phase's lead. It rises straight up past the
//!   board width to a per-phase height `board_width + (i + 1) · lead_pitch`,
//!   then runs left to `x = 0`. Each phase's break lies further right than
//!   every earlier phase's, so the leads nest without crossing.
//! - `delta` runs each layer-0 end on along its braid line until it reaches
//!   the previous phase's lead height, then (if still right of that phase's
//!   lead riser) along to it, and drops through a via onto that lead. Phase
//!   B's start joins A's lead, C's joins B's and A's joins C's, so the three
//!   leads are the three delta corners.
//! - `star` raises each layer-0 end one lead pitch onto a layer-0 neutral
//!   bar running across the break points; the layer-1 leads are the line
//!   terminals.
//!
//! Leads are inactive (non-thrust) conductors and are the only copper the
//! braid places outside the board width.

mod diamonds;
mod peaks_valleys;
mod segments;

use crate::context::RoutingContext;
use crate::error::{RoutingError, RoutingErrorKind};
use crate::model::{
    LegGrid, PhaseBand, PhaseBandShape, Point, PoleRegion, RouteSegment, RoutingResult, Via,
};
use crate::pattern::{ParamOption, RoutingPattern};

use self::diamonds::{compute_diamonds, compute_endpoints, compute_pole_region_xs};
use self::segments::{compute_bottom_layer_segments, compute_top_layer_segments};

const PHASE_NAMES: &[&str] = &["A", "B", "C", "D", "E", "F"];

/// How the phase windings are terminated (the `connection` parameter).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Connection {
    /// Each phase stays a closed ring with no leads.
    Closed,
    /// Each phase is opened and both ends are brought out as leads.
    Delta,
    /// As [`Connection::Delta`], with the layer-1 ends tied by a neutral bus.
    Star,
}

impl Connection {
    const CLOSED: f64 = 0.0;
    const DELTA: f64 = 1.0;
    const STAR: f64 = 2.0;

    fn from_param(value: f64) -> Self {
        match value.round() as i64 {
            1 => Self::Delta,
            2 => Self::Star,
            _ => Self::Closed,
        }
    }
}

/// The bundled infinity-braid pattern.
#[derive(Debug, Clone, Default)]
pub struct InfinityBraidPattern;

impl RoutingPattern for InfinityBraidPattern {
    fn id(&self) -> &str {
        "infinity-braid"
    }

    fn display_name(&self) -> &str {
        "Infinity Braid (pcbBraid)"
    }

    fn description(&self) -> &str {
        "Two-layer overlapping diamond braid after Verbeek & Dehez, with vias at crossing points."
    }

    fn author(&self) -> &str {
        "pcbmotorgen (port of pcbBraid)"
    }

    fn version(&self) -> &str {
        env!("CARGO_PKG_VERSION")
    }

    fn parameters(&self) -> Vec<crate::pattern::PatternParameter> {
        use crate::pattern::PatternParameter;
        // `n_periods` is intentionally NOT exposed: when a magnet layout is
        // present the period count is derived from the pole pitch so the
        // braid regenerates to match the magnets.
        vec![
            PatternParameter::int("num_strands", "Strands per period", 5.0, 2.0, 99.0)
                .with_description("Number of parallel braided paths in each period."),
            PatternParameter::int(
                "connection",
                "Winding connection",
                Connection::DELTA,
                Connection::DELTA,
                Connection::STAR,
            )
            .with_description(
                "How each phase winding terminates. Delta joins each phase end to the next phase start. Star joins the three phase ends into one neutral.",
            )
            .with_options(vec![
                ParamOption::new(Connection::DELTA, "Delta"),
                ParamOption::new(Connection::STAR, "Star (wye)"),
            ]),
        ]
    }

    fn min_layers(&self) -> Option<u32> {
        // The braid weaves a top layer against a mirrored bottom layer with
        // vias between them; `validated_braid_context` rejects < 2 layers,
        // so declare it as metadata instead of a generate-time surprise.
        Some(2)
    }

    fn expects_continuous(&self) -> bool {
        // The braid is a deliberate weave of many interleaved strands; it is
        // not a single continuous per-(layer,net) path, so we do not enforce
        // the continuity check.
        false
    }

    fn generate(&self, ctx: &RoutingContext) -> Result<RoutingResult, RoutingError> {
        let magnet_pitch = validated_braid_context(ctx)?;
        let phases = ctx.phases.max(1) as i64;
        let num_strands = (ctx.param("num_strands", 5.0) as i64).max(2);
        // Map the unrolled braid domain onto the routing area. The routing
        // domain EQUALS the active area — the braid's end turns are part of
        // the pattern, there is no end padding.
        let d_tot = ctx.active_area_length_mm;
        let layout = resolve_braid_layout(ctx, d_tot, magnet_pitch, phases, num_strands)?;
        // Amplitude = half the board width, mapping diamond ±A onto [0, board_width].
        let amplitude_mm = ctx.board_width_mm / 2.0;

        let connection = Connection::from_param(ctx.param("connection", Connection::CLOSED));
        let lead_pitch = lead_pitch_mm(layout, amplitude_mm, ctx);

        let geometry = braid_geometry(
            layout,
            amplitude_mm,
            phases,
            num_strands,
            connection,
            lead_pitch,
        );

        // Pattern-declared leg grid: the braid's active legs populate a
        // uniform interleave grid of one slot per phase/strand position per
        // period — `n_periods × phases × num_strands` slots in total. Its
        // interleave step is `tau_p / (phases × strands)` when a pole pitch is
        // known; per the glossary the braid is slotless, so this is the
        // equivalent leg-pitch model of the generated segments, and each
        // strand is its own single-trace leg.
        let leg_grid = Some(LegGrid {
            slot_count: (layout.n_periods * phases * num_strands) as u32,
            strands_per_leg: Some(num_strands as u32),
        });

        Ok(RoutingResult {
            segments: geometry.segments,
            curves: Vec::new(),
            vias: geometry.vias,
            pole_regions: geometry.pole_regions,
            leg_grid,
            phase_bands: geometry.phase_bands,
            ..Default::default()
        })
    }
}

/// Validated context inputs for the braid. Returns the resolved pole pitch
/// (`None` when the context carries no magnet layout).
fn validated_braid_context(ctx: &RoutingContext) -> Result<Option<f64>, RoutingError> {
    if ctx.num_layers < 2 {
        return Err(RoutingError::new(
            0,
            "num_layers",
            RoutingErrorKind::BadLayer,
            format!(
                "the infinity braid requires at least 2 copper layers, got {}",
                ctx.num_layers
            ),
        ));
    }
    if !ctx.active_area_length_mm.is_finite() || ctx.active_area_length_mm <= 0.0 {
        return Err(RoutingError::new(
            0,
            "active_area_length_mm",
            RoutingErrorKind::Generation,
            "active area must be finite and greater than zero",
        ));
    }
    if !ctx.board_width_mm.is_finite() || ctx.board_width_mm <= 0.0 {
        return Err(RoutingError::new(
            0,
            "board_width_mm",
            RoutingErrorKind::Generation,
            "board width must be finite and greater than zero",
        ));
    }
    match ctx.magnet_pitch_mm {
        Some(pitch) if pitch.is_finite() && pitch > 0.0 => Ok(Some(pitch)),
        Some(_) => Err(RoutingError::new(
            0,
            "magnet_pitch_mm",
            RoutingErrorKind::Generation,
            "pole pitch must be finite and greater than zero",
        )),
        None => Ok(None),
    }
}

/// How the unrolled diamond domain maps onto the routing area.
#[derive(Clone, Copy)]
struct BraidLayout {
    n_periods: i64,
    d_phase: f64,
    o: f64,
}

/// Resolve the braid layout for the routing domain.
///
/// With a magnet layout the period count is one complete diamond period per
/// pole pitch. The uniform phase/strand grid is reserved before selecting
/// the count so no remainder becomes a wide via gap.
fn resolve_braid_layout(
    ctx: &RoutingContext,
    d_tot: f64,
    magnet_pitch: Option<f64>,
    phases: i64,
    num_strands: i64,
) -> Result<BraidLayout, RoutingError> {
    let tail_slots = phases * num_strands - 1;
    match magnet_pitch {
        Some(pitch) => {
            // Reserve consecutive phase/strand bundles. Widening phase starts
            // while retaining the strand grid leaves missing bundles at both ends.
            let interleave_step = pitch / (num_strands * phases) as f64;
            let tail_span = tail_slots as f64 * interleave_step;
            let mut n_periods = ((d_tot - tail_span) / pitch).floor() as i64;
            // The braid's end joins permute its strands by the repeat
            // count. A shared divisor creates separate closed rings rather
            // than the single winding that the lead cut is meant to open.
            let gcd = |mut a: i64, mut b: i64| {
                while b != 0 { (a, b) = (b, a % b); }
                a
            };
            while n_periods > 0 && gcd(n_periods, num_strands) != 1 {
                n_periods -= 1;
            }
            if n_periods < 1 {
                return Err(RoutingError::new(
                    0,
                    "active_area_length_mm",
                    RoutingErrorKind::Generation,
                    format!(
                        "the routable length ({:.3} mm) cannot fit one complete pole-pitched braid period plus its phase/strand interleave ({:.3} mm required); increase the active area",
                        d_tot,
                        pitch + tail_span
                    ),
                ));
            }
            // Endpoints as well as interior repeats retain the uniform grid.
            let o = -interleave_step;
            Ok(BraidLayout {
                n_periods,
                d_phase: n_periods as f64 * pitch,
                o,
            })
        }
        None => {
            // No magnet layout: fall back to the packaged `n_periods` default
            // (kept for plugin probes and unit tests).
            let n_periods = (ctx.param("n_periods", 4.0) as i64).max(1);
            let o = -d_tot / (n_periods * num_strands * phases + tail_slots) as f64;
            let d_phase = n_periods as f64 * num_strands as f64 * phases as f64 * -o;
            Ok(BraidLayout {
                n_periods,
                d_phase,
                o,
            })
        }
    }
}

/// Centre-to-centre spacing of the lead runs above the board [mm].
///
/// Matches the depth of the braid's first crossing below its peaks (the
/// interleave step times the diamond edge slope), so the first lead sits at
/// the same spacing as the braid's own copper. Never tighter than one trace
/// plus one clearance.
fn lead_pitch_mm(layout: BraidLayout, amplitude_mm: f64, ctx: &RoutingContext) -> f64 {
    let period_length = layout.d_phase / layout.n_periods as f64;
    let crossing_depth = layout.o.abs() * amplitude_mm / period_length;
    crossing_depth.max(ctx.trace_width() + ctx.min_space_mm)
}

/// Generated braid geometry across all phases.
struct BraidGeometry {
    segments: Vec<RouteSegment>,
    vias: Vec<Via>,
    pole_regions: Vec<PoleRegion>,
    phase_bands: Vec<PhaseBand>,
}

/// Emit the per-phase diamond geometry: two segment layers (top / bottom),
/// one via per peak/valley/edge endpoint, and the pole regions at
/// board-centre height. Unless the connection is closed, each phase's ring is
/// opened at its break via and leads are added (see the module docs).
fn braid_geometry(
    layout: BraidLayout,
    amplitude_mm: f64,
    phases: i64,
    num_strands: i64,
    connection: Connection,
    lead_pitch: f64,
) -> BraidGeometry {
    let offset_step = -layout.o * num_strands as f64;
    let mut geometry = BraidGeometry {
        segments: Vec::new(),
        vias: Vec::new(),
        pole_regions: Vec::new(),
        phase_bands: Vec::new(),
    };
    // Per phase: net, break point, and the outward direction of its layer-0
    // trace through the break.
    let mut ends: Vec<(String, Point, Point)> = Vec::new();

    for i in 0..phases {
        let phase_idx = i as usize;
        let net = PHASE_NAMES[phase_idx % PHASE_NAMES.len()].to_string();
        let start_offset = offset_step * i as f64;

        let diamonds = compute_diamonds(
            start_offset,
            layout.d_phase,
            layout.n_periods,
            num_strands,
            layout.o,
            amplitude_mm,
        );
        let (points_obj, flatlist) = compute_endpoints(&diamonds);
        let region_xs = compute_pole_region_xs(&diamonds);
        for (pole_index, (start_x, end_x)) in region_xs.iter().enumerate() {
            geometry.pole_regions.push(PoleRegion {
                phase: net.clone(),
                pole_index: pole_index as u32,
                start: Point::new(*start_x, amplitude_mm),
                end: Point::new(*end_x, amplitude_mm),
            });
        }
        // Declared phase bands (kata hzs2), consistent with the pole regions:
        // the centerline is the first region's center (the band's first
        // repeat — adjacent phases occupy consecutive strand bundles), the
        // extent spans all of the phase's pole regions, and the diamonds map
        // onto the full board width [0, 2a].
        if let (Some(first), Some(last)) = (region_xs.first(), region_xs.last()) {
            for layer in 0..2u32 {
                geometry.phase_bands.push(PhaseBand {
                    layer,
                    net: net.clone(),
                    centerline_x_mm: (first.0 + first.1) / 2.0,
                    start_x_mm: first.0,
                    end_x_mm: last.1,
                    y_min_mm: 0.0,
                    y_max_mm: 2.0 * amplitude_mm,
                    shape: PhaseBandShape::Braided,
                });
            }
        }

        // The top vertex of the last strand's first diamond is the last peak
        // of the first period; its via is where the ring is opened.
        let break_point = diamonds[0][num_strands as usize - 1][0];
        let top_segments = compute_top_layer_segments(&points_obj);
        // The layer-0 trace leaving the break, extended past it, is the line
        // a delta joint follows out of the board.
        let outward = top_segments
            .iter()
            .find_map(|&(s, e)| {
                if s == break_point {
                    Some(e)
                } else if e == break_point {
                    Some(s)
                } else {
                    None
                }
            })
            .map(|other| {
                let (dx, dy) = (break_point.x - other.x, break_point.y - other.y);
                let len = dx.hypot(dy);
                Point::new(dx / len, dy / len)
            })
            .unwrap_or(Point::new(0.0, 1.0));
        ends.push((net.clone(), break_point, outward));

        for (s, e) in top_segments {
            geometry.segments.push(RouteSegment {
                start: s,
                end: e,
                layer: 0,
                net: net.clone(),
                is_active: true,
            });
        }
        for (s, e) in compute_bottom_layer_segments(&points_obj) {
            geometry.segments.push(RouteSegment {
                start: s,
                end: e,
                layer: 1,
                net: net.clone(),
                is_active: true,
            });
        }
        for p in flatlist {
            if connection != Connection::Closed && p == break_point {
                continue;
            }
            geometry.vias.push(Via {
                position: p,
                from_layer: 0,
                to_layer: 1,
                net: net.clone(),
            });
        }
    }

    if connection != Connection::Closed {
        add_leads(&mut geometry, &ends, connection, lead_pitch);
    }

    geometry
}

/// Bring each opened phase out to the edge (see the module docs).
///
/// The layer-1 end is the phase's lead: it rises to the phase's lead height
/// and runs left to `x = 0`. The layer-0 end makes the connection on the
/// board: for delta it runs on along the braid line and drops through a via
/// onto the previous phase's lead; for star it rises one lead pitch onto a
/// layer-0 neutral bar shared by all phases.
fn add_leads(
    geometry: &mut BraidGeometry,
    ends: &[(String, Point, Point)],
    connection: Connection,
    lead_pitch: f64,
) {
    let n = ends.len();
    let lead_y = |i: usize| ends[i].1.y + (i + 1) as f64 * lead_pitch;
    let mut push = |start: Point, end: Point, layer: u32, net: &str| {
        geometry.segments.push(RouteSegment {
            start,
            end,
            layer,
            net: net.to_string(),
            is_active: false,
        });
    };

    for (i, (net, brk, outward)) in ends.iter().enumerate() {
        let corner = Point::new(brk.x, lead_y(i));
        push(*brk, corner, 1, net);
        push(corner, Point::new(0.0, lead_y(i)), 1, net);

        match connection {
            Connection::Delta => {
                // Join this phase's start to the previous phase's lead.
                let prev = (i + n - 1) % n;
                let (target_x, target_y) = (ends[prev].1.x, lead_y(prev));
                let t = (target_y - brk.y) / outward.y;
                let reach = Point::new(brk.x + outward.x * t, target_y);
                push(*brk, reach, 0, net);
                let via_at = if reach.x > target_x {
                    let joint = Point::new(target_x, target_y);
                    push(reach, joint, 0, net);
                    joint
                } else {
                    reach
                };
                geometry.vias.push(Via {
                    position: via_at,
                    from_layer: 0,
                    to_layer: 1,
                    net: net.clone(),
                });
            }
            Connection::Star => {
                let neutral_y = brk.y + lead_pitch;
                push(*brk, Point::new(brk.x, neutral_y), 0, net);
                if i + 1 < n {
                    // The first bar piece belongs to the first phase, the
                    // rest to the phase they run back from.
                    let owner = if i == 0 { net } else { &ends[i + 1].0 };
                    push(
                        Point::new(brk.x, neutral_y),
                        Point::new(ends[i + 1].1.x, neutral_y),
                        0,
                        owner,
                    );
                }
            }
            Connection::Closed => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::validator::Validator;
    use std::collections::HashMap;

    fn ctx() -> RoutingContext {
        let mut params = HashMap::new();
        params.insert("num_strands".to_string(), 5.0);
        params.insert("n_periods".to_string(), 4.0);
        RoutingContext {
            // The routing domain equals the active area (no end padding):
            // 800 mm so the magnet-aligned tests keep their 65-period math.
            active_area_length_mm: 800.0,
            board_width_mm: 20.0,
            num_layers: 2,
            phases: 3,
            min_trace_mm: 0.1,
            min_space_mm: 0.1,
            expects_continuous: false,
            params,
            // No magnet layout by default: the tests below opt in explicitly.
            ..RoutingContext::default()
        }
    }

    /// Context with a magnet layout: 10 magnets at 12 mm pole pitch (span 120 mm).
    fn magnet_ctx() -> RoutingContext {
        let mut c = ctx();
        c.magnet_pitch_mm = Some(12.0);
        c.magnet_array_span_mm = Some(120.0);
        c
    }

    #[test]
    fn produces_two_layer_braid_with_vias() {
        let pat = InfinityBraidPattern;
        let r = pat.generate(&ctx()).unwrap();
        assert!(!r.segments.is_empty());
        assert!(!r.vias.is_empty());
        assert!(r.curves.is_empty());
        // Layer 0 and layer 1 both used.
        assert!(r.segments.iter().any(|s| s.layer == 0));
        assert!(r.segments.iter().any(|s| s.layer == 1));
        // Three phases present.
        let nets: std::collections::BTreeSet<&str> =
            r.segments.iter().map(|s| s.net.as_str()).collect();
        assert!(nets.contains("A") && nets.contains("B") && nets.contains("C"));
        // Vias route 0 → 1.
        assert!(r.vias.iter().all(|v| v.from_layer == 0 && v.to_layer == 1));
    }

    #[test]
    fn passes_strict_validation() {
        let pat = InfinityBraidPattern;
        let r = pat.generate(&ctx()).unwrap();
        let v = Validator::validate(&r, &ctx(), pat.expects_continuous());
        assert!(v.is_ok(), "braid failed validation: {:?}", v.err());
    }

    #[test]
    fn requires_two_layers() {
        let mut c = ctx();
        c.num_layers = 1;
        let err = InfinityBraidPattern.generate(&c).unwrap_err();
        assert_eq!(err.kind, RoutingErrorKind::BadLayer);
    }

    #[test]
    fn one_period_per_pole_pitch_when_magnet_layout_present() {
        // 800 mm fits 65 periods, but 65 and five strands form separate
        // rings. Select 64 connected 12 mm periods instead. The period is
        // exact and every adjacent left/right via-grid point uses the same
        // pole_pitch / (phases × strands) x spacing.
        let pat = InfinityBraidPattern;
        let base = pat.generate(&magnet_ctx()).unwrap();
        assert!(!base.segments.is_empty());
        assert!(
            Validator::validate(&base, &magnet_ctx(), pat.expects_continuous()).is_ok(),
            "magnet-aligned braid must remain bounded"
        );

        // The diamond period length equals the pole pitch and consecutive
        // period grids are spaced by that same pitch.
        let d_tot = magnet_ctx().active_area_length_mm;
        let n_expected = ((d_tot + 12.0 / (3.0 * 5.0)) / 12.0).floor() - 1.0;
        let period_length: f64 = 12.0;
        assert!((period_length - 12.0).abs() < 1e-9, "period {period_length} mm");
        assert_eq!(n_expected as usize, 65);
        assert_eq!(base.pole_regions.len(), 64 * magnet_ctx().phases as usize);
        assert_eq!(
            base.pole_regions
                .iter()
                .filter(|region| region.phase == "A")
                .count(),
            64
        );
        for region in base.pole_regions.iter().filter(|region| region.phase == "A") {
            assert!(region.end.x > region.start.x);
            assert_eq!(region.start.y, magnet_ctx().board_width_mm / 2.0);
            assert_eq!(region.end.y, magnet_ctx().board_width_mm / 2.0);
        }
        let phase_a_widths: Vec<f64> = base
            .pole_regions
            .iter()
            .filter(|region| region.phase == "A")
            .map(|region| region.end.x - region.start.x)
            .collect();
        assert!(phase_a_widths
            .windows(2)
            .all(|pair| (pair[0] - pair[1]).abs() < 1e-12));

        // The shared boundary between adjacent pole regions is the midpoint
        // of point 3's rightmost vertex in one period and point 1's leftmost
        // vertex in the next period. It must not be the point-0/top vertex.
        let context = magnet_ctx();
        let phases = context.phases as i64;
        let strands = context.param("num_strands", 5.0) as i64;
        let pitch = context.magnet_pitch().unwrap();
        let interleave = pitch / (phases * strands) as f64;
        let periods = ((context.active_area_length_mm
            + interleave)
            / pitch)
            .floor() as i64
            - 1;
        let o = -interleave;
        let a = context.board_width_mm / 2.0;
        let diamonds = compute_diamonds(
            0.0,
            periods as f64 * pitch,
            periods,
            strands,
            o,
            a,
        );
        let expected_boundary = (diamonds[0].last().unwrap()[3].x
            + diamonds[1].first().unwrap()[1].x)
            / 2.0;
        let phase_a = base
            .pole_regions
            .iter()
            .filter(|region| region.phase == "A")
            .collect::<Vec<_>>();
        assert!((phase_a[0].end.x - expected_boundary).abs() < 1e-12);

        // Phase-0 active conductors repeat at the period spacing.
        let phase0: Vec<f64> = base
            .segments
            .iter()
            .filter(|s| s.net == "A" && s.is_active)
            .map(|s| s.start.x)
            .collect();
        assert!(!phase0.is_empty());
        let first = phase0[0];
        let second = phase0.iter().find(|x| **x > first + 1e-6);
        if let Some(second_x) = second {
            // Spacing between neighbouring conductors is a sub-multiple of the
            // period (strands × phases interleave within one period).
            let spacing = second_x - first;
            assert!(spacing > 0.0 && spacing <= period_length + 1e-6);
        }
    }

    #[test]
    fn traces_regenerate_when_pole_pitch_changes() {
        // Changing the magnet pattern (pole pitch) MUST change the generated
        // geometry — this is the "traces follow the layout" invariant.
        let pat = InfinityBraidPattern;
        let pitch12 = pat.generate(&magnet_ctx()).unwrap();
        let mut tighter = magnet_ctx();
        tighter.magnet_pitch_mm = Some(10.0);
        let pitch10 = pat.generate(&tighter).unwrap();
        assert_ne!(pitch12.segments.len(), pitch10.segments.len());

        // And the fallback (no magnet layout) is unchanged from the packaged
        // default so plugin probes and legacy tests keep their behaviour.
        let legacy = pat.generate(&ctx()).unwrap();
        assert_ne!(legacy.segments.len(), pitch12.segments.len());
        let mut with_param = ctx();
        with_param.params.insert("n_periods".to_string(), 4.0);
        let legacy_param = pat.generate(&with_param).unwrap();
        assert_eq!(legacy.segments.len(), legacy_param.segments.len());
    }

    #[test]
    fn report_exposes_exact_pole_pitch_and_phase_band_width_budget() {
        let report = crate::generate_routing_report(&magnet_ctx(), "infinity-braid")
            .expect("reference braid report");
        assert_eq!(report.dimensions.pole_pitch_mm, Some(12.0));
        assert_eq!(report.dimensions.magnet_array_span_mm, Some(120.0));
        assert_eq!(report.dimensions.period_pitch_mm, Some(12.0));
        assert_eq!(report.dimensions.phase_band_pitch_mm, Some(4.0));
        assert_eq!(report.dimensions.period_count, Some(65));
        assert!(!report.dimensions.phase_band_widths.is_empty());
        assert!(report.dimensions.all_phase_bands_fit());
        assert!(report
            .dimensions
            .phase_band_widths
            .iter()
            .all(|band| (band.angle_rad - (20.0_f64 / 12.0).atan()).abs() < 1e-12));
    }

    #[test]
    fn declares_its_leg_grid_for_the_host_slot_metrics() {
        // The braid's declared leg grid is its uniform interleave grid:
        // periods × phases × strands slots. With the magnet layout the braid
        // emits 64 complete pole-pitched periods, coprime to five strands.
        let report = crate::generate_routing_report(&magnet_ctx(), "infinity-braid")
            .expect("reference braid report");
        let grid = report.result.leg_grid.as_ref().expect("declared leg grid");
        assert_eq!(grid.slot_count, 64 * 3 * 5);
        assert_eq!(grid.strands_per_leg, Some(5));
        // Host-derived slot metrics from the declaration. Slot pitch spans
        // the active copper length (the routing domain equals the active
        // area since kata hrd8): fixture active 800 mm / 960 slots.
        assert_eq!(report.dimensions.slot_count, Some(960));
        assert_eq!(report.dimensions.slot_pitch_mm, Some(800.0 / 960.0));
        assert_eq!(report.dimensions.interleave_step_mm, Some(0.8));

        // Fallback braid (no magnet layout): 4 periods × 3 phases × 5
        // strands; no pole pitch means no interleave step.
        let fallback = crate::generate_routing_report(&ctx(), "infinity-braid")
            .expect("fallback braid report");
        let grid = fallback.result.leg_grid.as_ref().expect("declared leg grid");
        assert_eq!(grid.slot_count, 4 * 3 * 5);
        assert_eq!(fallback.dimensions.slot_count, Some(60));
        // Fallback fixture active is also 800 mm (kata hrd8): 800 / 60 slots.
        assert_eq!(fallback.dimensions.slot_pitch_mm, Some(800.0 / 60.0));
        assert_eq!(fallback.dimensions.interleave_step_mm, None);
        // Each strand stays a single-trace leg: slot width below band width.
        for band in &fallback.dimensions.phase_band_widths {
            let slot = band.slot_width_mm.expect("single-leg slot width");
            assert!(slot < band.band_width_mm, "slot {slot} vs band {}", band.band_width_mm);
        }
    }

    #[test]
    fn declares_phase_bands_consistent_with_its_pole_regions() {
        // Magnet-aware braid: one band per (layer, net), centerline at the
        // first pole region's center, extent spanning all of the phase's
        // pole regions, braided shape across the full board width.
        let report = crate::generate_routing_report(&magnet_ctx(), "infinity-braid")
            .expect("reference braid report");
        let bands = &report.result.phase_bands;
        assert_eq!(bands.len(), 2 * magnet_ctx().phases as usize);

        for phase in ["A", "B", "C"] {
            let regions: Vec<&crate::model::PoleRegion> = report
                .result
                .pole_regions
                .iter()
                .filter(|region| region.phase == phase)
                .collect();
            assert!(!regions.is_empty());
            for layer in [0u32, 1u32] {
                let band = bands
                    .iter()
                    .find(|band| band.net == phase && band.layer == layer)
                    .expect("declared band per (layer, net)");
                assert_eq!(band.shape, crate::model::PhaseBandShape::Braided);
                assert_eq!(band.y_min_mm, 0.0);
                assert_eq!(band.y_max_mm, magnet_ctx().board_width_mm);
                assert_eq!(band.start_x_mm, regions[0].start.x);
                assert_eq!(band.end_x_mm, regions.last().unwrap().end.x);
                let first_center = (regions[0].start.x + regions[0].end.x) / 2.0;
                assert_eq!(band.centerline_x_mm, first_center);
                assert!(band.start_x_mm < band.centerline_x_mm);
                assert!(band.centerline_x_mm < band.end_x_mm);
            }
        }

        // Adjacent phase centerlines sit one physical bundle pitch apart:
        // the commutation offsets read from the declaration equal the
        // analytic pi * tau_band / tau_p law.
        let pitch = magnet_ctx().magnet_pitch().unwrap();
        let tau_band = pitch / f64::from(magnet_ctx().phases);
        let center = |phase: &str, layer: u32| {
            bands
                .iter()
                .find(|band| band.net == phase && band.layer == layer)
                .unwrap()
                .centerline_x_mm
        };
        assert!((center("B", 0) - center("A", 0) - tau_band).abs() < 1e-9);
        assert!((center("C", 0) - center("B", 0) - tau_band).abs() < 1e-9);
        // Layer copies share the phase geometry.
        assert_eq!(center("A", 0), center("A", 1));

        // The declared sidecar records carry derived = false.
        assert!(report
            .dimensions
            .phase_bands
            .iter()
            .all(|record| !record.derived));
        assert_eq!(report.dimensions.phase_bands.len(), bands.len());

        // Fallback braid (no magnet layout) declares bands too.
        let fallback = crate::generate_routing_report(&ctx(), "infinity-braid")
            .expect("fallback braid report");
        assert_eq!(fallback.result.phase_bands.len(), 2 * ctx().phases as usize);
        assert!(fallback
            .dimensions
            .phase_bands
            .iter()
            .all(|record| !record.derived));
    }

    /// The Fader workspace braid: 6 mm pole pitch, 3 phases × 3 strands,
    /// 8 mm board, 14 periods spanning x ∈ [0, 89.333].
    fn fader_ctx(connection: f64) -> RoutingContext {
        let mut params = HashMap::new();
        params.insert("num_strands".to_string(), 3.0);
        params.insert("connection".to_string(), connection);
        RoutingContext {
            active_area_length_mm: 89.0 + 1.0 / 3.0,
            board_width_mm: 8.0,
            num_layers: 2,
            phases: 3,
            min_trace_mm: 0.127,
            min_space_mm: 0.127,
            expects_continuous: false,
            params,
            magnet_pitch_mm: Some(6.0),
            magnet_array_span_mm: Some(30.0),
            ..RoutingContext::default()
        }
    }

    type NodeKey = (u32, i64, i64);

    fn node(layer: u32, p: Point) -> NodeKey {
        (layer, (p.x * 1e6).round() as i64, (p.y * 1e6).round() as i64)
    }

    /// Per-net conductor graph: trace endpoints per layer, joined by
    /// segments and by vias between layers 0 and 1.
    fn net_graph(r: &RoutingResult, net: &str) -> HashMap<NodeKey, Vec<NodeKey>> {
        let mut g: HashMap<NodeKey, Vec<NodeKey>> = HashMap::new();
        let mut link = |a: NodeKey, b: NodeKey| {
            g.entry(a).or_default().push(b);
            g.entry(b).or_default().push(a);
        };
        for s in r.segments.iter().filter(|s| s.net == net) {
            link(node(s.layer, s.start), node(s.layer, s.end));
        }
        for v in r.vias.iter().filter(|v| v.net == net) {
            link(node(v.from_layer, v.position), node(v.to_layer, v.position));
        }
        g
    }

    fn connected(g: &HashMap<NodeKey, Vec<NodeKey>>) -> bool {
        let Some(start) = g.keys().next() else { return true };
        let mut seen = std::collections::HashSet::from([*start]);
        let mut stack = vec![*start];
        while let Some(n) = stack.pop() {
            for m in &g[&n] {
                if seen.insert(*m) {
                    stack.push(*m);
                }
            }
        }
        seen.len() == g.len()
    }

    fn approx(a: Point, x: f64, y: f64) -> bool {
        (a.x - x).abs() < 1e-5 && (a.y - y).abs() < 1e-5
    }

    #[test]
    fn closed_connection_keeps_every_phase_a_ring() {
        let r = InfinityBraidPattern.generate(&fader_ctx(0.0)).unwrap();
        assert!(r.segments.iter().all(|s| s.is_active));
        for net in ["A", "B", "C"] {
            let g = net_graph(&r, net);
            assert!(connected(&g), "phase {net} is one piece of copper");
            let ends = g.values().filter(|n| n.len() == 1).count();
            assert_eq!(ends, 0, "a closed phase {net} has no free ends");
        }
    }

    const T: f64 = 1.0 / 3.0;
    const LEAD: [f64; 3] = [8.0 + 4.0 / 9.0, 8.0 + 8.0 / 9.0, 8.0 + 12.0 / 9.0];
    const BREAK_X: [f64; 3] = [4.0 + T, 6.0 + T, 8.0 + T];

    fn has_lead(r: &RoutingResult, net: &str, layer: u32, a: (f64, f64), b: (f64, f64)) -> bool {
        r.segments.iter().any(|s| {
            !s.is_active
                && s.net == net
                && s.layer == layer
                && approx(s.start, a.0, a.1)
                && approx(s.end, b.0, b.1)
        })
    }

    /// Layer-1 lead of every phase, shared by delta and star: up from the
    /// break to its lead height, then left to x = 0.
    fn assert_layer_one_leads(r: &RoutingResult) {
        for (i, net) in ["A", "B", "C"].into_iter().enumerate() {
            assert!(
                !r.vias.iter().any(|v| approx(v.position, BREAK_X[i], 8.0)),
                "phase {net} break via must be omitted"
            );
            assert!(has_lead(r, net, 1, (BREAK_X[i], 8.0), (BREAK_X[i], LEAD[i])));
            assert!(has_lead(r, net, 1, (BREAK_X[i], LEAD[i]), (0.0, LEAD[i])));
        }
    }

    #[test]
    fn delta_matches_the_fader_example() {
        // Reference: motor-coils_3s_0-4mm_delta.dxf, made from
        // closed_infinity_pattern.pmmotor. Each phase's layer-0 end runs on
        // along the braid line and drops onto the previous phase's lead.
        let r = InfinityBraidPattern.generate(&fader_ctx(1.0)).unwrap();
        assert_layer_one_leads(&r);

        assert!(has_lead(&r, "B", 0, (6.0 + T, 8.0), (6.0, LEAD[0])));
        assert!(has_lead(&r, "B", 0, (6.0, LEAD[0]), (4.0 + T, LEAD[0])));
        assert!(has_lead(&r, "C", 0, (8.0 + T, 8.0), (7.0 + 2.0 * T, LEAD[1])));
        assert!(has_lead(&r, "C", 0, (7.0 + 2.0 * T, LEAD[1]), (6.0 + T, LEAD[1])));
        assert!(has_lead(&r, "A", 0, (4.0 + T, 8.0), (3.0 + T, LEAD[2])));
        for (net, x, y) in [("B", 4.0 + T, LEAD[0]), ("C", 6.0 + T, LEAD[1]), ("A", 3.0 + T, LEAD[2])] {
            assert!(
                r.vias.iter().any(|v| v.net == net && approx(v.position, x, y)),
                "delta joint via for {net} at ({x}, {y})"
            );
        }
        assert_eq!(r.segments.iter().filter(|s| !s.is_active).count(), 11);

        let closed = InfinityBraidPattern.generate(&fader_ctx(0.0)).unwrap();
        assert_eq!(r.vias.len(), closed.vias.len(), "three breaks, three joints");
        let v = Validator::validate(&r, &fader_ctx(1.0), false);
        assert!(v.is_ok(), "{v:?}");
    }

    #[test]
    fn star_matches_the_fader_example() {
        // Reference: motor-coils_3s_0-4mm_star.dxf. Each layer-0 end rises
        // one lead pitch onto a layer-0 neutral bar.
        let r = InfinityBraidPattern.generate(&fader_ctx(2.0)).unwrap();
        assert_layer_one_leads(&r);

        let n = LEAD[0];
        for (i, net) in ["A", "B", "C"].into_iter().enumerate() {
            assert!(has_lead(&r, net, 0, (BREAK_X[i], 8.0), (BREAK_X[i], n)));
        }
        assert!(has_lead(&r, "A", 0, (BREAK_X[0], n), (BREAK_X[1], n)));
        assert!(has_lead(&r, "C", 0, (BREAK_X[1], n), (BREAK_X[2], n)));
        assert_eq!(r.segments.iter().filter(|s| !s.is_active).count(), 11);

        let closed = InfinityBraidPattern.generate(&fader_ctx(0.0)).unwrap();
        assert_eq!(r.vias.len(), closed.vias.len() - 3, "no vias in the neutral");
        assert!(Validator::validate(&r, &fader_ctx(2.0), false).is_ok());
    }

    /// Copper graph over every net's lead traces and vias (the star neutral
    /// joins different nets, so nets are ignored here).
    fn lead_graph(segments: &[RouteSegment], vias: &[Via]) -> HashMap<NodeKey, Vec<NodeKey>> {
        let mut g: HashMap<NodeKey, Vec<NodeKey>> = HashMap::new();
        let mut link = |a: NodeKey, b: NodeKey| {
            g.entry(a).or_default().push(b);
            g.entry(b).or_default().push(a);
        };
        for s in segments.iter().filter(|s| !s.is_active) {
            link(node(s.layer, s.start), node(s.layer, s.end));
        }
        for v in vias {
            link(node(v.from_layer, v.position), node(v.to_layer, v.position));
        }
        g
    }

    fn reaches(g: &HashMap<NodeKey, Vec<NodeKey>>, from: NodeKey, to: NodeKey) -> bool {
        let mut seen = std::collections::HashSet::from([from]);
        let mut stack = vec![from];
        while let Some(n) = stack.pop() {
            if n == to {
                return true;
            }
            for m in g.get(&n).into_iter().flatten() {
                if seen.insert(*m) {
                    stack.push(*m);
                }
            }
        }
        false
    }

    #[test]
    fn star_neutral_joins_every_layer_zero_end_on_layer_zero() {
        let r = InfinityBraidPattern.generate(&fader_ctx(2.0)).unwrap();
        let end = |i: usize, layer: u32| node(layer, Point::new(BREAK_X[i], 8.0));
        let g = lead_graph(&r.segments, &r.vias);
        for i in 1..3 {
            assert!(reaches(&g, end(0, 0), end(i, 0)), "phase {i} layer-0 end on the neutral");
        }
        for i in 0..3 {
            assert!(!reaches(&g, end(i, 1), end(0, 0)), "lead {i} stays off the neutral");
        }

        // B's stub must stay on layer 0: on layer 1 it would lie on B's own
        // lead riser and leave B's layer-0 end off the neutral.
        let mut moved = r.segments.clone();
        let stub = moved
            .iter_mut()
            .find(|s| s.net == "B" && s.layer == 0 && !s.is_active)
            .unwrap();
        stub.layer = 1;
        let g = lead_graph(&moved, &r.vias);
        assert!(!reaches(&g, end(1, 0), end(0, 0)));
    }

    #[test]
    fn validator_rejects_a_stray_via_above_the_board() {
        let mut r = InfinityBraidPattern.generate(&fader_ctx(1.0)).unwrap();
        r.vias.push(Via {
            position: Point::new(20.0, 9.0),
            from_layer: 0,
            to_layer: 1,
            net: "A".to_string(),
        });
        assert!(Validator::validate(&r, &fader_ctx(1.0), false).is_err());
    }

    #[test]
    fn leads_never_tighter_than_trace_plus_space() {
        let mut c = fader_ctx(1.0);
        c.min_trace_mm = 0.4;
        c.min_space_mm = 0.4;
        let r = InfinityBraidPattern.generate(&c).unwrap();
        let mut ys: Vec<f64> = r
            .segments
            .iter()
            .filter(|s| !s.is_active && s.layer == 0 && s.start.y == s.end.y)
            .map(|s| s.start.y)
            .collect();
        ys.sort_by(f64::total_cmp);
        assert!((ys[0] - 8.8).abs() < 1e-9);
        assert!(ys.windows(2).all(|w| (w[1] - w[0] - 0.8).abs() < 1e-9));
    }

    #[test]
    fn validator_still_rejects_active_copper_off_the_board() {
        let mut r = InfinityBraidPattern.generate(&fader_ctx(1.0)).unwrap();
        let lead = r.segments.iter_mut().find(|s| !s.is_active).unwrap();
        lead.is_active = true;
        assert!(Validator::validate(&r, &fader_ctx(1.0), false).is_err());
    }

    #[test]
    fn rejects_a_routing_span_shorter_than_one_pole_pitch() {
        let mut short = magnet_ctx();
        short.active_area_length_mm = 5.0;
        let error = InfinityBraidPattern.generate(&short).unwrap_err();
        assert_eq!(error.kind, RoutingErrorKind::Generation);
        assert!(error.message.contains("cannot fit one complete pole-pitched"));
    }

    #[test]
    fn fallback_report_exposes_period_without_claiming_magnet_alignment() {
        let report = crate::generate_routing_report(&ctx(), "infinity-braid")
            .expect("fallback braid report");
        assert!(report.dimensions.pole_pitch_mm.is_none());
        assert_eq!(report.dimensions.period_count, Some(4));
        assert!(report.dimensions.period_pitch_mm.unwrap() > 0.0);
    }

    #[test]
    fn compact_interleave_covers_both_ends_for_all_connection_modes() {
        // The doubled phase offset formerly passed interior/force checks while
        // leaving gaps at the finite winding's ends. Check the actual via rows,
        // not just the declared band metadata, including a negative control.
        for strands in [2, 3, 5] {
            for magnet_pitch in [None, Some(6.0)] {
                for connection in [0.0, 1.0, 2.0] {
                    let mut context = fader_ctx(connection);
                    context.active_area_length_mm = 92.0;
                    context.magnet_pitch_mm = magnet_pitch;
                    context.params.insert("num_strands".into(), strands as f64);
                    let layout = resolve_braid_layout(&context, 92.0, magnet_pitch, 3, strands).unwrap();
                    let result = InfinityBraidPattern.generate(&context).unwrap();
                    let mut row: Vec<_> = result.vias.iter()
                        .filter(|v| (v.position.y - context.board_width_mm / 2.0).abs() < 1e-10)
                        .map(|v| (v.position.x, v.net.clone())).collect();
                    row.sort_by(|a, b| a.0.total_cmp(&b.0));
                    let count = (3 * strands) as usize;
                    assert_eq!(row.len(), 2 * count);
                    let uniform = |points: &[(f64, String)]| points.windows(2)
                        .all(|p| ((p[1].0 - p[0].0) - layout.o.abs()).abs() < 1e-10);
                    assert!(uniform(&row[..count]), "left end: strands={strands}, pitch={magnet_pitch:?}, connection={connection}");
                    assert!(uniform(&row[count..]), "right end: strands={strands}, pitch={magnet_pitch:?}, connection={connection}");
                    assert!(Validator::validate(&result, &context, false).is_ok());

                    // Reproduce a496f71's extra bundle shift on each phase.
                    let mut widened = row.clone();
                    for (x, phase) in &mut widened {
                        let index = PHASE_NAMES.iter().position(|&name| name == phase).unwrap();
                        *x += index as f64 * strands as f64 * layout.o.abs();
                    }
                    widened.sort_by(|a, b| a.0.total_cmp(&b.0));
                    assert!(!uniform(&widened[..count]));
                    assert!(!uniform(&widened[count..]));
                }
            }
        }
    }

    #[test]
    fn via_x_spacing_is_uniform_across_phase_boundaries_on_both_layers() {
        let context = magnet_ctx();
        let result = InfinityBraidPattern.generate(&context).unwrap();
        let phases = context.phases as usize;
        let strands = context.param("num_strands", 5.0) as usize;
        let vias_per_phase = result.vias.len() / phases;
        let phase_vias: Vec<&[Via]> = result.vias.chunks(vias_per_phase).collect();
        let expected_step = context.magnet_pitch().unwrap() / (phases * strands) as f64;

        // The first `num_strands` vias in each phase are its left-side
        // endpoints. They form the horizontal via grid shared by the top and
        // bottom layer copies. The boundary between phase i and phase i+1
        // must be the same as the final within-phase step.
        for phase in 0..phases {
            let left = &phase_vias[phase][..strands];
            let within_phase = (left[strands - 1].position.x - left[strands - 2].position.x).abs();
            assert!((within_phase - expected_step).abs() < 1e-12);

            if let Some(next) = phase_vias.get(phase + 1) {
                let across_phases =
                    (next[0].position.x - left[strands - 1].position.x).abs();
                assert!((across_phases - within_phase).abs() < 1e-12);
                let start_step = next[0].position.x - left[0].position.x;
                assert!((start_step - context.magnet_pitch().unwrap() / 3.0).abs() < 1e-12);
            }
        }

        // Both layer copies use the same via coordinates. Check the explicit
        // 0 → 1 via rows as well as the phase-grid relationship above.
        assert!(result
            .vias
            .iter()
            .all(|via| via.from_layer == 0 && via.to_layer == 1));
    }
}
