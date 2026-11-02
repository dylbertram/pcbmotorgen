import type { CadGeometry, CoilPathDto, CoilSegmentDto, CoilArcDto } from "../types";

/** Filter scene keys, never rebuild/reindex geometry used by native heat maps. */
export function previewCopperKeys(
  geometry: CadGeometry | null,
  coils: CoilPathDto | null,
  segments: ReadonlyMap<number, CoilSegmentDto[]>,
  arcs: ReadonlyMap<number, CoilArcDto[]>,
): Set<string> {
  const keys = new Set<string>();
  if (!geometry || !coils) return keys;
  const pointKey = (x: number, y: number) => `${Math.round(x * 1e6)},${Math.round(y * 1e6)}`;
  const lineKey = (a: string, b: string) => [a, b].sort().join(":");
  const allowed = new Map<string, { lines: Set<string>; arcs: Set<string>; minX: number; maxX: number }>();
  for (const phase of coils.phases) {
    const phaseLayer = phase.phase_idx * 1000 + phase.layer_idx;
    const visible = segments.get(phaseLayer) ?? phase.segments;
    const curves = arcs.get(phaseLayer) ?? phase.corner_arcs ?? [];
    // Preview coordinates are in metres; CAD geometry is in millimetres.
    const previewPointKey = (p: readonly number[]) => pointKey(p[0] * 1000, p[1] * 1000);
    const xs = visible.flatMap(s => [s.start[0] * 1000, s.end[0] * 1000]);
    allowed.set(`${phase.phase_name}:${phase.layer_idx}`, {
      lines: new Set(visible.map(s => lineKey(previewPointKey(s.start), previewPointKey(s.end)))),
      arcs: new Set(curves.map(s => `${lineKey(previewPointKey(s.start), previewPointKey(s.end))}:${previewPointKey(s.mid)}`)),
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
    });
  }
  geometry.routing.segments.forEach((segment, i) => {
    const key = lineKey(pointKey(segment.start.x, segment.start.y), pointKey(segment.end.x, segment.end.y));
    if (allowed.get(`${segment.net}:${segment.layer}`)?.lines.has(key)) keys.add(`segment-${i}`);
  });
  geometry.routing.curves.forEach((curve, i) => {
    const key = `${lineKey(pointKey(curve.start.x, curve.start.y), pointKey(curve.end.x, curve.end.y))}:${pointKey(curve.mid.x, curve.mid.y)}`;
    if (allowed.get(`${curve.net}:${curve.layer}`)?.arcs.has(key)) keys.add(`arc-${i}`);
  });
  (geometry.routing.splines ?? []).forEach((spline, i) => {
    const range = allowed.get(`${spline.net}:${spline.layer}`);
    if (range && spline.control_points.every(p => p.x >= range.minX - 1e-6 && p.x <= range.maxX + 1e-6)) {
      keys.add(`spline-${i}`);
    }
  });
  return keys;
}
