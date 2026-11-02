import { Vector3 } from "three";

export interface AxisCamera { position: number[]; target: number[]; up?: number[] }
export type AxisView = "top" | "front" | "left" | "iso";

/** Board XYZ -> the renderer's X/Z-minus-Y frame -> screen directions. */
export function viewportAxes(view: AxisView, camera: AxisCamera | null) {
  const direction = view === "top" ? [0, 1, 0] : view === "front" ? [0, 0, 1] : view === "left" ? [-1, 0, 0] : [12, 10, 14];
  const backward = camera ? new Vector3().fromArray(camera.position).sub(new Vector3().fromArray(camera.target)).normalize() : new Vector3().fromArray(direction).normalize();
  const referenceUp = new Vector3().fromArray(camera?.up ?? (view === "top" ? [0, 0, -1] : [0, 1, 0]));
  const right = referenceUp.clone().cross(backward).normalize();
  const up = backward.clone().cross(right).normalize();
  return [
    { name: "X", vector: new Vector3(1, 0, 0), color: "#f87171" },
    { name: "Y", vector: new Vector3(0, 0, -1), color: "#34d399" },
    { name: "Z", vector: new Vector3(0, 1, 0), color: "#60a5fa" },
  ].map(axis => ({ name: axis.name, color: axis.color, x: axis.vector.dot(right), y: -axis.vector.dot(up), depth: axis.vector.dot(backward) }))
    // End-on axes have no useful screen direction. Hide them instead of
    // drawing a dot and label over the remaining axes.
    .filter(axis => Math.hypot(axis.x, axis.y) >= .08)
    .sort((a, b) => a.depth - b.depth);
}
