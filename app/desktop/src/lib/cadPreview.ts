import type { CadGeometry, CoilPathDto, PhaseCoilDto } from "./types";

const M = 1e-3;

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
