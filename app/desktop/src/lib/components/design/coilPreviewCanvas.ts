/**
 * coilPreviewCanvas.ts
 * ============================================================================
 * Canvas paint routines for the coil preview (extracted from
 * CoilPreview.svelte, which now only builds the per-tick `CoilPreviewDrawInput`
 * snapshot and owns the frame/canvas refs + ResizeObserver sizing).
 *
 * Everything drawn in one tick lives in `CoilPreviewRenderer.draw`:
 *   - the dark PCB panel + active-copper band,
 *   - pole-region zones (behind the traces),
 *   - per-phase traces (active conductors, end-turns, vias, corner arcs),
 *   - the mover magnet strip,
 *   - routing_dimensions overlays (pole-pitch ruler, band-width brackets,
 *     lightbox measure ruler),
 *   - the legend + disclaimer overlays.
 *
 * Draw ops happen in two coordinate spaces:
 *  1. world metres (y-up) under `scale(s, -s)` for the schematic itself;
 *     screen-constant strokes are `screenPx / s` wide so they don't
 *     fatten when zoomed (the canvas equivalent of non-scaling-stroke).
 *  2. virtual 760×260 csspx under `setTransform(k, …)` for the legend and
 *     disclaimer overlays that must not move with the world.
 *
 * Introspection counters. These are NOT Svelte `$state`: draw() runs inside
 * an `$effect` in the component, and writing reactive state from an effect
 * reschedules the effect (Svelte retries the flush ~1000×), i.e. a full
 * repaint storm on load. Plain locals + imperative `canvas.dataset` writes
 * give e2e/debug hooks with zero reactivity feedback. `#revision` is a single
 * shared counter across the inline and modal canvases (one renderer instance
 * per CoilPreview); `drawnSegments`/`drawnVias` are per-draw locals written to
 * whatever canvas was passed in.
 */

import type { CoilArcDto, CoilPathDto, CoilSegmentDto } from "../../types";
import {
  computeMeasureRuler,
  formatMarginMm,
  formatMetresMm,
  type BandWidthRow,
  type MagnetStrip,
  type PolePitchRuler,
  type PoleRegionZone,
  type Point2D,
  type PreviewGeometry,
} from "../../previewGeometry";
import type { WorldTransform } from "../../chart";
import { arcSvgPath, splineSvgPath } from "../../curvePaths";

/** Virtual drawing-space width (the canvas maps to 760 virtual px). */
export const PREVIEW_W = 760;
/** Virtual drawing-space height (the canvas maps to 260 virtual px). */
export const PREVIEW_H = 260;

/** Trace colours, one per phase (cycled by `phase_idx`). */
export const PHASE_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6"];

// Pole-region zone fills. Alternating red/blue by `pole_index` parity,
// translucent so the winding traces stay readable above them.
const POLE_REGION_EVEN_FILL = "rgba(248, 113, 113, 0.18)"; // red-400
const POLE_REGION_ODD_FILL = "rgba(96, 165, 250, 0.18)"; // blue-400

/** Measure-ruler overlay points the component passes in from the lightbox. */
export interface CoilPreviewMeasureOverlay {
  p1: Point2D | null;
  p2: Point2D | null;
  cursor: Point2D | null;
}

