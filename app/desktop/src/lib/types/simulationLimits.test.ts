import { describe, expect, it } from "vitest";
import { MAX_MAGNET_COUNT, MAX_PCB_LAYERS, ABSOLUTE_TEMPERATURE_TARGET_C } from "./simulationLimits";
import { BACKPLANE_MAX_THICKNESS_M, BACKPLANE_MAX_LAYERS, HOUSING_MAX_THICKNESS_M, HOUSING_MAX_GAP_M, HOUSING_MATERIAL_OPTIONS, isSupportedHousingMaterial } from "./backplane";
import { layerOptions, patternLayerRange } from "../layerConstraints";

describe("coreless screening envelope", () => {
  it("keeps physical input caps distinct from temperature target", () => {
    expect(MAX_MAGNET_COUNT).toBe(12);
    expect(MAX_PCB_LAYERS).toBe(16);
    expect(BACKPLANE_MAX_LAYERS).toBe(3);
    expect(BACKPLANE_MAX_THICKNESS_M).toBe(.002);
    expect(HOUSING_MAX_THICKNESS_M).toBe(.005);
    expect(HOUSING_MAX_GAP_M).toBe(.01);
    expect(ABSOLUTE_TEMPERATURE_TARGET_C).toBe(100);
  });
  it("offers nonmagnetic housings without erasing legacy file types", () => {
    expect(HOUSING_MATERIAL_OPTIONS.map((option) => option.value)).toEqual(["aluminum6061", "aluminum5052", "stainless304", "stainless316"]);
    expect(isSupportedHousingMaterial("steel1018")).toBe(false);
    expect(isSupportedHousingMaterial("stainless430")).toBe(false);
  });
  it("never offers more than sixteen copper layers even with legacy maxima", () => {
    expect(layerOptions(64, patternLayerRange(null))).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
  });
});
