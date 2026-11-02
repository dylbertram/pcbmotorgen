/**
 * Pure geometry math for the coil preview (shared by the Canvas viewer and
 * available to any future renderer). No Svelte, no DOM — unit-testable.
 *
 * Layers are drawn OVERLAID at their TRUE coordinates (a top-down view,
 * matching the DXF export): there is no schematic exploded-layer offset.
 * Overlapping layers are distinguished with the per-layer show/hide
 * toggles in the viewer, so each copper layer can be inspected alone.
 *
 * `contentBox` = the raw winding footprint; the magnet strip overlay sits
 * 1 mm above the tallest drawn content.
 */

import { unionBounds, type ViewportBBox } from "../chart";
import { computePoleRegionBounds, computePoleRegionZones, type PoleRegionZone } from "./poleRegions";
import type { PolePitchRuler } from "./polePitch";
import type { BandWidthRow } from "./bandWidth";
import type {
  CoilPathDto,
  RoutingDimensionsDto,
} from "../types";

/** The subset of the config the preview geometry depends on. */
export interface PreviewConfigLike {
  magnet_count: number;
  magnet_width_mm: number;
  magnet_gap_mm: number;
}

/** Board panel rectangle (world units) drawn behind the winding. */
export interface BoardRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** All layout constants the canvas viewer needs before drawing. */
export interface PreviewGeometry {
  /** Union of raw winding geometry bounds (true coordinates). */
  footprintBox: ViewportBBox;
  /** Content bounds — layers overlaid, so identical to `footprintBox`. */
  contentBox: ViewportBBox;
  /** y of the magnet strip top edge (1 mm above the tallest content). */
  magnetTop: number;
  /** x-extent of the magnet strip (magnet_count × pitch). */
  magnetSpan: number;
  /** Union of content + magnet strip — what the camera must fit. */
  fitBounds: ViewportBBox;
  /** Dark PCB panel rect (contentBox + 1.5 mm margin). */
  boardRect: BoardRect;
  /** Number of DISTINCT layer indices in the data (what actually renders). */
  renderedLayerCount: number;
}

/** One magnet strip segment (x range + pole polarity). */
export interface MagnetStrip {
  x: number;
  w: number;
  pole: number; // +1 N, -1 S
}

const BOARD_MARGIN_M = 0.0015; // 1.5 mm of panel around the winding
const MAGNET_STRIP_CLEARANCE_M = 0.001; // 1 mm above tallest content
const MAGNET_STRIP_HEIGHT_M = 0.003;

/**
 * Raw winding footprint: bounds of each phase's segments, arcs and spline control points.
 * Layers are overlaid at true coordinates, so this IS the content box.
 */
export function computeFootprintBox(coils: CoilPathDto | null): ViewportBBox {
  const boxes: ViewportBBox[] = [];
  if (coils) {
    for (const ph of coils.phases) {
      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity;
      for (const s of ph.segments) {
        minX = Math.min(minX, s.start[0], s.end[0]);
        maxX = Math.max(maxX, s.start[0], s.end[0]);
        minY = Math.min(minY, s.start[1], s.end[1]);
        maxY = Math.max(maxY, s.start[1], s.end[1]);
      }
      for (const a of ph.corner_arcs ?? []) {
        minX = Math.min(minX, a.start[0], a.mid[0], a.end[0]);
        maxX = Math.max(maxX, a.start[0], a.mid[0], a.end[0]);
        minY = Math.min(minY, a.start[1], a.mid[1], a.end[1]);
        maxY = Math.max(maxY, a.start[1], a.mid[1], a.end[1]);
      }
      for (const spline of ph.splines ?? []) {
        for (const p of spline.control_points) {
          minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
          minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
        }
      }
      if (minX !== Infinity) boxes.push({ minX, minY, maxX, maxY });
    }
  }
  return unionBounds(...boxes);
}

/**
 * X extent of the routed traces in metres, `[firstX, lastX]`, computed from
 * the actual segment/arc points the backend returned — or `null` when no
 * coil payload exists yet. Compare against `config.trace_total_length_mm`
 * to detect preview/reflection dimension drift.
 */
export function traceExtentMetres(coils: CoilPathDto | null): [number, number] | null {
  if (!coils || coils.phases.length === 0) return null;
  const box = computeFootprintBox(coils);
  if (!Number.isFinite(box.minX) || !Number.isFinite(box.maxX)) return null;
  return [box.minX, box.maxX];
}

