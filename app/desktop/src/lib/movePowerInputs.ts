import type { MoveProfile, RoutedMoveRequest } from "./types/movePower";
import { validateLossInputs } from "./moveLossInputs";

const numericProfileFields: (keyof MoveProfile)[] = ["start_m", "end_m", "initial_velocity_m_s", "final_velocity_m_s",
  "duration_s", "travel_min_m", "travel_max_m", "max_speed_m_s", "max_acceleration_m_s2", "max_deceleration_m_s2",
  "moving_mass_kg", "coulomb_friction_n", "damping_n_s_per_m", "external_load_n", "time_step_s"];

/** Deliberately incomplete. Opening an old file must not invent a move. */
export function emptyMoveTemplate(): string {
  return JSON.stringify({ profile: { ...Object.fromEntries(numericProfileFields.map(k => [k, null])), mass_includes: "" },
    control: "balanced_star_sinusoidal", electrical_angle_at_zero_rad: null, phase_peak_limit_a: null,
    source: { boundary: "stiff_dc_link", accepts_regeneration: null },
    additional_driver_loss_w: null, loss_model: null, force_positions: null }, null, 2);
}

/** Shape checking only. Physical validation and all arithmetic remain native. */
export function parseMoveRequest(text: string): RoutedMoveRequest {
  const v = JSON.parse(text);
  if (!v || typeof v !== "object" || !v.profile || typeof v.profile !== "object")
    throw new Error("Add a profile object with explicit move and load inputs.");
  for (const [object, allowed, path] of [
    [v, ["profile", "control", "electrical_angle_at_zero_rad", "phase_peak_limit_a", "source", "additional_driver_loss_w", "loss_model", "force_positions"], "move"],
    [v.profile, [...numericProfileFields, "mass_includes"], "profile"],
    [v.source ?? {}, ["boundary", "accepts_regeneration"], "source"],
  ] as const) {
    for (const key of Object.keys(object)) if (!(allowed as readonly string[]).includes(key))
      throw new Error(`Unsupported ${path}.${key}. It would not be applied by this model.`);
  }
  for (const key of numericProfileFields) {
    if (typeof v.profile[key] !== "number" || !Number.isFinite(v.profile[key]))
      throw new Error(`Set profile.${key} to a finite number. Its name states the SI unit.`);
  }
  if (typeof v.profile.mass_includes !== "string" || !v.profile.mass_includes.trim())
    throw new Error("State which moving parts and cap are included in profile.mass_includes.");
  if (v.control !== "balanced_star_sinusoidal") throw new Error("Only balanced_star_sinusoidal move control is supported.");
  for (const key of ["electrical_angle_at_zero_rad", "phase_peak_limit_a", "force_positions"]) {
    if (typeof v[key] !== "number" || !Number.isFinite(v[key])) throw new Error(`Set ${key} explicitly.`);
  }
  if (!Number.isInteger(v.force_positions)) throw new Error("force_positions must be an integer.");
  if (v.source?.boundary !== "stiff_dc_link" || typeof v.source?.accepts_regeneration !== "boolean")
    throw new Error("Declare the stiff_dc_link source and set accepts_regeneration to true or false.");
  if (v.additional_driver_loss_w !== null && (typeof v.additional_driver_loss_w !== "number" || !Number.isFinite(v.additional_driver_loss_w)))
    throw new Error("Set additional_driver_loss_w to a declared constant loss in W, or null for Unknown.");
  if (v.loss_model != null) {
    validateLossInputs(v.loss_model);
    if (v.additional_driver_loss_w !== null) throw new Error("Set additional_driver_loss_w to null when using loss_model; do not count driver losses twice.");
  }
  return v as RoutedMoveRequest;
}
