import type {
  CadGeometry,
  CadPoint,
  CadRouteCurve,
  CadRouteSegment,
  CoilPathDto,
  PhaseCoilDto,
} from "./types";

const M = 1e-3;

interface PreviewEndpoint {
  point: CadPoint;
  layer: number;
  net: string;
  primitive: number;
  set: (point: CadPoint) => void;
}

interface EndpointCluster {
  anchor: CadPoint;
  members: PreviewEndpoint[];
}

export interface JoinedCadPreview {
  segments: CadRouteSegment[];
  curves: CadRouteCurve[];
}

/**
 * Close small endpoint gaps for display only. Imported/saved CAD geometry is
 * deliberately left untouched; snapping is constrained to the same net and
 * copper layer and uses the import tolerance as its maximum distance.
 */
export function joinCadPreviewEndpoints(
  geometry: CadGeometry,
  toleranceMm: number,
): JoinedCadPreview {
  const segments = geometry.routing.segments.map((segment) => ({
    ...segment,
    start: { ...segment.start },
    end: { ...segment.end },
  }));
  const curves = geometry.routing.curves.map((curve) => ({
    ...curve,
    start: { ...curve.start },
    mid: { ...curve.mid },
    end: { ...curve.end },
  }));

  if (!Number.isFinite(toleranceMm) || toleranceMm <= 0) {
    return { segments, curves };
  }

  const endpoints: PreviewEndpoint[] = [];
  let primitive = 0;
  for (const segment of segments) {
    const id = primitive++;
    endpoints.push(
      {
        point: segment.start,
        layer: segment.layer,
        net: segment.net,
        primitive: id,
        set: (point) => {
          segment.start = point;
        },
      },
      {
        point: segment.end,
        layer: segment.layer,
        net: segment.net,
        primitive: id,
        set: (point) => {
          segment.end = point;
        },
      },
    );
  }
  for (const curve of curves) {
    const id = primitive++;
    endpoints.push(
      {
        point: curve.start,
        layer: curve.layer,
        net: curve.net,
        primitive: id,
        set: (point) => {
          curve.start = point;
        },
      },
      {
        point: curve.end,
        layer: curve.layer,
        net: curve.net,
        primitive: id,
        set: (point) => {
          curve.end = point;
        },
      },
    );
  }

  const cellSize = toleranceMm;
  const cell = (point: CadPoint) => ({
    x: Math.floor(point.x / cellSize),
    y: Math.floor(point.y / cellSize),
  });
  const groupKey = (layer: number, net: string) => JSON.stringify([layer, net]);
  const viaGrid = new Map<string, Map<string, CadPoint[]>>();
  for (const via of geometry.routing.vias) {
    for (const layer of [via.from_layer, via.to_layer]) {
      const key = groupKey(layer, via.net);
      let grid = viaGrid.get(key);
      if (!grid) viaGrid.set(key, (grid = new Map()));
      const { x, y } = cell(via.position);
      const bucketKey = `${x},${y}`;
      const bucket = grid.get(bucketKey) ?? [];
      bucket.push(via.position);
      grid.set(bucketKey, bucket);
    }
  }

  const unresolved: PreviewEndpoint[] = [];
  for (const endpoint of endpoints) {
    const grid = viaGrid.get(groupKey(endpoint.layer, endpoint.net));
    const { x, y } = cell(endpoint.point);
    let nearest: { point: CadPoint; distance: number } | undefined;
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        for (const point of grid?.get(`${x + dx},${y + dy}`) ?? []) {
          const distance = Math.hypot(endpoint.point.x - point.x, endpoint.point.y - point.y);
          if (distance <= toleranceMm && (!nearest || distance < nearest.distance)) {
            nearest = { point, distance };
          }
        }
      }
    }

    if (nearest) endpoint.set({ ...nearest.point });
    else unresolved.push(endpoint);
  }

  const groups = new Map<string, Map<string, EndpointCluster[]>>();
  const clusters: EndpointCluster[] = [];

  for (const endpoint of unresolved) {
    const netKey = groupKey(endpoint.layer, endpoint.net);
    let grid = groups.get(netKey);
    if (!grid) groups.set(netKey, (grid = new Map()));
    const { x, y } = cell(endpoint.point);
    const nearby = new Set<EndpointCluster>();
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        for (const cluster of grid.get(`${x + dx},${y + dy}`) ?? []) nearby.add(cluster);
      }
    }

    const matching = [...nearby]
      .filter((cluster) =>
        cluster.members.every((member) =>
          member.primitive !== endpoint.primitive &&
          Math.hypot(
            member.point.x - endpoint.point.x,
            member.point.y - endpoint.point.y,
          ) <= toleranceMm,
        ),
      )
      .sort((a, b) =>
        Math.hypot(a.anchor.x - endpoint.point.x, a.anchor.y - endpoint.point.y) -
        Math.hypot(b.anchor.x - endpoint.point.x, b.anchor.y - endpoint.point.y),
      );
    let cluster = matching[0];
    if (!cluster) {
      cluster = { anchor: endpoint.point, members: [] };
      clusters.push(cluster);
      const { x: cellX, y: cellY } = cell(endpoint.point);
      const key = `${cellX},${cellY}`;
      const bucket = grid.get(key) ?? [];
      bucket.push(cluster);
      grid.set(key, bucket);
    }
    cluster.members.push(endpoint);
  }

  for (const cluster of clusters) {
    if (cluster.members.length < 2) continue;
    const point = cluster.members.reduce(
      (average, member) => ({
        x: average.x + member.point.x / cluster.members.length,
        y: average.y + member.point.y / cluster.members.length,
      }),
      { x: 0, y: 0 },
    );
    for (const member of cluster.members) member.set(point);
  }

  return { segments, curves };
}

