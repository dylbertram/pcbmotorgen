import { describe, expect, it } from "vitest";
import { defaultCadTerminals, withAutomaticCadTerminals } from "./cadTerminals";
import type { CadGeometry } from "./types";
import type { CoilPathDto } from "./types";
import { generatedTerminalGeometry } from "./generatedTerminalGeometry";

const end = (x: number, y: number, layer = 0) => ({ position: { x, y }, layer });
const line = (net: string, ax: number, ay: number, bx: number, by: number, layer = 0) => ({ net, start: { x: ax, y: ay }, end: { x: bx, y: by }, layer, is_active: false });
describe("connected winding terminals", () => {
  it("automatically selects live generated star leads without creating editable geometry", () => {
    const coils = { phases: ["A", "B", "C"].map((phase_name, i) => ({ phase_name, phase_idx: i, layer_idx: 1, segments: [{ start: [0, (i + 1) * .001], end: [.004, .004], is_active: false }], via_positions: [], corner_arcs: [] })) } as unknown as CoilPathDto;
    const geometry = generatedTerminalGeometry(coils, 2, 1.6, .127, 2);
    expect(geometry.terminal_connection).toBe("star");
    for (const [i, coil] of ["A", "B", "C"].entries()) expect(geometry.coil_terminals![coil]).toEqual({ input: end(0, i + 1, 1), output: end(4, 4, 1) });
  });
  it("identifies separate driver leads and a shared star junction", () => {
    const geometry: CadGeometry = { layer_z_mm: [0], trace_width_mm: .127, routing: { format_version: 2, curves: [], vias: [], segments: [line("A", 0, 1, 4, 4), line("B", 0, 2, 4, 4), line("C", 0, 3, 4, 4)] } };
    for (const [i, coil] of ["A", "B", "C"].entries()) expect(defaultCadTerminals(geometry, coil)).toEqual({ input: end(0, i + 1), output: end(4, 4) });
    expect(Object.keys(withAutomaticCadTerminals(geometry).coil_terminals!)).toHaveLength(3);
    expect(geometry.coil_terminals).toBeUndefined();
  });
  it("recognizes a delta end joining the middle of another layer's lead through a via", () => {
    const geometry: CadGeometry = { layer_z_mm: [-1.6, 0], trace_width_mm: .127, routing: { format_version: 2, curves: [], vias: [{ position: { x: 4, y: 2 }, from_layer: 0, to_layer: 1, net: "A" }], segments: [line("A", 0, 1, 4, 2), line("B", 0, 2, 8, 2, 1)] } };
    expect(defaultCadTerminals(geometry, "A")).toEqual({ input: end(0, 1), output: end(4, 2) });
  });
  it("keeps manual choices and refuses disconnected or multiply terminated windings", () => {
    const geometry: CadGeometry = { layer_z_mm: [0], trace_width_mm: .127, coil_terminals: { A: { input: end(4, 4), output: end(0, 1) } }, routing: { format_version: 2, curves: [], vias: [], segments: [line("A", 0, 1, 4, 4), line("B", 0, 2, 4, 4)] } };
    expect(withAutomaticCadTerminals(geometry).coil_terminals!.A).toEqual(geometry.coil_terminals!.A);
    geometry.routing.segments.push(line("A", 10, 10, 11, 11));
    expect(defaultCadTerminals(geometry, "A")).toBeNull();
  });
});