/** Measured geometry derived from an actual coil payload (all values mm). */
export interface TraceMeasure {
  /** First→last X span of the routed traces. */
  traceLengthMm: number;
  /** Domain-frame X where the traces begin. */
  traceStartMm: number;
}

/**
 * Measure what the routing backend ACTUALLY returned: the trace X extent.
 * The braid floors whole periods, so the measured span is intentionally
 * shorter than the nominal domain (the active area, which IS the routing
 * domain) by up to one period — previews and readouts must use THIS, not
 * the configured numbers. Null when no payload exists.
 */
export function measureTrace(
  coils: CoilPathDto | null,
  _config: PreviewConfigLike,
): TraceMeasure | null {
  const span = traceExtentMetres(coils);
  if (!span) return null;
  return {
    traceLengthMm: (span[1] - span[0]) * 1000,
    traceStartMm: span[0] * 1000,
  };
}

/**
 * Mover-strip bounds in the DOMAIN (routing) frame — THE single anchor
 * shared by the canvas overlay, the iso view, the design reflection AND the
 * position readouts. The strip is centred on the MotionStore's clamped
 * position (absolute track coordinates), so drawn edges always equal
 * position ± mover_span/2 and every printed number agrees with every pixel.
 */
export function stripBoundsDomainMm(
  config: PreviewConfigLike & { mover_span_mm: number },
  motion: { clampedPositionMm: number },
): { startMm: number; endMm: number } {
  const half = config.mover_span_mm / 2;
  return {
    startMm: motion.clampedPositionMm - half,
    endMm: motion.clampedPositionMm + half,
  };
}

/** Full geometry derivation for the preview camera + drawing. */
export function computePreviewGeometry(
  coils: CoilPathDto | null,
  config: PreviewConfigLike,
): PreviewGeometry {
  const footprintBox = computeFootprintBox(coils);

  // Layers are overlaid at their true coordinates (top-down schematic,
  // matching the DXF). contentBox == footprintBox.
  const contentBox: ViewportBBox = { ...footprintBox };

  // Magnet strip sits 1 mm above the tallest drawn content.
  const magnetTop = contentBox.maxY + MAGNET_STRIP_CLEARANCE_M;
  const magnets = computeMagnets(config, coils?.routing_dimensions);
  const magnetWidth = config.magnet_width_mm / 1000;
  const magnetGap = Math.max(config.magnet_gap_mm, 0) / 1000;
  const magnetSpan = Math.max(
    (config.magnet_count - 1) * (magnetWidth + magnetGap) + magnetWidth,
    0.001,
  );
  // Fit the painted solids themselves. Do not include synthetic half-gap
  // margins at either end: that shifts the apparent first-magnet position
  // when the camera is reset, especially for a sidecar-aligned array.
  const magnetStartX = magnets[0]?.x ?? 0;
  const lastMagnet = magnets[magnets.length - 1];
  const magnetEndX = lastMagnet ? lastMagnet.x + lastMagnet.w : magnetStartX + magnetSpan;

  const fitBounds = unionBounds(contentBox, {
    minX: magnetStartX,
    minY: magnetTop,
    maxX: magnetEndX,
    maxY: magnetTop + MAGNET_STRIP_HEIGHT_M,
  });

  const boardRect: BoardRect = {
    x: contentBox.minX - BOARD_MARGIN_M,
    y: contentBox.minY - BOARD_MARGIN_M,
    w: contentBox.maxX - contentBox.minX + 2 * BOARD_MARGIN_M,
    h: contentBox.maxY - contentBox.minY + 2 * BOARD_MARGIN_M,
  };

  const renderedLayerCount = coils
    ? new Set(coils.phases.map((p) => p.layer_idx)).size
    : 0;

  return {
    footprintBox,
    contentBox,
    magnetTop,
    magnetSpan,
    fitBounds,
    boardRect,
    renderedLayerCount,
  };
}

/**
 * Distinct layers present in the data (the per-(phase, layer) coil list is
 * deduped by `layer_idx`), sorted ascending — drives the layer toggles.
 */
export function computeUniqueLayers(
  coils: CoilPathDto | null,
): { idx: number }[] {
  if (!coils) return [];
  const set = new Set<number>();
  for (const ph of coils.phases) set.add(ph.layer_idx);
  return [...set]
    .sort((a, b) => a - b)
    .map((idx) => ({ idx }));
}

