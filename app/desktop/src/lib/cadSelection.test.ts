import { describe, expect, it } from "vitest";
import type { CadGeometry } from "./types";
import { reassignTraces, selectableTraces, traceChain, traceDistance, traceInBox } from "./cadSelection";
import { CadSelectionTool } from "./utils/cadSelectionTool.svelte";

function fixture(): CadGeometry {
  return { layer_z_mm: [-1.6, 0], trace_width_mm: 0.4, routing: { format_version: 2,
    segments: [0, 1, 2].map((x) => ({ start: { x, y: 0 }, end: { x: x + 1, y: 0 }, layer: 0, net: x === 2 ? "B" : "A", is_active: true })),
    curves: [{ start: { x: 3, y: 0 }, mid: { x: 4, y: 1 }, end: { x: 5, y: 0 }, layer: 0, net: "B", is_active: false }],
    splines: [{ degree: 1, knots: [0, 0, 1, 1], control_points: [{ x: 5, y: 0 }, { x: 6, y: 0 }], net: "B", layer: 0, is_active: true }],
    vias: [{ position: { x: 0, y: 0 }, net: "A", from_layer: 0, to_layer: 1 }],
  }, coil_terminals: Object.fromEntries(["A", "B", "C"].map((coil) => [coil, { input: { position: { x: 0, y: 0 }, layer: 0 }, output: { position: { x: 1, y: 0 }, layer: 0 } }])) };
}

