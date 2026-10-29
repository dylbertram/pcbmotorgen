import type { DeclaredLossModel } from "./types/moveLosses";

/** Incomplete on purpose. No unknown loss is converted to zero by this editor. */
export function emptyLossTemplate(): object {
  const phase = () => [null, null, null];
  const law = () => ({ constant_j: null, abs_mean_current_j_per_a: null, mean_square_current_j_per_a2: null });
  return {
    basis: null, reference: "", phase_names: [null, null, null],
    domain: { driver_name: "", source_voltage_v: null, pwm_hz: null, winding_temp_c: null,
      driver_path_resistance_ohm: null, max_phase_peak_a: null, max_speed_m_s: null },
    winding_fundamental_ac_increment_ohm: phase(), winding_ripple_ac_increment_ohm: phase(),
    external_series_resistance_ohm: phase(), external_core_loss_w: phase(),
    ripple: { covariance_a2: [phase(), phase(), phase()], peak_deviation_a: phase(), reference: "" },
    switching: law(), deadtime: law(), controller_power_w: null, other_dc_link_power_w: null, omitted_losses: [],
  };
}

function object(value: unknown, keys: readonly string[], path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`Set ${path} to an object.`);
  const v = value as Record<string, unknown>;
  for (const key of Object.keys(v)) if (!keys.includes(key)) throw new Error(`Unsupported ${path}.${key}; it would not be applied.`);
  for (const key of keys) if (!(key in v)) throw new Error(`Set ${path}.${key} explicitly; unknown losses are not zero.`);
  return v;
}

function number(value: unknown, path: string): void {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`Set ${path} to a finite number, or keep loss_model null.`);
}

function text(value: unknown, path: string): void {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Provide ${path}; a declaration needs its reference and applicability.`);
}

function phases(value: unknown, path: string): void {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`Set ${path} to three values in native phase order.`);
  value.forEach((v, i) => number(v, `${path}[${i}]`));
}

/** Shape checking only. Passivity, domain matching and all arithmetic are native. */
export function validateLossInputs(value: unknown): DeclaredLossModel {
  const keys = ["basis", "reference", "domain", "phase_names", "winding_fundamental_ac_increment_ohm",
    "winding_ripple_ac_increment_ohm", "external_series_resistance_ohm", "external_core_loss_w", "ripple",
    "switching", "deadtime", "controller_power_w", "other_dc_link_power_w", "omitted_losses"];
  const v = object(value, keys, "loss_model");
  if (v.basis !== "declared_parameters" && v.basis !== "idealized")
    throw new Error("Choose loss_model.basis as declared_parameters or idealized. Neither claims measured results or a bound.");
  text(v.reference, "loss_model.reference");
  const d = object(v.domain, ["driver_name", "source_voltage_v", "pwm_hz", "winding_temp_c",
    "driver_path_resistance_ohm", "max_phase_peak_a", "max_speed_m_s"], "loss_model.domain");
  text(d.driver_name, "loss_model.domain.driver_name");
  for (const [key, value] of Object.entries(d)) if (key !== "driver_name") number(value, `loss_model.domain.${key}`);
  if (!Array.isArray(v.phase_names) || v.phase_names.length !== 3) throw new Error("Declare all three loss_model.phase_names in native phase order.");
  v.phase_names.forEach((name, i) => text(name, `loss_model.phase_names[${i}]`));
  for (const key of ["winding_fundamental_ac_increment_ohm", "winding_ripple_ac_increment_ohm", "external_series_resistance_ohm", "external_core_loss_w"])
    phases(v[key], `loss_model.${key}`);
  const ripple = object(v.ripple, ["covariance_a2", "peak_deviation_a", "reference"], "loss_model.ripple");
  text(ripple.reference, "loss_model.ripple.reference"); phases(ripple.peak_deviation_a, "loss_model.ripple.peak_deviation_a");
  if (!Array.isArray(ripple.covariance_a2) || ripple.covariance_a2.length !== 3) throw new Error("Declare the three-by-three loss_model.ripple.covariance_a2 matrix.");
  ripple.covariance_a2.forEach((row, i) => phases(row, `loss_model.ripple.covariance_a2[${i}]`));
  for (const key of ["switching", "deadtime"]) {
    const law = object(v[key], ["constant_j", "abs_mean_current_j_per_a", "mean_square_current_j_per_a2"], `loss_model.${key}`);
    for (const [name, value] of Object.entries(law)) number(value, `loss_model.${key}.${name}`);
  }
  number(v.controller_power_w, "loss_model.controller_power_w"); number(v.other_dc_link_power_w, "loss_model.other_dc_link_power_w");
  if (!Array.isArray(v.omitted_losses)) throw new Error("List loss_model.omitted_losses explicitly. A nonempty list keeps totals Unknown.");
  v.omitted_losses.forEach((s, i) => text(s, `loss_model.omitted_losses[${i}]`));
  return value as DeclaredLossModel;
}