/** Geometry summary shared by the viewer header and workspace status bar. */
export function computePreviewSummary(coils: CoilPathDto | null): string {
  if (!coils) return "no coils yet";
  const phases = computeUniquePhases(coils).length;
  const layers = computeUniqueLayers(coils).length;
  return `${phases} phase${phases === 1 ? "" : "s"} · ${layers} layer${layers === 1 ? "" : "s"} · ${coils.phases.length} coil group${coils.phases.length === 1 ? "" : "s"}`;
}

/** First solid-magnet x position for the preview.
 *
 * The phase-band start/end boundaries come from the pattern-owned
 * `pole_regions` sidecar (the routing crate's authoritative phase/pole
 * geometry): each region spans one pole pitch for one phase, and the phases
 * are interleaved by `pole_pitch / phases`. At rest the FIRST magnet bar's
 * CENTRE is anchored to the neutral (second-phase) phase-band centre, so
 * each pole sits symmetrically inside its phase band and every later bar
 * centre lands on the next such phase-band centre automatically (the regions
 * repeat every pole pitch). The anchor is
 * kept on the neutral B phase so the poles read A1 positive, B1 neutral and
 * C1/A2 negative — matching the no-overlap three-phase sequence. Pattern-owned
 * pole regions are the authoritative source for those zone centres. When a
 * legacy payload has no regions, the fallback places each bar in the centre
 * of its configured pitch cell, splitting the configured gap at each cell
 * boundary rather than leaving it all on one side of a bar.
 */
export function computeMagnetStartX(
  config: PreviewConfigLike,
  dimensions:
    | Partial<Pick<RoutingDimensionsDto, "pole_regions">>
    | null
    | undefined = undefined,
): number {
  const widthM = config.magnet_width_mm / 1000;
  const gapM = Math.max(config.magnet_gap_mm, 0) / 1000;
  const pitchM = widthM + gapM;
  if (!Number.isFinite(widthM) || widthM <= 0 || !Number.isFinite(pitchM) || pitchM <= 0) {
    return 0;
  }

  const zones = computePoleRegionZones(dimensions);
  const phaseOrder: string[] = [];
  for (const zone of zones) {
    if (!phaseOrder.includes(zone.phase)) phaseOrder.push(zone.phase);
  }

  const zoneAt = (phase: string, poleIndex: number): PoleRegionZone | null =>
    zones.find((zone) => zone.phase === phase && zone.poleIndex === poleIndex) ?? null;
  const firstZone = (phase: string, poleIndex: number): PoleRegionZone | null =>
    zoneAt(phase, poleIndex) ?? zones.find((zone) => zone.phase === phase) ?? null;
  const centreX = (zone: PoleRegionZone): number => (zone.x0 + zone.x1) / 2;

  // Anchor the FIRST magnet bar's CENTRE on the neutral B1 phase-band
  // centre, so the pole sits inside its phase band with the neutral phase
  // flanked symmetrically by the magnets that surround it. Every later bar
  // centre falls on the next B phase-band centre automatically (B zones
  // repeat every pole pitch). Neither the configured gap nor any end
  // margin can move the first solid bar away from the pattern-owned
  // coordinate.
  if (phaseOrder.length >= 2) {
    const neutral = zoneAt(phaseOrder[1], 0) ?? firstZone(phaseOrder[1], 0);
    if (neutral) {
      const neutralCentre = centreX(neutral);
      if (Number.isFinite(neutralCentre)) {
        return neutralCentre - widthM / 2;
      }
    }
  }

  // Neutral phase absent from a three-phase sidecar: fall back to the
  // equivalent C1/A2 midpoint (the negative-pole phase-band centre). The
  // first N bar centre sits one full pitch before that midpoint.
  if (phaseOrder.length === 3) {
    const c1 = zoneAt(phaseOrder[2], 0);
    const a2 = zoneAt(phaseOrder[0], 1);
    if (c1 && a2) {
      const negativeMagnetCentre = (centreX(c1) + centreX(a2)) / 2;
      if (Number.isFinite(negativeMagnetCentre)) {
        return negativeMagnetCentre - pitchM - widthM / 2;
      }
    }
  }

  // No pattern-owned zones: centre each solid bar in its pitch cell.  This
  // preserves the old origin while splitting the configured gap at the array
  // boundaries for legacy/mock payloads.
  return gapM / 2;
}

