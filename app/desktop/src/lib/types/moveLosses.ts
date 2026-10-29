/** Supplied cycle-average loss laws, not generated PWM or measured results. */
export type PhaseValues = [number, number, number];
export type PhaseMatrix = [PhaseValues, PhaseValues, PhaseValues];

export interface LossOperatingPoint {
  driver_name: string;
  pwm_hz: number;
  winding_temp_c: number;
  copper_thickness_m?: number | null;
}

export interface LossDomain extends LossOperatingPoint {
  source_voltage_v: number;
  driver_path_resistance_ohm: number;
  max_phase_peak_a: number;
  max_speed_m_s: number;
  geometry?: { phase_resistance_hot_ohm: PhaseValues; effective_phase_inductance_h: number;
    copper_thickness_m: number; electrical_period_m: number } | null;
}

/** Whole-inverter joules per configured PWM cycle, not per FET or edge. */
export interface CycleLossLaw {
  constant_j: number;
  abs_mean_current_j_per_a: number;
  mean_square_current_j_per_a2: number;
}

export interface DeclaredLossModel {
  basis: "declared_parameters" | "idealized" | "engineering_estimate";
  reference: string;
  domain: LossDomain;
  phase_names: [string, string, string];
  winding_fundamental_ac_increment_ohm: PhaseValues;
  winding_ripple_ac_increment_ohm: PhaseValues;
  external_series_resistance_ohm: PhaseValues;
  external_core_loss_w: PhaseValues;
  ripple: { covariance_a2: PhaseMatrix; peak_deviation_a: PhaseValues; reference: string };
  switching: CycleLossLaw;
  deadtime: CycleLossLaw;
  controller_power_w: number;
  other_dc_link_power_w: number;
  omitted_losses: string[];
}

export interface LossSample {
  mean_square_phase_current_a2: PhaseValues;
  phase_peak_envelope_a: PhaseValues;
  winding_dc_ripple_loss_w: number;
  winding_ac_loss_w: number;
  external_series_loss_w: number;
  external_core_loss_w: number;
  switching_loss_w: number;
  deadtime_loss_w: number;
  controller_loss_w: number;
  other_dc_link_loss_w: number;
}

export interface LossEnergy {
  winding_dc_ripple_energy_j: number;
  winding_ac_energy_j: number;
  external_series_energy_j: number;
  external_core_energy_j: number;
  switching_energy_j: number;
  deadtime_energy_j: number;
  controller_energy_j: number;
  other_dc_link_energy_j: number;
}
