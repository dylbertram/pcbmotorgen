import type { DeclaredLossModel } from "../types/moveLosses";

function requireObject(value: unknown, keys: readonly string[], path: string, optional: readonly string[] = []): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`Set ${path} to an object.`);
  const v = value as Record<string, unknown>;
  for (const key of Object.keys(v)) if (!keys.includes(key) && !optional.includes(key)) throw new Error(`Unsupported ${path}.${key}; it would not be applied.`);
  for (const key of keys) if (!(key in v)) throw new Error(`Set ${path}.${key} explicitly; unknown losses are not zero.`);
  return v;
}

function requireFiniteNumber(value: unknown, path: string): void {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`Set ${path} to a finite number, or keep loss_model null.`);
}

function requireNonEmptyText(value: unknown, path: string): void {
  if (typeof value !== "string" || !value.trim()) throw new Error(`Provide ${path}; a declaration needs its reference and applicability.`);
}

function requirePhaseValues(value: unknown, path: string): void {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`Set ${path} to three values in native phase order.`);
  value.forEach((v, i) => requireFiniteNumber(v, `${path}[${i}]`));
}

/** Check fixture shape only; passivity, domain matching and arithmetic are native. */
export function validateDeclaredLossShape(value: unknown): DeclaredLossModel {
  const keys = ["basis", "reference", "domain", "phase_names", "winding_fundamental_ac_increment_ohm",
    "winding_ripple_ac_increment_ohm", "external_series_resistance_ohm", "external_core_loss_w", "ripple",
    "switching", "deadtime", "controller_power_w", "other_dc_link_power_w", "omitted_losses"];
  const v = requireObject(value, keys, "loss_model");
  if (v.basis !== "declared_parameters" && v.basis !== "idealized" && v.basis !== "engineering_estimate")
    throw new Error("Choose loss_model.basis as declared_parameters, engineering_estimate or idealized. None claims measured results or a bound.");
  requireNonEmptyText(v.reference, "loss_model.reference");
  const d = requireObject(v.domain, ["driver_name", "source_voltage_v", "pwm_hz", "winding_temp_c",
    "driver_path_resistance_ohm", "max_phase_peak_a", "max_speed_m_s"], "loss_model.domain", ["geometry"]);
  requireNonEmptyText(d.driver_name, "loss_model.domain.driver_name");
  for (const [key, value] of Object.entries(d)) if (key !== "driver_name" && key !== "geometry") requireFiniteNumber(value, `loss_model.domain.${key}`);
  if (v.basis === "engineering_estimate" && d.geometry == null) throw new Error("Engineering estimates require loss_model.domain.geometry.");
  if (d.geometry != null) {
    const g = requireObject(d.geometry, ["phase_resistance_hot_ohm", "effective_phase_inductance_h", "copper_thickness_m", "electrical_period_m"], "loss_model.domain.geometry");
    requirePhaseValues(g.phase_resistance_hot_ohm, "loss_model.domain.geometry.phase_resistance_hot_ohm");
    for (const key of ["effective_phase_inductance_h", "copper_thickness_m", "electrical_period_m"]) requireFiniteNumber(g[key], `loss_model.domain.geometry.${key}`);
  }
  if (!Array.isArray(v.phase_names) || v.phase_names.length !== 3) throw new Error("Declare all three loss_model.phase_names in native phase order.");
  v.phase_names.forEach((name, i) => requireNonEmptyText(name, `loss_model.phase_names[${i}]`));
  for (const key of ["winding_fundamental_ac_increment_ohm", "winding_ripple_ac_increment_ohm", "external_series_resistance_ohm", "external_core_loss_w"])
    requirePhaseValues(v[key], `loss_model.${key}`);
  const ripple = requireObject(v.ripple, ["covariance_a2", "peak_deviation_a", "reference"], "loss_model.ripple");
  requireNonEmptyText(ripple.reference, "loss_model.ripple.reference"); requirePhaseValues(ripple.peak_deviation_a, "loss_model.ripple.peak_deviation_a");
  if (!Array.isArray(ripple.covariance_a2) || ripple.covariance_a2.length !== 3) throw new Error("Declare the three-by-three loss_model.ripple.covariance_a2 matrix.");
  ripple.covariance_a2.forEach((row, i) => requirePhaseValues(row, `loss_model.ripple.covariance_a2[${i}]`));
  for (const key of ["switching", "deadtime"]) {
    const law = requireObject(v[key], ["constant_j", "abs_mean_current_j_per_a", "mean_square_current_j_per_a2"], `loss_model.${key}`);
    for (const [name, value] of Object.entries(law)) requireFiniteNumber(value, `loss_model.${key}.${name}`);
  }
  requireFiniteNumber(v.controller_power_w, "loss_model.controller_power_w"); requireFiniteNumber(v.other_dc_link_power_w, "loss_model.other_dc_link_power_w");
  if (!Array.isArray(v.omitted_losses)) throw new Error("List loss_model.omitted_losses explicitly. A nonempty list keeps totals Unknown.");
  v.omitted_losses.forEach((s, i) => requireNonEmptyText(s, `loss_model.omitted_losses[${i}]`));
  return value as DeclaredLossModel;
}
