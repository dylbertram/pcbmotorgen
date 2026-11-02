/**
 * Coil → phase mapping for imported CAD geometry. Mirrors
 * `CadGeometry::phase_of` in the export crate: an explicit assignment wins,
 * else a coil already named after a phase drives that phase.
 */

import type { CadGeometry } from "../types";

export const PHASE_LABELS = ["A", "B", "C", "D", "E", "F"];

/** Coils with routed segments, arcs or splines; via-only nets are excluded. */
export function coilNamesWithPaths(geometry: CadGeometry): string[] {
  const names = new Set<string>();
  for (const s of geometry.routing.segments) names.add(s.net);
  for (const c of geometry.routing.curves) names.add(c.net);
  for (const s of geometry.routing.splines ?? []) names.add(s.net);
  return [...names].sort();
}

export function phaseOf(geometry: CadGeometry, coil: string): string | null {
  const explicit = geometry.coil_phases?.[coil]?.trim();
  if (explicit) return explicit;
  return PHASE_LABELS.includes(coil) ? coil : null;
}

/** Copy of `geometry` with `coil` assigned to `phase` (null clears it). */
export function withCoilPhase(geometry: CadGeometry, coil: string, phase: string | null): CadGeometry {
  const coil_phases = { ...(geometry.coil_phases ?? {}) };
  if (phase) coil_phases[coil] = phase;
  else delete coil_phases[coil];
  return { ...geometry, coil_phases };
}

const keys = new WeakMap<object, number>();
let nextKey = 1;

/** Stable identity for a geometry object (it is replaced, never mutated). */
export function geometryKey(geometry: CadGeometry | null): number {
  if (!geometry) return 0;
  let key = keys.get(geometry);
  if (key === undefined) {
    key = nextKey++;
    keys.set(geometry, key);
  }
  return key;
}
