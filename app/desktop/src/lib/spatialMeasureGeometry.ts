import { Vector3 } from "three";
import type { CoilScene } from "./coilScene";
import type { PhysicalPoint } from "./spatialMeasure.svelte";

/** Scene axes are X, physical Z, -Y. Return true model millimetres. */
export function sceneToPhysicalMm(point: Vector3, scene: Pick<CoilScene, "centerMm" | "scale">): PhysicalPoint {
  return { x: point.x / scene.scale + scene.centerMm[0], y: -(point.z / scene.scale + scene.centerMm[2]), z: point.y / scene.scale + scene.centerMm[1] };
}

export function physicalMmToScene(point: PhysicalPoint, scene: Pick<CoilScene, "centerMm" | "scale">): Vector3 {
  return new Vector3((point.x - scene.centerMm[0]) * scene.scale, (point.z - scene.centerMm[1]) * scene.scale, (-point.y - scene.centerMm[2]) * scene.scale);
}
