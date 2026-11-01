import { BufferGeometry, Color, Float32BufferAttribute, Vector3 } from "three";
import type { CoilScene } from "./coilScene";
import type { FieldPreview } from "./types/simulationVisualization";
import { FIELD_PALETTE, physicalToScene } from "./visualizationGeometry";

export type FieldStyle = "lines-slice" | "lines" | "lines-3d" | "slice" | "arrows";
type Point = [number, number, number];
type SceneTransform = Pick<CoilScene, "centerMm" | "scale">;

/** Interpolate validated native XYZ samples only. Never extrapolate or create
 * an analytical/browser substitute. Integration and all lengths stay in SI. */
export function sampledFieldGrid(field: FieldPreview) {
  const axes = [0, 1, 2].map(axis => [...new Set(field.samples.map(s => s.position_m[axis]))].sort((a, b) => a - b));
  const counts = axes.map(a => a.length);
  if (counts.some(n => n < 2) || counts.reduce((a, b) => a * b, 1) !== field.samples.length || field.samples.length > 2048) {
    throw new Error("Field lines require a complete bounded native XYZ grid");
  }
  const spacing = axes.map(a => (a.at(-1)! - a[0]) / (a.length - 1));
  if (spacing.some(v => !Number.isFinite(v) || v <= 0) || field.samples.some((sample, i) => {
    const indices = [i % counts[0], Math.floor(i / counts[0]) % counts[1], Math.floor(i / (counts[0] * counts[1]))];
    return sample.position_m.some((v, axis) => !Number.isFinite(v) || Math.abs(v - (axes[axis][0] + indices[axis] * spacing[axis])) > 1e-12)
      || sample.b_t.some(v => !Number.isFinite(v));
  })) throw new Error("Field grid is not ordered, finite and uniformly sampled");
  const bounds = axes.map(a => [a[0], a.at(-1)!] as [number, number]);
  const insideMagnet = (p: Point) => field.magnets.some(m => p.every((v, axis) => Math.abs(v - m.center_m[axis]) <= m.size_m[axis] / 2));
  const crossesMagnet = (a: Point, b: Point) => field.magnets.some(m => {
    let enter = 0, leave = 1;
    for (let axis = 0; axis < 3; axis++) {
      const lo = m.center_m[axis] - m.size_m[axis] / 2, hi = m.center_m[axis] + m.size_m[axis] / 2, delta = b[axis] - a[axis];
      if (Math.abs(delta) < 1e-20) { if (a[axis] < lo || a[axis] > hi) return false; }
      else {
        const first = (lo - a[axis]) / delta, last = (hi - a[axis]) / delta;
        enter = Math.max(enter, Math.min(first, last)); leave = Math.min(leave, Math.max(first, last));
        if (enter > leave) return false;
      }
    }
    return true;
  });
  const sample = (p: Point): Point | null => {
    if (p.some((v, axis) => !Number.isFinite(v) || v < bounds[axis][0] || v > bounds[axis][1])) return null;
    const indices = p.map((v, axis) => Math.min(counts[axis] - 2, Math.floor((v - bounds[axis][0]) / spacing[axis])));
    const weights = p.map((v, axis) => (v - axes[axis][indices[axis]]) / spacing[axis]);
    const value: Point = [0, 0, 0];
    for (let z = 0; z < 2; z++) for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) {
      const w = (x ? weights[0] : 1 - weights[0]) * (y ? weights[1] : 1 - weights[1]) * (z ? weights[2] : 1 - weights[2]);
      const b = field.samples[((indices[2] + z) * counts[1] + indices[1] + y) * counts[0] + indices[0] + x].b_t;
      for (let axis = 0; axis < 3; axis++) value[axis] += w * b[axis];
    }
    return value;
  };
  return { bounds, spacing, sample, insideMagnet, crossesMagnet };
}

function fieldColor(magnitude: number, maximum: number): Color {
  const at = Math.max(0, Math.min(1, maximum > 0 ? magnitude / maximum : 0)) * (FIELD_PALETTE.length - 1);
  const low = Math.min(FIELD_PALETTE.length - 2, Math.floor(at));
  return new Color(FIELD_PALETTE[low]).lerp(new Color(FIELD_PALETTE[low + 1]), at - low);
}
function geometry(positions: number[], colors: number[]): BufferGeometry {
  return new BufferGeometry().setAttribute("position", new Float32BufferAttribute(positions, 3)).setAttribute("color", new Float32BufferAttribute(colors, 3));
}

/** XZ slice at a selectable physical Y. Magnitude is the norm of the
 * interpolated vector, not an invented scalar texture or a thermal map. */
