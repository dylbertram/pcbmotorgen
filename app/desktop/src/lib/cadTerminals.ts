import type { CadCoilTerminals, CadGeometry, CadTerminal } from "./types";
import { splinePointAt } from "./curvePaths";

export function sameTerminal(a: CadTerminal, b: CadTerminal): boolean {
  return a.layer === b.layer && Math.hypot(a.position.x - b.position.x, a.position.y - b.position.y) <= 1e-9;
}

/** Original trace endpoints only. No snapping, via centres or spline controls. */
export function cadTerminalCandidates(geometry: CadGeometry, coil: string): CadTerminal[] {
  const points: CadTerminal[] = [];
  const add = (point: CadTerminal) => {
    if (!points.some((p) => sameTerminal(p, point))) points.push(point);
  };
  for (const trace of [...geometry.routing.segments, ...geometry.routing.curves]) {
    if (trace.net !== coil) continue;
    add({ position: trace.start, layer: trace.layer });
    add({ position: trace.end, layer: trace.layer });
  }
  for (const spline of geometry.routing.splines ?? []) {
    if (spline.net !== coil) continue;
    add({ position: splinePointAt(spline, spline.knots[spline.degree]), layer: spline.layer });
    add({ position: splinePointAt(spline, spline.knots[spline.control_points.length]), layer: spline.layer });
  }
  return points.sort((a, b) => a.layer - b.layer || a.position.x - b.position.x || a.position.y - b.position.y);
}

/** Infer terminals only for one isolated, unbranched, open endpoint-connected chain. */
export function defaultCadTerminals(geometry: CadGeometry, coil: string): CadCoilTerminals | null {
  const nodes: { point: CadTerminal; owners: Set<string>; via: boolean }[] = [];
  const parents: number[] = [];
  const grid = new Map<string, number[]>();
  const tolerance = 1e-9;
  const key = (point: CadTerminal, dx = 0, dy = 0) => `${point.layer}:${Math.floor(point.position.x / tolerance) + dx}:${Math.floor(point.position.y / tolerance) + dy}`;
  function node(point: CadTerminal, owner: string, via = false): number {
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const index of grid.get(key(point, dx, dy)) ?? []) if (sameTerminal(nodes[index].point, point)) {
        nodes[index].owners.add(owner);
        nodes[index].via ||= via;
        return index;
      }
    }
    const index = nodes.length;
    nodes.push({ point, owners: new Set([owner]), via }); parents.push(index);
    const bucket = grid.get(key(point)) ?? [];
    bucket.push(index); grid.set(key(point), bucket);
    return index;
  }
  function root(index: number): number {
    while (parents[index] !== index) { parents[index] = parents[parents[index]]; index = parents[index]; }
    return index;
  }
  const edges: [number, number][] = [];
  function trace(start: CadTerminal, end: CadTerminal, net: string) {
    const a = node(start, net), b = node(end, net);
    if (net === coil) edges.push([a, b]);
  }
  for (const segment of [...geometry.routing.segments, ...geometry.routing.curves]) {
    trace({ position: segment.start, layer: segment.layer }, { position: segment.end, layer: segment.layer }, segment.net);
  }
  for (const spline of geometry.routing.splines ?? []) {
    trace({ position: splinePointAt(spline, spline.knots[spline.degree]), layer: spline.layer },
      { position: splinePointAt(spline, spline.knots[spline.control_points.length]), layer: spline.layer }, spline.net);
  }
  if (!edges.length) return null;
  for (const via of geometry.routing.vias) {
    let first: number | undefined;
    for (let layer = Math.min(via.from_layer, via.to_layer); layer <= Math.max(via.from_layer, via.to_layer); layer++) {
      const index = node({ position: via.position, layer }, via.net, true);
      if (first === undefined) first = index;
      else parents[root(index)] = root(first);
    }
  }
  const groups = new Map<number, { owners: Set<string>; via: boolean; point: CadTerminal }>();
  nodes.forEach((entry, index) => {
    const id = root(index), group = groups.get(id) ?? { owners: new Set<string>(), via: false, point: entry.point };
    for (const owner of entry.owners) group.owners.add(owner);
    group.via ||= entry.via;
    groups.set(id, group);
  });
  const adjacency = new Map<number, number[]>();
  for (const [start, end] of edges) {
    const a = root(start), b = root(end);
    if (a === b) return null;
    const from = adjacency.get(a) ?? [], to = adjacency.get(b) ?? [];
    from.push(b); to.push(a); adjacency.set(a, from); adjacency.set(b, to);
  }
  const ends: CadTerminal[] = [];
  for (const [id, group] of groups) {
    if (!group.owners.has(coil)) continue;
    const degree = adjacency.get(id)?.length ?? 0;
    if (group.owners.size !== 1 || degree === 0 || degree > 2) return null;
    if (degree === 1) {
      // A dangling via is not a free trace end.
      if (group.via) return null;
      ends.push(group.point);
    }
  }
  if (ends.length !== 2) return null;
  const visited = new Set<number>();
  const queue = [adjacency.keys().next().value!];
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i];
    if (visited.has(id)) continue;
    visited.add(id); queue.push(...adjacency.get(id)!);
  }
  if (visited.size !== adjacency.size) return null;
  ends.sort((a, b) => a.layer - b.layer || a.position.x - b.position.x || a.position.y - b.position.y);
  return { input: ends[0], output: ends[1] };
}

export function assignCadTerminals(geometry: CadGeometry, coil: string, terminals: CadCoilTerminals): CadGeometry {
  const candidates = cadTerminalCandidates(geometry, coil);
  if (!candidates.some((p) => sameTerminal(p, terminals.input)) || !candidates.some((p) => sameTerminal(p, terminals.output))) {
    throw new Error("Choose trace endpoints belonging to this coil.");
  }
  if (sameTerminal(terminals.input, terminals.output)) throw new Error("The driver end and opposite end must be different endpoints.");
  const copy = (terminal: CadTerminal): CadTerminal => ({ position: { ...terminal.position }, layer: terminal.layer });
  return { ...geometry, coil_terminals: { ...geometry.coil_terminals, [coil]: { input: copy(terminals.input), output: copy(terminals.output) } } };
}

export function terminalDescription(terminal: CadTerminal): string {
  return `L${terminal.layer}, X ${Number(terminal.position.x.toFixed(6))} mm, Y ${Number(terminal.position.y.toFixed(6))} mm`;
}
