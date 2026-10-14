import { describe, expect, it } from "vitest";
import type { CadGeometry } from "./types";
import { coilNames, phaseOf, unmappedCoils, withCoilPhase, geometryKey } from "./cadPhases";

const seg = (net: string) => ({ start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net, is_active: true });
const geometry: CadGeometry = {
  routing: { format_version: 2, segments: [seg("A"), seg("outer"), seg("inner")], curves: [], vias: [] },
  layer_z_mm: [0],
  trace_width_mm: 0.2,
};

describe("cadPhases", () => {
  it("maps phase-named coils implicitly and reports the rest", () => {
    expect(coilNames(geometry)).toEqual(["A", "inner", "outer"]);
    expect(phaseOf(geometry, "A")).toBe("A");
    expect(unmappedCoils(geometry)).toEqual(["inner", "outer"]);
  });

  it("assigns and clears explicit phases without mutating", () => {
    const mapped = withCoilPhase(withCoilPhase(geometry, "inner", "B"), "outer", "B");
    expect(unmappedCoils(mapped)).toEqual([]);
    expect(geometry.coil_phases).toBeUndefined();
    expect(phaseOf(withCoilPhase(mapped, "inner", null), "inner")).toBeNull();
    expect(geometryKey(mapped)).not.toBe(geometryKey(geometry));
    expect(geometryKey(mapped)).toBe(geometryKey(mapped));
  });
});
