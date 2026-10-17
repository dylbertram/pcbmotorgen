import type { CadGeometry, CadPoint, CadVia } from "./types";
import { arcSvgPath, sampleSpline, splineSvgPath } from "./curvePaths";

export interface SelectableTrace {
  id: string;
  net: string;
  layer: number;
  points: CadPoint[];
  path: string;
}
export interface SelectionBox { minX: number; minY: number; maxX: number; maxY: number }

function sampleArc(a: CadPoint, b: CadPoint, c: CadPoint): CadPoint[] {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return [a, c];
  const aa = a.x * a.x + a.y * a.y, bb = b.x * b.x + b.y * b.y, cc = c.x * c.x + c.y * c.y;
  const x = (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d;
  const y = (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d;
  const angle = (p: CadPoint) => Math.atan2(p.y - y, p.x - x);
  const tau = 2 * Math.PI, start = angle(a), sweep = (angle(c) - start + tau) % tau;
  const delta = (angle(b) - start + tau) % tau < sweep ? sweep : sweep - tau;
  const radius = Math.hypot(a.x - x, a.y - y);
  const steps = Math.max(16, Math.ceil(Math.abs(delta) * 32));
  return Array.from({ length: steps + 1 }, (_, i) => ({ x: x + radius * Math.cos(start + delta * i / steps), y: y + radius * Math.sin(start + delta * i / steps) }));
}

export function selectableTraces(geometry: CadGeometry): SelectableTrace[] {
  return [
    ...geometry.routing.segments.map((s, i) => ({ id: `segments:${i}`, net: s.net, layer: s.layer, points: [s.start, s.end], path: `M ${s.start.x} ${s.start.y} L ${s.end.x} ${s.end.y}` })),
    ...geometry.routing.curves.map((s, i) => ({ id: `curves:${i}`, net: s.net, layer: s.layer, points: sampleArc(s.start, s.mid, s.end), path: arcSvgPath(s) })),
    ...(geometry.routing.splines ?? []).map((s, i) => ({ id: `splines:${i}`, net: s.net, layer: s.layer, points: sampleSpline(s, 32), path: splineSvgPath(s) })),
  ];
}

export function traceDistance(point: CadPoint, trace: SelectableTrace): number {
  let distance = Infinity;
  for (let i = 1; i < trace.points.length; i++) {
    const a = trace.points[i - 1], b = trace.points[i];
    const dx = b.x - a.x, dy = b.y - a.y;
    const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy || 1)));
    distance = Math.min(distance, Math.hypot(point.x - a.x - t * dx, point.y - a.y - t * dy));
  }
  return distance;
}

export function traceInBox(trace: SelectableTrace, box: SelectionBox, crossing: boolean): boolean {
  const inside = (p: CadPoint) => p.x >= box.minX && p.x <= box.maxX && p.y >= box.minY && p.y <= box.maxY;
  if (!crossing) return trace.points.every(inside);
  if (trace.points.some(inside)) return true;
  // Clip each sampled edge against the box, including edges with both ends outside.
  return trace.points.slice(1).some((b, i) => {
    const a = trace.points[i], dx = b.x - a.x, dy = b.y - a.y;
    let lo = 0, hi = 1;
    for (const [p, q] of [[-dx, a.x - box.minX], [dx, box.maxX - a.x], [-dy, a.y - box.minY], [dy, box.maxY - a.y]]) {
      if (p === 0) { if (q < 0) return false; }
      else if (p < 0) lo = Math.max(lo, q / p);
      else hi = Math.min(hi, q / p);
    }
    return lo <= hi;
  });
}

/** Find the shortest endpoint-connected path, crossing layers only through vias. */
export function traceChain(traces: SelectableTrace[], first: string, last: string, tolerance = 0.05, vias: CadVia[] = []): string[] {
  const start = traces.find((t) => t.id === first), end = traces.find((t) => t.id === last);
  if (!start || !end) return [];
  const cellSize = Math.max(tolerance, 1e-9);
  const key = (p: CadPoint, layer: number, dx = 0, dy = 0) => `${layer}:${Math.floor(p.x / cellSize) + dx}:${Math.floor(p.y / cellSize) + dy}`;
  const endpoints = new Map<string, { point: CadPoint; trace: SelectableTrace }[]>();
  const viaGrid = new Map<string, CadVia[]>();
  for (const trace of traces) for (const point of [trace.points[0], trace.points.at(-1)!]) {
    const k = key(point, trace.layer), bucket = endpoints.get(k) ?? [];
    bucket.push({ point, trace }); endpoints.set(k, bucket);
  }
  for (const via of vias) for (let layer = Math.min(via.from_layer, via.to_layer); layer <= Math.max(via.from_layer, via.to_layer); layer++) {
    const k = key(via.position, layer), bucket = viaGrid.get(k) ?? [];
    bucket.push(via); viaGrid.set(k, bucket);
  }
  const near = (a: CadPoint, b: CadPoint) => Math.hypot(a.x - b.x, a.y - b.y) <= tolerance + 1e-9;
  function neighbors(point: CadPoint, layer: number): SelectableTrace[] {
    const found: SelectableTrace[] = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const endpoint of endpoints.get(key(point, layer, dx, dy)) ?? []) if (near(point, endpoint.point)) found.push(endpoint.trace);
    }
    return found;
  }
  const previous = new Map<string, string | null>([[first, null]]);
  const queue = [start];
  for (let i = 0; i < queue.length; i++) {
    const current = queue[i];
    if (current.id === last) {
      const path: string[] = [];
      for (let id: string | null = last; id !== null; id = previous.get(id) ?? null) path.unshift(id);
      return path;
    }
    const candidates = [current.points[0], current.points.at(-1)!].flatMap((point) => {
      const found = neighbors(point, current.layer);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
        for (const via of viaGrid.get(key(point, current.layer, dx, dy)) ?? []) if (near(point, via.position)) {
          for (let layer = Math.min(via.from_layer, via.to_layer); layer <= Math.max(via.from_layer, via.to_layer); layer++) found.push(...neighbors(via.position, layer));
        }
      }
      return found;
    });
    for (const next of candidates) {
      if (!previous.has(next.id)) {
        previous.set(next.id, current.id);
        queue.push(next);
      }
    }
  }
  return [];
}

export function reassignTraces(geometry: CadGeometry, selected: string[], net?: string, layer?: number): CadGeometry {
  const ids = new Set(selected);
  const affected = new Set<string>();
  const update = <T extends { net: string; layer: number }>(items: T[], kind: string): T[] => items.map((s, i) => {
    if (!ids.has(`${kind}:${i}`)) return s;
    if ((net === undefined || net === s.net) && (layer === undefined || layer === s.layer)) return s;
    affected.add(s.net);
    if (net) affected.add(net);
    return { ...s, net: net ?? s.net, layer: layer ?? s.layer };
  });
  const routing = { ...geometry.routing, segments: update(geometry.routing.segments, "segments"), curves: update(geometry.routing.curves, "curves"), splines: update(geometry.routing.splines ?? [], "splines") };
  // Changed membership can invalidate explicit endpoints. Never keep stale terminals.
  const coil_terminals = Object.fromEntries(Object.entries(geometry.coil_terminals ?? {}).filter(([coil]) => !affected.has(coil)));
  return { ...geometry, routing, coil_terminals };
}
