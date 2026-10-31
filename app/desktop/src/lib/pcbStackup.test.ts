import { describe, expect, it } from "vitest";
import { initialPcbStackup, pcbStackupHeightsMm, pcbStackupThicknessMm, pcbStackupToSi, validatePcbStackup } from "./pcbStackup";
import { ConfigStore } from "./stores/config.svelte";
import { placedCopperGeometry } from "./copperLayerPlacement";
import type { CadGeometry } from "./types";

const stack = { copper_mm: [.035, .018, .070, .035], dielectric_mm: [.1, .4, .142] };
describe("explicit PCB stackup", () => {
  it("includes copper and dielectric thickness in the total and physical center heights", () => {
    expect(pcbStackupThicknessMm(stack)).toBeCloseTo(.8, 12);
    const z = pcbStackupHeightsMm(stack);
    [-.0175, -.144, -.588, -.7825].forEach((v, i) => expect(z[i]).toBeCloseTo(v, 12));
    expect(pcbStackupToSi(stack).copper_m[1]).toBeCloseTo(18e-6);
    const g = { layer_z_mm: [-4.8, -3.2, -1.6, 0] } as CadGeometry;
    const before = JSON.stringify(g);
    expect(placedCopperGeometry(g, .8, stack).layer_z_mm).toEqual(z);
    expect(JSON.stringify(g)).toBe(before);
  });
  it("rejects mismatched counts, nonpositive and nonfinite thickness and inconsistent totals", () => {
    expect(() => validatePcbStackup(stack, 6)).toThrow(/6 copper/);
    expect(() => validatePcbStackup(stack, 4, 1.6)).toThrow(/sum/);
    for (const bad of [0, -1, NaN, Infinity]) expect(() => validatePcbStackup({ ...stack, copper_mm: [bad, .018, .07, .035] }, 4)).toThrow();
    expect(() => initialPcbStackup(16, .1, 3, 3)).toThrow();
  });
  it("seeds from legacy weights and total without changing legacy defaults or silently resizing stacks", () => {
    const c = new ConfigStore();
    expect(c.toIpc()).not.toHaveProperty("pcb_stackup");
    c.pcb_thickness_mm = .8;
    c.pcb_stackup_mm = initialPcbStackup(4, .8, 2, .5);
    expect(c.pcb_thickness_mm).toBeCloseTo(.8);
    [70e-6,17.5e-6,17.5e-6,70e-6].forEach((t,i) => expect(c.toIpc().pcb_stackup!.copper_m[i]).toBeCloseTo(t,14));
    c.pcb_stackup_mm = structuredClone(stack);
    expect(c.toIpc().pcb_thickness_m).toBeCloseTo(.0008);
    c.num_layers = 6;
    expect(c.pcb_stackup_mm).toEqual(stack);
    expect(() => validatePcbStackup(c.pcb_stackup_mm!, c.num_layers)).toThrow();
  });
});
