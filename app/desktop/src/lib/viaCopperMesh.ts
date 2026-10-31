import { BufferGeometry, ExtrudeGeometry, Path, Shape, Vector2, type Vector3 } from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { Ring } from "polygon-clipping";

export const VIA_RADIAL_SEGMENTS = 48;
export interface CopperPad {
  point: Vector3;
  thickness: number;
  layer: number;
  net: string;
}

/** One shared polygon for pads and trace cutouts, so their edges meet exactly. */
export function viaCircle(x: number, y: number, radius: number): Ring {
  const ring: Ring = Array.from({ length: VIA_RADIAL_SEGMENTS }, (_, i) => {
    const angle = i * 2 * Math.PI / VIA_RADIAL_SEGMENTS;
    return [x + radius * Math.cos(angle), y + radius * Math.sin(angle)];
  });
  return [...ring, ring[0]];
}

function annularSolid(x: number, z: number, innerRadius: number, outerRadius: number, bottom: number, height: number): BufferGeometry {
  const points = (radius: number) => viaCircle(x, -z, radius).slice(0, -1).map(([a, b]) => new Vector2(a, b));
  const shape = new Shape(points(outerRadius));
  shape.holes.push(new Path(points(innerRadius).reverse()));
  const geometry = new ExtrudeGeometry(shape, { depth: height, bevelEnabled: false, steps: 1, curveSegments: 1 });
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, bottom, 0);
  return geometry;
}

function mergeAndDispose(parts: BufferGeometry[]): BufferGeometry {
  const result = parts.length ? mergeGeometries(parts)! : new BufferGeometry();
  parts.forEach(part => part.dispose());
  return result;
}

/** Copper thickness stays physical while the layer centers are magnified. */
export function annularPadsGeometry(pads: CopperPad[], diameter: number, drill: number, zScale = 1): BufferGeometry {
  return mergeAndDispose(pads.map(({ point, thickness }) => annularSolid(point.x, point.z,
    drill / 2, diameter / 2, point.y * zScale - thickness / 2, thickness)));
}

/** Hollow plated barrel, rather than an opaque tube spanning the bore. */
export function viaBarrelsGeometry(paths: { points: Vector3[] }[], drill: number, plating: number, zScale = 1): BufferGeometry {
  const parts = paths.flatMap(({ points }) => {
    const a = points[0], b = points.at(-1);
    if (!a || !b || Math.abs(a.y - b.y) < 1e-12) return [];
    return [annularSolid(a.x, a.z, drill / 2, drill / 2 + plating, Math.min(a.y, b.y) * zScale, Math.abs(a.y - b.y) * zScale)];
  });
  return mergeAndDispose(parts);
}
