import { describe, expect, it } from "vitest";
import { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

describe("nested coil/layer visibility", () => {
  it("defaults to physical Z height and keeps its display scale independent of visibility", () => {
    const view = new CoilPreviewViewState();
    expect(view.zScale).toBe(1);
    view.zScale = 10;
    view.toggleLayer(0);
    expect(view.zScale).toBe(10);
  });

  it("defaults to visible and hides only the chosen coil/layer", () => {
    const view = new CoilPreviewViewState();
    expect(view.isCoilLayerVisible("A", 0)).toBe(true);
    view.toggleCoilLayer("A", 0);
    expect(view.isCoilLayerVisible("A", 0)).toBe(false);
    expect(view.isCoilLayerVisible("A", 1)).toBe(true);
    expect(view.isCoilLayerVisible("B", 0)).toBe(true);
    expect(view.isLayerVisible(0)).toBe(true);
    expect(view.isPhaseVisible(0)).toBe(true);
    view.showCoilLayer("A", 0);
    expect(view.isCoilLayerVisible("A", 0)).toBe(true);
  });

  it("keeps visibility independent of global toggles and arbitrary coil names", () => {
    const view = new CoilPreviewViewState();
    view.toggleCoilLayer("A:1", 0);
    view.toggleLayer(0);
    expect(view.isCoilLayerVisible("A:1", 0)).toBe(false);
    expect(view.isCoilLayerVisible("A", 1)).toBe(true);
    view.toggleLayer(0);
    expect(view.isCoilLayerVisible("A:1", 0)).toBe(false);
    view.toggleCoilLayer("A:1", 0);
    expect(view.isCoilLayerVisible("A:1", 0)).toBe(true);
  });
});
