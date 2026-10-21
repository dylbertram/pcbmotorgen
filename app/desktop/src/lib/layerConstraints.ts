/**
 * UI input constraints derived from IPC-provided pattern metadata.
 *
 * These helpers shape WHAT THE UI OFFERS (layer-selector options, snapping,
 * input hints) — they are input enablement, NOT validation. The authoritative
 * rules stay in Rust: the app config validates `num_layers` (even, >= 2,
 * <= max_layers) in `src-tauri/src/config/validation.rs`, and the routing
 * crate validates the pattern's layer range + parameter multiples at
 * generate time (`validate_layer_range` / `validate_routing_params`).
 */

import type { RoutingPatternInfo } from "./types";
import { MAX_PCB_LAYERS } from "./types/simulationLimits";

/** Layer-range constraints of the active pattern (null = unconstrained). */
export interface PatternLayerRange {
  min_layers: number | null;
  max_layers: number | null;
  layers_multiple_of: number | null;
}

/**
 * Extract a pattern's declared layer range from the catalog metadata.
 * Accepts `undefined`/`null` (catalog not loaded / unknown pattern) and
 * resolves every field to null = unconstrained.
 */
export function patternLayerRange(
  info: RoutingPatternInfo | undefined | null,
): PatternLayerRange {
  return {
    min_layers: info?.min_layers ?? null,
    max_layers: info?.max_layers ?? null,
    layers_multiple_of: info?.layers_multiple_of ?? null,
  };
}

/**
 * Copper-layer counts the UI may offer: even, >= 2, within the board's
 * `max_layers`, intersected with the pattern's declared min/max and
 * multiple-of constraint. `maxLayers` below 2 yields an empty list (the
 * config invariant keeps it >= 2 in practice).
 */
export function layerOptions(
  maxLayers: number,
  range: PatternLayerRange,
): number[] {
  const boardMax = Number.isFinite(maxLayers) ? Math.floor(maxLayers) : 0;
  const lo = Math.max(2, range.min_layers ?? 2);
  const hi = Math.min(boardMax, range.max_layers ?? boardMax, MAX_PCB_LAYERS);
  const mult = range.layers_multiple_of;
  const options: number[] = [];
  for (let n = 2; n <= hi; n += 2) {
    if (n < lo) continue;
    if (mult !== null && mult > 0 && n % mult !== 0) continue;
    options.push(n);
  }
  return options;
}

/**
 * Epsilon-tolerant "is a whole multiple of" check, mirroring the routing
 * crate's 1e-9 discipline so the UI and the backend agree. Degenerate inputs
 * (non-finite value, non-positive/NaN multiple) pass — the backend owns the
 * real rejection.
 */
export function isMultipleOf(value: number, multipleOf: number): boolean {
  if (!Number.isFinite(value)) return true;
  if (!Number.isFinite(multipleOf) || multipleOf <= 0) return true;
  const scaled = value / multipleOf;
  return Math.abs(Math.round(scaled) - scaled) * multipleOf <= 1e-9;
}

/**
 * Nearest option to `n` (ties pick the smaller option). Empty options list
 * returns `n` unchanged — the caller decides what an empty option set means.
 */
export function nearestLayer(n: number, options: number[]): number {
  const first = options[0];
  if (first === undefined) return n;
  let best = first;
  for (const o of options) {
    if (Math.abs(o - n) < Math.abs(best - n)) best = o;
  }
  return best;
}

/** Human-readable one-liner of a pattern's declared layer range. */
export function formatLayerRange(range: PatternLayerRange): string {
  const parts: string[] = [];
  if (range.min_layers !== null && range.max_layers !== null) {
    parts.push(`${range.min_layers}\u2013${range.max_layers} layers`);
  } else if (range.min_layers !== null) {
    parts.push(`\u2265 ${range.min_layers} layers`);
  } else if (range.max_layers !== null) {
    parts.push(`\u2264 ${range.max_layers} layers`);
  }
  if (range.layers_multiple_of !== null && range.layers_multiple_of > 2) {
    parts.push(`multiples of ${range.layers_multiple_of}`);
  } else if (range.layers_multiple_of === 2) {
    parts.push("even");
  }
  return parts.length > 0
    ? `pattern supports ${parts.join(", ")}`
    : "pattern: no layer constraints";
}
