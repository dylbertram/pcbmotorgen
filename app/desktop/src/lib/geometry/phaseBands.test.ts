import { describe, expect, it } from "vitest";
import { phaseBandPitchMm, phaseBandPitchDifferenceMm } from "./phaseBands";

describe("phase-band geometry", () => {
  it("scales the pole pitch by the vernier ratio", () => {
    expect(phaseBandPitchMm(12, 3, 1)).toBeCloseTo(4);
    expect(phaseBandPitchDifferenceMm(12, 3, 1)).toBe(0);
    expect(phaseBandPitchMm(12, 3, 5 / 6)).toBeCloseTo(10 / 3);
    expect(phaseBandPitchDifferenceMm(12, 3, 5 / 6)).toBeCloseTo(2 / 3);
  });

  it("clamps a negative pitch difference to zero", () => {
    expect(phaseBandPitchDifferenceMm(12, 3, 1.5)).toBe(0);
  });
});