/** Per-tick snapshot of everything the canvas paints from. */
export interface CoilPreviewDrawInput {
  coils: CoilPathDto | null;
  /** Active-copper band length, in mm (config.active_area_length_mm). */
  activeAreaLengthMm: number;
  /** Layout constants (board rect, magnet top, …) from previewGeometry. */
  geometry: PreviewGeometry;
  /** World→virtual camera transform for the current zoom. */
  worldTransform: WorldTransform;
  /** Current pan offsets, virtual px (from the gesture utility). */
  panX: number;
  panY: number;
  /** Magnet strip shifted to the shared mover position. */
  visibleMagnets: readonly MagnetStrip[];
  /** Segments/arcs after the one-section filter, keyed by phase*1000+layer. */
  visibleSegments: ReadonlyMap<number, readonly CoilSegmentDto[]>;
  visibleArcs: ReadonlyMap<number, readonly CoilArcDto[]>;
  /** Phase/layer trace visibility predicates (component presentation state). */
  isPhaseVisible: (phaseIdx: number) => boolean;
  isLayerVisible: (layerIdx: number) => boolean;
  isCoilLayerVisible: (coil: string, layerIdx: number) => boolean;
  showVias: boolean;
  traceMode: "traces" | "centerlines";
  traceWidthMm: number;
  viaDrillMm: number;
  viaAnnularRingMm: number;
  /** Pole-pitch ruler + toggle (ruler null without a routing sidecar). */
  poleRuler: PolePitchRuler | null;
  showPolePitch: boolean;
  /** Band-width rows already filtered by visibility + one-section window. */
  bandRows: readonly BandWidthRow[];
  /** Pole-region zones already filtered by visibility + phase picker. */
  poleRegions: readonly PoleRegionZone[];
  /** Measure-ruler state, or null when the lightbox is closed/mode off. */
  measure: CoilPreviewMeasureOverlay | null;
}

/**
 * One-section filter for band rows: show only rows anchored inside the
 * currently kept (first-N-active) conductor x-window for their phase.
 */
export function bandRowInOnePeriod(
  row: BandWidthRow,
  oneSection: boolean,
  visibleSegments: ReadonlyMap<number, CoilSegmentDto[]>,
): boolean {
  if (!oneSection) return true;
  const segs = visibleSegments.get(row.phaseIdx * 1000 + row.layer);
  if (!segs || segs.length === 0) return false;
  let minX = Infinity;
  let maxX = -Infinity;
  for (const seg of segs) {
    if (!seg.is_active) continue;
    minX = Math.min(minX, seg.start[0], seg.end[0]);
    maxX = Math.max(maxX, seg.start[0], seg.end[0]);
  }
  if (!Number.isFinite(minX)) return false;
  return row.anchorX >= minX && row.anchorX <= maxX;
}

/**
 * Owns one draw-revision counter shared by the inline and modal canvases.
 * The component instantiates it once and calls `draw` from its draw effect.
 */
export class CoilPreviewRenderer {
  #revision = 0;

  draw(
    frame: HTMLDivElement,
    canvas: HTMLCanvasElement,
    input: CoilPreviewDrawInput,
  ): void {
    if (frame.clientWidth <= 0) return;
    const viewportHeight = PREVIEW_W * frame.clientHeight / frame.clientWidth;
    this.#revision += 1;
    const drawRevision = this.#revision;
    let drawnSegments = 0;
    let drawnVias = 0;
    let drawnBandWidths = 0;
    let drawnPoleRegions = 0;
    const coils = input.coils;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const k = (frame.clientWidth / PREVIEW_W) * dpr; // virtual px → device px
    ctx.setTransform(k, 0, 0, k, 0, 0);
    ctx.clearRect(0, 0, PREVIEW_W, viewportHeight);
    // Page panel behind the (same-coloured) board rect.
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, PREVIEW_W, viewportHeight);

    if (!coils) {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "14px sans-serif";
      ctx.fillStyle = "#64748b";
      ctx.fillText("Awaiting coil generation…", PREVIEW_W / 2, viewportHeight / 2);
      drawnSegments = 0;
      drawnVias = 0;
      canvas.dataset.segments = "0";
      canvas.dataset.vias = "0";
      canvas.dataset.polePitch = "0";
      canvas.dataset.bandWidths = "0";
      canvas.dataset.poleRegions = "0";
      canvas.dataset.revision = String(drawRevision);
      return;
    }

