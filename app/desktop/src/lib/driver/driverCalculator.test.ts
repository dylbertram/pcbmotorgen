import { describe, expect, it } from "vitest";
import { calculateDriver, emptyDriverInput, snapshotFromAnalysis } from "./driverCalculator";
import { DEFAULT_DRIVE_SETTINGS } from "../types/drive";
import { mockDriveAnalysis } from "../ipc/driveAnalysisMock";
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
  it("assesses open-circuit EMF without needing an electrical period", () => {
    const result = calculateDriver({ ...input(), speedMS: 2, forceConstant: 1.5 });
    expect(result.backEmfConstant).toBe(1);
    expect(result.backEmfSource).toBe("force constant");
    expect(result.phaseBackEmfV).toBe(2);
    expect(result.lineBackEmfV).toBeCloseTo(2 * Math.sqrt(3), 12);
    expect(result.lineBackEmfRmsV).toBeCloseTo(Math.sqrt(6), 12);
    expect(result.availableV).toBeCloseTo(10.2, 12);
    expect(result.backEmfMarginV).toBeCloseTo(10.2 - 2 * Math.sqrt(3), 12);
    expect(result.backEmfSpeedLimitMS).toBeCloseTo(10.2 / Math.sqrt(3), 12);
    expect(result.speedV).toBeNull();
    expect(result.voltageMarginV).toBeNull();
    expect(result.maxSpeedMS).toBeNull();
  });
  it("uses entered Ke for voltage, without fabricating a force constant", () => {
    const values = { ...input(), speedMS: .5, backEmfConstant: 2, electricalPeriodM: .012 };
    const result = calculateDriver(values);
    expect(result.backEmfSource).toBe("entered");
    expect(result.phaseBackEmfV).toBe(1);
    expect(result.forceN).toBeNull();
    expect(result.speedV).toBeCloseTo(Math.sqrt(3) * Math.hypot(3, 2 * Math.PI * .5 / .012 * 100e-6) + .21, 12);
    expect(calculateDriver({ ...values, forceConstant: 15 }).phaseBackEmfV).toBe(1);
    expect(calculateDriver({ ...values, forceConstant: 15, backEmfConstant: null }).phaseBackEmfV).toBe(5);
  });
  it("keeps loaded and back-EMF-only limits distinct and solves the loaded boundary", () => {
    const values = { ...input(), speedMS: 5, backEmfConstant: 1, electricalPeriodM: .012, seriesInductanceH: .001 };
    const result = calculateDriver(values);
    expect(result.checks.find(c => c.label.startsWith("Open-circuit"))?.status).toBe("pass");
    expect(result.checks.find(c => c.label === "Voltage at target speed")?.status).toBe("fail");
    expect(result.backEmfMarginV).toBeGreaterThan(0);
    expect(result.voltageMarginV).toBeLessThan(0);
    expect(result.maxSpeedMS).toBeLessThan(result.backEmfSpeedLimitMS!);
    const boundary = calculateDriver({ ...values, speedMS: result.maxSpeedMS! });
    expect(boundary.speedV).toBeCloseTo(boundary.availableV!, 10);
    expect(calculateDriver({ ...values, speedMS: result.maxSpeedMS! + .001 }).voltageMarginV).toBeLessThan(0);
    expect(calculateDriver({ ...values, seriesInductanceH: 0 }).maxSpeedMS).toBeGreaterThan(result.maxSpeedMS!);
    expect(calculateDriver({ ...values, headroom: .5 }).maxSpeedMS).toBeLessThan(result.maxSpeedMS!);
    expect(calculateDriver({ ...values, busV: 1 }).maxSpeedMS).toBe(0);
    expect(calculateDriver({ ...values, speedMS: 10 }).checks.find(c => c.label.startsWith("Open-circuit"))?.status).toBe("fail");
    const weakEmf = { ...values, backEmfConstant: 1e-30 };
    const weakLimit = calculateDriver(weakEmf).maxSpeedMS!;
    expect(weakLimit).toBeGreaterThan(0);
    expect(calculateDriver({ ...weakEmf, speedMS: weakLimit }).voltageMarginV).toBeCloseTo(0, 10);
  });
  it("does not invent a speed ceiling without Ke, including at standstill", () => {
    const stopped = calculateDriver(input());
    expect(stopped.phaseBackEmfV).toBe(0);
    expect(stopped.backEmfSource).toBe("unavailable");
    expect(stopped.backEmfSpeedLimitMS).toBeNull();
    expect(stopped.maxSpeedMS).toBeNull();
    const moving = calculateDriver({ ...input(), speedMS: 1 });
    expect(moving.backEmfMarginV).toBeNull();
    expect(moving.checks.find(c => c.label.startsWith("Open-circuit"))?.status).toBe("unknown");
  });
  it("rejects invalid Ke and suppresses the assessment for unsupported wiring", () => {
    for (const backEmfConstant of [0, -1, NaN, Infinity]) {
      const result = calculateDriver({ ...input(), backEmfConstant });
      expect(result.errors).toContain("Phase-peak back-EMF constant must be blank or positive.");
      expect(result.checks).toEqual([]);
      expect(result.backEmfMarginV).toBeUndefined();
    }
    for (const patch of [{ connection: "delta" as const }, { phaseCount: 2 }]) {
      const result = calculateDriver({ ...input(), backEmfConstant: 1, ...patch });
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.maxSpeedMS).toBeUndefined();
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
