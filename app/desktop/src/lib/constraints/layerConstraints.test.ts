import { describe, expect, it } from "vitest";
import {
  formatLayerRange,
  isMultipleOf,
  layerOptions,
  nearestLayer,
  patternLayerRange,
} from "./layerConstraints";

describe("patternLayerRange", () => {
  it("resolves missing catalog entries and fields to unconstrained", () => {
    expect(patternLayerRange(null)).toEqual({
      min_layers: null,
      max_layers: null,
      layers_multiple_of: null,
    });
    expect(patternLayerRange(undefined)).toEqual({
      min_layers: null,
      max_layers: null,
      layers_multiple_of: null,
    });
    expect(patternLayerRange({ id: "p", display_name: "P" })).toEqual({
      min_layers: null,
      max_layers: null,
      layers_multiple_of: null,
    });
  });

  it("passes through declared constraints", () => {
    expect(
      patternLayerRange({
        id: "p",
        display_name: "P",
        min_layers: 2,
        max_layers: 8,
        layers_multiple_of: 2,
      }),
    ).toEqual({ min_layers: 2, max_layers: 8, layers_multiple_of: 2 });
  });
});

describe("layerOptions", () => {
  it("offers the even ladder 2..max_layers when the pattern is unconstrained", () => {
    expect(layerOptions(12, patternLayerRange(null))).toEqual([
      2, 4, 6, 8, 10, 12,
    ]);
  });

  it("caps at the board maximum", () => {
    expect(layerOptions(6, patternLayerRange(null))).toEqual([2, 4, 6]);
  });

  it("respects the pattern's min/max", () => {
    const range = patternLayerRange({
      id: "p",
      display_name: "P",
      min_layers: 4,
      max_layers: 8,
    });
    expect(layerOptions(12, range)).toEqual([4, 6, 8]);
  });

  it("intersects an additional multiple-of constraint with the even ladder", () => {
    // multiple_of 4: 4, 8, 12 (all even anyway).
    const quad = patternLayerRange({
      id: "p",
      display_name: "P",
      layers_multiple_of: 4,
    });
    expect(layerOptions(12, quad)).toEqual([4, 8, 12]);
    // Odd multiple_of (unusual) must still intersect the even ladder.
    const triple = patternLayerRange({
      id: "p",
      display_name: "P",
      layers_multiple_of: 3,
    });
    expect(layerOptions(12, triple)).toEqual([6, 12]);
  });

  it("returns an empty list when the range excludes everything", () => {
    const range = patternLayerRange({
      id: "p",
      display_name: "P",
      min_layers: 20,
    });
    expect(layerOptions(12, range)).toEqual([]);
  });
});

describe("isMultipleOf", () => {
  it("accepts whole multiples", () => {
    expect(isMultipleOf(4, 2)).toBe(true);
    expect(isMultipleOf(2, 2)).toBe(true);
    expect(isMultipleOf(2.5, 0.5)).toBe(true);
  });

  it("rejects non-multiples", () => {
    expect(isMultipleOf(3, 2)).toBe(false);
    expect(isMultipleOf(1.3, 0.5)).toBe(false);
  });

  it("is epsilon-tolerant like the routing crate (1e-9)", () => {
    expect(isMultipleOf(4 + 5e-10, 2)).toBe(true);
    expect(isMultipleOf(4 + 1e-6, 2)).toBe(false);
  });

  it("passes degenerate inputs through (backend owns rejection)", () => {
    expect(isMultipleOf(Number.NaN, 2)).toBe(true);
    expect(isMultipleOf(4, 0)).toBe(true);
    expect(isMultipleOf(4, Number.NaN)).toBe(true);
  });
});

describe("nearestLayer", () => {
  it("picks the nearest option", () => {
    expect(nearestLayer(5, [2, 4, 6, 8])).toBe(4);
    expect(nearestLayer(7, [2, 4, 6, 8])).toBe(6);
  });

  it("picks the smaller option on ties", () => {
    expect(nearestLayer(5, [4, 6])).toBe(4);
  });

  it("returns n unchanged for an empty option list", () => {
    expect(nearestLayer(4, [])).toBe(4);
  });
});

describe("formatLayerRange", () => {
  it("describes a full range", () => {
    expect(
      formatLayerRange({ min_layers: 2, max_layers: 12, layers_multiple_of: 2 }),
    ).toBe("pattern supports 2\u201312 layers, even");
  });

  it("describes one-sided ranges and multiples", () => {
    expect(
      formatLayerRange({ min_layers: 4, max_layers: null, layers_multiple_of: 4 }),
    ).toBe("pattern supports \u2265 4 layers, multiples of 4");
    expect(
      formatLayerRange({ min_layers: null, max_layers: 8, layers_multiple_of: null }),
    ).toBe("pattern supports \u2264 8 layers");
  });

  it("reports unconstrained patterns", () => {
    expect(
      formatLayerRange({ min_layers: null, max_layers: null, layers_multiple_of: null }),
    ).toBe("pattern: no layer constraints");
  });
});
