import { describe, it, expect } from "vitest";
import type { CadGeometry } from "./types";
import type { CopperLossPreview, FieldPreview } from "./types/simulationVisualization";
import { buildCoilScene } from "./coilScene";
import { physicalToScene, mapCopperLoss, fieldGlyphGeometry, heatColor } from "./visualizationGeometry";

const geometry = (): CadGeometry => ({ layer_z_mm: [0, -.8], trace_width_mm: .2, routing: { format_version: 2, curves: [], vias: [
  { position: { x: 10, y: 0 }, net: "A", from_layer: 0, to_layer: 1 }], segments: [
  { start: { x: 0, y: 0 }, end: { x: 10, y: 0 }, layer: 0, net: "A", is_active: true }] } });
const heat = (): CopperLossPreview => ({ method: "native-resistor-graph-rms-i2r", scope: "unit-test graph data", phase_peak_a: 1,
  phase_rms_a: 1 / Math.SQRT2, winding_temperature_c: 20, total_loss_w: .75, power_balance_relative_error: 0, edges: [
    { net: "A", kind: "trace", layers: [0, 0], points_m: [[0, 0, 0], [.01, 0, 0]], loss_w: .5, rms_current_a: .5, resistance_ohm: 2 },
    { net: "A", kind: "via", layers: [0, 1], points_m: [[.01, 0, 0], [.01, 0, -.0008]], loss_w: .25, rms_current_a: .5, resistance_ohm: 1 }] });

describe("physical visualization coordinates and conservative loss mapping", () => {
  it("uses one SI-to-mm/centered/Y-up transform and display-only Z scale", () => {
    const scene = { centerMm: [5, -.4, -1] as [number, number, number], scale: 1 };
    expect(physicalToScene([.01, .002, -.0008], scene).toArray()).toEqual([5, -.4, -1]);
    expect(physicalToScene([.01, .002, -.0008], scene, 20).toArray()).toEqual([5, -8, -1]);
    const g = geometry(), before = structuredClone(g); buildCoilScene(g); expect(g).toEqual(before);
  });
  it("maps reversed/reordered native branches onto real primitives and conserves total W", () => {
    const g = geometry(), h = heat(); h.edges.reverse(); h.edges[1].points_m.reverse();
    const map = mapCopperLoss(g, h); expect(map.get("segment-0")).toBe(.5); expect(map.get("via-0")).toBe(.25);
    expect([...map.values()].reduce((a, b) => a + b, 0)).toBe(h.total_loss_w);
    g.routing.segments[0].net = "coil"; g.coil_phases = { coil: "A" }; expect(mapCopperLoss(g, h).get("segment-0")).toBe(.5);
  });
  it("never matches altered depth or duplicate physical routes and never invents hot spots", () => {
    const deeper = geometry(); deeper.layer_z_mm[0] = -.1; expect(() => mapCopperLoss(deeper, heat())).toThrow("depth");
    const duplicate = geometry(); duplicate.routing.segments.push({ ...duplicate.routing.segments[0] });
    expect(() => mapCopperLoss(duplicate, heat())).toThrow("uniquely");
    const changed = heat(); changed.total_loss_w *= 2; expect(() => mapCopperLoss(geometry(), changed)).toThrow("conserve");
    expect(heatColor(0, 0)).toBe(heatColor(0, 1));
  });
  it("batches real vector shafts/heads while preserving physical magnitudes", () => {
    const scene = buildCoilScene(geometry())!;
    const field: FieldPreview = { method: "analytical-pm-only-xyz", scope: "unit-test data", magnets: [], samples: [
      { position_m: [.005, .001, 0], b_t: [0, 0, .1], magnitude_t: .1 }] };
    const original = structuredClone(field); const a = fieldGlyphGeometry(field, scene, 1), b = fieldGlyphGeometry(field, scene, 20);
    expect(a.getAttribute("position").count).toBe(6); expect(a.getAttribute("color").count).toBe(6); expect(field).toEqual(original);
    expect([...a.getAttribute("position").array]).not.toEqual([...b.getAttribute("position").array]); a.dispose(); b.dispose();
  });
});
