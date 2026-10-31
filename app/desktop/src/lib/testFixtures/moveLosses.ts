/** Numerical test declarations only. Never a production driver/material preset. */
import type { DeclaredLossModel } from "../types/moveLosses";

export function declaredLossFixture(driverName = "Analytic fixture only", driverPathOhm = 0.21): DeclaredLossModel {
  return {
    basis: "declared_parameters", reference: "Numerical test inputs, not measured driver or material data",
    domain: { driver_name: driverName, source_voltage_v: 12, pwm_hz: 100000, winding_temp_c: 75,
      driver_path_resistance_ohm: driverPathOhm, max_phase_peak_a: 5, max_speed_m_s: 1 },
    phase_names: ["A", "B", "C"], winding_fundamental_ac_increment_ohm: [0.01, 0.02, 0.03],
    winding_ripple_ac_increment_ohm: [0.1, 0.2, 0.3], external_series_resistance_ohm: [0.05, 0.05, 0.05],
    external_core_loss_w: [0.001, 0.002, 0.003],
    ripple: { covariance_a2: [[0.0001, -0.00005, -0.00005], [-0.00005, 0.0001, -0.00005], [-0.00005, -0.00005, 0.0001]],
      peak_deviation_a: [0.02, 0.02, 0.02], reference: "Analytic covariance, not a generated switching waveform" },
    switching: { constant_j: 1e-7, abs_mean_current_j_per_a: 2e-8, mean_square_current_j_per_a2: 1e-9 },
    deadtime: { constant_j: 2e-8, abs_mean_current_j_per_a: 1e-8, mean_square_current_j_per_a2: 0 },
    controller_power_w: 0.02, other_dc_link_power_w: 0.03, omitted_losses: [],
  };
}
