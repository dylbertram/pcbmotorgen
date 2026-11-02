import { describe, expect, it } from "vitest";
import { clientToVirtual, virtualToWorld, computeMeasureRuler } from "./measureRuler";

describe("measure ruler helpers", () => {
  it("converts client px into virtual px over a canvas frame", () => {
    const rect = { left: 100, top: 50, width: 760, height: 260 };
    expect(clientToVirtual(100, 50, rect, 760, 260)).toEqual({ x: 0, y: 0 });
    expect(clientToVirtual(860, 310, rect, 760, 260)).toEqual({ x: 760, y: 260 });
    const wide = { left: 10, top: 10, width: 1520, height: 520 };
    expect(clientToVirtual(10 + 760, 10 + 260, wide, 760, 260)).toEqual({ x: 380, y: 130 });
  });

  it("converts virtual px back into world metres, honouring pan", () => {
    const t = { s: 100, tx: 30, ty: 80 };
    const w = virtualToWorld(30 + 100 * 0.012, 80 - 100 * 0.004, t, 0, 0);
    expect(w.x).toBeCloseTo(0.012, 9);
    expect(w.y).toBeCloseTo(0.004, 9);
    const pan = virtualToWorld(30 + 10 + 100 * 0.006, 80 - 20 - 100 * 0.002, t, 10, -20);
    expect(pan.x).toBeCloseTo(0.006, 9);
    expect(pan.y).toBeCloseTo(0.002, 9);
  });

  it("guards against a degenerate transform", () => {
    expect(virtualToWorld(50, 50, { s: 0, tx: 0, ty: 0 }, 0, 0)).toEqual({ x: 0, y: 0 });
  });

  it("computes the mm distance between world points", () => {
    expect(computeMeasureRuler({ x: 0, y: 0 }, { x: 0.03, y: 0.04 }).mm).toBeCloseTo(50);
    expect(computeMeasureRuler({ x: 0.012, y: 0 }, { x: 0, y: 0 }).mm).toBeCloseTo(12);
    expect(computeMeasureRuler({ x: 1, y: 2 }, { x: 1, y: 2 }).mm).toBe(0);
  });

  it("builds a horizontal ruler with the caption nudged perpendicular", () => {
    const r = computeMeasureRuler({ x: 0, y: 0 }, { x: 0.012, y: 0 });
    expect(r.mm).toBeCloseTo(12);
    expect(r.label.x).toBeCloseTo(0.006, 9);
    expect(r.label.y).toBeCloseTo(0.0012, 9);
    expect(r.bounds.minX).toBeLessThan(0);
    expect(r.bounds.maxX).toBeGreaterThan(0.012);
    expect(r.bounds.maxY).toBeGreaterThan(0);
  });

  it("keeps a vertical ruler readable by offsetting the label sideways", () => {
    const r = computeMeasureRuler({ x: 0.01, y: 0 }, { x: 0.01, y: 0.02 });
    expect(r.mm).toBeCloseTo(20);
    expect(r.label.x).toBeCloseTo(0.01 - 0.0012, 9);
    expect(r.label.y).toBeCloseTo(0.01, 9);
  });
});
