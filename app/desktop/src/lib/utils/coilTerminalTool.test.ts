import { describe, expect, it, vi } from "vitest";
import { CoilTerminalTool } from "./coilTerminalTool.svelte";
import type { CadGeometry, CadTerminal } from "../types";

const point = (x: number, layer = 0): CadTerminal => ({ position: { x, y: 0 }, layer });
function fixture() {
  let geometry: CadGeometry = { layer_z_mm: [-1.6, 0], trace_width_mm: 0.4, routing: { format_version: 2, curves: [], vias: [],
    segments: [0, 1].map((layer) => ({ start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer, net: "A", is_active: true })),
  } };
  const onChange = vi.fn((next: CadGeometry) => { geometry = next; });
  const onReveal = vi.fn();
  const tool = new CoilTerminalTool({ getGeometry: () => geometry, onChange, onReveal });
  return { tool, onChange, onReveal, getGeometry: () => geometry, replace: () => { geometry = { ...geometry }; } };
}

describe("CoilTerminalTool", () => {
  it("moves through coil, IN, OUT, review and Done, saving only once confirmed", () => {
    const { tool, onChange, getGeometry } = fixture();
    tool.begin(); tool.chooseCoil("A"); tool.next();
    expect(tool.step).toBe("input");
    tool.pick(point(0));
    expect(tool.step).toBe("output");
    tool.chooseLayer(1); tool.pick(point(1, 1));
    expect(tool.step).toBe("review");
    expect(onChange).not.toHaveBeenCalled();
    tool.done();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(getGeometry().coil_terminals!.A).toEqual({ input: point(0), output: point(1, 1) });
    expect(tool.active).toBe(false);
  });
  it("cancels or goes back without committing any partial selection", () => {
    const { tool, onChange } = fixture();
    tool.begin(); tool.chooseCoil("A"); tool.next(); tool.pick(point(0)); tool.pick(point(1));
    tool.back(); expect(tool.step).toBe("output"); expect(tool.output).toBeNull();
    tool.back(); expect(tool.step).toBe("input"); expect(tool.input).toBeNull();
    tool.pick(point(1)); tool.cancel(); tool.done();
    expect(onChange).not.toHaveBeenCalled();
  });
  it("rejects the same endpoint and ignores wrong points or the wrong layer", () => {
    const { tool, onChange } = fixture();
    tool.begin(); tool.chooseCoil("A"); tool.next();
    tool.pick(point(4)); tool.pick(point(0, 1)); expect(tool.step).toBe("input");
    tool.pick(point(0)); tool.pick(point(0));
    expect(tool.error).toContain("different"); expect(tool.step).toBe("output");
    tool.done(); expect(onChange).not.toHaveBeenCalled();
    tool.pick(point(1)); expect(tool.error).toBe("");
  });
  it("will not commit a draft after the project geometry has been replaced", () => {
    const { tool, onChange, replace } = fixture();
    tool.begin(); tool.chooseCoil("A"); tool.next(); tool.pick(point(0)); tool.pick(point(1));
    replace(); expect(tool.active).toBe(false); tool.done();
    expect(onChange).not.toHaveBeenCalled();
    tool.begin(); expect(tool.active).toBe(true); expect(tool.input).toBeNull();
  });
});
