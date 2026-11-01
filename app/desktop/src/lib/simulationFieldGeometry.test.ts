import { describe, expect, it } from "vitest";
import { sampledFieldGrid, fieldLineGeometry, fieldSliceGeometry } from "./simulationFieldGeometry";
import type { FieldPreview } from "./types/simulationVisualization";

const scene = { centerMm: [0, 0, 0] as [number, number, number], scale: .001 };
function field(value = (x: number, y: number, z: number) => [1 + x, 2 + y, 3 + z]): FieldPreview {
  const samples: FieldPreview["samples"] = [];
  for (let z = 0; z < 3; z++) for (let y = 0; y < 3; y++) for (let x = 0; x < 3; x++) {
    const b = value(x, y, z) as [number, number, number];
    samples.push({ position_m: [x, y, z], b_t: b, magnitude_t: Math.hypot(...b) });
  }
  return { method: "analytical-pm-only-xyz", scope: "mathematical unit-test grid, not physical evidence", magnets: [], samples };
}

describe("native sampled-field interpolation and bounded rendering", () => {
  it("reconstructs affine vectors, honors all axes and never extrapolates", () => {
    const grid = sampledFieldGrid(field());
    expect(grid.sample([.25, .75, 1.25])).toEqual([1.25, 2.75, 4.25]);
    expect(grid.sample([2, 2, 2])).toEqual([3, 4, 5]);
    expect(grid.sample([0, 0, 0])).toEqual([1, 2, 3]);
    expect(grid.sample([2.00001, 1, 1])).toBeNull(); expect(grid.sample([NaN, 1, 1])).toBeNull();
    const missing = field(); missing.samples.pop(); expect(() => sampledFieldGrid(missing)).toThrow("complete");
    const unordered = field(); unordered.samples.reverse(); expect(() => sampledFieldGrid(unordered)).toThrow("ordered");
    const invalid = field(); invalid.samples[0].b_t[0] = Infinity; expect(() => sampledFieldGrid(invalid)).toThrow("finite");
  });
  it("integrates straight lines parallel to a uniform field, within the native domain", () => {
    const f = field(() => [1, 0, 0]), before = structuredClone(f);
    const lines = fieldLineGeometry(f, scene, .5), points = lines.getAttribute("position");
    expect(points.count).toBeGreaterThan(0); expect(points.count).toBeLessThanOrEqual(144 * 2 * 240 * 6);
    for (let i = 0; i < points.count; i += 2) {
      expect(points.getX(i)).toBeGreaterThanOrEqual(0); expect(points.getX(i)).toBeLessThanOrEqual(2);
      expect(points.getY(i)).toBeGreaterThanOrEqual(0); expect(points.getY(i)).toBeLessThanOrEqual(2);
      expect(points.getZ(i)).toBeCloseTo(-1, 5);
      // Most pairs are field-line segments. Direction cues have a lateral offset.
      if (Math.abs(points.getY(i) - points.getY(i + 1)) < 1e-6) expect(points.getZ(i + 1)).toBeCloseTo(-1, 5);
    }
    expect(f).toEqual(before); lines.dispose();
  });
  it("keeps every line and arrowhead on the selected XZ plane, even with a large normal field", () => {
    const f = field(() => [1, 100, 1]), before = structuredClone(f);
    for (const fraction of [0, .25, .75, 1]) {
      const lines = fieldLineGeometry(f, scene, fraction), slice = fieldSliceGeometry(f, scene, fraction);
      const points = lines.getAttribute("position"), plane = slice.getAttribute("position").getZ(0);
      expect(points.count).toBeGreaterThan(0);
      for (let i = 0; i < points.count; i++) expect(points.getZ(i)).toBeCloseTo(plane, 6);
      lines.dispose(); slice.dispose();
    }
    expect(f).toEqual(before);
  });
  it("integrates the in-plane vector, rather than flattening a 3D trajectory afterward", () => {
    // The normal component cannot change the in-plane trajectory or its reach.
    const a = fieldLineGeometry(field(() => [1, 0, 1]), scene, .25);
    const b = fieldLineGeometry(field(() => [1, 100, 1]), scene, .25);
    expect(Array.from(a.getAttribute("position").array)).toEqual(Array.from(b.getAttribute("position").array));
    a.dispose(); b.dispose();
  });
  it("draws no projected direction for a purely normal field, without losing slice magnitude", () => {
    const f = field(() => [0, 5, 0]), before = structuredClone(f);
    const lines = fieldLineGeometry(f, scene, .5), slice = fieldSliceGeometry(f, scene, .5);
    expect(lines.getAttribute("position").count).toBe(0);
    expect(slice.getAttribute("position").count).toBeGreaterThan(0);
    expect(f).toEqual(before);
    lines.dispose(); slice.dispose();
  });
  it("only follows the normal component in explicitly requested 3D mode", () => {
    const lines = fieldLineGeometry(field(() => [0, 5, 0]), scene, .5, "3d");
    const points = lines.getAttribute("position");
    expect(points.count).toBeGreaterThan(0);
    expect(new Set(Array.from({ length: points.count }, (_, i) => points.getZ(i))).size).toBeGreaterThan(1);
    lines.dispose();
  });
  it("draws no lines through a null field and does not invent magnitude", () => {
    const f = field(() => [0, 0, 0]);
    const lines = fieldLineGeometry(f, scene, .5), slice = fieldSliceGeometry(f, scene, .5);
    expect(lines.getAttribute("position").count).toBe(0);
    expect(slice.getAttribute("position").count).toBeGreaterThan(0);
    const colors = slice.getAttribute("color");
    expect(new Set(Array.from(colors.array).map((v, i) => `${i % 3}:${v}`)).size).toBe(3);
    lines.dispose(); slice.dispose();
  });
  it("moves the physical Y slice and its magnitude colors without altering the samples", () => {
    const f = field(), before = structuredClone(f);
    const a = fieldSliceGeometry(f, scene, .25), c = fieldSliceGeometry(f, scene, .75);
    expect(a.getAttribute("position").getZ(0)).toBe(-.5); expect(c.getAttribute("position").getZ(0)).toBe(-1.5);
    expect(Array.from(a.getAttribute("color").array)).not.toEqual(Array.from(c.getAttribute("color").array));
    expect(f).toEqual(before); [a, c].forEach(g => g.dispose());
  });
  it("leaves magnet interiors unpainted and stops field trajectories at their boundaries", () => {
    const f = field(() => [1, 0, 0]); f.magnets = [{ center_m: [1, 1, 1], size_m: [.4, .4, .4], positive_z: true }];
    const grid = sampledFieldGrid(f), lines = fieldLineGeometry(f, scene, .5), slice = fieldSliceGeometry(f, scene, .5);
    for (const g of [lines, slice]) {
      const p = g.getAttribute("position");
      for (let i = 0; i < p.count; i++) expect(grid.insideMagnet([p.getX(i), -p.getZ(i), p.getY(i)])).toBe(false);
      g.dispose();
    }
  });
  it("cannot leap across a thin magnet between integration endpoints", () => {
    const f = field(() => [1, 0, 0]); f.magnets = [{ center_m: [1, 1, 1], size_m: [.000001, .4, .4], positive_z: true }];
    const grid = sampledFieldGrid(f);
    expect(grid.insideMagnet([.99, 1, 1])).toBe(false); expect(grid.insideMagnet([1.01, 1, 1])).toBe(false);
    expect(grid.crossesMagnet([.99, 1, 1], [1.01, 1, 1])).toBe(true);
    expect(grid.crossesMagnet([1.01, 1, 1], [.99, 1, 1])).toBe(true);
    expect(grid.crossesMagnet([.99, 0, 1], [1.01, 0, 1])).toBe(false);
  });
});
