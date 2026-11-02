import type { CoilPathDto, PhaseCoilDto, RoutingDimensionsDto } from "../types";
import { isValidMetres } from "./dimensionValues";

const MARGIN_EPS = 1e-12;

export type BandWidthStatus = "over-budget" | "ok" | "no-limit";

/** Sidecar diagnostic anchored to the matched phase geometry, in metres. */
export interface BandWidthRow {
  phaseIdx: number;
  layer: number;
  phaseName: string;
  anchorX: number;
  y: number;
  bandM: number;
  maxM: number | null;
  marginM: number | null;
  status: BandWidthStatus;
}

function medianValues(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Median active-conductor x (start/end) of a phase coil, in metres. */
export function medianActiveConductorX(coil: PhaseCoilDto): number | null {
  const xs: number[] = [];
  for (const seg of coil.segments) {
    if (!seg.is_active) continue;
    xs.push(seg.start[0], seg.end[0]);
  }
  return medianValues(xs);
}

function medianActiveY(coil: PhaseCoilDto): number | null {
  const ys: number[] = [];
  for (const seg of coil.segments) {
    if (!seg.is_active) continue;
    ys.push(seg.start[1], seg.end[1]);
  }
  return medianValues(ys);
}

/** Match sidecar widths to phase coils and anchor rows to active conductors. */
export function computeBandWidthRows(
  coils: CoilPathDto | null,
  dimensions: Pick<RoutingDimensionsDto, "phase_band_widths"> | null | undefined,
  rowStrideM = 0.001,
): BandWidthRow[] {
  if (!coils || !dimensions?.phase_band_widths) return [];
  const byKey = new Map<string, PhaseCoilDto>();
  for (const ph of coils.phases) byKey.set(`${ph.layer_idx}|${ph.phase_name}`, ph);

  const rows: BandWidthRow[] = [];
  for (const band of dimensions.phase_band_widths) {
    if (!isValidMetres(band.band_width_m)) continue;
    const phase = byKey.get(`${band.layer}|${band.net}`);
    if (!phase) continue;
    const anchorX = medianActiveConductorX(phase);
    const railY = medianActiveY(phase);
    if (anchorX === null || railY === null) continue;

    // Zero or negative limits expose over-budget routing, not a missing limit.
    const maxM =
      typeof band.max_band_width_m === "number" && Number.isFinite(band.max_band_width_m)
        ? band.max_band_width_m
        : null;
    let marginM: number | null = null;
    if (maxM !== null) {
      marginM =
        typeof band.margin_m === "number" && Number.isFinite(band.margin_m)
          ? band.margin_m
          : maxM - band.band_width_m;
    }
    rows.push({
      phaseIdx: phase.phase_idx,
      layer: band.layer,
      phaseName: band.net,
      anchorX,
      y: railY,
      bandM: band.band_width_m,
      maxM,
      marginM,
      status:
        maxM === null
          ? "no-limit"
          : (marginM ?? 0) >= -MARGIN_EPS
            ? "ok"
            : "over-budget",
    });
  }

  rows.sort((a, b) => a.layer - b.layer || a.phaseIdx - b.phaseIdx);
  const n = rows.length;
  rows.forEach((row, i) => {
    row.y += (i - (n - 1) / 2) * rowStrideM;
  });
  return rows;
}
