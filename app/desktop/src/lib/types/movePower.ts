/** Native prescribed-move model; SI units, PWM-cycle-averaged, not measurements. */
import type { DriveAnalysis, DriveSettings } from "./drive";
import type { LinearMotorConfig } from "./config";
import type { CadGeometry } from "./dxf";
import type { DeclaredLossModel, LossOperatingPoint, LossSample, LossEnergy } from "./moveLosses";

export interface MoveProfile {
  start_m: number;
  end_m: number;
  initial_velocity_m_s: number;
  final_velocity_m_s: number;
  duration_s: number;
  travel_min_m: number;
  travel_max_m: number;
  max_speed_m_s: number;
  max_acceleration_m_s2: number;
  max_deceleration_m_s2: number;
  moving_mass_kg: number;
  mass_includes: string;
  coulomb_friction_n: number;
  damping_n_s_per_m: number;
  external_load_n: number;
  time_step_s: number;
}

export interface RoutedMoveRequest {
  profile: MoveProfile;
  control: "balanced_star_sinusoidal" | "delta" | "phase_a_only";
  electrical_angle_at_zero_rad: number;
  phase_peak_limit_a: number;
  source: { boundary: "stiff_dc_link"; accepts_regeneration: boolean };
  additional_driver_loss_w: number | null;
  force_positions: number;
  loss_model?: DeclaredLossModel | null;
}

export interface MoveElectricalModel {
  winding: RoutedMoveRequest["control"];
  phase_resistance_hot_ohm: number;
  effective_phase_inductance_h: number;
  electrical_period_m: number;
  electrical_angle_at_zero_rad: number;
  force_map: { position_m: number; kf_n_per_a: number }[];
  phase_peak_limit_a: number;
  source_voltage_v: number;
  voltage_headroom: number;
  driver_path_resistance_ohm: number;
  additional_driver_loss_w: number | null;
  source_accepts_regeneration: boolean;
  loss_model?: DeclaredLossModel | null;
  loss_operating_point?: LossOperatingPoint | null;
  phase_model?: {
    phase_names: [string, string, string];
    resistance_hot_ohm: [number, number, number];
    inductance_h: number[][];
    force_map: { position_m: number; force_n_per_a: [number, number, number] }[];
  };
}

export interface MovePowerSample {
  time_s: number;
  position_m: number;
  velocity_m_s: number;
  acceleration_m_s2: number;
  motor_force_n: number;
  q_current_phase_peak_a: number;
  phase_currents_a: [number, number, number];
  required_q_voltage_v: number;
  required_d_voltage_v: number;
  required_line_voltage_v: number;
  required_phase_voltages_v: [number, number, number];
  mechanical_power_w: number;
  copper_loss_w: number;
  driver_conduction_loss_w: number;
  friction_damping_loss_w: number;
  external_load_power_w: number;
  kinetic_energy_j: number;
  magnetic_energy_j: number;
  magnetic_power_w: number;
  partial_dc_link_power_w: number;
  required_source_voltage_v: number;
  required_source_current_a: number | null;
  required_source_power_w: number | null;
  losses: LossSample | null;
}

export interface MovePowerResult {
  model_version: string;
  source_model_scope: "partial_declared_scenario" | "declared_loss_model";
  profile: MoveProfile;
  electrical: MoveElectricalModel;
  actual_time_step_s: number;
  feasible: boolean;
  limiting_factors: string[];
  missing_inputs: string[];
  requested_distance_m: number;
  sampled_requested_peak_speed_m_s: number;
  sampled_requested_positive_acceleration_m_s2: number;
  sampled_requested_negative_acceleration_m_s2: number;
  achieved_distance_m: number | null;
  sampled_phase_peak_a: number;
  phase_rms_a: [number, number, number];
  copper_energy_j: number;
  conduction_energy_j: number;
  mechanical_work_j: number;
  friction_damping_energy_j: number;
  external_load_work_j: number;
  kinetic_energy_change_j: number;
  magnetic_energy_change_j: number;
  capacitor_energy_change_j: number;
  mechanical_balance_residual_j: number;
  electrical_balance_residual_j: number;
  source_balance_residual_j: number | null;
  loss_energy: LossEnergy | null;
  accounted_loss_energy_j: number;
  phase_rms_including_declared_ripple_a: [number, number, number] | null;
  sampled_phase_peak_including_declared_ripple_a: number | null;
  source: {
    sampled_positive_peak_power_w: number;
    sampled_positive_peak_current_a: number;
    average_power_w: number;
    drawn_energy_j: number;
    returned_energy_j: number;
    net_energy_j: number;
  } | null;
  notes: string[];
  samples: MovePowerSample[];
}

export interface MovePowerInputs {
  topology: string;
  config: LinearMotorConfig;
  drive: DriveSettings;
  cad_geometry: CadGeometry | null;
  move_request: RoutedMoveRequest;
}

export interface NativeMoveResult {
  request_id: string;
  input_sha256: string;
  inputs: MovePowerInputs;
  provenance: "simulated_not_measured";
  result: {
    demand: MovePowerResult;
    drive: DriveAnalysis;
    full_overlap_bounds_m: [number, number];
    conductor_samples: number;
    force_map_step_m: number;
    meshing: number;
  };
}
