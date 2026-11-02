import { describe, expect, it } from "vitest";
import { layoutTerminalMarkers } from "./terminalMarkerLayout";

describe("terminal callout layout", () => {
  it("separates coincident endpoints across coils and layers", () => {
    const points = Array.from({ length: 6 }, () => ({ x: 300, y: 200 }));
    const result = layoutTerminalMarkers(points, 900, 600);
    for (const [i, a] of result.entries()) {
      expect(a.x).toBe(300);
      expect(a.y).toBe(200);
      for (const b of result.slice(i + 1)) {
        expect(Math.abs(a.labelX - b.labelX) >= 138 || Math.abs(a.labelY - b.labelY) >= 30).toBe(true);
      }
    }
  });
  it("keeps callouts inside the viewport, including at its edges", () => {
    const result = layoutTerminalMarkers([{ x: 1, y: 1 }, { x: 799, y: 399 }, { x: 799, y: 399 }], 800, 400);
    for (const p of result) {
      expect(p.labelX).toBeGreaterThanOrEqual(4);
      expect(p.labelY).toBeGreaterThanOrEqual(4);
      expect(p.labelX + 132).toBeLessThanOrEqual(796);
      expect(p.labelY + 24).toBeLessThanOrEqual(396);
    }
  });
  it("is stable for the same camera and visible markers", () => {
    const points = [{ x: 100, y: 100 }, { x: 100, y: 100 }];
    expect(layoutTerminalMarkers(points, 600, 400)).toEqual(layoutTerminalMarkers(points, 600, 400));
    expect(layoutTerminalMarkers([], 600, 400)).toEqual([]);
  });
});
