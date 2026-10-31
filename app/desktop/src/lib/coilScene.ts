import { Box3, Vector3, ArcCurve } from "three";
import { sampleSpline } from "./curvePaths";
import type { CadGeometry, CadPoint, CadRouteCurve } from "./types";

export interface CopperPath {
  key: string;
  net: string;
  layer: number;
  points: Vector3[];
}

/** A barrel crosses every layer in its declared span, not only its end layers. */
export function isViaVisible(
  via: { from_layer: number; to_layer: number; net: string },
  isLayerVisible: (layer: number) => boolean,
  isCoilVisible: (net: string, layer: number) => boolean,
): boolean {
  for (let layer = Math.min(via.from_layer, via.to_layer); layer <= Math.max(via.from_layer, via.to_layer); layer++) {
    if (isLayerVisible(layer) && isCoilVisible(via.net, layer)) return true;
  }
  return false;
}

/** Sample the original circular arc, including major arcs through the midpoint. */
export function sampleCopperArc({ start: a, mid: b, end: c }: CadRouteCurve): CadPoint[] {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return [a, c];
  const aa = a.x ** 2 + a.y ** 2, bb = b.x ** 2 + b.y ** 2, cc = c.x ** 2 + c.y ** 2;
  const x = (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d;
  const y = (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d;
  const angle = (p: CadPoint) => Math.atan2(p.y - y, p.x - x);
  const tau = Math.PI * 2;
  const sweep = (angle(c) - angle(a) + tau) % tau;
  const throughMid = (angle(b) - angle(a) + tau) % tau;
  const clockwise = throughMid > sweep;
  const arc = new ArcCurve(x, y, Math.hypot(a.x - x, a.y - y), angle(a), angle(c), clockwise);
  return arc.getPoints(Math.max(8, Math.ceil((clockwise ? tau - sweep : sweep) / (Math.PI / 48))));
}

/** Convert mm into a centered, Y-up scene. Bounds include hidden copper and vias. */
export function buildCoilScene(geometry: CadGeometry | null) {
  if (!geometry || geometry.layer_z_mm.length === 0) return null;
  const g = geometry;
  const at = (p: CadPoint, layer: number) => new Vector3(p.x, g.layer_z_mm[layer] ?? 0, -p.y);
  const paths: CopperPath[] = [
    ...g.routing.segments.map((s, i) => ({ key: `segment-${i}`, net: s.net, layer: s.layer, points: [at(s.start, s.layer), at(s.end, s.layer)] })),
    ...g.routing.curves.map((c, i) => ({ key: `arc-${i}`, net: c.net, layer: c.layer, points: sampleCopperArc(c).map(p => at(p, c.layer)) })),
    ...(g.routing.splines ?? []).map((s, i) => ({ key: `spline-${i}`, net: s.net, layer: s.layer, points: sampleSpline(s).map(p => at(p, s.layer)) })),
  ];
  const vias = g.routing.vias.map((v, i) => ({ ...v, key: `via-${i}`, points: [at(v.position, v.from_layer), at(v.position, v.to_layer)] }));
  const terminals = Object.entries(g.coil_terminals ?? {}).flatMap(([net, ends]) =>
    (["input", "output"] as const).map(end => ({ key: `${net}-${end}`, net, layer: ends[end].layer, point: at(ends[end].position, ends[end].layer) })));
  const bounds = new Box3();
  for (const path of [...paths, ...vias]) for (const p of path.points) bounds.expandByPoint(p);
  for (const t of terminals) bounds.expandByPoint(t.point);
  if (bounds.isEmpty()) return null;
  const center = bounds.getCenter(new Vector3());
  const size = bounds.getSize(new Vector3());
  const scale = 10 / Math.max(size.x, size.y, size.z, g.trace_width_mm, 0.01);
  for (const path of [...paths, ...vias]) for (const p of path.points) p.sub(center).multiplyScalar(scale);
  for (const t of terminals) t.point.sub(center).multiplyScalar(scale);
  return { paths, vias, terminals, width: Math.max(g.trace_width_mm, 0.01) * scale,
    centerMm: center.toArray() as [number, number, number], scale,
    nets: [...new Set([...paths, ...vias].map(p => p.net))].sort() };
}

export type CoilScene = NonNullable<ReturnType<typeof buildCoilScene>>;