export function fieldSliceGeometry(field: FieldPreview, scene: SceneTransform, sliceFraction: number): BufferGeometry {
  const grid = sampledFieldGrid(field), positions: number[] = [], colors: number[] = [];
  const maximum = Math.max(0, ...field.samples.map(s => s.magnitude_t));
  const y = grid.bounds[1][0] + Math.max(0, Math.min(1, sliceFraction)) * (grid.bounds[1][1] - grid.bounds[1][0]);
  const nx = 96, nz = 48;
  const point = (x: number, z: number): Point => [grid.bounds[0][0] + x / nx * (grid.bounds[0][1] - grid.bounds[0][0]), y,
    grid.bounds[2][0] + z / nz * (grid.bounds[2][1] - grid.bounds[2][0])];
  for (let z = 0; z < nz; z++) for (let x = 0; x < nx; x++) {
    const corners = [point(x, z), point(x + 1, z), point(x + 1, z + 1), point(x, z + 1)];
    // Leave the magnet interiors unpainted. The mesh is an observation slice,
    // not a material field solution. No triangle spans a magnet boundary.
    const overlapsMagnet = field.magnets.some(m => Math.abs(y - m.center_m[1]) <= m.size_m[1] / 2
      && corners[0][0] <= m.center_m[0] + m.size_m[0] / 2 && corners[1][0] >= m.center_m[0] - m.size_m[0] / 2
      && corners[0][2] <= m.center_m[2] + m.size_m[2] / 2 && corners[2][2] >= m.center_m[2] - m.size_m[2] / 2);
    if (overlapsMagnet) continue;
    const values = corners.map(p => grid.sample(p));
    if (values.some(v => !v)) continue;
    for (const i of [0, 1, 2, 0, 2, 3]) {
      positions.push(...physicalToScene(corners[i], scene).toArray());
      colors.push(...fieldColor(Math.hypot(...values[i]!), maximum).toArray());
    }
  }
  return geometry(positions, colors);
}

/** Integrate Bx/Bz on the selected physical XZ plane by default, not a flattened
 * 3D trajectory. Color still shows full |B| at that observation. Explicit 3D
 * mode follows XYZ from the same seed plane. Both stop at magnets, domain
 * exits, projected nulls, loops or the fixed step/length cap. */
export function fieldLineGeometry(field: FieldPreview, scene: SceneTransform, sliceFraction: number, space: "slice" | "3d" = "slice"): BufferGeometry {
  const grid = sampledFieldGrid(field), positions: number[] = [], colors: number[] = [];
  const maximum = Math.max(0, ...field.samples.map(s => s.magnitude_t));
  const step = Math.min(...grid.spacing) / 6;
  const y = grid.bounds[1][0] + Math.max(0, Math.min(1, sliceFraction)) * (grid.bounds[1][1] - grid.bounds[1][0]);
  const segment = (a: Point, b: Point) => {
    for (const p of [a, b]) {
      positions.push(...physicalToScene(p, scene).toArray());
      colors.push(...fieldColor(Math.hypot(...grid.sample(p)!), maximum).toArray());
    }
  };
  const direction = (p: Point, sign: number): Point | null => {
    const b = grid.sample(p);
    if (!b || grid.insideMagnet(p)) return null;
    const projected: Point = space === "slice" ? [b[0], 0, b[2]] : b;
    const norm = Math.hypot(...projected);
    return norm > Math.max(1e-14, maximum * 1e-8) ? projected.map(v => sign * v / norm) as Point : null;
  };
  for (let iz = 0; iz < 6; iz++) for (let ix = 0; ix < 24; ix++) {
    const seed: Point = [grid.bounds[0][0] + (ix + .5) / 24 * (grid.bounds[0][1] - grid.bounds[0][0]), y,
      grid.bounds[2][0] + (iz + .5) / 6 * (grid.bounds[2][1] - grid.bounds[2][0])];
    for (const sign of [-1, 1]) {
      let p = seed;
      const visited = new Map<string, number>();
      for (let i = 0; i < 240; i++) {
        const first = direction(p, sign);
        if (!first) break;
        const midpoint = p.map((v, axis) => v + step * first[axis] / 2) as Point;
        const middle = direction(midpoint, sign);
        if (!middle) break;
        const next = p.map((v, axis) => v + step * middle[axis]) as Point;
        if (!direction(next, sign) || grid.crossesMagnet(p, next)) break;
        segment(p, next);
        // Direction cue along +B, placed sparsely rather than detached glyphs.
        if (sign === 1 && i % 40 === 20) {
          const forward = new Vector3(...middle), side = forward.clone().cross(Math.abs(forward.y) > .9 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0)).normalize();
          for (const offset of [-1, 1]) {
            const head = new Vector3(...next).addScaledVector(forward, -step * 1.8).addScaledVector(side, step * .7 * offset).toArray() as Point;
            if (grid.sample(head) && !grid.crossesMagnet(next, head)) segment(next, head);
          }
        }
        p = next;
        // Trilinear display interpolation need not be divergence-free. Stop
        // revisited trajectories instead of drawing repeated artificial spirals
        // around a coarse-grid null or overpainting the same closed path.
        const key = p.map(v => Math.round(v / step)).join(":");
        const previous = visited.get(key);
        if (previous !== undefined && i - previous > 8) break;
        if (previous === undefined) visited.set(key, i);
        if (i > 12 && Math.hypot(...p.map((v, axis) => v - seed[axis])) < step) break;
      }
    }
  }
  return geometry(positions, colors);
}
