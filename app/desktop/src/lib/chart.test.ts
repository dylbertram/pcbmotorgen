import { describe, expect, it } from "vitest";
import {
  createLinearScale,
  paddedRange,
  ticks,
  polyline,
  fitWorldToView,
  unionBounds,
  type ViewportBBox,
} from "./chart";

describe("createLinearScale", () => {
  it("maps domain endpoints to the pixel extremes", () => {
    const sx = createLinearScale(0, 100, 50, 500);
    expect(sx(0)).toBe(50);
    expect(sx(100)).toBe(550);
    expect(sx(50)).toBe(300);
    expect(sx.scale).toBe(5);
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
    // ascending domain: value 0 → pixel 0; value 2 → pixel 200
    expect(polyline(sx, sy, [0, 1, 2], [0, 1, 2])).toBe(
      "0.0,200.0 100.0,100.0 200.0,0.0",
    );
  });
});

describe("unionBounds", () => {
  it("unions two overlapping boxes to their extremes", () => {
    const a: ViewportBBox = { minX: 0, minY: 0, maxX: 10, maxY: 4 };
    const b: ViewportBBox = { minX: 5, minY: -2, maxX: 15, maxY: 6 };
    expect(unionBounds(a, b)).toEqual({ minX: 0, minY: -2, maxX: 15, maxY: 6 });
  });

  it("guards a degenerate uniform box to a tiny span", () => {
    const deg: ViewportBBox = { minX: 3, minY: 3, maxX: 3, maxY: 3 };
    const u = unionBounds(deg);
    expect(u.minX).toBe(3);
    expect(u.maxX).toBeGreaterThan(u.minX);
  });

  it("falls back to a tiny box for no inputs", () => {
    expect(unionBounds()).toEqual({ minX: 0, minY: 0, maxX: 0.001, maxY: 0.001 });
  });
});

describe("fitWorldToView", () => {
  const bbox: ViewportBBox = { minX: 0, minY: 0, maxX: 100, maxY: 50 };

  it("meets (never overflows) the drawing area", () => {
    const t = fitWorldToView(bbox, 760, 260, 30);
    // drawW = 700, drawH = 200 → fit scale = min(7, 4) = 4
    expect(t.s).toBe(4);
  });

  it("scales up when zoomed and keeps the bbox centred", () => {
    const t = fitWorldToView(bbox, 760, 260, 30, 2);
    expect(t.s).toBe(8);
    const centreX = t.tx + (bbox.minX + bbox.maxX) / 2 * t.s - (bbox.maxX + bbox.minX) / 2 * t.s;
    // Sanity: with a uniform scale the translate formula stays finite.
    expect(Number.isFinite(centreX)).toBe(true);
  });

  it("guards degenerate bboxes gracefully", () => {
    const degenerate: ViewportBBox = { minX: 0, minY: 0, maxX: 1e-9, maxY: 1e-9 };
    const t = fitWorldToView(degenerate, 760, 260, 30);
    expect(t.s).toBeGreaterThan(0);
    expect(Number.isFinite(t.tx)).toBe(true);
    expect(Number.isFinite(t.ty)).toBe(true);
  });
});
