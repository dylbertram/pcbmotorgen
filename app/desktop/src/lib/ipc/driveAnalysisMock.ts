import type { CheckStatus, DriveAnalysis, DriveSettings, LinearMotorConfig } from "../types";

/** Copper resistivity (Ω·m). */
const RHO = 1.72e-8;

/** Browser-only driver fixture. Its single-strand, two-layer geometry is not measured. */
export function mockDriveAnalysis(
  c: LinearMotorConfig,
  d: DriveSettings,
  kf: number | null,
): DriveAnalysis {
  const rho = RHO * (1 + 0.00393 * (d.winding_temp_c - 20));
  const length = c.active_area_length_m * (c.board_width_m / (c.magnet_pitch_m / 2)) * 2;
  const t = d.outer_copper_oz * 35e-6;
  const r = (rho * length) / (c.trace_width_m * t);
  const l = 2e-6;
  const lEff = l + Math.max(0, d.series_inductance_h);
  const i = c.max_current_a;
  const vBus = c.supply_voltage_v;
  const available = d.voltage_headroom * vBus;
  const ke = kf !== null ? (2 / 3) * kf : null;
  const pe = 2 * c.magnet_pitch_m;
  const required = (v: number) =>
    Math.sqrt(3) * Math.hypot(i * r + (ke ?? 0) * v, ((2 * Math.PI * v) / pe) * lEff * i) + i * d.driver.rds_on_ohm;
  const ripple = r > 1e-12 ? vBus / (2 * r) * Math.tanh(r / (4 * d.pwm_hz * lEff)) : vBus / (8 * d.pwm_hz * lEff);
  const rippleLimit = d.ripple_limit_fraction * i;
  const requiredFL = rippleLimit <= 0 || vBus <= 0 ? Infinity
    : r <= 1e-12 ? vBus / (8 * rippleLimit)
    : 2 * r * rippleLimit >= vBus ? 0
    : r / (4 * Math.atanh(2 * r * rippleLimit / vBus));
  const ampacity = 0.048 * d.allowed_rise_c ** 0.44 * ((c.trace_width_m / 25.4e-6) * (t / 25.4e-6)) ** 0.725;
  const vLimitedI = available / (Math.sqrt(3) * r + d.driver.rds_on_ohm);
  const maxCont = Math.min(d.driver.continuous_rms_a, ampacity, vLimitedI);
  const st = (ok: boolean, warn: boolean): CheckStatus => (ok ? "pass" : warn ? "warn" : "fail");
  const check = (id: string, label: string, status: CheckStatus, value: number, limit: number, unit: string) =>
    ({ id, label, status, value, limit, unit, detail: "Mock value: backend not connected." });
  const hold = required(0);
  const atSpeed = ke !== null ? required(d.target_speed_m_s) : null;
  return {
    driver_name: d.driver.name,
    phases: ["A", "B", "C"].slice(0, c.phases).map((net) => ({
      net,
      strands: 1,
      layers: [0, 1],
      strand_length_m: length,
      total_length_m: length,
      active_length_m: length * 0.8,
      vias_per_strand: 0,
      vias_total: 0,
      resistance_20c_ohm: (r * RHO) / rho,
      resistance_hot_ohm: r,
      via_resistance_ohm: 0,
      self_inductance_h: l,
      max_trace_share: 1,
      connected: true,
    })),
    trace_width_m: c.trace_width_m,
    outer_copper_m: t,
    inner_copper_m: d.inner_copper_oz * 35e-6,
    via_resistance_each_ohm: 0.0015,
    phase_resistance_ohm: r,
    phase_inductance_h: l,
    mutual_inductance_h: 0,
    line_inductance_h: 2 * l,
    synchronous_inductance_h: l,
    series_inductance_h: Math.max(0, d.series_inductance_h),
    effective_inductance_h: lEff,
    line_resistance_ohm: 2 * r,
    time_constant_s: lEff / r,
    bus_voltage_v: vBus,
    phase_current_a: i,
    pwm_hz: d.pwm_hz,
    target_speed_m_s: d.target_speed_m_s,
    thrust_constant_n_per_a: kf,
    back_emf_constant_v_s_per_m: ke,
    holding_voltage_v: hold,
    speed_voltage_v: atSpeed,
    available_voltage_v: available,
    voltage_limited_current_a: vLimitedI,
    max_speed_m_s: ke !== null ? Math.max(0, (available / Math.sqrt(3) - i * r) / Math.max(ke, 1e-9)) : null,
    ripple_pp_a: ripple,
    min_pwm_hz: requiredFL / lEff,
    added_inductance_h: Math.max(0, requiredFL / d.pwm_hz - lEff),
    peak_current_a: i + ripple / 2,
    trace_ampacity_a: ampacity,
    copper_loss_w: 1.5 * i * i * r,
    thrust_n: kf !== null ? kf * i : null,
    max_continuous_current_a: maxCont,
    limiting_factor: "mock",
    max_continuous_thrust_n: kf !== null ? kf * maxCont : null,
    checks: [
      check("supply", "Bus voltage within driver rating", st(vBus >= d.driver.min_supply_v && vBus <= d.driver.max_supply_v, false), vBus, d.driver.max_supply_v, "V"),
      check("holding_voltage", "Voltage to hold the phase current", st(hold <= available, hold <= vBus), hold, available, "V"),
      check("ripple", "PWM current ripple estimate (50% duty)", st(ripple <= rippleLimit, ripple <= i), ripple, rippleLimit, "A"),
      check("ampacity", "Trace ampacity", st(i <= ampacity, i <= 1.25 * ampacity), i, ampacity, "A"),
    ],
    speed_curve: Array.from({ length: 41 }, (_, k) => {
      const v = (Math.max(d.target_speed_m_s, 0.1) * 1.4 * k) / 40;
      return { speed_m_s: v, required_v: required(v) };
    }),
    notes: ["Mock analysis: backend not connected, geometry not measured."],
  };
}
