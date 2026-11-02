import { describe, expect, it } from "vitest";
import { phaseBandPitchMm, restOffsetMm } from "./phaseBands";

describe("phase-band geometry", () => {
  it("scales the pole pitch by the vernier ratio", () => {
    expect(phaseBandPitchMm(12, 3, 1)).toBeCloseTo(4);
    expect(restOffsetMm(12, 3, 1)).toBe(0);
    expect(phaseBandPitchMm(12, 3, 5 / 6)).toBeCloseTo(10 / 3);
    expect(restOffsetMm(12, 3, 5 / 6)).toBeCloseTo(2 / 3);
  });

  it("never returns a negative rest offset", () => {
    expect(restOffsetMm(12, 3, 1.5)).toBe(0);
  });
});
