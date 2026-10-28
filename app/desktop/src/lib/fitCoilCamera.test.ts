import { describe, expect, it } from "vitest";
import { Box3, OrthographicCamera, Vector3 } from "three";
import { fitCoilCamera } from "./fitCoilCamera";

describe("coil viewer camera fitting", () => {
  const box = new Box3(new Vector3(-6, -.1, -1), new Vector3(6, .1, 1));
  it("looks squarely at the XZ section instead of retaining isometric angles", () => {
    const camera = new OrthographicCamera();
    fitCoilCamera(camera, box, 1000, 500, new Vector3(12, 10, 14));
    fitCoilCamera(camera, box, 1000, 500, new Vector3(0, 0, 1));
    const direction = camera.getWorldDirection(new Vector3());
    expect(direction.x).toBeCloseTo(0, 12); expect(direction.y).toBeCloseTo(0, 12); expect(direction.z).toBeCloseTo(-1, 12);
    const first = new Vector3(-6, 0, 0).project(camera), last = new Vector3(6, 0, 0).project(camera);
    expect(first.y).toBeCloseTo(last.y, 12);
  });
  it("fits all corners in wide and narrow viewers, including exaggerated display height", () => {
    const before = box.clone();
    for (const [width, height] of [[1000, 300], [240, 600]]) for (const direction of [new Vector3(0, 0, 1), new Vector3(12, 10, 14)]) {
      const camera = new OrthographicCamera();
      const tall = box.clone(); tall.max.y = 20;
      fitCoilCamera(camera, tall, width, height, direction);
      for (const x of [tall.min.x, tall.max.x]) for (const y of [tall.min.y, tall.max.y]) for (const z of [tall.min.z, tall.max.z]) {
        const p = new Vector3(x, y, z).project(camera);
        expect(Math.abs(p.x)).toBeLessThanOrEqual(.800001); expect(Math.abs(p.y)).toBeLessThanOrEqual(.800001);
        expect(Math.abs(p.z)).toBeLessThan(1);
      }
    }
    expect(box).toEqual(before);
  });
  it("does not change the camera for empty or unmeasured scenes", () => {
    const camera = new OrthographicCamera(), before = camera.clone();
    expect(fitCoilCamera(camera, new Box3(), 1000, 500, new Vector3(0, 0, 1))).toBeNull();
    expect(fitCoilCamera(camera, box, 0, 500, new Vector3(0, 0, 1))).toBeNull();
    expect(camera.position).toEqual(before.position); expect(camera.zoom).toBe(before.zoom);
  });
});