describe("CAD selection geometry", () => {
  it("finds chains by connectivity, not array order or net name, including arcs and splines", () => {
    const traces = selectableTraces(fixture());
    expect(traceChain([...traces].reverse(), "segments:0", "splines:0")).toEqual(["segments:0", "segments:1", "segments:2", "curves:0", "splines:0"]);
    expect(traceChain(traces, "segments:0", "segments:0")).toEqual(["segments:0"]);
    expect(traceChain(traces.filter((t) => t.id !== "segments:1"), "segments:0", "segments:2")).toEqual([]);
    expect(traceChain(traces.map((t) => t.id === "segments:2" ? { ...t, layer: 1 } : t), "segments:0", "segments:2")).toEqual([]);
  });
  it("does not connect crossing interiors and respects endpoint tolerance", () => {
    const traces = selectableTraces(fixture()).slice(0, 2);
    traces[1] = { ...traces[1], points: [{ x: 1.04, y: 0 }, { x: 2, y: 0 }] };
    expect(traceChain(traces, traces[0].id, traces[1].id, 0.05)).toHaveLength(2);
    expect(traceChain(traces, traces[0].id, traces[1].id, 0.01)).toEqual([]);
    traces[1].points = [{ x: .5, y: -1 }, { x: .5, y: 1 }];
    expect(traceChain(traces, traces[0].id, traces[1].id)).toEqual([]);
  });
  it("crosses copper layers only through matching via endpoints", () => {
    const traces = selectableTraces(fixture()).slice(0, 2);
    traces[1] = { ...traces[1], layer: 1 };
    expect(traceChain(traces, traces[0].id, traces[1].id)).toEqual([]);
    expect(traceChain(traces, traces[0].id, traces[1].id, .05, [{ position: { x: 1, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }])).toEqual(["segments:0", "segments:1"]);
    expect(traceChain(traces, traces[0].id, traces[1].id, .05, [{ position: { x: 10, y: 0 }, from_layer: 0, to_layer: 1, net: "A" }])).toEqual([]);
  });
  it("distinguishes containment from crossing, including edges with neither endpoint inside", () => {
    const [line] = selectableTraces(fixture());
    const box = { minX: .4, maxX: .6, minY: -.1, maxY: .1 };
    expect(traceInBox(line, box, true)).toBe(true);
    expect(traceInBox(line, box, false)).toBe(false);
    expect(traceInBox(line, { minX: 0, maxX: 1, minY: 0, maxY: 1 }, false)).toBe(true);
    expect(traceInBox(line, { ...box, minY: 1, maxY: 2 }, true)).toBe(false);
    expect(traceInBox(line, { minX: 1, maxX: 2, minY: 0, maxY: 1 }, true)).toBe(true);
  });
  it("uses the circular arc and spline paths for hits and boxes", () => {
    const traces = selectableTraces(fixture());
    const arc = traces.find((t) => t.id === "curves:0")!;
    expect(traceDistance({ x: 4, y: 1 }, arc)).toBeLessThan(.001);
    expect(traceDistance({ x: 4, y: 0 }, arc)).toBeGreaterThan(.9);
    expect(traceInBox(arc, { minX: 3.9, maxX: 4.1, minY: .95, maxY: 1.1 }, true)).toBe(true);
    expect(traceInBox(arc, { minX: 3, maxX: 5, minY: -.1, maxY: .1 }, false)).toBe(false);
    expect(traceDistance({ x: 5.5, y: 0 }, traces.at(-1)!)).toBeLessThan(.001);
  });
  it("reassigns only selected primitives, preserves vias, and clears only affected terminals", () => {
    const original = fixture();
    original.source_file_name = "motor-coils.dxf";
    const changed = reassignTraces(original, ["segments:0", "curves:0", "splines:0"], "D", 1);
    expect(changed.routing.segments[0]).toMatchObject({ net: "D", layer: 1 });
    expect(changed.routing.segments[1]).toBe(original.routing.segments[1]);
    expect(changed.routing.curves[0]).toMatchObject({ net: "D", layer: 1 });
    expect(changed.routing.splines![0]).toMatchObject({ net: "D", layer: 1 });
    expect(changed.routing.vias).toBe(original.routing.vias);
    expect(changed.source_file_name).toBe("motor-coils.dxf");
    expect(Object.keys(changed.coil_terminals!)).toEqual(["C"]);
    expect(original.routing.segments[0].net).toBe("A");
    expect(Object.keys(original.coil_terminals!)).toEqual(["A", "B", "C"]);
  });
});

describe("CAD selection tool", () => {
  function setup() {
    let geometry = fixture();
    const tool = new CadSelectionTool({ getGeometry: () => geometry, onChange: (next) => { geometry = next; } });
    return { tool, traces: selectableTraces(geometry), geometry: () => geometry, replace: () => { geometry = { ...geometry }; } };
  }
  it("replaces on click and toggles with Shift", () => {
    const { tool, traces } = setup();
    tool.setMode("select");
    tool.pick({ x: .5, y: 0 }, traces, .1, false);
    tool.pick({ x: 1.5, y: 0 }, traces, .1, true);
    expect(tool.selected).toEqual(["segments:0", "segments:1"]);
    tool.pick({ x: .5, y: 0 }, traces, .1, true);
    expect(tool.selected).toEqual(["segments:1"]);
    tool.pick({ x: 0, y: 5 }, traces, .1, true);
    expect(tool.selected).toEqual(["segments:1"]);
    tool.pick({ x: 0, y: 5 }, traces, .1, false);
    expect(tool.selected).toEqual([]);
  });
  it("uses first/last chain picks, keeps the anchor after a disconnected pick, and clears on mode change", () => {
    const { tool, traces } = setup();
    tool.setMode("chain");
    tool.pickTrace("segments:0", traces, false);
    expect(tool.anchor).toBe("segments:0");
    tool.pickTrace("splines:0", traces, false);
    expect(tool.selected).toHaveLength(5);
    expect(tool.anchor).toBeNull();
    tool.pickTrace("segments:0", traces, false);
    tool.pickTrace("splines:0", traces.filter((t) => t.id !== "segments:1"), false);
    expect(tool.notice).toContain("No connected chain");
    expect(tool.anchor).toBe("segments:0");
    tool.setMode("select");
    expect(tool.anchor).toBeNull();
  });
  it("supports box replacement, addition, subtraction and Shift-add", () => {
    const { tool, traces } = setup();
    const box = { minX: -.1, maxX: .9, minY: -.1, maxY: .1 };
    tool.selectBox(box, traces, false);
    expect(tool.selected).toEqual(["segments:0"]);
    tool.selectBox({ ...box, minX: 1.1, maxX: 1.9 }, traces, true);
    expect(tool.selected).toEqual(["segments:0", "segments:1"]);
    tool.boxAction = "remove";
    tool.selectBox(box, traces, false);
    expect(tool.selected).toEqual(["segments:1"]);
    tool.crossing = false; tool.boxAction = "replace";
    tool.selectBox(box, traces, false);
    expect(tool.selected).toEqual([]);
  });
  it("assigns a coil or layer independently, validates layers, and undoes only the current edit", () => {
    const { tool, geometry, replace } = setup();
    const original = geometry();
    tool.selected = ["segments:0"];
    tool.apply("  D  ", "");
    expect(geometry().routing.segments[0]).toMatchObject({ net: "D", layer: 0 });
    expect(tool.canUndo).toBe(true);
    tool.undo();
    expect(geometry()).toBe(original);
    tool.apply("", "99"); expect(geometry()).toBe(original);
    tool.apply("", "1"); expect(geometry().routing.segments[0]).toMatchObject({ net: "A", layer: 1 });
    replace(); expect(tool.canUndo).toBe(false);
    const replaced = geometry(); tool.undo(); expect(geometry()).toBe(replaced);
  });
});
