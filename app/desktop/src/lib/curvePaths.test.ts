import { describe, expect, it } from "vitest";
import { arcSvgPath, sampleSpline, splinePointAt, splineSvgPath } from "./curvePaths";
import { cadGeometryToPreview } from "./cadPreview";
import { computeFootprintBox } from "./previewGeometry";
import type { CadRouteSpline } from "./types/dxf";

const spline: CadRouteSpline = {
  degree: 3, knots: [0, 0, 0, 0, 0.5, 0.5, 0.5, 1, 1, 1, 1],
  control_points: [
    { x: 0, y: 0 }, { x: 1, y: 2 }, { x: 2, y: 2 }, { x: 3, y: 0 },
    { x: 4, y: -2 }, { x: 5, y: -2 }, { x: 6, y: 0 },
  ],
  layer: 1, net: "CL1", is_active: true,
};

describe("curve previews", () => {
  it("renders generated B-splines as cubic paths rather than short lines", () => {
    const path = splineSvgPath(spline);
    expect(path).toBe("M 0 0 C 1 2 2 2 3 0 C 4 -2 5 -2 6 0");
    expect(splinePointAt(spline, 0.5)).toEqual({ x: 3, y: 0 });
    expect(splinePointAt(spline, 0.25)).toEqual({ x: 1.5, y: 1.5 });
    expect(sampleSpline(spline).at(-1)).toEqual({ x: 6, y: 0 });
  });

  it("evaluates rational splines without changing the model", () => {
    const rational: CadRouteSpline = {
      ...spline, degree: 2, knots: [0, 0, 0, 1, 1, 1],
      control_points: [{ x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }],
      weights: [1, Math.SQRT1_2, 1],
    };
    const mid = splinePointAt(rational, 0.5);
    expect(mid.x).toBeCloseTo(Math.SQRT1_2, 12);
    expect(mid.y).toBeCloseTo(Math.SQRT1_2, 12);
    expect(rational.control_points).toHaveLength(3);
  });

  it("keeps imported splines in metre-based motor previews and their fit bounds", () => {
    const preview = cadGeometryToPreview({
      routing: { format_version: 2, segments: [], curves: [], vias: [], splines: [spline] },
      layer_z_mm: [-1.6, 0], trace_width_mm: 0.15,
    });
    expect(preview.phases).toHaveLength(1);
    expect(preview.phases[0].segments).toHaveLength(0);
    expect(preview.phases[0].splines?.[0].control_points[6]).toEqual({ x: 0.006, y: 0 });
    expect(preview.phases[0].total_length_m).toBeGreaterThan(0.006);
    expect(computeFootprintBox(preview)).toEqual({ minX: 0, maxX: 0.006, minY: -0.002, maxY: 0.002 });
    expect(spline.control_points[6]).toEqual({ x: 6, y: 0 });
  });

  it("renders circular bends through their midpoint as arcs, in either direction", () => {
    const arc = { start: { x: 1, y: 0 }, mid: { x: 0, y: 1 }, end: { x: -1, y: 0 },
      layer: 0, net: "CL1", is_active: true };
    expect(arcSvgPath(arc)).toBe("M 1 0 A 1 1 0 0 1 -1 0");
    expect(arcSvgPath({ ...arc, start: arc.end, end: arc.start })).toBe("M -1 0 A 1 1 0 0 0 1 0");
  });
});
