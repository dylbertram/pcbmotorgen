import { describe, expect, it } from "vitest";
import type { CadGeometry } from "../types";
import { coilNamesWithPaths, phaseOf, withCoilPhase, geometryKey } from "./cadPhases";
import { cadCoilNames } from "./cadPreview";

const seg = (net: string) => ({ start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net, is_active: true });
const geometry: CadGeometry = {
  routing: { format_version: 2, segments: [seg("A"), seg("outer"), seg("inner")], curves: [], vias: [] },
  layer_z_mm: [0],
  trace_width_mm: 0.2,
};

describe("cadPhases", () => {
  it("maps phase-named coils implicitly and reports the rest", () => {
    expect(coilNamesWithPaths(geometry)).toEqual(["A", "inner", "outer"]);
    expect(phaseOf(geometry, "A")).toBe("A");
    expect(phaseOf(geometry, "inner")).toBeNull();
    expect(phaseOf(geometry, "outer")).toBeNull();
  });

  it("excludes via-only nets from phase mapping while retaining them in the preview list", () => {
    const viaOnly: CadGeometry = {
      ...geometry,
      routing: { ...geometry.routing, vias: [{ position: { x: 0, y: 0 }, from_layer: 0, to_layer: 1, net: "via-only" }] },
    };
    expect(coilNamesWithPaths(viaOnly)).toEqual(["A", "inner", "outer"]);
    expect(cadCoilNames(viaOnly)).toEqual(["A", "inner", "outer", "via-only"]);
  });

  it("assigns and clears explicit phases without mutating", () => {
    const mapped = withCoilPhase(withCoilPhase(geometry, "inner", "B"), "outer", "B");
    expect(phaseOf(mapped, "inner")).toBe("B");
    expect(phaseOf(mapped, "outer")).toBe("B");
    expect(geometry.coil_phases).toBeUndefined();
    expect(phaseOf(withCoilPhase(mapped, "inner", null), "inner")).toBeNull();
    expect(geometryKey(mapped)).not.toBe(geometryKey(geometry));
    expect(geometryKey(mapped)).toBe(geometryKey(mapped));
  });
});
