import { describe, expect, it } from "vitest";
import type { PoleRegionDto } from "../types";
import { computePoleRegionBounds, computePoleRegionPhases, computePoleRegionZones,
  filterPoleRegionsByPhase, isValidPoleRegion, poleRegionPolarity, resolvePoleRegionPhaseSelection } from "./poleRegions";

function poleRegionsFixture(): { pole_regions: PoleRegionDto[] } {
  return { pole_regions: [
    { phase: "A", pole_index: 0, start: [-0.004, 0.001], end: [0.008, 0.001] },
    { phase: "A", pole_index: 1, start: [0.008, 0.001], end: [0.02, 0.001] },
    { phase: "B", pole_index: 0, start: [0.005, 0.01], end: [0.017, 0.01] },
    { phase: "C", pole_index: 0, start: [0.012, 0.01], end: [0.009, 0.01] },
  ] };
}

describe("poleRegionPolarity", () => {
  it("alternates +1 even / -1 odd by pole_index", () => {
    expect(poleRegionPolarity(0)).toBe(1);
    expect(poleRegionPolarity(1)).toBe(-1);
    expect(poleRegionPolarity(2)).toBe(1);
    expect(poleRegionPolarity(3)).toBe(-1);
  });
});

describe("isValidPoleRegion", () => {
  const good: PoleRegionDto = { phase: "A", pole_index: 0, start: [0, 0], end: [0.012, 0] };
  it("accepts a well-formed region", () => {
    expect(isValidPoleRegion(good)).toBe(true);
  });
  it("rejects missing / malformed / legacy input", () => {
    expect(isValidPoleRegion(null)).toBe(false);
    expect(isValidPoleRegion(undefined)).toBe(false);
    expect(isValidPoleRegion({} as PoleRegionDto)).toBe(false);
    expect(isValidPoleRegion({ ...good, phase: "" })).toBe(false);
    expect(isValidPoleRegion({ ...good, phase: "   " })).toBe(false);
    expect(isValidPoleRegion({ ...good, pole_index: -1 })).toBe(false);
    expect(isValidPoleRegion({ ...good, pole_index: 1.5 })).toBe(false);
    expect(isValidPoleRegion({ ...good, pole_index: Number.NaN })).toBe(false);
    expect(isValidPoleRegion({ ...good, start: [Number.NaN, 0] })).toBe(false);
    expect(isValidPoleRegion({ ...good, end: [0.012, Number.POSITIVE_INFINITY] })).toBe(false);
    expect(isValidPoleRegion({ ...good, start: [0, 0, 0] } as unknown as PoleRegionDto)).toBe(true);
  });
  it("rejects a zero-width x span", () => {
    expect(isValidPoleRegion({ ...good, end: [0, 0] })).toBe(false);
  });
});

describe("computePoleRegionZones", () => {
  it("returns [] for missing/legacy/malformed dimensions", () => {
    expect(computePoleRegionZones(null)).toEqual([]);
    expect(computePoleRegionZones(undefined)).toEqual([]);
    expect(computePoleRegionZones({ pole_regions: [] })).toEqual([]);
    expect(computePoleRegionZones({ pole_regions: [{ phase: "A", pole_index: 0, start: [0, 0], end: [0, 0] }] })).toEqual([]);
  });
  it("validates, orders boundaries, and assigns alternating polarity", () => {
    const zones = computePoleRegionZones(poleRegionsFixture());
    expect(zones).toHaveLength(4);
    const c = zones.find((z) => z.phase === "C")!;
    expect(c.x0).toBeCloseTo(0.009, 9);
    expect(c.x1).toBeCloseTo(0.012, 9);
    expect(c.polarity).toBe(1);
    const a0 = zones.find((z) => z.phase === "A" && z.poleIndex === 0)!;
    const a1 = zones.find((z) => z.phase === "A" && z.poleIndex === 1)!;
    expect(a0.polarity).toBe(1);
    expect(a1.polarity).toBe(-1);
  });
  it("sorts by x, then phase, then pole index", () => {
    const zones = computePoleRegionZones({ pole_regions: [
      { phase: "B", pole_index: 0, start: [0, 0], end: [1, 0] },
      { phase: "A", pole_index: 2, start: [0, 0], end: [1, 0] },
      { phase: "C", pole_index: 0, start: [-1, 0], end: [1, 0] },
      { phase: "A", pole_index: 1, start: [0, 0], end: [1, 0] },
    ] });
    expect(zones.map(({ x0, phase, poleIndex }) => [x0, phase, poleIndex])).toEqual([
      [-1, "C", 0], [0, "A", 1], [0, "A", 2], [0, "B", 0],
    ]);
  });
});

describe("computePoleRegionPhases", () => {
  it("extracts distinct, sorted phase labels from region data", () => {
    const zones = computePoleRegionZones(poleRegionsFixture());
    expect(computePoleRegionPhases(zones)).toEqual(["A", "B", "C"]);
  });
  it("returns [] when there are no valid zones", () => {
    expect(computePoleRegionPhases([])).toEqual([]);
  });
});

describe("filterPoleRegionsByPhase", () => {
  const zones = computePoleRegionZones(poleRegionsFixture());
  it("returns all zones for null/empty selection", () => {
    expect(filterPoleRegionsByPhase(zones, null)).toHaveLength(4);
    expect(filterPoleRegionsByPhase(zones, "")).toHaveLength(4);
  });
  it("returns only the selected phase's zones", () => {
    const a = filterPoleRegionsByPhase(zones, "A");
    expect(a).toHaveLength(2);
    expect(a.every((z) => z.phase === "A")).toBe(true);
  });
  it("returns [] for an unknown phase", () => {
    expect(filterPoleRegionsByPhase(zones, "Z")).toEqual([]);
  });
  it("returns a fresh copy (never mutates the source)", () => {
    const all = filterPoleRegionsByPhase(zones, "");
    expect(all).not.toBe(zones);
  });
});

describe("computePoleRegionBounds", () => {
  it("returns null for no zones", () => {
    expect(computePoleRegionBounds([], 0, 1)).toBeNull();
  });
  it("unions x spans and honours the supplied y band", () => {
    const zones = computePoleRegionZones(poleRegionsFixture());
    const b = computePoleRegionBounds(zones, 0.018, 0.02)!;
    expect(b.minX).toBeCloseTo(-0.004, 9);
    expect(b.maxX).toBeCloseTo(0.02, 9);
    expect(b.minY).toBeCloseTo(0.018, 9);
    expect(b.maxY).toBeCloseTo(0.02, 9);
  });
});

describe("resolvePoleRegionPhaseSelection", () => {
  it("keeps a valid selection and always keeps '' (all phases)", () => {
    expect(resolvePoleRegionPhaseSelection("A", ["A", "B", "C"])).toBe("A");
    expect(resolvePoleRegionPhaseSelection("", ["A", "B"])).toBe("");
  });
  it("collapses a stale selection to '' when the label is gone", () => {
    expect(resolvePoleRegionPhaseSelection("C", ["A", "B"])).toBe("");
    expect(resolvePoleRegionPhaseSelection("Z", [])).toBe("");
  });
});
