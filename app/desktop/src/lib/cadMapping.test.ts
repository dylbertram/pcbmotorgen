import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
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

function innerLayerConnection(): CadGeometry {
  const g = mapped();
  g.layer_z_mm = [-0.8, -0.5, -0.3, 0];
  g.routing.segments[0].layer = 1;
  g.routing.segments[1].layer = 2;
  g.routing.vias[0].to_layer = 3;
  g.coil_terminals!.A.input.layer = 1;
  g.coil_terminals!.A.output.layer = 2;
  return g;
}

describe("imported motor mapping", () => {
  // Optional diagnostic for user attachments, never a dependency of CI.
  it.skipIf(!process.env.PCB_MOTOR_PROJECT_PATH)("accepts imported geometry in a supplied user project", () => {
    const project = JSON.parse(readFileSync(process.env.PCB_MOTOR_PROJECT_PATH!, "utf8"));
    const imported = project.versions.filter((v: { state: { cad_geometry: CadGeometry | null } }) => v.state.cad_geometry);
    expect(imported.length).toBeGreaterThan(0);
    for (const version of imported) {
      const { config, cad_geometry } = version.state;
      expect(cadMappingProblems(cad_geometry, config.phases, config.min_trace_mm)).toEqual([]);
    }
  });
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
    expect(problems).toContain("Via 1 refers to missing layer 3");
  });
  it.each([[0, 3], [3, 0], [1, 3], [0, 2]])("accepts a barrel spanning %i to %i with two inner landings", (from, to) => {
    const g = innerLayerConnection();
    g.routing.vias[0].from_layer = from;
    g.routing.vias[0].to_layer = to;
    expect(cadMappingProblems(g, 1, 0.127)).toEqual([]);
  });
  it("accepts arc and spline endpoints on inner layers", () => {
    const g = innerLayerConnection();
    g.routing.segments = [];
    g.routing.curves = [{ start: { x: 0, y: 0 }, mid: { x: 0.5, y: 0.5 }, end: { x: 1, y: 0 }, net: "A", layer: 1, is_active: true }];
    g.routing.splines = [{ degree: 2, knots: [0, 0, 0, 1, 1, 1], control_points: [{ x: 1, y: 0 }, { x: 1.5, y: 1 }, { x: 2, y: 0 }], weights: [1, 1, 1], net: "A", layer: 2, is_active: true }];
    expect(cadMappingProblems(g, 1, 0.127)).toEqual([]);
  });
  it.each(["one layer", "same-layer duplicates", "wrong coil", "outside span", "floating", "same-layer via"])("rejects a via with %s", (kind) => {
    const g = innerLayerConnection();
    if (kind === "one layer" || kind === "same-layer duplicates") {
      g.routing.segments[1].layer = 1;
      g.coil_terminals!.A.output.layer = 1;
      if (kind === "same-layer duplicates") g.routing.segments.push({ ...g.routing.segments[0] });
    } else if (kind === "wrong coil") g.routing.vias[0].net = "B";
    else if (kind === "outside span") g.routing.vias[0].to_layer = 1;
    else if (kind === "floating") g.routing.vias[0].position.x = 99;
    else g.routing.vias[0].from_layer = g.routing.vias[0].to_layer = 1;
    expect(cadMappingProblems(g, 1, 0.127).join(" ")).toContain("at least two distinct copper layers within its span");
  });
  it("changed coil assignments invalidate affected ends", () => {
    const g = mapped();
    const edited = reassignTraces(g, ["segments:0"], "new coil");
    expect(edited.coil_terminals).toEqual({});
    expect(g.coil_terminals?.A).toBeDefined();
  });
});
