import { describe, expect, it } from "vitest";
import {
  cadGeometryToPreview,
  groupCadImportWarnings,
  joinCadPreviewEndpoints,
} from "./cadPreview";
import type { CadGeometry } from "./types";

describe("cadGeometryToPreview", () => {
  it("groups centerlines and preserves layer/net/via positions", () => {
    const geometry: CadGeometry = {
      layer_z_mm: [-0.8, 0.8],
      trace_width_mm: 0.2,
      routing: {
        format_version: 2,
        segments: [{ start: { x: 1, y: 2 }, end: { x: 4, y: 2 }, layer: 0, net: "A", is_active: true }],
        curves: [],
        vias: [{ position: { x: 4, y: 2 }, from_layer: 0, to_layer: 1, net: "A" }],
      },
    };
    const preview = cadGeometryToPreview(geometry);
    expect(preview.layer_count).toBe(2);
    expect(preview.phases).toHaveLength(2);
    expect(preview.phases[0].phase_name).toBe("A");
    expect(preview.phases[0].segments[0].start).toEqual([0.001, 0.002]);
    expect(preview.phases[0].via_positions).toEqual([[0.004, 0.002]]);
    expect(preview.phases[1].via_positions).toEqual([[0.004, 0.002]]);
  });
});

describe("joinCadPreviewEndpoints", () => {
  it("visually joins nearby endpoints only on the same net and layer", () => {
    const geometry: CadGeometry = {
      layer_z_mm: [0, 1],
      trace_width_mm: 0.2,
      routing: {
        format_version: 2,
        segments: [
          { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net: "A", is_active: true },
          { start: { x: 1.02, y: 0 }, end: { x: 2, y: 0 }, layer: 0, net: "A", is_active: true },
          { start: { x: 1.03, y: 0 }, end: { x: 3, y: 0 }, layer: 1, net: "A", is_active: true },
          { start: { x: 1.04, y: 0 }, end: { x: 4, y: 0 }, layer: 0, net: "B", is_active: true },
          { start: { x: 1.08, y: 0 }, end: { x: 5, y: 0 }, layer: 0, net: "A", is_active: true },
        ],
        curves: [
          { start: { x: 2.02, y: 0 }, mid: { x: 2.5, y: 0.5 }, end: { x: 3, y: 1 }, layer: 0, net: "A", is_active: true },
        ],
        vias: [],
      },
    };

    const preview = joinCadPreviewEndpoints(geometry, 0.05);
    expect(preview.segments[0].end).toEqual(preview.segments[1].start);
    expect(preview.segments[1].end).toEqual(preview.curves[0].start);
    expect(preview.segments[2].start).toEqual({ x: 1.03, y: 0 });
    expect(preview.segments[3].start).toEqual({ x: 1.04, y: 0 });
    expect(preview.segments[4].start).toEqual({ x: 1.08, y: 0 });
    // Preview cleanup never mutates the imported/saved geometry.
    expect(geometry.routing.segments[0].end).toEqual({ x: 1, y: 0 });
    expect(geometry.routing.segments[1].start).toEqual({ x: 1.02, y: 0 });
  });

  it("aligns trace endpoints with nearby via centers on connected layers", () => {
    const geometry: CadGeometry = {
      layer_z_mm: [0, 1],
      trace_width_mm: 0.2,
      routing: {
        format_version: 2,
        segments: [
          { start: { x: 0, y: 0 }, end: { x: 2.03, y: 0 }, layer: 0, net: "A", is_active: true },
        ],
        curves: [],
        vias: [{ position: { x: 2, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }],
      },
    };

    const preview = joinCadPreviewEndpoints(geometry, 0.05);
    expect(preview.segments[0].end).toEqual(geometry.routing.vias[0].position);
  });
});

describe("groupCadImportWarnings", () => {
  it("collapses repeated disconnected-via diagnostics by layer and caps examples", () => {
    const warnings = Array.from({ length: 30 }, (_, i) =>
      `Via at (${i}.000, 1.000) mm has no matching trace endpoint on layer 2.`,
    );
    const [group] = groupCadImportWarnings(warnings);
    expect(group.title).toContain("layer 2");
    expect(group.count).toBe(30);
    expect(group.examples).toHaveLength(5);
  });
});
