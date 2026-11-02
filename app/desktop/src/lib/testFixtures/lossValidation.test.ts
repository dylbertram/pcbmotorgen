import { expect, it } from "vitest";
import { validateDeclaredLossShape } from "./lossValidation";
import { declaredLossFixture } from "./moveLosses";

it("preserves declared coefficients and references without doing loss arithmetic in the client", () => {
  const model = declaredLossFixture();
  expect(validateDeclaredLossShape(model)).toEqual(model);
});

it("requires a complete geometry binding for engineering estimates without changing legacy models", () => {
  const model = declaredLossFixture();
  model.basis = "engineering_estimate";
  expect(() => validateDeclaredLossShape(model)).toThrow("geometry");
  model.domain.geometry = { phase_resistance_hot_ohm: [1, 2, 3], effective_phase_inductance_h: 0.001,
    copper_thickness_m: 0.000035, electrical_period_m: 0.01 };
  expect(validateDeclaredLossShape(model)).toEqual(model);
  expect(() => validateDeclaredLossShape({ ...model, domain: { ...model.domain, geometry: { ...model.domain.geometry, unexpected: 1 } } })).toThrow("Unsupported");
  expect(() => validateDeclaredLossShape({ ...model, domain: { ...model.domain, geometry: { ...model.domain.geometry, phase_resistance_hot_ohm: [1, 2] } } })).toThrow("three values");
});

it("rejects missing terms, unknown laws, absent references and wrong array shapes", () => {
  for (const mutate of [(m: any) => { delete m.controller_power_w; },
    (m: any) => { m.ripple.reference = ""; }, (m: any) => { m.switching.invented_multiplier = 6; },
    (m: any) => { m.external_core_loss_w = [0, 0]; }, (m: any) => { m.ripple.covariance_a2 = [[0, 0, 0]]; }]) {
    const m = declaredLossFixture(); mutate(m);
    expect(() => validateDeclaredLossShape(m)).toThrow();
  }
});
