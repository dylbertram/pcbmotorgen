import { describe, expect, it } from "vitest";
import { viewportAxes } from "./viewportAxes";

describe("board XYZ orientation", () => {
  it("shows top XY and an end-on positive Z, not the renderer's Y-up axes", () => {
    const axes = Object.fromEntries(viewportAxes("top", null).map(axis => [axis.name, axis]));
    expect(axes.X.x).toBeCloseTo(1); expect(axes.X.y).toBeCloseTo(0);
    expect(axes.Y.x).toBeCloseTo(0); expect(axes.Y.y).toBeCloseTo(-1);
    expect(axes.Z.depth).toBeCloseTo(1);
  });
  it("shows front XZ and left YZ planes", () => {
    const front = Object.fromEntries(viewportAxes("front", null).map(a => [a.name, a]));
    expect(front.X.x).toBeCloseTo(1); expect(front.Z.y).toBeCloseTo(-1); expect(front.Y.depth).toBeCloseTo(-1);
    const left = Object.fromEntries(viewportAxes("left", null).map(a => [a.name, a]));
    expect(left.Y.x).toBeCloseTo(-1); expect(left.Z.y).toBeCloseTo(-1); expect(left.X.depth).toBeCloseTo(-1);
  });
  it("follows the actual camera orientation but ignores zoom, translation and display Z scale", () => {
    const a = viewportAxes("iso", { position: [12, 10, 14], target: [0, 0, 0], up: [0, 1, 0] });
    const b = viewportAxes("iso", { position: [24, 20, 28], target: [12, 10, 14], up: [0, 1, 0] });
    expect(a).toEqual(b);
    expect(viewportAxes("iso", { position: [-12, 10, 14], target: [0, 0, 0] })).not.toEqual(a);
  });
});
