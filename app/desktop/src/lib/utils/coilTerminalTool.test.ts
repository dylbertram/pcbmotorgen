import { describe, expect, it, vi } from "vitest";
import { CoilTerminalTool } from "./coilTerminalTool.svelte";
import type { CadGeometry, CadTerminal } from "../types";

const point = (x: number, layer = 0, y = 0): CadTerminal => ({ position: { x, y }, layer });
function fixture(ambiguous = false) {
  let geometry: CadGeometry = { layer_z_mm: [-1.6, 0], trace_width_mm: .4, routing: { format_version: 2, curves: [], vias: [],
    segments: [0, 1].map((x) => ({ start: { x: x === 1 && ambiguous ? 1.5 : x, y: 0 }, end: { x: x + 1, y: 0 }, layer: 0, net: "A", is_active: true })).concat([
      { start: { x: 0, y: 2 }, end: { x: 1, y: 2 }, layer: 0, net: "B", is_active: true },
    ]),
  } };
  const onChange = vi.fn((next: CadGeometry) => { geometry = next; });
  const onReveal = vi.fn();
  const tool = new CoilTerminalTool({ getGeometry: () => geometry, onChange, onReveal });
  return { tool, onChange, onReveal, getGeometry: () => geometry, replace: () => { geometry = { ...geometry }; } };
}

describe("CoilTerminalTool", () => {
  it("persists the connection convention without losing draft endpoints", () => {
    const { tool, getGeometry } = fixture();
    expect(tool.connection).toBe("star");
    tool.begin(); tool.change("input"); tool.pick(point(1));
    tool.setConnection("delta");
    expect(tool.connection).toBe("delta");
    expect(tool.active).toBe(true);
    expect(tool.input).toEqual(point(1));
    tool.done();
    expect(getGeometry().terminal_connection).toBe("delta");
    expect(getGeometry().coil_terminals!.A.input).toEqual(point(1));
  });
  it("opens the first coil with inferred endpoints ready to apply, without changing the project", () => {
    const { tool, onChange, getGeometry } = fixture();
    tool.begin();
    expect(tool.coil).toBe("A"); expect(tool.step).toBe("review"); expect(tool.defaultKind).toBe("open");
    expect(tool.input).toEqual(point(0)); expect(tool.output).toEqual(point(2));
    expect(onChange).not.toHaveBeenCalled();
    tool.done();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(getGeometry().coil_terminals!.A).toEqual({ input: point(0), output: point(2) });
    expect(tool.active).toBe(false);
  });
  it("starts on a requested coil and remembers saved manual endpoints rather than replacing them", () => {
    const { tool, onChange } = fixture();
    tool.begin("B"); expect(tool.input).toEqual(point(0, 0, 2));
    tool.begin("A"); tool.change("input"); tool.pick(point(1)); tool.flip(); tool.done();
    onChange.mockClear();
    tool.begin("A");
    expect(tool.defaultKind).toBe("saved");
    expect(tool.input).toEqual(point(2)); expect(tool.output).toEqual(point(1));
    expect(onChange).not.toHaveBeenCalled();
  });
  it("overrides IN or OUT in one pick without discarding the opposite endpoint", () => {
    const { tool, getGeometry } = fixture();
    tool.begin(); tool.change("input"); tool.pick(point(1));
    expect(tool.step).toBe("review"); expect(tool.output).toEqual(point(2));
    tool.change("output"); tool.pick(point(0));
    expect(tool.step).toBe("review"); expect(tool.input).toEqual(point(1));
    tool.done(); expect(getGeometry().coil_terminals!.A).toEqual({ input: point(1), output: point(0) });
  });
  it("flips the draft without changing geometry and supports a canceled override", () => {
    const { tool, onChange } = fixture();
    tool.begin(); tool.flip();
    expect(tool.input).toEqual(point(2)); expect(tool.output).toEqual(point(0));
    expect(onChange).not.toHaveBeenCalled();
    tool.change("input"); tool.finishPicking(); expect(tool.step).toBe("review");
    tool.cancel(); expect(onChange).not.toHaveBeenCalled();
    tool.begin(); expect(tool.input).toEqual(point(0));
  });
  it("falls back to manual picking for ambiguous coils and can pick OUT first", () => {
    const { tool, onChange } = fixture(true);
    tool.begin(); expect(tool.step).toBe("input"); expect(tool.input).toBeNull(); expect(tool.output).toBeNull();
    tool.done(); tool.flip(); expect(onChange).not.toHaveBeenCalled();
    tool.change("output"); tool.pick(point(2)); expect(tool.step).toBe("input");
    tool.pick(point(0)); expect(tool.step).toBe("review");
    tool.done(); expect(onChange).toHaveBeenCalledTimes(1);
  });
  it("rejects identical endpoints, invalid points and wrong layers without clearing the draft", () => {
    const { tool } = fixture();
    tool.begin(); tool.change("output");
    tool.pick(point(0)); expect(tool.error).toContain("different"); expect(tool.output).toEqual(point(2));
    tool.pick(point(99)); tool.pick(point(1, 1)); expect(tool.step).toBe("output");
    tool.pick(point(1)); expect(tool.error).toBe(""); expect(tool.step).toBe("review");
  });
  it("applies one coil and opens the next ready to review without reopening the tool", () => {
    const { tool, onChange, getGeometry } = fixture();
    tool.begin(); expect(tool.nextCoil).toBe("B");
    tool.applyAndNext(); expect(onChange).toHaveBeenCalledTimes(1);
    expect(getGeometry().coil_terminals!.A).toBeDefined();
    expect(tool.active).toBe(true); expect(tool.coil).toBe("B"); expect(tool.step).toBe("review");
    expect(tool.nextCoil).toBeUndefined();
    tool.done(); expect(Object.keys(getGeometry().coil_terminals!)).toEqual(["A", "B"]);
  });
  it("will not commit a draft after geometry has been replaced", () => {
    const { tool, onChange, replace } = fixture();
    tool.begin(); replace();
    expect(tool.active).toBe(false); tool.done(); expect(onChange).not.toHaveBeenCalled();
    tool.begin(); expect(tool.active).toBe(true); expect(tool.input).toEqual(point(0));
  });
  it("undoes an applied terminal change until another edit replaces it", () => {
    const { tool, getGeometry, replace } = fixture();
    tool.begin(); tool.done();
    expect(tool.canUndo).toBe(true);
    expect(getGeometry().coil_terminals!.A).toBeDefined();
    tool.undo();
    expect(tool.canUndo).toBe(false);
    expect(getGeometry().coil_terminals?.A).toBeUndefined();
    tool.begin(); tool.done();
    expect(tool.canUndo).toBe(true);
    replace();
    expect(tool.canUndo).toBe(false);
  });
  it("reveals both layers when inferred endpoints span an internal via", () => {
    const { tool, getGeometry, onReveal } = fixture();
    const geometry = getGeometry();
    geometry.routing.segments[1].layer = 1;
    geometry.routing.vias = [{ position: { x: 1, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }];
    tool.begin();
    expect(tool.step).toBe("review"); expect(tool.output).toEqual(point(2, 1));
    expect(onReveal).toHaveBeenCalledWith("A", 0); expect(onReveal).toHaveBeenCalledWith("A", 1);
  });
});
