import { describe, expect, it } from "vitest";
import { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

describe("nested coil/layer visibility", () => {
  it("switches layer organization without changing visibility or camera state", () => {
    const view = new CoilPreviewViewState();
    expect(view.layerSortMode).toBe("phases");
    view.toggleLayer(1); view.toggleCoilLayer("A", 0); view.phaseVisibility[0] = false;
    view.viewMode = "iso"; view.spatialZoom = 3;
    const before = JSON.stringify([view.layerVisibility, view.coilLayerVisibility, view.phaseVisibility, view.viewMode, view.spatialZoom]);
    view.layerSortMode = "layers";
    expect(JSON.stringify([view.layerVisibility, view.coilLayerVisibility, view.phaseVisibility, view.viewMode, view.spatialZoom])).toBe(before);
    view.layerSortMode = "phases";
    expect(JSON.stringify([view.layerVisibility, view.coilLayerVisibility, view.phaseVisibility, view.viewMode, view.spatialZoom])).toBe(before);
  });
  it("defaults to layers on entering coil ends but preserves a manual switch while picking", () => {
    const view = new CoilPreviewViewState();
    expect(view.positionBarMode).toBe("position");
    view.setTerminalPanelOpen(true);
    expect(view.positionBarMode).toBe("layers");
    view.positionBarMode = "position";
    view.setTerminalPanelOpen(true);
    view.requestTerminals("A");
    expect(view.positionBarMode).toBe("position");
    view.setTerminalPanelOpen(false);
    view.setTerminalPanelOpen(true);
    expect(view.positionBarMode).toBe("layers");
  });
  it("keeps detailed diagnostic overlays off until requested", () => {
    const view = new CoilPreviewViewState();
    expect(view.showBandWidths).toBe(false);
    expect(view.showPoleRegions).toBe(false);
    expect(view.showPolePitch).toBe(true);
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
