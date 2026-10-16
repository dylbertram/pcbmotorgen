import type { CadCoilTerminals, CadGeometry, CadTerminal } from "./types";
import { splinePointAt } from "./curvePaths";
import { cadCoilNames } from "./cadPreview";

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
  // A termination can meet the middle of another coil's lead, including on
  // the other side of a via. Intersections away from an endpoint are not
  // inferred as terminals: only nodes belonging to this winding are tested.
  for (const entry of nodes) {
    if (!entry.owners.has(coil)) continue;
    for (const segment of geometry.routing.segments) {
      if (segment.net === coil || segment.layer !== entry.point.layer) continue;
      const dx = segment.end.x - segment.start.x, dy = segment.end.y - segment.start.y;
      const length = Math.hypot(dx, dy);
      if (length === 0) continue;
      const px = entry.point.position.x - segment.start.x, py = entry.point.position.y - segment.start.y;
      const along = (px * dx + py * dy) / length;
      if (Math.abs(px * dy - py * dx) / length <= tolerance && along >= -tolerance && along <= length + tolerance) entry.owners.add(segment.net);
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
  const free: CadTerminal[] = [];
  const joined: CadTerminal[] = [];
  let isolatedChain = true;
  for (const [id, group] of groups) {
    if (!group.owners.has(coil)) continue;
    const degree = adjacency.get(id)?.length ?? 0;
    if (degree === 0) return null;
    if (group.owners.size !== 1 || degree > 2) isolatedChain = false;
    if (degree === 1) {
      // Retain a real endpoint on this coil, not another coil's endpoint
      // which happened to be encountered first at the shared junction.
      const endpoint = nodes.find((entry, index) => root(index) === id && entry.owners.has(coil))!.point;
      if (group.owners.size > 1) joined.push(endpoint);
      else if (!group.via) free.push(endpoint);
      if (group.via) isolatedChain = false;
      ends.push(endpoint);
    }
  }
  const visited = new Set<number>();
  const queue = [adjacency.keys().next().value!];
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i];
    if (visited.has(id)) continue;
    visited.add(id); queue.push(...adjacency.get(id)!);
  }
  if (visited.size !== adjacency.size) return null;
  if (free.length === 1 && joined.length === 1) return { input: free[0], output: joined[0] };
  if (!isolatedChain || ends.length !== 2) return null;
  ends.sort((a, b) => a.layer - b.layer || a.position.x - b.position.x || a.position.y - b.position.y);
  return { input: ends[0], output: ends[1] };
}

/** Presentation defaults never replace explicit selections or mutate a project. */
export function withAutomaticCadTerminals(geometry: CadGeometry): CadGeometry {
  let changed = false;
  const terminals = { ...geometry.coil_terminals };
  const coils = new Set([...geometry.routing.segments, ...geometry.routing.curves, ...(geometry.routing.splines ?? [])].map((trace) => trace.net));
  for (const coil of coils) {
    if (Object.hasOwn(terminals, coil)) continue;
    const inferred = defaultCadTerminals(geometry, coil);
    if (inferred) { terminals[coil] = inferred; changed = true; }
  }
  return changed ? { ...geometry, coil_terminals: terminals } : geometry;
}

/**
 * Coils that carry at least two trace endpoints but have no confirmed IN/OUT
 * end selection. The inferred defaults from {@link withAutomaticCadTerminals}
 * are presentation only; the Simulation tab treats imported copper as
 * electrically invalid until every such coil has an applied pair.
 */
export function coilsMissingEnds(geometry: CadGeometry): string[] {
  return cadCoilNames(geometry).filter((coil) => {
    const candidates = cadTerminalCandidates(geometry, coil);
    if (candidates.length < 2) return false;
    const saved = geometry.coil_terminals?.[coil];
    if (!saved) return true;
    return sameTerminal(saved.input, saved.output)
      || [saved.input, saved.output].some((point) => !candidates.some((candidate) => sameTerminal(candidate, point)));
  });
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
