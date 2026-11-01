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
  it("uses one physical SI-to-mm/centered/Y-up transform", () => {
    const scene = { centerMm: [5, -.4, -1] as [number, number, number], scale: 1 };
    expect(physicalToScene([.01, .002, -.0008], scene).toArray()).toEqual([5, -.4, -1]);
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
  it("colors short bends and long straights by the same W/m, without changing their total watts", () => {
    const g = geometry(); g.routing.vias = [];
    g.routing.curves.push({ start: { x: 10, y: 0 }, mid: { x: 10.7, y: .3 }, end: { x: 11, y: 1 }, layer: 0, net: "A", is_active: true });
    const h = heat(); h.edges.pop();
    const points: [number, number, number][] = [[.01, 0, 0], [.0107, .0003, 0], [.011, .001, 0]];
    const length = points.slice(1).reduce((sum, p, i) => sum + Math.hypot(...p.map((v, axis) => v - points[i][axis])), 0);
    const power = length * 50;
    h.edges.push({ net: "A", kind: "trace", layers: [0, 0], points_m: points, loss_w: power, rms_current_a: .5, resistance_ohm: power / .25 });
    h.total_loss_w = .5 + power;
    const colors = mapCopperLoss(g, h, "linear"), watts = mapCopperLoss(g, h);
    expect(colors.get("segment-0")).toBeCloseTo(50, 10); expect(colors.get("arc-0")).toBeCloseTo(50, 10);
    expect(heatColor(colors.get("segment-0")!, 50)).toBe(heatColor(colors.get("arc-0")!, 50));
    expect([...watts.values()].reduce((a, b) => a + b, 0)).toBe(h.total_loss_w);
    const changed = structuredClone(h); changed.edges.forEach(e => e.loss_w *= 4); changed.total_loss_w *= 4;
    expect(mapCopperLoss(g, changed, "linear").get("arc-0")).toBeCloseTo(200, 10);
  });
  it("does not change density when straight copper is split into display pieces", () => {
    const g = geometry(), h = heat(); g.routing.vias = []; h.edges.pop(); h.total_loss_w = .5;
    const original = mapCopperLoss(g, h, "linear").get("segment-0")!;
    g.routing.segments[0].end.x = 2;
    g.routing.segments.push({ ...g.routing.segments[0], start: { x: 2, y: 0 }, end: { x: 10, y: 0 } });
    h.edges[0].points_m[1][0] = .002; h.edges[0].loss_w = .1;
    h.edges.push({ ...h.edges[0], points_m: [[.002, 0, 0], [.01, 0, 0]], loss_w: .4 });
    expect([...mapCopperLoss(g, h, "linear").values()]).toEqual([original, original]);
    const invalid = heat(); invalid.edges[0].points_m[1] = [...invalid.edges[0].points_m[0]];
    expect(() => mapCopperLoss(geometry(), invalid, "linear")).toThrow();
  });
  it("normalizes aggregated via intervals by their actual total barrel length", () => {
    const g = geometry(), h = heat(); g.layer_z_mm = [0, -.3, -.8]; g.routing.vias[0].to_layer = 2;
    h.edges[1].layers = [0, 1]; h.edges[1].points_m[1][2] = -.0003; h.edges[1].loss_w = .09375;
    h.edges.push({ ...h.edges[1], layers: [1, 2], points_m: [[.01, 0, -.0003], [.01, 0, -.0008]], loss_w: .15625 });
    expect(mapCopperLoss(g, h, "linear").get("via-0")).toBeCloseTo(.25 / .0008, 10);
    expect(mapCopperLoss(g, h).get("via-0")).toBe(.25);
  });
  it("batches real vector shafts/heads while preserving physical magnitudes", () => {
    const scene = buildCoilScene(geometry())!;
    const field: FieldPreview = { method: "analytical-pm-only-xyz", scope: "unit-test data", magnets: [], samples: [
      { position_m: [.005, .001, 0], b_t: [0, 0, .1], magnitude_t: .1 }] };
    const original = structuredClone(field); const a = fieldGlyphGeometry(field, scene);
    expect(a.getAttribute("position").count).toBe(6); expect(a.getAttribute("color").count).toBe(6); expect(field).toEqual(original);
    const start = physicalToScene(field.samples[0].position_m, scene);
    const positions = a.getAttribute("position");
    expect(positions.getY(0)).toBeCloseTo(start.y, 6);
    expect(positions.getY(1)).toBeGreaterThan(positions.getY(0));
    a.dispose();
  });
});
