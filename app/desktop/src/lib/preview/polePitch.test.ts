import { describe, expect, it } from "vitest";
import { computePolePitchValue, computePolePitchRuler, firstMagnetCenterX } from "./polePitch";

describe("computePolePitchValue", () => {
  it("returns null for absent/legacy sidecars and invalid pitches", () => {
    expect(computePolePitchValue(null)).toBeNull();
    expect(computePolePitchValue(undefined)).toBeNull();
    expect(computePolePitchValue({ pole_pitch_m: null, period_pitch_m: null })).toBeNull();
    expect(computePolePitchValue({ pole_pitch_m: 0, period_pitch_m: 0 })).toBeNull();
    expect(computePolePitchValue({ pole_pitch_m: -0.012, period_pitch_m: -0.013 })).toBeNull();
    expect(computePolePitchValue({ pole_pitch_m: Number.NaN, period_pitch_m: Number.NaN })).toBeNull();
    expect(computePolePitchValue({ pole_pitch_m: Number.POSITIVE_INFINITY, period_pitch_m: undefined })).toBeNull();
  });
  it("prefers pole_pitch_m and labels it Pole pitch", () => {
    expect(computePolePitchValue({ pole_pitch_m: 0.012, period_pitch_m: 0.013 }))
      .toEqual({ pitchM: 0.012, source: "pole_pitch_m", label: "Pole pitch" });
  });
  it("falls back to period_pitch_m but clearly labels it Repeat period", () => {
    expect(computePolePitchValue({ pole_pitch_m: null, period_pitch_m: 0.013 }))
      .toEqual({ pitchM: 0.013, source: "period_pitch_m", label: "Repeat period" });
  });
});

describe("firstMagnetCenterX", () => {
  it("returns the centre of the first magnet strip", () => {
    expect(firstMagnetCenterX([{ x: 0, w: 0.01, pole: 1 }])).toBeCloseTo(0.005, 9);
  });
  it("returns null when the array is empty", () => {
    expect(firstMagnetCenterX([])).toBeNull();
  });
});

describe("computePolePitchRuler", () => {
  it("is null when the pitch or the magnet centre is unavailable", () => {
    expect(computePolePitchRuler({ pole_pitch_m: 0.012 }, null, 0.1)).toBeNull();
    expect(computePolePitchRuler(null, 0.005, 0.1)).toBeNull();
  });
  it("aligns the ruler to first centre → first centre + pitch", () => {
    const r = computePolePitchRuler({ pole_pitch_m: 0.012 }, 0.005, 0.1);
    expect(r).not.toBeNull();
    expect(r!.x1).toBeCloseTo(0.005, 9);
    expect(r!.x2).toBeCloseTo(0.017, 9);
    expect(r!.y).toBeCloseTo(0.1, 9);
    expect(r!.label).toBe("Pole pitch");
    expect(r!.source).toBe("pole_pitch_m");
  });
});
