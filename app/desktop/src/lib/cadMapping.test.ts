import { describe, expect, it } from "vitest";
import type { CadGeometry } from "./types";
import { cadMappingProblems } from "./cadMapping";
import { reassignTraces } from "./cadSelection";

function mapped(): CadGeometry {
  return {
    layer_z_mm: [-1.6, 0], trace_width_mm: 0.2,
    coil_terminals: { A: {
      input: { position: { x: 0, y: 0 }, layer: 0 },
      output: { position: { x: 2, y: 0 }, layer: 1 },
    } },
    routing: { format_version: 2, curves: [], vias: [{ position: { x: 1, y: 0 }, net: "A", from_layer: 0, to_layer: 1 }],
      segments: [
        { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, net: "A", layer: 0, is_active: true },
        { start: { x: 1, y: 0 }, end: { x: 2, y: 0 }, net: "A", layer: 1, is_active: false },
      ],
    },
  };
}

describe("imported motor mapping", () => {
  it("accepts a complete mapping without a review checkbox", () => {
    expect(cadMappingProblems(mapped(), 1, 0.127)).toEqual([]);
  });
  it("names incomplete phase, width and missing via landings", () => {
    const g = mapped();
    g.trace_width_mm = 0.05;
    g.routing.vias[0].to_layer = 3;
    const problems = cadMappingProblems(g, 2, 0.127).join(" ");
    expect(problems).toContain("0.127");
    expect(problems).toContain("phase B");
    expect(problems).toContain("Via 1 on coil 'A' has no trace endpoint on layer 3");
  });
  it("changed coil assignments invalidate affected ends", () => {
    const g = mapped();
    const edited = reassignTraces(g, ["segments:0"], "new coil");
    expect(edited.coil_terminals).toEqual({});
    expect(g.coil_terminals?.A).toBeDefined();
  });
});
