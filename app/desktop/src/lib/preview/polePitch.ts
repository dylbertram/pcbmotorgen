import type { RoutingDimensionsDto } from "../types";
import type { MagnetStrip } from "./previewGeometry";
import { isPositiveFiniteDimension } from "../geometry/dimensionValues";

/** Centre of the first magnet strip segment (world x, in metres). */
export function firstMagnetCenterX(magnets: readonly MagnetStrip[]): number | null {
  const m = magnets[0];
  return m ? m.x + m.w / 2 : null;
}

/** Pitch choice for the dimension ruler, with an honest caption. */
export interface PolePitchValue {
  pitchM: number;
  /** A repeat-period fallback must not be labelled as pole pitch. */
  label: "Pole pitch" | "Repeat period";
}

/** Prefer adjacent-pole pitch; label the repeat-period fallback separately. */
export function computePolePitchValue(
  dimensions: Partial<Pick<RoutingDimensionsDto, "pole_pitch_m" | "period_pitch_m">> | null | undefined,
): PolePitchValue | null {
  if (isPositiveFiniteDimension(dimensions?.pole_pitch_m)) {
    return { pitchM: dimensions.pole_pitch_m, label: "Pole pitch" };
  }
  if (isPositiveFiniteDimension(dimensions?.period_pitch_m)) {
    return { pitchM: dimensions.period_pitch_m, label: "Repeat period" };
  }
  return null;
}

/** World-space geometry for the horizontal double-ended dimension ruler. */
export interface PolePitchRuler {
  label: "Pole pitch" | "Repeat period";
  pitchM: number;
  /** Start, end and baseline in world metres. */
  x1: number;
  x2: number;
  y: number;
}

/** Anchor the sidecar pitch to the first magnet centre and supplied baseline. */
export function computePolePitchRuler(
  dimensions: Partial<Pick<RoutingDimensionsDto, "pole_pitch_m" | "period_pitch_m">> | null | undefined,
  firstCenterX: number | null,
  baselineY: number,
): PolePitchRuler | null {
  const pitch = computePolePitchValue(dimensions);
  if (!pitch || firstCenterX === null) return null;
  return {
    label: pitch.label,
    pitchM: pitch.pitchM,
    x1: firstCenterX,
    x2: firstCenterX + pitch.pitchM,
    y: baselineY,
  };
}
