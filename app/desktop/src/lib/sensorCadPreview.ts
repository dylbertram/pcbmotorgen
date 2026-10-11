import type { CadGeometry, SensorGeometry, SensorNetGeometry } from "./types";

/** Map imported centerlines to the sensor preview without changing their nets. */
export function cadGeometryToSensorPreview(cad: CadGeometry, viaSize: number): SensorGeometry {
  const nets = new Map<string, SensorNetGeometry>();
  const netFor = (name: string): SensorNetGeometry => {
    let net = nets.get(name);
    if (!net) {
      net = { name, segments: [], curves: [], splines: [], vias: [], trace_width_mm: cad.trace_width_mm, via_size_mm: viaSize };
      nets.set(name, net);
    }
    return net;
  };
  const points = [];
  for (const segment of cad.routing.segments) {
    netFor(segment.net).segments.push(segment);
    points.push(segment.start, segment.end);
  }
  for (const curve of cad.routing.curves) {
    netFor(curve.net).curves!.push(curve);
    points.push(curve.start, curve.mid, curve.end);
  }
  for (const spline of cad.routing.splines ?? []) {
    netFor(spline.net).splines!.push(spline);
    points.push(...spline.control_points);
  }
  for (const via of cad.routing.vias) {
    netFor(via.net).vias.push(via);
    points.push(via.position);
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const { x, y } of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return {
    nets: [...nets.values()],
    terminal_markers: [],
    board_bounds_mm: points.length ? [minX, minY, maxX, maxY] : [0, 0, 1, 1],
  };
}