    // World metres, y-up (scale(s, -s) flips y).
    const wt = input.worldTransform;
    const s = wt.s;
    const g = input.geometry;
    // World geometry uses a y-up transform. Canvas text would be upside down
    // under `scale(s, -s)`, so dimension captions are painted in the virtual
    // screen space after converting their world anchor explicitly.
    const worldToVirtual = (x: number, y: number): [number, number] => [
      wt.tx + input.panX + x * s,
      wt.ty + input.panY - y * s,
    ];
    const drawWorldCaption = (
      text: string,
      x: number,
      y: number,
      color: string,
      align: CanvasTextAlign = "center",
    ): void => {
      const [vx, vy] = worldToVirtual(x, y);
      ctx.save();
      ctx.setTransform(k, 0, 0, k, 0, 0);
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = color;
      ctx.font = "9px sans-serif";
      ctx.textAlign = align;
      ctx.textBaseline = "alphabetic";
      ctx.fillText(text, vx, vy);
      ctx.restore();
    };
    ctx.translate(wt.tx + input.panX, wt.ty + input.panY);
    ctx.scale(s, -s);

    let segments = 0;
    let vias = 0;

    // Dark PCB panel: fill + slate stroke, 1 screen px.
    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1 / s;
    ctx.setLineDash([]);
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
      ctx.roundRect(
        g.boardRect.x,
        g.boardRect.y,
        g.boardRect.w,
        g.boardRect.h,
        0.0015,
      );
    } else {
      // roundRect is not available in every engine — fall back to a plain rect.
      ctx.rect(g.boardRect.x, g.boardRect.y, g.boardRect.w, g.boardRect.h);
    }
    ctx.fill();
    ctx.stroke();

    // Active-copper band (always on): the copper active area — the full
    // routing domain the traces route across (the braid's end turns are
    // part of the pattern). The mover travels over this whole span.
    {
      const ax = 0;
      const aw = input.activeAreaLengthMm / 1000;
      if (aw > 0 && ax + aw <= g.boardRect.x + g.boardRect.w) {
        const ay = g.boardRect.y;
        const ah = g.boardRect.h;
        ctx.fillStyle = "rgba(52, 211, 153, 0.07)";
        ctx.fillRect(ax, ay, aw, ah);
        ctx.strokeStyle = "rgba(52, 211, 153, 0.55)";
        ctx.lineWidth = 1 / s;
        ctx.setLineDash([0.0012, 0.0012]);
        ctx.strokeRect(ax, ay, aw, ah);
        ctx.setLineDash([]);
      }
    }

    // Pole-region zones (pattern-owned phase/pole boundaries). Painted here,
    // BEHIND the traces, so the translucent alternating red/blue bands tint
    // the board without hiding the winding. Bands fill the board's y extent
    // and the sidecar's authoritative x boundaries — never the magnet config.
    if (input.poleRegions.length > 0) {
      const zoneY = g.boardRect.y;
      const zoneH = g.boardRect.h;
      for (const zone of input.poleRegions) {
        ctx.fillStyle =
          zone.polarity > 0 ? POLE_REGION_EVEN_FILL : POLE_REGION_ODD_FILL;
        ctx.fillRect(zone.x0, zoneY, zone.x1 - zone.x0, zoneH);
        drawnPoleRegions += 1;
      }
    }

    // Per-phase schematic layers, overlaid at their true coordinates.
    for (const ph of coils.phases) {
      if (!input.isPhaseVisible(ph.phase_idx) || !input.isLayerVisible(ph.layer_idx) || !input.isCoilLayerVisible(ph.phase_name, ph.layer_idx))
        continue;
      const layerOpacity = Math.max(0.35, 1 - ph.layer_idx * 0.15);
      const color = PHASE_COLORS[ph.phase_idx % PHASE_COLORS.length];
      const segs =
        input.visibleSegments.get(ph.phase_idx * 1000 + ph.layer_idx) ??
        ph.segments;
      const arcs =
        input.visibleArcs.get(ph.phase_idx * 1000 + ph.layer_idx) ??
        ph.corner_arcs ??
        [];

      const centerlines = input.traceMode === "centerlines";
      const band = coils.routing_dimensions?.phase_band_widths.find(
        (row) => row.layer === ph.layer_idx && row.net === ph.phase_name,
      );
      // Copper width stays constant in world metres, independent of camera zoom.
      const traceWidth = band?.trace_width_m ?? coils.trace_width_m ?? input.traceWidthMm / 1000;
      const lineWidth = centerlines ? 1 / s : traceWidth;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // a. Active conductors.
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.setLineDash([]);
      ctx.globalAlpha = layerOpacity;
      ctx.beginPath();
      for (const seg of segs) {
        if (!seg.is_active) continue;
        ctx.moveTo(seg.start[0], seg.start[1]);
        ctx.lineTo(seg.end[0], seg.end[1]);
        segments += 1;
      }
      ctx.stroke();

      // b. End-turns are dashed only in centerline mode.
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.setLineDash(centerlines ? [3 / s, 2 / s] : []);
      ctx.globalAlpha = layerOpacity;
      ctx.beginPath();
      for (const seg of segs) {
        if (seg.is_active) continue;
        ctx.moveTo(seg.start[0], seg.start[1]);
        ctx.lineTo(seg.end[0], seg.end[1]);
        segments += 1;
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // d. Corner arcs use the same copper width as straight traces.
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      for (const arc of arcs) {
        ctx.setLineDash(centerlines && !arc.is_active ? [3 / s, 2 / s] : []);
        ctx.globalAlpha = layerOpacity;
        ctx.stroke(new Path2D(arcSvgPath({
          start: { x: arc.start[0], y: arc.start[1] },
          mid: { x: arc.mid[0], y: arc.mid[1] },
          end: { x: arc.end[0], y: arc.end[1] },
          layer: ph.layer_idx, net: ph.phase_name, is_active: arc.is_active ?? false,
        })));
      }
      for (const spline of ph.splines ?? []) {
        ctx.setLineDash(centerlines && !spline.is_active ? [3 / s, 2 / s] : []);
        ctx.globalAlpha = layerOpacity;
        ctx.lineWidth = lineWidth;
        ctx.stroke(new Path2D(splineSvgPath(spline)));
        segments += 1;
      }
    }

    ctx.lineCap = "butt";
    ctx.lineJoin = "miter";

    // Paint pads and drill holes after all traces so other layers cannot
    // obscure the holes. Shared via coordinates are drawn only once.
    if (input.showVias) {
      const seen = new Set<string>();
      const drillRadius = Math.max(0, input.viaDrillMm / 2) * 1e-3;
      const padRadius = drillRadius + Math.max(0, input.viaAnnularRingMm) * 1e-3;
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 0.000025;
      for (const ph of input.coils.phases) {
        if (!input.isPhaseVisible(ph.phase_idx) || !input.isLayerVisible(ph.layer_idx) || !input.isCoilLayerVisible(ph.phase_name, ph.layer_idx)) continue;
        for (const [vx, vy] of ph.via_positions ?? []) {
          const key = `${vx},${vy}`;
          if (seen.has(key)) continue;
          seen.add(key);
          ctx.fillStyle = "#fbbf24";
          ctx.beginPath();
          ctx.arc(vx, vy, padRadius, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = "#020617";
          ctx.beginPath();
          ctx.arc(vx, vy, drillRadius, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          vias += 1;
        }
      }
    }

    // Magnet array overlay along the top edge of the fitted region. The bars
    // track the shared mover position (shifted by `motion.offsetFromRestMm`),
    // so the strip slides over the fixed stator zones as the slider moves.
    for (const mag of input.visibleMagnets) {
      ctx.globalAlpha = 0.7;
      ctx.fillStyle = mag.pole > 0 ? "#f97316" : "#3b82f6";
      // Paint the configured solid width exactly. A fixed 0.5 mm inset here
      // adds an unmodelled gap and moves the visible pole centre away from the
      // leg-zone anchor.
      ctx.fillRect(mag.x, g.magnetTop, Math.max(mag.w, 0.0005), 0.003);
    }
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);

    // -----------------------------------------------------------------
    // routing_dimensions overlays — still in world metres, under the same
    // transform, so they pan/zoom WITH the schematic. Dimension strokes are
    // screen-constant; captions are converted to upright virtual-screen text.
    // -----------------------------------------------------------------
    // a. Pole-pitch / repeat-period dimension ruler (sidecar, no own
    //    origin → aligned to the first magnet centre + one pitch).
    if (input.showPolePitch && input.poleRuler) {
      const r = input.poleRuler;
      const tick = 0.0012;
      const labelY = r.y + tick + 0.0004;
      ctx.globalAlpha = 0.95;
      ctx.setLineDash([]);
      ctx.strokeStyle = "#a5b4fc"; // indigo-300: ruler line
      ctx.fillStyle = "#cbd5e1";
      ctx.lineWidth = 1.4 / s;
      // Double-ended baseline between the two magnet centres.
      ctx.beginPath();
      ctx.moveTo(r.x1, r.y);
      ctx.lineTo(r.x2, r.y);
      // End ticks (+y side; the magnet strip sits below the ruler).
      ctx.moveTo(r.x1, r.y);
      ctx.lineTo(r.x1, r.y + tick);
      ctx.moveTo(r.x2, r.y);
      ctx.lineTo(r.x2, r.y + tick);
      ctx.stroke();
      // Centre markers at each end.
      ctx.fillStyle = "#a5b4fc";
      for (const x of [r.x1, r.x2]) {
        ctx.beginPath();
        ctx.arc(x, r.y, 0.00035, 0, Math.PI * 2);
        ctx.fill();
      }
      // Caption (mm), honestly labelled. Paint it upright in virtual space;
      // the world group is y-flipped for the schematic geometry.
      drawWorldCaption(
        `${r.label} ${formatMetresMm(r.pitchM)}`,
        (r.x1 + r.x2) / 2,
        labelY,
        "#cbd5e1",
      );
    }

    // b. Band-width diagnostics — one bracket per matched (layer, net).
    //    Rows arrive pre-filtered by phase/layer visibility and the
    //    one-section window (`bandRowInOnePeriod`).
    if (input.bandRows.length > 0) {
      const endTick = 0.0005;
      const labelRaise = endTick + 0.0005;
      for (const row of input.bandRows) {
        const halfM = Math.max(row.bandM / 2, 0.0004);
        // Negative margin → red over-budget; ok margin → green; no top-down
        // limit known → amber/grey.
        const strokeColor =
          row.status === "over-budget"
            ? "#f87171"
            : row.status === "ok"
              ? "#34d399"
              : "#fbbf24";
        const maxHalfM =
          row.maxM !== null && row.maxM > 0
            ? Math.max(row.maxM / 2, 0.0004)
            : null;
        ctx.globalAlpha = 0.9;
        // Optional top-down maximum: a dashed neutral reference bracket.
        if (maxHalfM !== null) {
          ctx.setLineDash([3 / s, 2 / s]);
          ctx.strokeStyle = "#94a3b8";
          ctx.lineWidth = 0.8 / s;
          ctx.beginPath();
          ctx.moveTo(row.anchorX - maxHalfM, row.y);
          ctx.lineTo(row.anchorX + maxHalfM, row.y);
          ctx.stroke();
        }

        ctx.setLineDash([]);
        ctx.strokeStyle = strokeColor;
        ctx.fillStyle = strokeColor;
        ctx.lineWidth = 1.2 / s;
        // Effective-width bracket + short perpendicular end ticks.
        ctx.beginPath();
        ctx.moveTo(row.anchorX - halfM, row.y);
        ctx.lineTo(row.anchorX + halfM, row.y);
        ctx.moveTo(row.anchorX - halfM, row.y);
        ctx.lineTo(row.anchorX - halfM, row.y + endTick);
        ctx.moveTo(row.anchorX + halfM, row.y);
        ctx.lineTo(row.anchorX + halfM, row.y + endTick);
        ctx.stroke();

        // Compact one-line label above the bracket:
        //   L0 A 2.00 mm / max 4.00 mm · Δ +2.00 mm
        const limitText =
          row.maxM === null ? "max —" : `max ${formatMetresMm(row.maxM)}`;
        const marginText =
          row.marginM === null ? "" : ` · Δ ${formatMarginMm(row.marginM)}`;
        drawWorldCaption(
          `L${row.layer} ${row.phaseName} ${formatMetresMm(row.bandM)} / ${limitText}${marginText}`,
          row.anchorX,
          row.y + labelRaise,
          strokeColor,
        );
        drawnBandWidths += 1;
      }
      ctx.globalAlpha = 1;
    }

    // c. Lightbox measure ruler (two-click dimension tool, lightbox only).
    //    Pink to stay distinct from the indigo pole-pitch ruler. The live
    //    preview (start point + cursor) is dashed; the locked dimension is
    //    solid with perpendicular end ticks. Draws only while expanded.
    if (input.measure && input.measure.p1) {
      const measureP1 = input.measure.p1;
      const end = input.measure.p2 ?? input.measure.cursor;
      if (end) {
        const ruler = computeMeasureRuler(measureP1, end);
        const placing = !input.measure.p2;
        const tick = 0.0012;
        const dx = ruler.p2.x - ruler.p1.x;
        const dy = ruler.p2.y - ruler.p1.y;
        const len = Math.max(Math.hypot(dx, dy), 1e-9);
        const nx = -dy / len;
        const ny = dx / len;
        ctx.globalAlpha = placing ? 0.75 : 0.95;
        ctx.setLineDash(placing ? [4 / s, 3 / s] : []);
        ctx.strokeStyle = "#f472b6"; // pink-400: user measure ruler
        ctx.fillStyle = "#f9a8d4";
        ctx.lineWidth = 1.4 / s;
        ctx.beginPath();
        ctx.moveTo(ruler.p1.x, ruler.p1.y);
        ctx.lineTo(ruler.p2.x, ruler.p2.y);
        // Perpendicular end ticks.
        ctx.moveTo(ruler.p1.x, ruler.p1.y);
        ctx.lineTo(ruler.p1.x + nx * tick, ruler.p1.y + ny * tick);
        ctx.moveTo(ruler.p2.x, ruler.p2.y);
        ctx.lineTo(ruler.p2.x + nx * tick, ruler.p2.y + ny * tick);
        ctx.stroke();
        ctx.setLineDash([]);
        drawWorldCaption(
          formatMetresMm(ruler.mm / 1000),
          ruler.label.x,
          ruler.label.y,
          "#f9a8d4",
        );
        ctx.globalAlpha = 1;
      }
    }

    // -----------------------------------------------------------------
    // Overlays — back in virtual px, so they stay put under pan/zoom.
    // -----------------------------------------------------------------
    ctx.setTransform(k, 0, 0, k, 0, 0);

    // Centerline legend (bottom-left). Copper traces are all solid.
    if (input.traceMode === "centerlines") {
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.font = "11px sans-serif";
    ctx.fillStyle = "#94a3b8";
    ctx.strokeStyle = "#94a3b8";
    ctx.lineWidth = 2.4;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(0, viewportHeight - 8);
    ctx.lineTo(20, viewportHeight - 8);
    ctx.stroke();
    ctx.fillText("active leg", 26, viewportHeight - 4);
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 2]);
    ctx.beginPath();
    ctx.moveTo(170, viewportHeight - 8);
    ctx.lineTo(190, viewportHeight - 8);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText("end-turn", 196, viewportHeight - 4);
    }

    drawnSegments = segments;
    drawnVias = vias;
    canvas.dataset.segments = String(drawnSegments);
    canvas.dataset.traceMode = input.traceMode;
    canvas.dataset.vias = String(drawnVias);
    canvas.dataset.polePitch = String(
      input.showPolePitch && input.poleRuler ? 1 : 0,
    );
    canvas.dataset.bandWidths = String(drawnBandWidths);
    canvas.dataset.poleRegions = String(drawnPoleRegions);
    canvas.dataset.revision = String(drawRevision);
  }
}
