import { describe, expect, it } from "vitest";
import type { CadGeometry } from "./types";
import { cadMappingProblems } from "./cadMapping";
import { assignTraceRole, reassignTraces } from "./cadSelection";

function mapped(): CadGeometry {
  return {
    motor_mapping_reviewed: true, layer_z_mm: [-1.6, 0], trace_width_mm: 0.2,
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
  it("accepts a reviewed mapping with via landings on both planes", () => {
    expect(cadMappingProblems(mapped(), 1, 0.127)).toEqual([]);
  });
  it("names incomplete review, phase, width and missing via landings", () => {
    const g = mapped();
    g.motor_mapping_reviewed = false;
    g.trace_width_mm = 0.05;
    g.routing.vias[0].to_layer = 3;
    const problems = cadMappingProblems(g, 2, 0.127).join(" ");
    expect(problems).toContain("Review");
    expect(problems).toContain("0.127");
    expect(problems).toContain("phase B");
    expect(problems).toContain("Via 1 on coil 'A' has no trace endpoint on layer 3");
  });
  it("role changes preserve endpoints and require renewed review", () => {
    const g = mapped();
    const edited = assignTraceRole(g, ["segments:0"], false);
    expect(edited.routing.segments.every((s) => !s.is_active)).toBe(true);
    expect(g.routing.segments[0].is_active).toBe(true);
    expect(edited.coil_terminals).toEqual(g.coil_terminals);
    expect(edited.motor_mapping_reviewed).toBe(false);
    expect(reassignTraces(g, ["segments:0"], undefined, 1).motor_mapping_reviewed).toBe(false);
  });
});