/** Convert saved CAD centerlines to the existing top-down coil preview DTO. */
export function cadGeometryToPreview(geometry: CadGeometry): CoilPathDto {
  const grouped = new Map<string, PhaseCoilDto>();
  const netOrder = new Map<string, number>();
  const getGroup = (layer: number, net: string): PhaseCoilDto => {
    const key = `${layer}\u0000${net}`;
    let coil = grouped.get(key);
    if (!coil) {
      if (!netOrder.has(net)) netOrder.set(net, netOrder.size);
      coil = {
        phase_idx: netOrder.get(net)!, layer_idx: layer, phase_name: net,
        pattern_id: "imported-cad", segments: [], corner_arcs: [], via_positions: [],
        total_length_m: 0, active_length_m: 0, end_turn_length_m: 0,
        active_conductor_count: 0, bounding_box: [0, 0, 0, 0],
        terminal_start: [0, 0], terminal_end: [0, 0],
      };
      grouped.set(key, coil);
    }
    return coil;
  };
  const bounds = new Map<string, [number, number, number, number]>();
  const addBounds = (coil: PhaseCoilDto, pts: Array<[number, number]>) => {
    const key = `${coil.layer_idx}\u0000${coil.phase_name}`;
    const b = bounds.get(key) ?? [Infinity, Infinity, -Infinity, -Infinity];
    for (const [x, y] of pts) {
      b[0] = Math.min(b[0], x * M); b[1] = Math.min(b[1], y * M);
      b[2] = Math.max(b[2], x * M); b[3] = Math.max(b[3], y * M);
    }
    bounds.set(key, b);
  };

  for (const segment of geometry.routing.segments) {
    const coil = getGroup(segment.layer, segment.net);
    const start: [number, number] = [segment.start.x * M, segment.start.y * M];
    const end: [number, number] = [segment.end.x * M, segment.end.y * M];
    const length = Math.hypot(end[0] - start[0], end[1] - start[1]);
    coil.segments.push({ start, end, is_active: segment.is_active });
    coil.total_length_m += length;
    if (segment.is_active) { coil.active_length_m += length; coil.active_conductor_count += 1; }
    else coil.end_turn_length_m += length;
    addBounds(coil, [[segment.start.x, segment.start.y], [segment.end.x, segment.end.y]]);
  }
  for (const curve of geometry.routing.curves) {
    const coil = getGroup(curve.layer, curve.net);
    const start: [number, number] = [curve.start.x * M, curve.start.y * M];
    const mid: [number, number] = [curve.mid.x * M, curve.mid.y * M];
    const end: [number, number] = [curve.end.x * M, curve.end.y * M];
    coil.corner_arcs!.push({ start, mid, end, is_active: curve.is_active });
    addBounds(coil, [[curve.start.x, curve.start.y], [curve.mid.x, curve.mid.y], [curve.end.x, curve.end.y]]);
  }
  for (const via of geometry.routing.vias) {
    getGroup(via.from_layer, via.net).via_positions!.push([via.position.x * M, via.position.y * M]);
    getGroup(via.to_layer, via.net).via_positions!.push([via.position.x * M, via.position.y * M]);
  }
  const phases = [...grouped.values()];
  for (const coil of phases) {
    const b = bounds.get(`${coil.layer_idx}\u0000${coil.phase_name}`) ?? [0, 0, 0, 0];
    coil.bounding_box = b;
    const first = coil.segments[0];
    const last = coil.segments[coil.segments.length - 1];
    coil.terminal_start = first?.start ?? [b[0], b[1]];
    coil.terminal_end = last?.end ?? [b[2], b[3]];
  }
  return { phases, layer_count: Math.max(geometry.layer_z_mm.length, 1) };
}

export interface CadWarningGroup {
  key: string;
  title: string;
  count: number;
  examples: string[];
}

/** Collapse repeated import diagnostics by failure class/layer for the UI. */
export function groupCadImportWarnings(warnings: string[]): CadWarningGroup[] {
  const groups = new Map<string, CadWarningGroup>();
  for (const warning of warnings) {
    const viaLayer = warning.match(/^Via at .* has no matching trace endpoint on layer (\d+)\.$/)?.[1];
    const unsupported = warning.match(/^Skipped unsupported DXF (.+) entity on layer '(.+)'\.$/);
    const key = viaLayer !== undefined
      ? `unconnected-via-layer-${viaLayer}`
      : unsupported
        ? `unsupported-${unsupported[1]}-${unsupported[2]}`
        : `warning-${warning}`;
    const title = viaLayer !== undefined
      ? `Via endpoint does not meet a trace · layer ${viaLayer}`
      : unsupported
        ? `Unsupported ${unsupported[1]} entities · ${unsupported[2]}`
        : warning;
    const group = groups.get(key) ?? { key, title, count: 0, examples: [] };
    group.count += 1;
    if (group.examples.length < 5) group.examples.push(warning);
    groups.set(key, group);
  }
  return [...groups.values()];
}
