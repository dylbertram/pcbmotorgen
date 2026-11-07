import { DEFAULT_DRIVE_SETTINGS, type DriverSpec, type DriveAnalysis, type DriveSettings } from "../types/drive";

export interface DriverCalculatorInput {
  driver: DriverSpec;
  phaseCount: number;
  resistanceOhm: number | null;
  inductanceH: number | null;
  seriesInductanceH: number | null;
  currentA: number | null;
  busV: number | null;
  pwmHz: number | null;
  speedMS: number | null;
  forceConstant: number | null;
  /** Optional measured phase-to-neutral peak volts per m/s; overrides 2 Kf / 3. */
  backEmfConstant?: number | null;
  electricalPeriodM: number | null;
  ampacityA: number | null;
  headroom: number | null;
  rippleFraction: number | null;
  connection: "star" | "delta";
}
export interface DriverCalculatorSnapshot {
  source: string;
  capturedAt: string;
  native: boolean;
  input: DriverCalculatorInput;
  notes: string[];
}
export function emptyDriverInput(): DriverCalculatorInput {
  return {
    driver: structuredClone(DEFAULT_DRIVE_SETTINGS.driver), phaseCount: 3, resistanceOhm: null, inductanceH: null,
    seriesInductanceH: 0, currentA: 1, busV: 12, pwmHz: 100e3, speedMS: 0,
    forceConstant: null, backEmfConstant: null, electricalPeriodM: null, ampacityA: null,
    headroom: .85, rippleFraction: .3, connection: "star",
  };
}
export function snapshotFromAnalysis(source: string, analysis: DriveAnalysis, settings: DriveSettings, period: number, delta: boolean, native: boolean): DriverCalculatorSnapshot {
  return {
    source, capturedAt: new Date().toISOString(), native,
    input: {
      driver: { ...settings.driver }, phaseCount: analysis.phases.length, resistanceOhm: analysis.phase_resistance_ohm,
      inductanceH: analysis.synchronous_inductance_h, seriesInductanceH: analysis.series_inductance_h,
      currentA: analysis.phase_current_a, busV: analysis.bus_voltage_v, pwmHz: analysis.pwm_hz,
      speedMS: analysis.target_speed_m_s, forceConstant: analysis.thrust_constant_n_per_a, backEmfConstant: null,
      electricalPeriodM: period, ampacityA: analysis.trace_ampacity_a,
      headroom: settings.voltage_headroom, rippleFraction: settings.ripple_limit_fraction,
      connection: delta ? "delta" : "star",
    },
    notes: [
      "Imported hot winding resistance, synchronous inductance and ampacity are frozen coefficients, not a live geometry analysis.",
      ...(analysis.backplane ? ["This calculator does not recompute frequency-dependent backplane or housing effects. Imported low-frequency inductance is a constant approximation."] : []),
      ...(!native ? ["Browser preview winding values are demo estimates, not native copper measurements."] : []),
    ],
  };
}

