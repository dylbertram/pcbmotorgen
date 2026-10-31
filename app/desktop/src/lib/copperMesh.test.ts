import { describe, expect, it } from "vitest";
import { Box3, Vector3 } from "three";
import { copperRibbonShape, joinCopperPaths, rectangularCopperGeometry } from "./copperMesh";

const p = (x: number, z: number, y = 0) => new Vector3(x, y, z);
describe("rectangular copper", () => {
  it("uses independent physical width and thickness without stretching copper at exaggerated Z", () => {
    const geometry = rectangularCopperGeometry([{ points: [p(0, 0, -2), p(5, 0, -2)] }], .2, .035, 20);
    geometry.computeBoundingBox();
    const box = geometry.boundingBox!;
    expect(box.min.x).toBeCloseTo(0); expect(box.max.x).toBeCloseTo(5);
    expect(box.getSize(new Vector3()).z).toBeCloseTo(.2);
    expect(box.getSize(new Vector3()).y).toBeCloseTo(.035, 4);
    expect(box.getCenter(new Vector3()).y).toBeCloseTo(-40);
    geometry.dispose();
  });
  it("stitches shuffled and reversed line/curve endpoints without internal caps", () => {
    const paths = [{ points: [p(1, 0), p(0, 0)] }, { points: [p(1, 1), p(2, 1)] }, { points: [p(1, 0), p(1, 1)] }];
    const before = JSON.stringify(paths);
    const joined = joinCopperPaths(paths);
    expect(joined).toHaveLength(1); expect(joined[0]).toHaveLength(4);
    expect(JSON.stringify(paths)).toBe(before);
    const shape = copperRibbonShape(joined[0], .2)!;
    expect(shape.getPoints().every(v => Number.isFinite(v.x + v.y))).toBe(true);
  });
  it("does not join different heights, disconnected paths, or invent a branch order", () => {
    expect(joinCopperPaths([{ points: [p(0, 0), p(1, 0)] }, { points: [p(1, 0, -.3), p(2, 0, -.3)] }])).toHaveLength(2);
    expect(joinCopperPaths([1, 2, 3].map(x => ({ points: [p(0, 0), p(x, x * x)] })))).toHaveLength(3);
  });
  it("makes a closed loop with a real hole and no long corner spikes", () => {
    const shape = copperRibbonShape([p(0, 0), p(2, 0), p(2, 2), p(0, 2), p(0, 0)], .2)!;
    expect(shape.holes).toHaveLength(1);
    const box = new Box3().setFromPoints(shape.getPoints().map(v => p(v.x, v.y)));
    expect(box.getSize(new Vector3()).x).toBeCloseTo(2.2);
    const acute = copperRibbonShape([p(0, 0), p(1, 0), p(0, .001)], .2)!;
    expect(acute.getPoints().every(v => Math.abs(v.x) <= 1.4 && Math.abs(v.y) < .4)).toBe(true);
  });
  it("shares the same miter profile across differently colored heat batches", () => {
    const a = { points: [p(0, 0), p(1, 0)] }, b = { points: [p(1, 0), p(1, 1)] };
    const geometries = [a, b].map(path => rectangularCopperGeometry([path], .2, .035, 1, [a, b]));
    const profile = (geometry: typeof geometries[number]) => {
      const position = geometry.getAttribute("position"), points = new Set<string>();
      for (let i = 0; i < position.count; i++) {
        const x = position.getX(i), z = position.getZ(i);
        if (Math.abs(x - 1) <= .11 && Math.abs(z) <= .11) points.add(`${x.toFixed(4)},${z.toFixed(4)}`);
      }
      return [...points].sort();
    };
    expect(profile(geometries[0])).toEqual(["0.9000,0.1000", "1.1000,-0.1000"]);
    expect(profile(geometries[1])).toEqual(profile(geometries[0]));
    geometries.forEach(g => g.dispose());
  });
});
