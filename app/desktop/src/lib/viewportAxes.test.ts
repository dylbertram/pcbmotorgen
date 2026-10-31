import { describe, expect, it } from "vitest";
import { viewportAxes } from "./viewportAxes";

describe("board XYZ orientation", () => {
  it("shows only the top XY plane, not the end-on Z axis", () => {
    const axes = Object.fromEntries(viewportAxes("top", null).map(axis => [axis.name, axis]));
    expect(axes.X.x).toBeCloseTo(1); expect(axes.X.y).toBeCloseTo(0);
    expect(axes.Y.x).toBeCloseTo(0); expect(axes.Y.y).toBeCloseTo(-1);
    expect(axes.Z).toBeUndefined();
  });
  it("shows front XZ and left YZ planes", () => {
    const front = Object.fromEntries(viewportAxes("front", null).map(a => [a.name, a]));
    expect(front.X.x).toBeCloseTo(1); expect(front.Z.y).toBeCloseTo(-1); expect(front.Y).toBeUndefined();
    const left = Object.fromEntries(viewportAxes("left", null).map(a => [a.name, a]));
    expect(left.Y.x).toBeCloseTo(-1); expect(left.Z.y).toBeCloseTo(-1); expect(left.X).toBeUndefined();
  });
  for (const [axis, position, up] of [
    ["X", [1, 0, 0], [0, 1, 0]], ["X", [-1, 0, 0], [0, 1, 0]],
    ["Y", [0, 0, -1], [0, 1, 0]], ["Y", [0, 0, 1], [0, 1, 0]],
    ["Z", [0, 1, 0], [0, 0, -1]], ["Z", [0, -1, 0], [0, 0, -1]],
  ] as const) it(`hides end-on ${axis} for camera ${position}`, () => {
    const axes = viewportAxes("iso", { position: [...position], target: [0, 0, 0], up: [...up] });
    expect(axes).toHaveLength(2);
    expect(axes.map(a => a.name)).not.toContain(axis);
  });
  it("hides near-end-on axes and restores them as the camera moves off-axis", () => {
    const camera = { position: [.01, 1, 0], target: [0, 0, 0], up: [0, 0, -1] };
    expect(viewportAxes("iso", camera).map(a => a.name)).not.toContain("Z");
    camera.position = [.1, 1, 0];
    expect(viewportAxes("iso", camera).map(a => a.name)).toContain("Z");
    expect(viewportAxes("iso", null)).toHaveLength(3);
  });
  it("follows the actual camera orientation but ignores zoom, translation and display Z scale", () => {
    const a = viewportAxes("iso", { position: [12, 10, 14], target: [0, 0, 0], up: [0, 1, 0] });
    const b = viewportAxes("iso", { position: [24, 20, 28], target: [12, 10, 14], up: [0, 1, 0] });
    expect(a).toEqual(b);
    expect(viewportAxes("iso", { position: [-12, 10, 14], target: [0, 0, 0] })).not.toEqual(a);
  });
});
