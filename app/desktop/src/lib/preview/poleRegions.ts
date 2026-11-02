import type { ViewportBBox } from "../geometry/viewport";
import type { PoleRegionDto, RoutingDimensionsDto } from "../types";

/** Pole-region boundaries and phase labels come from the routing sidecar. */
export interface PoleRegionZone {
  phase: string;
  poleIndex: number;
  x0: number;
  x1: number;
  polarity: 1 | -1;
}

export function poleRegionPolarity(poleIndex: number): 1 | -1 {
  return poleIndex % 2 === 0 ? 1 : -1;
}

function isFiniteNumberPair(v: unknown): v is [number, number] {
  return (
    Array.isArray(v) && v.length >= 2 &&
    typeof v[0] === "number" && typeof v[1] === "number" &&
    Number.isFinite(v[0]) && Number.isFinite(v[1])
  );
}

/** Reject malformed or zero-width sidecar regions rather than drawing them. */
export function isValidPoleRegion(region: PoleRegionDto | null | undefined): boolean {
  if (!region) return false;
  if (typeof region.phase !== "string" || region.phase.trim() === "") return false;
  const idx = region.pole_index;
  if (typeof idx !== "number" || !Number.isFinite(idx) || idx < 0 || !Number.isInteger(idx)) return false;
  if (!isFiniteNumberPair(region.start) || !isFiniteNumberPair(region.end)) return false;
  return region.end[0] !== region.start[0];
}

/** Translate valid sidecar regions into deterministic world-space zones. */
export function computePoleRegionZones(
  dimensions: Partial<Pick<RoutingDimensionsDto, "pole_regions">> | null | undefined,
): PoleRegionZone[] {
  const regions = dimensions?.pole_regions;
  if (!Array.isArray(regions)) return [];
  const zones: PoleRegionZone[] = [];
  for (const region of regions) {
    if (!isValidPoleRegion(region)) continue;
    zones.push({
      phase: region.phase,
      poleIndex: region.pole_index,
      x0: Math.min(region.start[0], region.end[0]),
      x1: Math.max(region.start[0], region.end[0]),
      polarity: poleRegionPolarity(region.pole_index),
    });
  }
  zones.sort((a, b) => a.x0 - b.x0 || a.phase.localeCompare(b.phase) || a.poleIndex - b.poleIndex);
  return zones;
}

export function computePoleRegionPhases(zones: readonly PoleRegionZone[]): string[] {
  return [...new Set(zones.map((z) => z.phase))].sort();
}

/** Null or empty selects all phases; the result never aliases the input. */
export function filterPoleRegionsByPhase(zones: readonly PoleRegionZone[], phase: string | null): PoleRegionZone[] {
  if (phase == null || phase === "") return zones.slice();
  const result: PoleRegionZone[] = [];
  for (const z of zones) if (z.phase === phase) result.push(z);
  return result;
}

/** Clear a phase selection that no longer exists after regeneration. */
export function resolvePoleRegionPhaseSelection(selected: string, available: readonly string[]): string {
  return selected === "" || available.includes(selected) ? selected : "";
}

/** Fit box covering the selected zones within the supplied board y band. */
export function computePoleRegionBounds(zones: readonly PoleRegionZone[], yMin: number, yMax: number): ViewportBBox | null {
  if (zones.length === 0) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  for (const z of zones) {
    minX = Math.min(minX, z.x0);
    maxX = Math.max(maxX, z.x1);
  }
  if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return null;
  return { minX, minY: yMin, maxX, maxY: yMax };
}
