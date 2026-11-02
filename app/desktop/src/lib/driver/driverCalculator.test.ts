import { describe, expect, it } from "vitest";
import { calculateDriver, emptyDriverInput, snapshotFromAnalysis } from "./driverCalculator";
import { DEFAULT_DRIVE_SETTINGS } from "../types/drive";
import { mockDriveAnalysis } from "../ipc/mocks";
import { ConfigStore } from "../stores/config.svelte";

describe("independent driver calculator", () => {
  const input = () => ({ ...emptyDriverInput(), resistanceOhm: 2, inductanceH: 100e-6, currentA: 1, busV: 12, pwmHz: 100e3 });
  it("uses the balanced-star RL screening equations", () => {
    const result = calculateDriver(input());
    expect(result.errors).toEqual([]);
    expect(result.rippleA).toBeCloseTo(12 / 4 * Math.tanh(2 / 40), 12);
    expect(result.holdingV).toBeCloseTo(Math.sqrt(3) * 2 + .21, 12);
    expect(result.copperW).toBe(3);
    expect(result.checks.find(c => c.label.startsWith("Trace ampacity"))?.status).toBe("unknown");
  });
  it("does not invent at-speed voltage without the motor constants", () => {
    expect(calculateDriver({ ...input(), speedMS: .5 }).speedV).toBeNull();
    const result = calculateDriver({ ...input(), speedMS: .5, forceConstant: 1.5, electricalPeriodM: .012 });
    expect(result.speedV).toBeCloseTo(Math.sqrt(3) * Math.hypot(2 + .5, 2 * Math.PI * .5 / .012 * 100e-6) + .21, 12);
  });
  it("rejects missing, negative, nonfinite and unsupported inputs without stale checks", () => {
    for (const values of [emptyDriverInput(), { ...input(), pwmHz: 0 }, { ...input(), resistanceOhm: NaN }, { ...input(), seriesInductanceH: -1 }, { ...input(), connection: "delta" as const }]) {
      const result = calculateDriver(values);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.checks).toEqual([]);
    }
  });
  it("copies the source driver instead of retaining mutable references", () => {
    const config = new ConfigStore();
    const drive = mockDriveAnalysis(config.toIpc(), DEFAULT_DRIVE_SETTINGS, null);
    const snapshot = snapshotFromAnalysis("Motor A", drive, DEFAULT_DRIVE_SETTINGS, .012, false, true);
    snapshot.input.driver.name = "Different driver";
    expect(DEFAULT_DRIVE_SETTINGS.driver.name).not.toBe("Different driver");
    expect(snapshot.input.resistanceOhm).toBe(drive.phase_resistance_ohm);
  });
});
