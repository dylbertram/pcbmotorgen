/**
 * Driver suitability analysis (analyze_drive). Mirrors
 * `pcbmotorgen_simulation::drive` field-for-field; SI units on the wire.
 */

/** Datasheet limits of one three-phase driver IC. */
export interface DriverSpec {
  name: string;
  /** Confirmed built-in driver/controller delta handling. Absent means unconfirmed. */
  supports_delta?: boolean;
  min_supply_v: number;
  max_supply_v: number;
  /** Peak output / overcurrent trip [A]. */
  peak_current_a: number;
  /** Continuous RMS output per phase [A]. */
  continuous_rms_a: number;
  /** High side + low side on-resistance in the current path [Ω]. */
  rds_on_ohm: number;
  max_pwm_hz: number;
}

/** Operating point and board assumptions for the analysis. */
export interface DriveSettings {
  driver: DriverSpec;
  pwm_hz: number;
  target_speed_m_s: number;
  outer_copper_oz: number;
  inner_copper_oz: number;
  via_plating_m: number;
  winding_temp_c: number;
  allowed_rise_c: number;
  ripple_limit_fraction: number;
  voltage_headroom: number;
  /** External series inductance per phase at the driver terminals [H]. */
  series_inductance_h: number;
  /** Opt-in established steady travel; starts/stops are not represented. */
  housing_motion?: { duration_s: number } | null;
}

export interface HousingMotionEstimate {
  method: string;
  housing_material: import("./backplane").HousingMaterial;
  speed_m_s: number;
  duration_s: number;
  equivalent_travel_m: number;
  housing_drag_n: number;
  signed_housing_drag_n: number;
  housing_joule_power_w: number;
  housing_energy_j: number;
  layer_joule_power_w: number[];
  total_stack_joule_power_w: number;
  total_stack_drag_n: number;
  power_balance_relative_error: number;
  quadrature_relative_change: number;
  quadrature_samples: number;
  warnings: string[];
}

export type HousingMotionAnalysis =
  | { status: "experimental"; estimate: HousingMotionEstimate }
  | { status: "unavailable"; reason: string };

export interface PhaseElectrical {
  net: string;
  strands: number;
  layers: number[];
  strand_length_m: number;
  total_length_m: number;
  active_length_m: number;
  vias_per_strand: number;
  vias_total: number;
  resistance_20c_ohm: number;
  resistance_hot_ohm: number;
  via_resistance_ohm: number;
  self_inductance_h: number;
  max_trace_share: number;
  connected: boolean;
}

export type CheckStatus = "pass" | "warn" | "fail" | "unknown";

export interface DriveCheck {
  id: string;
  label: string;
  status: CheckStatus;
  value: number;
  limit: number;
  unit: string;
  detail: string;
}

export interface SpeedVoltagePoint {
  speed_m_s: number;
  required_v: number;
}

/** Eddy drag and normal force at one mover speed. */
export interface DragPoint {
  speed_m_s: number;
  drag_n: number;
  normal_n: number;
}

/** Backplane and housing at the operating point (`DriveBackplane`). */
export interface DriveBackplane {
  housing_motion?: HousingMotionAnalysis | null;
  /** Low-frequency inductance factor, with the magnets' bias. */
  inductance_factor: number;
  /** Inductance factor at the PWM frequency, eddy currents included. */
  pwm_inductance_factor: number;
  /** Per-phase inductance at the PWM frequency plus series [H]; used by the ripple check. */
  pwm_inductance_h: number;
  /** Series resistance per phase added by eddy currents at the PWM frequency [Ω]. */
  pwm_resistance_ohm: number;
  /** Eddy loss in the backplane and housing from the PWM ripple [W]. */
  ripple_eddy_loss_w: number;
  /** Eddy drag at the target speed [N], opposing motion. */
  drag_n: number;
  normal_force_n: number;
  drag_power_w: number;
  /** Mean thrust minus drag at the target speed [N]. */
  net_thrust_n?: number | null;
  /** Lowest speed at which drag reaches the full-current thrust [m/s]. */
  drag_limited_speed_m_s?: number | null;
  drag_curve: DragPoint[];
}

export interface DriveAnalysis {
  driver_name: string;
  phases: PhaseElectrical[];
  trace_width_m: number;
  outer_copper_m: number;
  inner_copper_m: number;
  via_resistance_each_ohm: number;
  phase_resistance_ohm: number;
  phase_inductance_h: number;
  mutual_inductance_h: number;
  line_inductance_h: number;
  synchronous_inductance_h: number;
  /** External series inductance per phase defined at the terminals [H]. */
  series_inductance_h: number;
  /** Copper + external per-phase inductance the checks use [H]. */
  effective_inductance_h: number;
  line_resistance_ohm: number;
  time_constant_s: number;
  bus_voltage_v: number;
  phase_current_a: number;
  pwm_hz: number;
  target_speed_m_s: number;
  thrust_constant_n_per_a: number | null;
  back_emf_constant_v_s_per_m: number | null;
  holding_voltage_v: number;
  speed_voltage_v: number | null;
  available_voltage_v: number;
  voltage_limited_current_a: number;
  max_speed_m_s: number | null;
  ripple_pp_a: number;
  min_pwm_hz: number;
  added_inductance_h: number;
  peak_current_a: number;
  trace_ampacity_a: number;
  copper_loss_w: number;
  thrust_n: number | null;
  max_continuous_current_a: number;
  limiting_factor: string;
  max_continuous_thrust_n: number | null;
  checks: DriveCheck[];
  speed_curve: SpeedVoltagePoint[];
  notes: string[];
  /** Absent without a backplane. */
  backplane?: DriveBackplane | null;
}

/**
 * Driver presets. Typical datasheet values: check them against the revision
 * you design with. Additional parts can be added from the Simulation tab.
 */
export const DRIVER_PRESETS: DriverSpec[] = [
  {
    name: "DRV8311",
    supports_delta: false,
    min_supply_v: 3,
    max_supply_v: 20,
    peak_current_a: 5,
    continuous_rms_a: 1.5,
    rds_on_ohm: 0.21,
    max_pwm_hz: 200e3,
  },
  {
    name: "DRV8316",
    supports_delta: false,
    min_supply_v: 4.5,
    max_supply_v: 35,
    peak_current_a: 8,
    continuous_rms_a: 3,
    rds_on_ohm: 0.19,
    max_pwm_hz: 200e3,
  },
  {
    name: "DRV8313",
    supports_delta: false,
    min_supply_v: 8,
    max_supply_v: 60,
    peak_current_a: 2.5,
    continuous_rms_a: 1.75,
    rds_on_ohm: 0.48,
    max_pwm_hz: 250e3,
  },
];

export const DEFAULT_DRIVE_SETTINGS: DriveSettings = {
  driver: { ...DRIVER_PRESETS[0] },
  pwm_hz: 100e3,
  target_speed_m_s: 0.5,
  outer_copper_oz: 1,
  inner_copper_oz: 1,
  via_plating_m: 25e-6,
  winding_temp_c: 75,
  allowed_rise_c: 20,
  ripple_limit_fraction: 0.3,
  voltage_headroom: 0.85,
  series_inductance_h: 0,
};
