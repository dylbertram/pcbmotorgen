import { describe, expect, it } from "vitest";
import { cadGeometryToPreview, groupCadImportWarnings } from "./cadPreview";
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
