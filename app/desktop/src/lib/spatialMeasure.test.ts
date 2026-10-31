import { describe, expect, it } from "vitest";
import { Vector3 } from "three";
import { SpatialMeasure } from "./spatialMeasure.svelte";
import { physicalMmToScene, sceneToPhysicalMm } from "./spatialMeasureGeometry";

describe("physical 3D measurements", () => {
  const scene = { centerMm: [23, -.4, -4] as [number, number, number], scale: .125 };
  it("includes physical layer height, not display magnification or scene scale", () => {
    for (const zScale of [1, 2, 20]) {
      const measure = new SpatialMeasure(); measure.toggleMode();
      const a = { x: 3, y: 4, z: -.8 }, b = { x: 6, y: 8, z: 0 };
      measure.pick(sceneToPhysicalMm(physicalMmToScene(a, scene, zScale), scene, zScale));
      measure.pick(sceneToPhysicalMm(physicalMmToScene(b, scene, zScale), scene, zScale));
      expect(measure.distanceMm).toBeCloseTo(Math.hypot(3, 4, .8), 12);
    }
  });
  it("does not divide the unexaggerated copper cross-section by the height multiplier", () => {
    const layerY = -.4 * scene.scale;
    const picked = new Vector3(.1, layerY * 20 + .0175 * scene.scale, .5);
    const physical = sceneToPhysicalMm(picked, scene, 20, layerY);
    expect(physical.z).toBeCloseTo(-.8 + .0175, 12);
    expect(physicalMmToScene(physical, scene, 20).distanceTo(picked)).toBeLessThan(1e-12);
  });
  it("supports hover, lock, clear, and does not pick outside measure mode", () => {
    const measure = new SpatialMeasure();
    measure.pick({ x: 0, y: 0, z: 0 }); expect(measure.p1).toBeNull();
    measure.toggleMode(); measure.pick({ x: 0, y: 0, z: 0 });
    measure.cursor = { x: 0, y: 0, z: .8 }; expect(measure.distanceMm).toBe(.8);
    measure.pick({ x: 0, y: 0, z: 1.6 }); expect(measure.distanceMm).toBe(1.6);
    measure.pick({ x: 5, y: 6, z: 0 }); expect(measure.p1).toBeNull();
    measure.toggleMode(); expect(measure.mode).toBe(false); expect(measure.cursor).toBeNull();
  });
});
