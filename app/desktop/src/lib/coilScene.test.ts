import { describe, expect, it } from "vitest";
import { buildCoilScene, isViaVisible, sampleCopperArc } from "./coilScene";
import type { CadGeometry } from "./types";

function fixture(): CadGeometry {
  return {
    layer_z_mm: [-0.8, 0.8], trace_width_mm: 0.2,
    routing: { format_version: 1, segments: [
      { start: { x: 0, y: 0 }, end: { x: 10, y: 0 }, layer: 0, net: "A", is_active: true },
      { start: { x: 0, y: 0 }, end: { x: 10, y: 0 }, layer: 1, net: "A", is_active: true },
    ], curves: [], vias: [{ position: { x: 10, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }] },
  };
}

describe("Threlte coil geometry", () => {
  it("keeps a through-via visible through inner layers without revealing hidden coils", () => {
    const via = { net: "A", from_layer: 0, to_layer: 7 };
    const innerOnly = (layer: number) => layer === 3;
    expect(isViaVisible(via, innerOnly, () => true)).toBe(true);
    expect(isViaVisible({ ...via, from_layer: 7, to_layer: 0 }, innerOnly, () => true)).toBe(true);
    expect(isViaVisible(via, innerOnly, net => net !== "A")).toBe(false);
    expect(isViaVisible(via, innerOnly, (_net, layer) => layer !== 3)).toBe(false);
    expect(isViaVisible(via, () => false, () => true)).toBe(false);
    expect(isViaVisible({ ...via, to_layer: 1 }, innerOnly, () => true)).toBe(false);
  });

  for (const layers of [4, 6, 8]) {
    it(`places a ${layers}-layer through-via across the entire board, not the first pair`, () => {
      const g = fixture();
      g.layer_z_mm = Array.from({ length: layers }, (_, i) => -1.6 * i / (layers - 1));
      g.routing.vias[0].to_layer = layers - 1;
      g.routing.segments[1].layer = layers - 1;
      const before = JSON.stringify(g);
      const scene = buildCoilScene(g)!;
      const [top, bottom] = scene.vias[0].points;
      expect(top).toEqual(scene.paths[0].points[1]);
      expect(bottom).toEqual(scene.paths[1].points[1]);
      expect(Math.abs(top.y - bottom.y) / scene.scale).toBeCloseTo(1.6, 12);
      expect(JSON.stringify(g)).toBe(before);
    });
  }
  it("centers copper and places via endpoints on the matching layers without changing CAD data", () => {
    const g = fixture();
    const original = JSON.stringify(g);
    const scene = buildCoilScene(g)!;
    expect(scene.paths[0].points[0].y).toBe(-0.8);
    expect(scene.paths[1].points[0].y).toBe(0.8);
    // Default Z-to-XY proportions match the original millimetre geometry.
    const zSpan = scene.paths[1].points[0].y - scene.paths[0].points[0].y;
    const xSpan = scene.paths[0].points[1].x - scene.paths[0].points[0].x;
    expect(zSpan / xSpan).toBeCloseTo(1.6 / 10);
    expect(scene.vias[0].points[0]).toEqual(scene.paths[0].points[1]);
    expect(scene.vias[0].points[1]).toEqual(scene.paths[1].points[1]);
    expect(JSON.stringify(g)).toBe(original);
  });

  it("renders via-only geometry and includes its extent in camera framing", () => {
    const g = fixture();
    g.routing.segments = [];
    const scene = buildCoilScene(g)!;
    expect(scene.paths).toEqual([]);
    expect(scene.vias[0].points.map(p => p.y)).toEqual([-5, 5]);
    expect(scene.nets).toEqual(["A"]);
  });

  it("samples major circular arcs through the specified midpoint", () => {
    const points = sampleCopperArc({ start: { x: 1, y: 0 }, mid: { x: -1, y: 0 }, end: { x: 0, y: 1 }, layer: 0, net: "A", is_active: true });
    expect(points[0].x).toBeCloseTo(1);
    expect(points.at(-1)!.y).toBeCloseTo(1);
    expect(Math.min(...points.map(p => p.y))).toBeCloseTo(-1);
    expect(Math.min(...points.map(p => p.x))).toBeCloseTo(-1);
    for (const p of points) expect(Math.hypot(p.x, p.y)).toBeCloseTo(1);
  });

  it("samples splines and preserves terminal layers", () => {
    const g = fixture();
    g.routing.splines = [{ degree: 1, knots: [0, 0, 1, 1], control_points: [{ x: 0, y: 0 }, { x: 10, y: 0 }], layer: 1, net: "B", is_active: true }];
    g.coil_terminals = { A: { input: { position: { x: 0, y: 0 }, layer: 0 }, output: { position: { x: 10, y: 0 }, layer: 1 } } };
    const scene = buildCoilScene(g)!;
    expect(scene.paths[2].points[0]).toEqual(scene.paths[1].points[0]);
    expect(scene.terminals.map(t => t.point.y)).toEqual([-0.8, 0.8]);
    expect(scene.nets).toEqual(["A", "B"]);
  });

  it("handles empty geometry and degenerate arcs", () => {
    expect(buildCoilScene(null)).toBeNull();
    const g = fixture();
    g.routing = { format_version: 1, segments: [], curves: [], vias: [] };
    expect(buildCoilScene(g)).toBeNull();
    expect(sampleCopperArc({ start: { x: 0, y: 0 }, mid: { x: 1, y: 0 }, end: { x: 2, y: 0 }, layer: 0, net: "A", is_active: true })).toEqual([{ x: 0, y: 0 }, { x: 2, y: 0 }]);
  });
});
