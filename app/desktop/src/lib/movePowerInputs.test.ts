import { expect, it } from "vitest";
import { emptyMoveTemplate, parseMoveRequest } from "./movePowerInputs";

it("requires explicit quantities, mass coverage and regeneration choice, not null-to-zero defaults", () => {
  const draft = JSON.parse(emptyMoveTemplate());
  expect(() => parseMoveRequest(JSON.stringify(draft))).toThrow("finite number");
  for (const key of Object.keys(draft.profile)) if (key !== "mass_includes") draft.profile[key] = 0;
  expect(() => parseMoveRequest(JSON.stringify(draft))).toThrow("moving parts");
  draft.profile.mass_includes = "Explicit test assembly";
  draft.electrical_angle_at_zero_rad = 0;
  draft.phase_peak_limit_a = 1;
  draft.force_positions = 65;
  expect(() => parseMoveRequest(JSON.stringify(draft))).toThrow("accepts_regeneration");
  draft.source.accepts_regeneration = false;
  const parsed = parseMoveRequest(JSON.stringify(draft));
  expect(parsed.additional_driver_loss_w).toBeNull();
  expect(parsed.profile.external_load_n).toBe(0);
  draft.profile.peak_duration_s = 1;
  expect(() => parseMoveRequest(JSON.stringify(draft))).toThrow("Unsupported profile.peak_duration_s");
  delete draft.profile.peak_duration_s;
  draft.control = "delta";
  expect(() => parseMoveRequest(JSON.stringify(draft))).toThrow("Only balanced_star");
});
