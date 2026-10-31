import type { CadGeometry, CadPoint, CoilPathDto, LinearMotorConfig } from "./types";

export interface RoutingOrientation {
  mirror_x: boolean;
  mirror_y: boolean;
  reverse_layers: boolean;
}
export const DEFAULT_ROUTING_ORIENTATION: RoutingOrientation = { mirror_x: false, mirror_y: false, reverse_layers: false };
export type RoutingFlip = keyof RoutingOrientation;

/** Reflect an authoritative CAD edit, including manually picked endpoints. */
export function flipCadGeometry(geometry: CadGeometry, flip: RoutingOrientation): CadGeometry {
  const result = structuredClone(geometry);
  const applied = { ...DEFAULT_ROUTING_ORIENTATION, ...geometry.applied_orientation };
  for (const key of Object.keys(flip) as RoutingFlip[]) if (flip[key]) applied[key] = !applied[key];
  if (Object.values(applied).some(Boolean)) result.applied_orientation = applied;
  else delete result.applied_orientation;
  const points = [
    ...geometry.routing.segments.flatMap(s => [s.start, s.end]),
    ...geometry.routing.curves.flatMap(c => [c.start, c.mid, c.end]),
    ...(geometry.routing.splines ?? []).flatMap(s => s.control_points),
    ...geometry.routing.vias.map(v => v.position),
  ];
  if (!points.length) return result;
  const extent = (axis: "x" | "y") => {
    let low = Infinity, high = -Infinity;
    for (const point of points) { low = Math.min(low, point[axis]); high = Math.max(high, point[axis]); }
    return low + high;
  };
  const xSum = extent("x"), ySum = extent("y");
  const point = (p: CadPoint) => ({ x: flip.mirror_x ? xSum - p.x : p.x, y: flip.mirror_y ? ySum - p.y : p.y });
  const layer = (value: number) => flip.reverse_layers ? geometry.layer_z_mm.length - 1 - value : value;
  for (const s of result.routing.segments) { s.start = point(s.start); s.end = point(s.end); s.layer = layer(s.layer); }
  for (const c of result.routing.curves) { c.start = point(c.start); c.mid = point(c.mid); c.end = point(c.end); c.layer = layer(c.layer); }
  for (const s of result.routing.splines ?? []) { s.control_points = s.control_points.map(point); s.layer = layer(s.layer); }
  for (const v of result.routing.vias) { v.position = point(v.position); v.from_layer = layer(v.from_layer); v.to_layer = layer(v.to_layer); }
  for (const ends of Object.values(result.coil_terminals ?? {})) {
    for (const end of [ends.input, ends.output]) { end.position = point(end.position); end.layer = layer(end.layer); }
  }
  if (flip.reverse_layers) {
    const sum = Math.min(...geometry.layer_z_mm) + Math.max(...geometry.layer_z_mm);
    result.layer_z_mm = [...geometry.layer_z_mm].reverse().map(z => sum - z);
  }
  return result;
}

/** Browser preview only. Native generation applies the same host transform in Rust. */
export function orientCoilPreview(coils: CoilPathDto, config: LinearMotorConfig): CoilPathDto {
  const flip = config.routing_orientation;
  if (!flip || !Object.values(flip).some(Boolean)) return coils;
  const result = structuredClone(coils);
  const point = ([x, y]: [number, number]): [number, number] => [flip.mirror_x ? config.active_area_length_m - x : x, flip.mirror_y ? config.board_width_m - y : y];
  const layer = (value: number) => flip.reverse_layers ? config.num_layers - 1 - value : value;
  for (const phase of result.phases) {
    phase.layer_idx = layer(phase.layer_idx);
    for (const s of phase.segments) { s.start = point(s.start); s.end = point(s.end); }
    for (const c of phase.corner_arcs ?? []) { c.start = point(c.start); c.mid = point(c.mid); c.end = point(c.end); }
    for (const s of phase.splines ?? []) { s.control_points = s.control_points.map(p => { const [x, y] = point([p.x, p.y]); return { x, y }; }); s.layer = layer(s.layer); }
    phase.terminal_start = point(phase.terminal_start);
    phase.terminal_end = point(phase.terminal_end);
    if (phase.via_positions) phase.via_positions = phase.via_positions.map(point);
    for (const v of phase.routed_vias ?? []) { v.position = point(v.position); v.from_layer = layer(v.from_layer); v.to_layer = layer(v.to_layer); }
    const [x0, y0] = point([phase.bounding_box[0], phase.bounding_box[1]]), [x1, y1] = point([phase.bounding_box[2], phase.bounding_box[3]]);
    phase.bounding_box = [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
  }
  result.phases.sort((a, b) => a.layer_idx - b.layer_idx || a.phase_idx - b.phase_idx);
  if (result.routing_dimensions) {
    for (const band of result.routing_dimensions.phase_band_widths) band.layer = layer(band.layer);
    for (const region of result.routing_dimensions.pole_regions) { region.start = point(region.start); region.end = point(region.end); }
  }
  return result;
}
