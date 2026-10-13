import { describe, expect, it } from "vitest";
import { simplifyCadLines } from "./cadSimplify";
import type { CadGeometry, CadRouteSegment } from "./types";

const line = (x0: number, x1: number, extra: Partial<CadRouteSegment> = {}): CadRouteSegment => ({
  start: { x: x0, y: 0 }, end: { x: x1, y: 0 }, layer: 0, net: "A", is_active: true, ...extra,
});
const geometry = (segments: CadRouteSegment[]): CadGeometry => ({
  layer_z_mm: [-1.6, 0], trace_width_mm: 0.4, source_layer_coils: { L0_A: "A" },
  routing: { format_version: 2, segments, curves: [], vias: [] },
});

describe("simplifyCadLines", () => {
  it("merges connected, overlapping, reversed and duplicate intervals", () => {
    const source = geometry([line(0, 1), line(3, 2), line(1, 2), line(0.5, 2.5), line(0, 3)]);
    const result = simplifyCadLines(source);
    expect(result.routing.segments).toEqual([line(0, 3)]);
    expect(source.routing.segments).toHaveLength(5);
    expect(simplifyCadLines(result)).toEqual(result);
    expect(result.source_layer_coils).toEqual(source.source_layer_coils);
  });

  it("never merges different coils, planes, active roles, gaps or parallel offsets", () => {
    const source = geometry([
      line(0, 1), line(1, 2, { net: "B" }), line(1, 2, { layer: 1 }),
      line(1, 2, { is_active: false }), line(1.000001, 2),
      line(0, 1, { start: { x: 0, y: 0.000001 }, end: { x: 1, y: 0.000001 } }),
      line(1, 2, { end: { x: 2, y: 0.01 } }),
    ]);
    expect(simplifyCadLines(source)).toEqual(source);
  });

  it("merges vertical and diagonal lines and preserves curves and vias", () => {
    const source = geometry([
      line(0, 0, { end: { x: 0, y: 1 } }),
      line(0, 0, { start: { x: 0, y: 2 }, end: { x: 0, y: 1 } }),
      line(2, 3, { start: { x: 2, y: 2 }, end: { x: 3, y: 3 } }),
      line(3, 4, { start: { x: 3, y: 3 }, end: { x: 4, y: 4 } }),
    ]);
    source.routing.vias.push({ position: { x: 0, y: 1 }, from_layer: 0, to_layer: 1, net: "A" });
    source.routing.curves.push({ start: { x: 0, y: 2 }, mid: { x: 1, y: 3 }, end: { x: 2, y: 2 }, layer: 0, net: "A", is_active: true });
    const result = simplifyCadLines(source);
    expect(result.routing.segments).toHaveLength(2);
    expect(result.routing.segments[0].end).toEqual({ x: 0, y: 2 });
    expect(result.routing.segments[1].end).toEqual({ x: 4, y: 4 });
    expect(result.routing.vias).toEqual(source.routing.vias);
    expect(result.routing.curves).toEqual(source.routing.curves);
  });
});
