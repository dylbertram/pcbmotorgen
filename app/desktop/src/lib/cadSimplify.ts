import type { CadGeometry, CadRouteSegment } from "./types";
import { sameTerminal } from "./cadTerminals";

// Numerical roundoff only, deliberately independent of the import Z/XY tolerance.
const EPS_MM = 1e-9;

function merge(a: CadRouteSegment, b: CadRouteSegment): CadRouteSegment | null {
  if (a.layer !== b.layer || a.net !== b.net || a.is_active !== b.is_active) return null;
  const dx = a.end.x - a.start.x, dy = a.end.y - a.start.y;
  const length = Math.hypot(dx, dy);
  if (length <= EPS_MM) return null;
  const ux = dx / length, uy = dy / length;
  const project = (p: { x: number; y: number }) =>
    (p.x - a.start.x) * ux + (p.y - a.start.y) * uy;
  const distance = (p: { x: number; y: number }) =>
    Math.abs((p.x - a.start.x) * uy - (p.y - a.start.y) * ux);
  if (distance(b.start) > EPS_MM || distance(b.end) > EPS_MM) return null;
  const p = project(b.start), q = project(b.end);
  const low = Math.min(p, q), high = Math.max(p, q);
  if (low > length + EPS_MM || high < -EPS_MM) return null;
  // Keep original extreme endpoint coordinates, never snap or bridge real gaps.
  return {
    ...a,
    start: low < 0 ? (p < q ? b.start : b.end) : a.start,
    end: high > length ? (p > q ? b.start : b.end) : a.end,
  };
}

/** Merge touching/overlapping collinear traces without changing coils or planes.
 * Arcs, splines, via positions/spans and source-layer assignments stay intact.
 * Returns a new geometry and never mutates the saved/input geometry.
 */
export function simplifyCadLines(geometry: CadGeometry): CadGeometry {
  const segments: CadRouteSegment[] = [];
  for (const segment of geometry.routing.segments) {
    let candidate = { ...segment };
    let insertAt = segments.length;
    for (let i = 0; i < segments.length;) {
      const combined = i < insertAt ? merge(segments[i], candidate) : merge(candidate, segments[i]);
      if (!combined) { i += 1; continue; }
      const terminals = geometry.coil_terminals && Object.hasOwn(geometry.coil_terminals, combined.net) ? geometry.coil_terminals[combined.net] : undefined;
      // Explicit IN/OUT points must remain endpoints after simplification.
      if (terminals && [terminals.input, terminals.output].some((terminal) =>
        terminal.layer === combined.layer &&
        [segments[i].start, segments[i].end, candidate.start, candidate.end].some((position) => sameTerminal(terminal, { position, layer: combined.layer })) &&
        ![combined.start, combined.end].some((position) => sameTerminal(terminal, { position, layer: combined.layer }))
      )) { i += 1; continue; }
      candidate = combined;
      insertAt = Math.min(insertAt, i);
      segments.splice(i, 1);
      i = 0; // A bridge can now join an earlier, previously disjoint interval.
    }
    segments.splice(insertAt, 0, candidate);
  }
  return { ...geometry, routing: { ...geometry.routing, segments } };
}
