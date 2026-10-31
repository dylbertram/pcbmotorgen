import { Box3, OrthographicCamera, Vector3 } from "three";
import type { CoilScene } from "./coilScene";
import type { WorldTransform } from "./chart";

export interface TopCameraTransform { transform: WorldTransform; panX: number; panY: number; width: number; height: number }

/** Project the shared orthographic camera onto the editor's existing metric
 * transform. Selection, terminal and annotation overlays use this same mapping. */
export function alignTopCamera(camera: OrthographicCamera, scene: Pick<CoilScene,"scale"|"centerMm">, top: TopCameraTransform, width: number, height: number): Vector3 | null {
  const { transform: t, panX, panY } = top;
  if (![t.s,top.width,top.height,width,height].every(v => Number.isFinite(v) && v>0)) return null;
  const xMm = (top.width/2-t.tx-panX)/t.s*1000;
  const yMm = (t.ty+panY-top.height/2)/t.s*1000;
  const target = new Vector3((xMm-scene.centerMm[0])*scene.scale,0,(-yMm-scene.centerMm[2])*scene.scale);
  camera.up.set(0,0,-1); camera.position.copy(target).add(new Vector3(0,500,0)); camera.lookAt(target);
  camera.left=-width/2; camera.right=width/2; camera.top=height/2; camera.bottom=-height/2;
  camera.zoom=t.s*width/(top.width*1000*scene.scale); camera.far=2000;
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
  return target;
}

/** Fit display geometry in the requested view without another controller's
 * cached camera angles. World/SI geometry is never changed by camera fitting. */
export function fitCoilCamera(camera: OrthographicCamera, box: Box3, width: number, height: number, direction: Vector3): Vector3 | null {
  if (box.isEmpty() || width <= 0 || height <= 0 || !Number.isFinite(width + height)) return null;
  const center = box.getCenter(new Vector3()), size = box.getSize(new Vector3());
  const distance = Math.max(14, size.length() * 2);
  const offset = direction.clone().normalize();
  if (!Number.isFinite(offset.lengthSq()) || offset.lengthSq() === 0) return null;
  camera.position.copy(center).addScaledVector(offset, distance);
  camera.lookAt(center); camera.updateMatrixWorld(true);
  let halfWidth = 0, halfHeight = 0;
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
    const p = new Vector3(x, y, z).applyMatrix4(camera.matrixWorldInverse);
    halfWidth = Math.max(halfWidth, Math.abs(p.x)); halfHeight = Math.max(halfHeight, Math.abs(p.y));
  }
  camera.left = -width / 2; camera.right = width / 2;
  camera.top = height / 2; camera.bottom = -height / 2;
  camera.zoom = Math.min(width / Math.max(halfWidth * 2 * 1.25, 1e-6), height / Math.max(halfHeight * 2 * 1.25, 1e-6));
  camera.far = Math.max(1000, distance + size.length() * 2);
  camera.updateProjectionMatrix();
  return center;
}

/** Normalized screen corners, projected onto the current orbit-target plane.
 * Recenter both camera and orbit pivot without changing the viewing angle. */
export function fitCoilWindow(camera: OrthographicCamera, target: Vector3, a: [number, number], b: [number, number]): Vector3 | null {
  const width = Math.abs(a[0] - b[0]), height = Math.abs(a[1] - b[1]);
  if (!a.concat(b).every(Number.isFinite) || width < 1e-6 || height < 1e-6) return null;
  camera.updateMatrixWorld(true);
  const depth = target.clone().project(camera).z;
  const center = new Vector3(a[0] + b[0] - 1, 1 - a[1] - b[1], depth).unproject(camera);
  camera.position.add(center.clone().sub(target));
  camera.zoom *= Math.min(1 / width, 1 / height);
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
  return center;
}
