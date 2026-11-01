import { describe, expect, it } from "vitest";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { practicalMoveEstimate } from "./practicalMoveEstimate";
import { validateLossInputs } from "./moveLossInputs";
import { ConfigStore } from "./stores/config.svelte";
import { mockDriveAnalysis } from "./ipc/mocks";

const baselines = process.env.PCB_MOTOR_SCREENING_BASELINES;
const models = process.env.PCB_MOTOR_SCREENING_MODELS;
const designs = process.env.PCB_MOTOR_GENERATED_BRAID_AUDIT ? ["generated4"] : ["fader", "star2"];

describe("practical estimate declaration", () => {
  it.skipIf(!baselines || !process.env.PCB_MOTOR_ESTIMATE_OUTPUT)("exports declarations from the same frontend builder used by the UI", () => {
    const output = process.env.PCB_MOTOR_ESTIMATE_OUTPUT!;
    mkdirSync(output); // Exclusive new directory; preserve existing evidence.
    for (const design of designs) for (const scenario of ["full-forward", "short-forward", "short-return"]) {
      const filename = `${design}-${scenario}.json`;
      const native = JSON.parse(readFileSync(join(baselines!, filename), "utf8")).native;
      const model = practicalMoveEstimate(native.inputs.config, native.inputs.drive, native.result.drive);
      validateLossInputs(model);
      writeFileSync(join(output, filename), JSON.stringify(model, null, 2) + "\n", { flag: "wx" });
    }
  });

  it.skipIf(!baselines || !models)("matches the independently checked Python parameters for both unchanged saved designs", () => {
    for (const design of designs) {
      const file = `${design}-full-forward.json`;
      const receipt = JSON.parse(readFileSync(join(baselines!, file), "utf8"));
      const expected = JSON.parse(readFileSync(join(models!, file), "utf8"));
      const native = receipt.native;
      const model = practicalMoveEstimate(native.inputs.config, native.inputs.drive, native.result.drive);
      expect(validateLossInputs(model)).toEqual(model);
      expect(model.basis).toBe("engineering_estimate");
      expect(model.omitted_losses).toEqual(expected.omitted_losses);
      expect(model.phase_names).toEqual(expected.phase_names);
      for (const key of ["winding_fundamental_ac_increment_ohm", "winding_ripple_ac_increment_ohm",
        "external_series_resistance_ohm", "external_core_loss_w"] as const) {
        model[key].forEach((v, i) => expect(Math.abs(v - expected[key][i])).toBeLessThanOrEqual(1e-10 * Math.max(1e-15, Math.abs(expected[key][i]))));
      }
      for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++)
        expect(Math.abs(model.ripple.covariance_a2[i][j] - expected.ripple.covariance_a2[i][j])).toBeLessThan(1e-12);
      expect(model.switching.abs_mean_current_j_per_a).toBeCloseTo(expected.switching.abs_mean_current_j_per_a, 14);
      expect(model.deadtime.abs_mean_current_j_per_a).toBeCloseTo(expected.deadtime.abs_mean_current_j_per_a, 14);
      expect(model.controller_power_w).toBeCloseTo(expected.controller_power_w, 12);
      expect(() => practicalMoveEstimate({ ...native.inputs.config, supply_voltage_v: 24 }, native.inputs.drive, native.result.drive)).toThrow("12 V");
      expect(() => practicalMoveEstimate(native.inputs.config, { ...native.inputs.drive, pwm_hz: 200000 }, native.result.drive)).toThrow("100 kHz");
      expect(() => practicalMoveEstimate({ ...native.inputs.config, backplane: { layers: [], housing: { material: "aluminum6061", thickness_m: .001, gap_m: .001 } } }, native.inputs.drive, native.result.drive)).toThrow("no backplane");
    }
  });

  it("keeps an uncharacterised 64 µH inductance and lists its unknown losses", () => {
    const config = new ConfigStore();
    config.supply_voltage_v = 12;
    const settings = { ...config.drive, series_inductance_h: 64e-6 };
    const ipc = config.toIpc();
    const drive = mockDriveAnalysis(ipc, settings, null);
    expect(drive.effective_inductance_h).toBeGreaterThan(settings.series_inductance_h);
    const model = practicalMoveEstimate(ipc, settings, drive);
    expect(validateLossInputs(model)).toEqual(model);
    expect(model.basis).toBe("engineering_estimate");
    expect(model.domain.geometry?.effective_phase_inductance_h).toBeCloseTo(drive.effective_inductance_h, 15);
    // No component is invented for an arbitrary inductance: both terms stay
    // at zero and the omission keeps the total conditional.
    expect(model.external_series_resistance_ohm).toEqual([0, 0, 0]);
    expect(model.external_core_loss_w).toEqual([0, 0, 0]);
    expect(model.omitted_losses.join(" ")).toContain("64.000 µH");
    expect(model.reference).toContain("64.000 µH");
    expect(model.ripple.peak_deviation_a[0]).toBeGreaterThan(0);
  });
});
