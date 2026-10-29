import { expect, it } from "vitest";
import { emptyLossTemplate, validateLossInputs } from "./moveLossInputs";
import { declaredLossFixture } from "./testFixtures/moveLosses";
import { emptyMoveTemplate, parseMoveRequest } from "./movePowerInputs";

it("inserts no guessed coefficients or implicit zero-loss declaration", () => {
  const template = emptyLossTemplate() as any;
  expect(template.basis).toBeNull();
  expect(template.ripple.covariance_a2[0]).toEqual([null, null, null]);
  expect(template.controller_power_w).toBeNull();
  expect(() => validateLossInputs(template)).toThrow("Choose loss_model.basis");
});

it("preserves declared coefficients and references without doing loss arithmetic in the client", () => {
  const model = declaredLossFixture();
  expect(validateLossInputs(model)).toEqual(model);
});

it("rejects missing terms, unknown laws, absent references and wrong array shapes", () => {
  for (const mutate of [(m: any) => { delete m.controller_power_w; },
    (m: any) => { m.ripple.reference = ""; }, (m: any) => { m.switching.invented_multiplier = 6; },
    (m: any) => { m.external_core_loss_w = [0, 0]; }, (m: any) => { m.ripple.covariance_a2 = [[0, 0, 0]]; }]) {
    const m = declaredLossFixture(); mutate(m);
    expect(() => validateLossInputs(m)).toThrow();
  }
});

it("legacy moves need no component declaration, and duplicate driver watts cannot be applied", () => {
  const move = JSON.parse(emptyMoveTemplate());
  expect(move).not.toHaveProperty("phase_peak_limit_a");
  expect(move.profile).not.toHaveProperty("max_speed_m_s");
  expect(move.profile).not.toHaveProperty("max_acceleration_m_s2");
  expect(move.profile).not.toHaveProperty("max_deceleration_m_s2");
  for (const key of Object.keys(move.profile)) if (key !== "mass_includes") move.profile[key] = 0;
  move.profile.mass_includes = "Numerical input-shape fixture only";
  Object.assign(move, { electrical_angle_at_zero_rad: 0, phase_peak_limit_a: 1, force_positions: 65 });
  move.source.accepts_regeneration = false;
  delete move.loss_model;
  expect(parseMoveRequest(JSON.stringify(move)).loss_model).toBeUndefined();
  move.loss_model = declaredLossFixture(); move.additional_driver_loss_w = 0;
  expect(() => parseMoveRequest(JSON.stringify(move))).toThrow("do not count driver losses twice");
  move.additional_driver_loss_w = null;
  expect(parseMoveRequest(JSON.stringify(move)).loss_model?.basis).toBe("declared_parameters");
});
