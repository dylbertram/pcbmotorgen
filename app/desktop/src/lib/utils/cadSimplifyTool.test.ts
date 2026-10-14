import { describe, expect, it } from "vitest";
import type { CadGeometry } from "../types";
import { CadSimplifyTool } from "./cadSimplifyTool.svelte";

function setup() {
  let geometry: CadGeometry | null = {
    layer_z_mm: [0, -1.6], trace_width_mm: .4,
    routing: { format_version: 2, curves: [], vias: [], segments: [0, 1].map(x => ({
      start: { x, y: 0 }, end: { x: x + 1, y: 0 }, net: "A", layer: 0, is_active: true,
    })) },
  };
  const tool = new CadSimplifyTool({ getGeometry: () => geometry, onChange: next => { geometry = next; } });
  return { tool, get geometry() { return geometry; }, replace: (next: CadGeometry | null) => { geometry = next; } };
}

describe("shared simplification tool", () => {
  it("simplifies and restores the exact previous geometry", () => {
    const state = setup();
    const before = state.geometry;
    state.tool.simplify();
    expect(state.geometry?.routing.segments).toHaveLength(1);
    expect(state.tool.canUndo).toBe(true);
    expect(state.tool.notice).toBe("1 line(s) merged.");
    state.tool.undo();
    expect(state.geometry).toBe(before);
    expect(state.tool.canUndo).toBe(false);
  });
  it("does not overwrite a later terminal or segment edit with stale undo", () => {
    const state = setup();
    state.tool.simplify();
    const edited = { ...state.geometry!, trace_width_mm: .6 };
    state.replace(edited);
    expect(state.tool.canUndo).toBe(false);
    state.tool.undo();
    expect(state.geometry).toBe(edited);
  });
  it("retains undo after a no-op simplify and clears it on reimport", () => {
    const state = setup();
    state.tool.simplify();
    state.tool.simplify();
    expect(state.tool.canUndo).toBe(true);
    state.tool.reset();
    expect(state.tool.canUndo).toBe(false);
    expect(state.tool.notice).toBe("");
    state.replace(null);
    state.tool.simplify();
    expect(state.geometry).toBeNull();
  });
});