/** Magnet array overlay: count × pitch segments, alternating polarity. */
export function computeMagnets(
  config: PreviewConfigLike,
  dimensions:
    | Partial<Pick<RoutingDimensionsDto, "pole_regions">>
    | null
    | undefined = undefined,
): MagnetStrip[] {
  const arr: MagnetStrip[] = [];
  const pitch = (config.magnet_width_mm + Math.max(config.magnet_gap_mm, 0)) / 1000;
  const mw = config.magnet_width_mm / 1000;
  const firstX = computeMagnetStartX(config, dimensions);
  for (let i = 0; i < config.magnet_count; i++) {
    arr.push({ x: firstX + i * pitch, w: mw, pole: i % 2 === 0 ? 1 : -1 });
  }
  return arr;
}

/**
 * Distinct phases present in the data, keyed by `phase_idx` (dedupes the
 * per-(phase, layer) coil list), sorted by index.
 */
export function computeUniquePhases(
  coils: CoilPathDto | null,
): { idx: number; name: string; colorIdx: number }[] {
  if (!coils) return [];
  const byIdx: Record<number, { idx: number; name: string; colorIdx: number }> = {};
  for (const ph of coils.phases) {
    if (!(ph.phase_idx in byIdx)) {
      byIdx[ph.phase_idx] = {
        idx: ph.phase_idx,
        name: ph.phase_name,
        colorIdx: ph.phase_idx,
      };
    }
  }
  return Object.values(byIdx).sort((a, b) => a.idx - b.idx);
}

/** World-space box the pole-pitch ruler occupies (camera-fit input). */
function polePitchRulerBounds(ruler: PolePitchRuler): ViewportBBox {
  const padX = Math.max(ruler.pitchM * 0.1, 0.001);
  return {
    minX: ruler.x1 - padX,
    minY: ruler.y - 0.004,
    maxX: ruler.x2 + padX,
    maxY: ruler.y + 0.004,
  };
}

/** World-space box a band-width row occupies (camera-fit input). */
function bandWidthRowBounds(row: BandWidthRow): ViewportBBox {
  // Include the optional top-down limit too: the canvas draws it as a dashed
  // reference bracket so a generous phase band cannot be clipped at reset.
  const extentM = Math.max(row.bandM, row.maxM ?? 0);
  const half = Math.max(extentM / 2, 0.0005);
  return {
    minX: row.anchorX - half,
    minY: row.y - 0.002,
    maxX: row.anchorX + half,
    maxY: row.y + 0.002,
  };
}

/**
 * Expand the schematic fit box to cover the active overlays, so the camera
 * reset never clips the ruler or band brackets (rows live inside the content
 * box already, but the ruler floats above the magnet strip). Pole-region
 * zones (optional, `regionZones`) are also included bounded to a caller-
 * supplied board y band so a zone poking past the nominal domain is not
 * clipped at reset.
 */
export function computeOverlayFitBounds(
  base: ViewportBBox,
  ruler: PolePitchRuler | null,
  rows: readonly BandWidthRow[],
  regionZones: readonly PoleRegionZone[] = [],
  regionYMin = 0,
  regionYMax = 0,
): ViewportBBox {
  const boxes: ViewportBBox[] = [base];
  if (ruler) boxes.push(polePitchRulerBounds(ruler));
  for (const row of rows) boxes.push(bandWidthRowBounds(row));
  const zoneBox = computePoleRegionBounds(regionZones, regionYMin, regionYMax);
  if (zoneBox) boxes.push(zoneBox);
  return unionBounds(...boxes);
}

/**
 * Expand the schematic fit box to cover the magnet strip when the mover is
 * translated by `offsetM` metres. The strip translates monolithically, so
 * its two extremes are the resting position (0) and the far end of travel
 * (`offsetM`); unioning both with the base box keeps the reset-view camera
 * from clipping the moved strip. Returns the base box when there are no
 * magnets or the offset is not usable.
 */
export function computeMoverStripBounds(
  base: ViewportBBox,
  magnets: readonly MagnetStrip[],
  offsetM: number,
  yTop: number,
  stripHeightM: number,
): ViewportBBox {
  if (magnets.length === 0 || !Number.isFinite(offsetM) || offsetM < 0) return base;
  let minX = Infinity;
  let maxX = -Infinity;
  for (const m of magnets) {
    minX = Math.min(minX, m.x + offsetM);
    maxX = Math.max(maxX, m.x + m.w + offsetM);
  }
  if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return base;
  return unionBounds(base, {
    minX,
    minY: yTop,
    maxX,
    maxY: yTop + stripHeightM,
  });
}
