import { Vector3 } from "three";
import type { CoilScene } from "./coilScene";
import type { PhysicalPoint } from "./spatialMeasure.svelte";

/** Scene axes are X, physical Z, -Y. Return true model millimetres, not
 * camera coordinates or magnified heights. Copper thickness is not stretched. */
export function sceneToPhysicalMm(point: Vector3, scene: Pick<CoilScene, "centerMm" | "scale">, zScale: number, copperLayerY?: number): PhysicalPoint {
  const y = copperLayerY === undefined ? point.y / zScale : copperLayerY + point.y - copperLayerY * zScale;
  return { x: point.x / scene.scale + scene.centerMm[0], y: -(point.z / scene.scale + scene.centerMm[2]), z: y / scene.scale + scene.centerMm[1],
    ...(copperLayerY === undefined ? {} : { copperLayerZ: copperLayerY / scene.scale + scene.centerMm[1] }) };
}

export function physicalMmToScene(point: PhysicalPoint, scene: Pick<CoilScene, "centerMm" | "scale">, zScale: number): Vector3 {
  const y = point.copperLayerZ === undefined ? (point.z - scene.centerMm[1]) * zScale
    : (point.copperLayerZ - scene.centerMm[1]) * zScale + point.z - point.copperLayerZ;
  return new Vector3((point.x - scene.centerMm[0]) * scene.scale, y * scene.scale, (-point.y - scene.centerMm[2]) * scene.scale);
}
