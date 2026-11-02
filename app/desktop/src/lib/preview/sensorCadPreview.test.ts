import { describe, expect, it } from "vitest";
import type { CadGeometry } from "../types";
import { cadGeometryToSensorPreview } from "./sensorCadPreview";

describe("cadGeometryToSensorPreview", () => {
  it("groups imported geometry by net and includes every geometry type in the bounds", () => {
    const segment = { net: "A", start: { x: 0, y: 0 }, end: { x: 2, y: 1 } };
    const curve = { net: "B", start: { x: 2, y: 1 }, mid: { x: 3, y: 5 }, end: { x: 4, y: 1 } };
    const spline = { net: "A", control_points: [{ x: -2, y: 0 }, { x: 1, y: 2 }] };
    const via = { net: "B", position: { x: 6, y: -3 } };
    const cad = {
      trace_width_mm: 0.2,
      routing: { segments: [segment], curves: [curve], splines: [spline], vias: [via] },
    } as unknown as CadGeometry;
    const original = structuredClone(cad);

    const preview = cadGeometryToSensorPreview(cad, 0.7);
    expect(preview.board_bounds_mm).toEqual([-2, -3, 6, 5]);
    expect(preview.terminal_markers).toEqual([]);
    expect(preview.nets).toEqual([
      { name: "A", segments: [segment], curves: [], splines: [spline], vias: [], trace_width_mm: 0.2, via_size_mm: 0.7 },
      { name: "B", segments: [], curves: [curve], splines: [], vias: [via], trace_width_mm: 0.2, via_size_mm: 0.7 },
    ]);
    expect(cad).toEqual(original);
  });

  it("uses default bounds for an empty import without optional splines", () => {
    const cad = { trace_width_mm: 0.1, routing: { segments: [], curves: [], vias: [] } } as unknown as CadGeometry;
    expect(cadGeometryToSensorPreview(cad, 0.6)).toEqual({
      nets: [], terminal_markers: [], board_bounds_mm: [0, 0, 1, 1],
    });
  });
});
