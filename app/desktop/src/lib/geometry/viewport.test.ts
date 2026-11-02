import { describe, expect, it } from "vitest";
import { fitWorldToView, unionBounds, type ViewportBBox } from "./viewport";

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
    const offsetBox: ViewportBBox = { minX: 20, minY: -40, maxX: 120, maxY: 10 };
    const t = fitWorldToView(offsetBox, 760, 260, 30, 2);
    expect(t.s).toBe(8);
    const centreX = (offsetBox.minX + offsetBox.maxX) / 2;
    const centreY = (offsetBox.minY + offsetBox.maxY) / 2;
    expect(t.tx + centreX * t.s).toBe(380);
    expect(t.ty - centreY * t.s).toBe(130);
  });

  it("fits a tiny nonzero bounding box with a finite transform", () => {
    const tiny: ViewportBBox = { minX: 0, minY: 0, maxX: 1e-9, maxY: 1e-9 };
    const t = fitWorldToView(tiny, 760, 260, 30);
    expect(t.s).toBeGreaterThan(0);
    expect(Number.isFinite(t.tx)).toBe(true);
    expect(Number.isFinite(t.ty)).toBe(true);
  });
});
