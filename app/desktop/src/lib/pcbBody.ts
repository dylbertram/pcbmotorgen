import type { CadGeometry } from "./types";
import type { CoilScene } from "./coilScene";

/** Context envelope, not an exportable/manufacturing board outline. A 1 mm
 * edge allowance encloses all copper, including hidden layers and terminals. */
export function pcbBody(geometry: CadGeometry, scene: CoilScene, thicknessMm: number, zScale = 1, boardTopMm?: number) {
  if (!(thicknessMm > 0) || !Number.isFinite(thicknessMm)) throw new Error("PCB thickness must be positive and finite.");
  const points = [...scene.paths.flatMap(p => p.points), ...scene.vias.flatMap(v => v.points), ...scene.terminals.map(t => t.point)];
  const margin = scene.scale + scene.width / 2;
  const minX = Math.min(...points.map(p => p.x)) - margin, maxX = Math.max(...points.map(p => p.x)) + margin;
  const minZ = Math.min(...points.map(p => p.z)) - margin, maxZ = Math.max(...points.map(p => p.z)) + margin;
  const topMm = boardTopMm ?? Math.max(...geometry.layer_z_mm);
  return { size: [maxX - minX, thicknessMm * scene.scale * zScale, maxZ - minZ] as [number, number, number],
    position: [(minX + maxX) / 2, (topMm - thicknessMm / 2 - scene.centerMm[1]) * scene.scale * zScale, (minZ + maxZ) / 2] as [number, number, number] };
}
