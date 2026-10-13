import { describe, expect, it } from "vitest";
import { assignCadTerminals, cadTerminalCandidates } from "./cadTerminals";
import { cadGeometryToPreview } from "./cadPreview";
import { simplifyCadLines } from "./cadSimplify";
import type { CadGeometry, CadTerminal } from "./types";

const terminalFixture = (): CadGeometry => ({
  layer_z_mm: [-1.6, 0], trace_width_mm: 0.4,
  routing: { format_version: 2, curves: [],
    segments: [
      { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net: "A", is_active: true },
      { start: { x: 1, y: 0 }, end: { x: 2, y: 0 }, layer: 0, net: "A", is_active: true },
      { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 1, net: "A", is_active: true },
      { start: { x: 0, y: 2 }, end: { x: 1, y: 2 }, layer: 0, net: "B", is_active: true },
    ],
    vias: [{ position: { x: 0, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }],
  },
});
const terminal = (x: number, layer = 0, y = 0): CadTerminal => ({ position: { x, y }, layer });

describe("CAD terminals", () => {
  it("deduplicates shared endpoints without combining copper layers or coils", () => {
    const candidates = cadTerminalCandidates(terminalFixture(), "A");
    expect(candidates).toHaveLength(5);
    expect(candidates.filter((p) => p.position.x === 0)).toHaveLength(2);
    expect(candidates.every((p) => p.position.y === 0)).toBe(true);
    expect(cadTerminalCandidates(terminalFixture(), "unknown")).toHaveLength(0);
  });
  it("uses arc ends and evaluated spline ends rather than midpoints or control points", () => {
    const geometry = terminalFixture();
    geometry.routing.curves.push({ start: { x: 2, y: 0 }, mid: { x: 3, y: 1 }, end: { x: 4, y: 0 }, net: "A", layer: 0, is_active: true });
    geometry.routing.splines = [{ degree: 2, knots: [0, 0, 0, 1, 1, 1], control_points: [{ x: 4, y: 0 }, { x: 5, y: 2 }, { x: 6, y: 0 }], weights: [1, 0.5, 1], net: "A", layer: 0, is_active: true }];
    const candidates = cadTerminalCandidates(geometry, "A");
    expect(candidates).toContainEqual(terminal(6));
    expect(candidates).not.toContainEqual(terminal(3, 0, 1));
    expect(candidates).not.toContainEqual(terminal(5, 0, 2));
  });
  it("rejects wrong coils, arbitrary points and identical IN/OUT selections", () => {
    const geometry = terminalFixture();
    expect(() => assignCadTerminals(geometry, "A", { input: terminal(0), output: terminal(0) })).toThrow("different");
    expect(() => assignCadTerminals(geometry, "A", { input: terminal(0), output: terminal(9) })).toThrow("belonging");
    expect(() => assignCadTerminals(geometry, "B", { input: terminal(0), output: terminal(2) })).toThrow("belonging");
    expect(() => assignCadTerminals(geometry, "A", { input: terminal(0), output: terminal(2, 9) })).toThrow("belonging");
  });
  it("preserves explicit coil direction across layers, serialization and simplification", () => {
    const original = terminalFixture();
    const geometry = assignCadTerminals(original, "A", { input: terminal(2), output: terminal(0, 1) });
    expect(original.coil_terminals).toBeUndefined();
    const restored = JSON.parse(JSON.stringify(geometry));
    expect(restored.coil_terminals.A).toEqual(geometry.coil_terminals!.A);
    const preview = cadGeometryToPreview(restored);
    for (const coil of preview.phases.filter((p) => p.phase_name === "A")) {
      expect(coil.terminal_start).toEqual([0.002, 0]);
      expect(coil.terminal_end).toEqual([0, 0]);
    }
    expect(simplifyCadLines(geometry).coil_terminals).toEqual(geometry.coil_terminals);
    // A selected junction stays an endpoint, rather than disappearing into a merged line.
    const junction = assignCadTerminals(original, "A", { input: terminal(1), output: terminal(2) });
    expect(simplifyCadLines(junction).routing.segments).toHaveLength(4);
  });
});
