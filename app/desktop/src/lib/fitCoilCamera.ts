import { Box3, OrthographicCamera, Plane, Raycaster, Vector2, Vector3, type Object3D } from "three";
import type { CoilScene } from "./coilScene";
import type { WorldTransform } from "./chart";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface TopCameraTransform { transform: WorldTransform; panX: number; panY: number; width: number; height: number }

/** Clear pending orbit/pan damping without applying its remaining motion to
 * the displayed camera. Programmatic fits start from what the user sees. */
export function stopCoilCameraMotion(camera: OrthographicCamera, controls: OrbitControls): void {
  const position = camera.position.clone(), target = controls.target.clone(), zoom = camera.zoom;
  const damping = controls.enableDamping;
  controls.enableDamping = false; controls.update();
  camera.position.copy(position); controls.target.copy(target); camera.zoom = zoom;
  camera.updateProjectionMatrix(); controls.update(); controls.enableDamping = damping;
}

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

/** Focus on the visible surface under the window center, or the copper's
 * layer plane when the center falls in a gap between traces. Hidden objects
 * and annotation geometry never supply the depth of the orbit pivot. */
export function coilWindowFocus(camera: OrthographicCamera, content: Object3D, a: [number, number], b: [number, number]): Vector3 | null {
  if (!a.concat(b).every(Number.isFinite)) return null;
  camera.updateMatrixWorld(true); content.updateWorldMatrix(true, true);
  const ray = new Raycaster();
  ray.params.Line.threshold = 2 / camera.zoom;
  ray.setFromCamera(new Vector2(a[0] + b[0] - 1, 1 - a[1] - b[1]), camera);
  const objects: Object3D[] = [], copper = new Box3();
  content.traverseVisible(object => {
    if (!object.userData.measureable) return;
    objects.push(object);
    if (typeof object.userData.copperLayerY === "number") copper.union(new Box3().setFromObject(object, true));
  });
  const hit = ray.intersectObjects(objects, false)[0];
  if (hit) {
    // Thin centerlines have a screen-space hit tolerance, not a solid surface.
    if (hit.object.type === "LineSegments" && Math.abs(ray.ray.direction.y) >= 1e-6)
      return ray.ray.intersectPlane(new Plane(new Vector3(0, 1, 0), -hit.point.y), new Vector3());
    return hit.point;
  }
  // An edge-on ray may lie in the copper plane. Its origin is near the
  // camera, not a useful focus point; keep the current depth in that case.
  if (copper.isEmpty() || Math.abs(ray.ray.direction.y) < 1e-6) return null;
  return ray.ray.intersectPlane(new Plane(new Vector3(0, 1, 0), -copper.getCenter(new Vector3()).y), new Vector3());
}

/** Normalized screen corners, projected at the selected geometry's depth.
 * Recenter both camera and orbit pivot without changing the viewing angle. */
export function fitCoilWindow(camera: OrthographicCamera, target: Vector3, a: [number, number], b: [number, number], focus: Vector3 = target): Vector3 | null {
  const width = Math.abs(a[0] - b[0]), height = Math.abs(a[1] - b[1]);
  if (!a.concat(b).every(Number.isFinite) || width < 1e-6 || height < 1e-6) return null;
  camera.updateMatrixWorld(true);
  const depth = focus.clone().project(camera).z;
  const center = new Vector3(a[0] + b[0] - 1, 1 - a[1] - b[1], depth).unproject(camera);
  camera.position.add(center.clone().sub(target));
  camera.zoom *= Math.min(1 / width, 1 / height);
  camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
  return center;
}
