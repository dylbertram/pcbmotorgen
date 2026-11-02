import { describe, expect, it } from "vitest";
import {
  createLinearScale,
  paddedRange,
  ticks,
  polyline,
} from "./chart";

describe("createLinearScale", () => {
  it("maps domain endpoints to the pixel extremes", () => {
    const sx = createLinearScale(0, 100, 50, 500);
    expect(sx(0)).toBe(50);
    expect(sx(100)).toBe(550);
    expect(sx(50)).toBe(300);
  });

  it("guards against a degenerate zero-width domain", () => {
    const sx = createLinearScale(10, 10, 0, 100);
    expect(sx(10)).toBe(0);
  });
});

describe("paddedRange", () => {
  it("pads by the requested fraction", () => {
    const [min, max] = paddedRange([0, 100], 0.1);
    expect(min).toBe(-10);
    expect(max).toBe(110);
  });

  it("falls back to a tiny pad for flat data", () => {
    const [min, max] = paddedRange([5, 5]);
    expect(max - min).toBeCloseTo(0.002, 9);
  });
});

describe("ticks", () => {
  it("produces count evenly spaced ticks", () => {
    const sx = createLinearScale(0, 100, 0, 1000);
    const t = ticks(0, 100, 5, sx);
    expect(t).toHaveLength(5);
    expect(t.map((x) => x.v)).toEqual([0, 25, 50, 75, 100]);
    expect(t[1].pos).toBe(250);
  });
});

describe("polyline", () => {
  it("joins points into an SVG points string", () => {
    const sx = createLinearScale(0, 2, 0, 200);
    const sy = createLinearScale(0, 2, 200, -200);
    expect(polyline(sx, sy, [0, 1, 2], [0, 1, 2])).toBe(
      "0.0,200.0 100.0,100.0 200.0,0.0",
    );
  });
});
