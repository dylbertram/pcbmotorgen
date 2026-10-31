import { BufferGeometry, ExtrudeGeometry, Path, Shape, Vector2, Vector3 } from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const endpointKey = (v: Vector3) => v.toArray().map(n => Math.round(n * 1e8)).join(",");
type Neighbors = Map<string, Vector2[]>;

/** Shared end profiles also survive a heat-color batch boundary. */
function endpointDirections(paths: { points: Vector3[] }[]): Neighbors {
  const neighbors: Neighbors = new Map();
  for (const { points } of paths) {
    if (points.length < 2) continue;
    for (const [a, b] of [[points[0], points[1]], [points.at(-1)!, points.at(-2)!]]) {
      const key = endpointKey(a), direction = new Vector2(b.x - a.x, a.z - b.z).normalize();
      neighbors.set(key, [...(neighbors.get(key) ?? []), direction]);
    }
  }
  return neighbors;
}

/** Join only degree-two endpoints. Layer/net partitioning belongs to the caller.
 * Do not bridge nearby traces, branches, or endpoints on different layers. */
export function joinCopperPaths(paths: { points: Vector3[] }[]): Vector3[][] {
  const lines = paths.map(p => p.points.filter((v, i, a) => !i || v.distanceToSquared(a[i - 1]) > 1e-20)).filter(p => p.length > 1);
  const key = endpointKey;
  const ends = new Map<string, number[]>();
  lines.forEach((p, i) => {
    for (const v of [p[0], p.at(-1)!]) {
      const k = key(v); ends.set(k, [...(ends.get(k) ?? []), i]);
    }
  });
  const used = new Set<number>(), result: Vector3[][] = [];
  for (let i = 0; i < lines.length; i++) {
    if (used.has(i)) continue;
    used.add(i);
    let points = [...lines[i]];
    for (let side = 0; side < 2; side++) {
      while (true) {
        const end = key(points.at(-1)!), touching = ends.get(end)!;
        if (touching.length !== 2) break;
        const next = touching.find(j => !used.has(j));
        if (next === undefined) break;
        used.add(next);
        const line = key(lines[next][0]) === end ? lines[next] : [...lines[next]].reverse();
        points.push(...line.slice(1));
      }
      points.reverse();
    }
    result.push(points);
  }
  return result;
}

/** A flat ribbon with butt ends, shared miter joins and bounded bevel corners.
 * Curves are the original sampled centerlines, not smoothed routing changes. */
export function copperRibbonShape(points: Vector3[], width: number, neighbors?: Neighbors): Shape | null {
  const closed = points.length > 2 && points[0].distanceToSquared(points.at(-1)!) < 1e-16;
  const p = (closed ? points.slice(0, -1) : points).map(v => new Vector2(v.x, -v.z));
  if (p.length < 2 || width <= 0 || !Number.isFinite(width)) return null;
  const offset = (sign: number) => p.flatMap((v, i) => {
    const prev = p[(i - 1 + p.length) % p.length], next = p[(i + 1) % p.length];
    let before = v.clone().sub(prev).normalize(), after = next.clone().sub(v).normalize();
    const normal = (d: Vector2) => new Vector2(-d.y, d.x).multiplyScalar(sign * width / 2);
    if (!closed && (i === 0 || i === p.length - 1)) {
      const own = i === 0 ? after : before.clone().negate();
      const touching = neighbors?.get(endpointKey(points[i]));
      const other = touching?.length === 2 ? touching.find(d => d.dot(own) < .999999) : undefined;
      if (!other) return [v.clone().add(normal(i === 0 ? after : before))];
      if (i === 0) before = other.clone().negate(); else after = other;
    }
    const a = normal(before), b = normal(after), bisector = a.clone().add(b);
    const denominator = bisector.dot(b);
    if (denominator < width * width * 1e-8) return [v.clone().add(a), v.clone().add(b)];
    const miter = bisector.multiplyScalar(b.lengthSq() / denominator);
    return miter.length() <= width * 2 ? [v.clone().add(miter)] : [v.clone().add(a), v.clone().add(b)];
  });
  const left = offset(1), right = offset(-1);
  if (!closed) return new Shape([...left, ...right.reverse()]);
  // A closed centerline needs a hole, rather than a cut across the copper ring.
  const signedArea = p.reduce((sum, v, i) => sum + v.cross(p[(i + 1) % p.length]), 0);
  const shape = new Shape(signedArea > 0 ? right : left);
  shape.holes.push(new Path(signedArea > 0 ? left : right));
  return shape;
}

export function rectangularCopperGeometry(paths: { points: Vector3[] }[], width: number, thickness: number, zScale = 1, contextPaths = paths): BufferGeometry {
  if (!Number.isFinite(thickness) || thickness <= 0) throw new Error("Copper thickness must be positive and finite.");
  const ribbons: BufferGeometry[] = [];
  const neighbors = endpointDirections(contextPaths);
  for (const points of joinCopperPaths(paths)) {
    const shape = copperRibbonShape(points, width, neighbors);
    if (!shape) continue;
    const geometry = new ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false, steps: 1, curveSegments: 1 });
    geometry.rotateX(-Math.PI / 2);
    geometry.translate(0, points[0].y * zScale - thickness / 2, 0);
    ribbons.push(geometry);
  }
  const result = ribbons.length ? mergeGeometries(ribbons) : new BufferGeometry();
  for (const ribbon of ribbons) ribbon.dispose();
  return result;
}