export interface CalculatorCheck { label: string; status: "pass" | "fail" | "unknown"; value: number | null; limit: number | null; unit: string }
export interface BackEmfAssessment {
  backEmfConstant: number | null;
  backEmfSource: "entered" | "force constant" | "unavailable";
  phaseBackEmfV: number | null;
  lineBackEmfV: number | null;
  lineBackEmfRmsV: number | null;
  availableV: number;
  backEmfMarginV: number | null;
  voltageMarginV: number | null;
  backEmfSpeedLimitMS: number | null;
  maxSpeedMS: number | null;
}
export function calculateDriver(input: DriverCalculatorInput): { errors: string[]; checks: CalculatorCheck[]; rippleA?: number; holdingV?: number; speedV?: number | null; copperW?: number; effectiveH?: number; minPwmHz?: number; addedInductanceH?: number; forceN?: number | null } & Partial<BackEmfAssessment> {
  const errors: string[] = [];
  const finite = (v: number | null): v is number => typeof v === "number" && Number.isFinite(v);
  for (const [key, label, positive] of [
    ["resistanceOhm", "Hot phase resistance", true], ["inductanceH", "Synchronous winding inductance", false],
    ["seriesInductanceH", "Series inductance", false], ["currentA", "Phase current", true],
    ["busV", "Bus voltage", true], ["pwmHz", "PWM frequency", true], ["speedMS", "Speed", false],
    ["headroom", "Usable bus share", true], ["rippleFraction", "Ripple limit", true],
  ] as const) {
    const value = input[key];
    if (!finite(value) || (positive ? value <= 0 : value < 0)) errors.push(`${label} must be ${positive ? "positive" : "zero or positive"}.`);
  }
  for (const key of ["forceConstant", "electricalPeriodM", "ampacityA"] as const) {
    if (input[key] !== null && (!finite(input[key]) || input[key]! <= 0)) errors.push(`${key} must be blank or positive.`);
  }
  if (input.backEmfConstant != null && (!finite(input.backEmfConstant) || input.backEmfConstant <= 0)) errors.push("Phase-peak back-EMF constant must be blank or positive.");
  if (input.headroom !== null && input.headroom > 1) errors.push("Usable bus share cannot exceed 100%.");
  if (input.connection !== "star") errors.push("This calculator models balanced three-phase star wiring. Delta requires a topology-specific circuit model; no star substitution is made.");
  if (input.phaseCount !== 3) errors.push("This calculator requires three phases. No conversion from other phase counts is made.");
  const driver = input.driver;
  for (const key of ["min_supply_v", "max_supply_v", "peak_current_a", "continuous_rms_a", "rds_on_ohm", "max_pwm_hz"] as const) {
    if (!Number.isFinite(driver[key]) || driver[key] < 0 || (key !== "rds_on_ohm" && driver[key] === 0)) errors.push(`Invalid driver limit: ${key}.`);
  }
  if (driver.min_supply_v > driver.max_supply_v) errors.push("Driver supply-voltage limits are reversed.");
  const r = input.resistanceOhm!, l = input.inductanceH! + input.seriesInductanceH!;
  if (!(l > 0)) errors.push("Total phase inductance must be positive.");
  if (errors.length) return { errors, checks: [] };
  const i = input.currentA!, bus = input.busV!, pwm = input.pwmHz!, available = bus * input.headroom!;
  // Same balanced-star screening equations as simulation/drive/mod.rs. No
  // geometry, material solver, source-current or thermal result is fabricated.
  const ripple = bus / (2 * r) * Math.tanh(r / (4 * pwm * l));
  const rippleLimit = i * input.rippleFraction!;
  const requiredFL = 2 * r * rippleLimit >= bus ? 0 : r / (4 * Math.atanh(2 * r * rippleLimit / bus));
  const holding = Math.sqrt(3) * i * r + i * driver.rds_on_ohm;
  const speed = input.speedMS!;
  // Kf uses phase-current amplitude: F = Kf I, Ke_phase = 2 Kf / 3.
  const forceN = input.forceConstant === null ? null : input.forceConstant * i;
  const ke = input.backEmfConstant ?? (input.forceConstant === null ? null : (2 / 3) * input.forceConstant);
  const phaseBackEmfV = speed === 0 ? 0 : ke === null ? null : ke * speed;
  const lineBackEmfV = phaseBackEmfV === null ? null : Math.sqrt(3) * phaseBackEmfV;
  const requiredVoltage = (v: number) => Math.sqrt(3) * Math.hypot(i * r + ke! * v, 2 * Math.PI * v / input.electricalPeriodM! * l * i) + i * driver.rds_on_ohm;
  const speedV = speed === 0 ? holding : ke !== null && input.electricalPeriodM !== null ? requiredVoltage(speed) : null;
  const backEmfSpeedLimitMS = ke === null ? null : available / (Math.sqrt(3) * ke);
  let maxSpeedMS: number | null = null;
  if (backEmfSpeedLimitMS !== null && input.electricalPeriodM !== null) {
    // Bound by both EMF and inductive demand, so very small Ke does not
    // leave bisection searching an unnecessarily large speed interval.
    const voltageSlope = Math.hypot(ke!, 2 * Math.PI / input.electricalPeriodM * l * i);
    let low = 0, high = available / (Math.sqrt(3) * voltageSlope);
    // Required voltage is monotonic for positive speed, Ke, R and L.
    if (holding <= available) {
      for (let n = 0; n < 80; n++) {
        const mid = low + (high - low) / 2;
        if (requiredVoltage(mid) <= available) low = mid; else high = mid;
      }
    }
    maxSpeedMS = low;
  }
  const check = (label: string, value: number | null, limit: number | null, unit: string): CalculatorCheck => ({ label, value, limit, unit, status: value === null || limit === null ? "unknown" : value <= limit ? "pass" : "fail" });
  const checks: CalculatorCheck[] = [
    { label: "Driver supply range", value: bus, limit: driver.max_supply_v, unit: "V", status: bus >= driver.min_supply_v && bus <= driver.max_supply_v ? "pass" : "fail" },
    check("PWM frequency", pwm, driver.max_pwm_hz, "Hz"),
    check("Voltage to hold phase current", holding, available, "V"),
    check("Open-circuit back-EMF, line-to-line peak", lineBackEmfV, available, "V"),
    check("Voltage at target speed", speedV, available, "V"),
    check("PWM ripple, peak-to-peak at 50% duty", ripple, i * input.rippleFraction!, "A"),
    check("Terminal peak including ripple", i + ripple / 2, driver.peak_current_a, "A"),
    check("Phase RMS, triangular-ripple approximation", Math.hypot(i / Math.sqrt(2), ripple / Math.sqrt(12)), driver.continuous_rms_a, "A"),
    check("Trace ampacity at imported assumptions", i, input.ampacityA, "A"),
  ];
  return { errors, checks, rippleA: ripple, holdingV: holding, speedV, copperW: 1.5 * r * i * i, effectiveH: l, minPwmHz: requiredFL / l, addedInductanceH: Math.max(0, requiredFL / pwm - l), forceN, phaseBackEmfV, lineBackEmfV,
    backEmfConstant: ke, backEmfSource: input.backEmfConstant != null ? "entered" : ke !== null ? "force constant" : "unavailable",
    lineBackEmfRmsV: lineBackEmfV === null ? null : lineBackEmfV / Math.sqrt(2), availableV: available,
    backEmfMarginV: lineBackEmfV === null ? null : available - lineBackEmfV,
    voltageMarginV: speedV === null ? null : available - speedV, backEmfSpeedLimitMS, maxSpeedMS };
}
