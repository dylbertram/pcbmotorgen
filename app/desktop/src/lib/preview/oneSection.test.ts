import { describe, expect, it } from "vitest";
import type { PhaseCoilDto } from "../types";
import { braidLikeFixture } from "../testFixtures/braidLike";
import { computeVisibleArcs, computeVisibleSegments } from "./oneSection";

describe("computeVisibleSegments", () => {
  const coilKey = (ph: PhaseCoilDto) => ph.phase_idx * 1000 + ph.layer_idx;

  it("fast path returns all segments keyed by phase+layer", () => {
    const coils = braidLikeFixture();
    const m = computeVisibleSegments(coils, false, 6);
    expect(m.size).toBe(coils.phases.length);
    for (const ph of coils.phases) expect(m.get(coilKey(ph))).toBe(ph.segments);
  });

  it("one-section keeps the first N active conductors + interior end-turns", () => {
    const coils = braidLikeFixture();
    const m = computeVisibleSegments(coils, true, 2);
    for (const ph of coils.phases) {
      const segs = m.get(coilKey(ph))!;
      const actives = segs.filter((s) => s.is_active);
      expect(actives.length).toBeLessThanOrEqual(2);
      expect(actives.length).toBeGreaterThan(0);
      expect(segs.some((s) => !s.is_active)).toBe(true);
    }
  });

  it("returns empty map with no coils", () => {
    expect(computeVisibleSegments(null, false, 6).size).toBe(0);
  });
});

describe("computeVisibleArcs", () => {
  it("fast path returns all arcs keyed by phase+layer", () => {
    const coils = braidLikeFixture();
    const m = computeVisibleArcs(coils, false, 6);
    expect(m.size).toBe(coils.phases.length);
    expect([...m.values()].filter((a) => a.length > 0)).toHaveLength(1);
  });

  it("keeps an intersecting arc and drops an arc outside the selected x-window", () => {
    const coils = braidLikeFixture();
    const first = coils.phases[0];
    const inside = first.corner_arcs![0];
    const outside = { start: [0.01, 0.02], mid: [0.011, 0.021], end: [0.012, 0.02], is_active: false } as typeof inside;
    first.corner_arcs!.push(outside);
    const m = computeVisibleArcs(coils, true, 1);
    expect(m.get(0)).toEqual([inside]);
  });
});

it("keeps neither segments nor arcs when a one-section window has no conductors", () => {
  const coils = braidLikeFixture();
  const segments = computeVisibleSegments(coils, true, 0);
  const arcs = computeVisibleArcs(coils, true, 0);
  for (const phase of coils.phases) {
    const key = phase.phase_idx * 1000 + phase.layer_idx;
    expect(segments.get(key)).toEqual([]);
    expect(arcs.get(key)).toEqual([]);
  }
});
