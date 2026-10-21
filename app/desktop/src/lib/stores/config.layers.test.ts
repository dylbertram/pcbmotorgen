import { describe, expect, it } from "vitest";
import { ConfigStore } from "./config.svelte";
import type { RoutingPatternInfo } from "../types";

/** Catalog fixture: the bundled braid (min 2 layers, no upper bound) and a
 *  hypothetical pattern requiring even multiples of 4 up to 8 layers. */
const CATALOG: RoutingPatternInfo[] = [
  { id: "infinity-braid", display_name: "Infinity Braid", min_layers: 2 },
  {
    id: "quad-stack",
    display_name: "Quad Stack",
    min_layers: 2,
    max_layers: 8,
    layers_multiple_of: 4,
  },
];

function storeWithLayers(numLayers: number, patternId: string): ConfigStore {
  const store = new ConfigStore();
  store.routing_patterns = CATALOG;
  store.num_layers = numLayers;
  store.routing_pattern = patternId;
  return store;
}

describe("ConfigStore pattern-constrained layer selection", () => {
  it("derives the layer options from the board max and pattern metadata", () => {
    const store = storeWithLayers(4, "infinity-braid");
    // Braid: min 2, no max -> even ladder up to the 16-layer program cap.
    expect(store.layerOptions).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
    expect(store.patternLayerRange).toEqual({
      min_layers: 2,
      max_layers: null,
      layers_multiple_of: null,
    });
  });

  it("intersects the options with a stricter pattern range", () => {
    const store = storeWithLayers(4, "quad-stack");
    expect(store.layerOptions).toEqual([4, 8]);
  });

  it("updates options and range when the pattern switches", () => {
    const store = storeWithLayers(4, "infinity-braid");
    expect(store.layerOptions).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
    store.routing_pattern = "quad-stack";
    expect(store.layerOptions).toEqual([4, 8]);
  });

  it("keeps num_layers when it already satisfies the pattern", () => {
    const store = storeWithLayers(4, "quad-stack");
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(4);
  });

  it("snaps num_layers to the nearest valid option after a pattern switch", () => {
    // 6 is invalid for quad-stack (multiples of 4 only): nearest is 4 or 8,
    // tie picks the smaller.
    const store = storeWithLayers(6, "quad-stack");
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(4);

    // 6 is valid for the braid: untouched.
    const braid = storeWithLayers(6, "infinity-braid");
    braid.constrainLayersToPattern();
    expect(braid.num_layers).toBe(6);
  });

  it("clamps num_layers above the pattern maximum", () => {
    const store = storeWithLayers(12, "quad-stack");
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(8);
  });

  it("clamps num_layers below the pattern minimum", () => {
    const store = storeWithLayers(2, "quad-stack");
    // quad-stack allows 2 (>= min 2, multiple of 4? no) -> options [4, 8].
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(4);
  });

  it("is unconstrained for an unknown pattern (catalog not loaded yet)", () => {
    const store = storeWithLayers(10, "not-in-catalog");
    expect(store.layerOptions).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(10);
  });

  it("no-ops when the option set is empty", () => {
    const store = new ConfigStore();
    store.routing_patterns = [
      { id: "huge", display_name: "Huge", min_layers: 40 },
    ];
    store.max_layers = 12; // board cannot satisfy the pattern
    store.num_layers = 4;
    store.routing_pattern = "huge";
    expect(store.layerOptions).toEqual([]);
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(4);
  });

  it("preserves an unsupported imported layer count instead of truncating geometry", () => {
    const store = storeWithLayers(20, "infinity-braid");
    store.max_layers = 24;
    store.constrainLayersToPattern();
    expect(store.num_layers).toBe(20);
    expect(store.layerOptions).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
  });
});
