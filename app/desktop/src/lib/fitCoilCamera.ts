import { Box3, OrthographicCamera, Vector3 } from "three";

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
