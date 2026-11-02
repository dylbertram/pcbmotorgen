import type { DriveCheck, DriveSettings } from "./types";
import type { NativeMoveResult } from "./types/movePower";
import { formatSi } from "./format";

export type MoveCheckStatus = "pass" | "warn" | "fail" | "unknown";

export interface MoveSummaryCheck {
  label: string;
  status: MoveCheckStatus;
  reading: string;
  detail: string;
}

export interface MoveSummary {
  scope: "Engineering estimate" | "Partial estimate" | "Unavailable";
  scopeText: string;
  headline: {
    peakPower: string;
    averagePower: string;
    energy: string;
    peakSupplyCurrent: string;
  };
  motion: {
    distance: string;
    duration: string;
    peakSpeed: string;
    peakAcceleration: string;
    peakForce: string;
  };
  electrical: {
    phasePeak: string;
    phasePeakIncludingRipple: string | null;
    phaseCurrentVersusSupply: string;
  };
  checks: MoveSummaryCheck[];
  omissions: string[];
  exclusions: string[];
  lossReferences: string[];
  notes: string[];
  hasCompleteModel: boolean;
}

export interface MoveSummaryOptions {
  exclusions?: string[];
}

function watts(value: number): string {
  return formatSi(value, "W");
}

function joules(value: number): string {
  return formatSi(value, "J");
}

function amps(value: number): string {
  return formatSi(value, "A");
}

function volts(value: number): string {
  return formatSi(value, "V");
}

function phaseCheck(check: DriveCheck | undefined): MoveSummaryCheck | null {
  if (!check) return null;
  return {
    label: check.label,
    status: check.status,
    reading: `${formatSi(check.value, check.unit)} against ${formatSi(check.limit, check.unit)}`,
    detail: check.detail,
  };
}

/**
 * One presentation model shared by the panel, Markdown and HTML report. All
 * values come from the native result; nothing is recomputed from formatted
 * text or fitted to a target.
 */
export function summariseMove(result: NativeMoveResult, options: MoveSummaryOptions = {}): MoveSummary {
  const demand = result.result.demand;
  const settings: DriveSettings = result.inputs.drive;
  const source = demand.source;
  const complete = demand.source_model_scope === "engineering_estimate" || demand.source_model_scope === "declared_loss_model";
  const scope: MoveSummary["scope"] = demand.samples.length === 0 ? "Unavailable" : complete ? "Engineering estimate" : "Partial estimate";

  // With no complete loss model the native result still provides motor and
  // FET-conduction demand. Present that explicitly rather than as a total.
  const duration = demand.profile.duration_s;
  const timePower = (i: number) => {
    const s = demand.samples[i];
    return source ? (s.required_source_power_w ?? 0) : s.partial_dc_link_power_w;
  };
  let peak = 0;
  let energy = 0;
  for (let i = 0; i < demand.samples.length; i++) {
    const value = timePower(i);
    if (value > peak) peak = value;
    if (i > 0) {
      const a = demand.samples[i - 1], b = demand.samples[i];
      energy += (timePower(i - 1) + value) / 2 * (b.time_s - a.time_s);
    }
  }
  const peakPowerW = source?.sampled_positive_peak_power_w ?? peak;
  const averagePowerW = source?.average_power_w ?? (duration > 0 ? energy / duration : 0);
  const netEnergyJ = source?.net_energy_j ?? energy;
  const peakSupplyA = demand.electrical.source_voltage_v > 0 ? peakPowerW / demand.electrical.source_voltage_v : 0;
  const phasePeakWithRipple = demand.sampled_phase_peak_including_declared_ripple_a;

  const peakLineV = Math.max(...demand.samples.map(s => s.required_line_voltage_v));
  const voltageLimited = demand.limiting_factors.some(f => f.startsWith("Required line voltage"));
  const regenerates = demand.samples.some(s => (s.required_source_power_w ?? 0) < 0);
  const regenerationBlocked = demand.limiting_factors.some(f => f.startsWith("Source cannot absorb"));
  const phasePeak = Math.max(demand.sampled_phase_peak_a, phasePeakWithRipple ?? 0);

  const checks: MoveSummaryCheck[] = [
    {
      label: "Voltage for this move",
      status: voltageLimited ? "fail" : "pass",
      reading: `${volts(peakLineV)} required of ${volts(demand.electrical.source_voltage_v)} available`,
      detail: voltageLimited
        ? "The imposed move needs more line voltage than the bus provides. Demand is still calculated; achieved tracking is not claimed."
        : "Sampled phase-command span stays within the declared DC link for this imposed move.",
    },
  ];
  const [overlapMin, overlapMax] = result.result.full_overlap_bounds_m;
  const lowest = Math.min(demand.profile.start_m, demand.profile.end_m);
  const highest = Math.max(demand.profile.start_m, demand.profile.end_m);
  const partialOverlap = lowest < overlapMin - 1e-9 || highest > overlapMax + 1e-9;
  checks.push({
    label: "Copper and magnet overlap",
    status: partialOverlap ? "warn" : "pass",
    reading: partialOverlap
      ? `Move reaches outside the ${(overlapMin * 1000).toFixed(1)} to ${(overlapMax * 1000).toFixed(1)} mm full-overlap interval`
      : `Move stays within ${(overlapMin * 1000).toFixed(1)} to ${(overlapMax * 1000).toFixed(1)} mm`,
    detail: "Full overlap is a magnetic observation from this model, not a mechanical end stop. Force is evaluated at partial overlap without extending copper.",
  });
  const peakRatio = settings.driver.peak_current_a > 0 ? phasePeak / settings.driver.peak_current_a : 0;
  checks.push({
    label: "Peak phase current",
    status: peakRatio > 1 ? "fail" : peakRatio > 0.8 ? "warn" : "pass",
    reading: `${amps(phasePeak)} against ${amps(settings.driver.peak_current_a)} ${settings.driver.name} peak`,
    detail: "Includes the declared PWM ripple envelope when a loss model is present. This is phase current, not supply current.",
  });
  const phaseRms = Math.max(...(demand.phase_rms_including_declared_ripple_a ?? demand.phase_rms_a));
  const continuousRatio = settings.driver.continuous_rms_a > 0 ? phaseRms / settings.driver.continuous_rms_a : 0;
  checks.push({
    label: "Average phase current over the move",
    status: continuousRatio > 1 ? "warn" : "pass",
    reading: `${amps(phaseRms)} RMS against ${amps(settings.driver.continuous_rms_a)} ${settings.driver.name} continuous`,
    detail: "A single move is not a sustained thermal duty. Repeating moves needs a thermal analysis that this model does not provide.",
  });
  if (regenerates) {
    checks.push({
      label: "Returned energy",
      status: regenerationBlocked ? "fail" : demand.electrical.source_accepts_regeneration ? "pass" : "unknown",
      reading: demand.electrical.source_accepts_regeneration ? "Source declared able to absorb return" : "Source declared unable to absorb return",
      detail: "Negative demand occurs during braking in this imposed move. No capacitor or clamp transient is modelled.",
    });
  }
  const ampacity = phaseCheck(result.result.drive.checks.find(c => c.id === "ampacity"));
  if (ampacity) checks.push({ ...ampacity, label: "Trace ampacity at the configured current", detail: `${ampacity.detail} Static winding check, separate from this move's current.` });
  checks.push({
    label: "Winding temperature rise",
    status: "unknown",
    reading: "Not modelled",
    detail: `Colour and loss values are not temperature. The move assumes ${formatSi(settings.winding_temp_c, "°C")} copper; no cooling or duty-cycle model is applied.`,
  });
  if (settings.series_inductance_h > 0 && !(Math.abs(settings.series_inductance_h - 47e-6) < 1e-12)) {
    checks.push({
      label: "External inductor losses",
      status: "unknown",
      reading: `${formatSi(settings.series_inductance_h, "H")} per phase, component unspecified`,
      detail: "DCR and core loss are excluded. Peak and average power omit this contribution and are not a complete hardware total.",
    });
  }

  const omissions = demand.missing_inputs.map(item => item.replace(/^Declared omitted loss: /, ""));
  return {
    scope,
    scopeText: scope === "Engineering estimate"
      ? "Estimated from the active copper and the documented driver/ripple assumptions. Sampled peak, not a guaranteed maximum."
      : scope === "Partial estimate"
        ? "Motor and FET conduction only. Switching, inductor and board losses are missing, so this is not total supply demand."
        : "No usable move result is available.",
    headline: {
      peakPower: watts(peakPowerW),
      averagePower: watts(averagePowerW),
      energy: joules(netEnergyJ),
      peakSupplyCurrent: amps(peakSupplyA),
    },
    motion: {
      distance: `${(Math.abs(demand.requested_distance_m) * 1000).toFixed(1)} mm`,
      duration: `${formatSi(duration, "s")}`,
      peakSpeed: `${demand.sampled_requested_peak_speed_m_s.toFixed(3)} m/s`,
      peakAcceleration: `${demand.sampled_requested_positive_acceleration_m_s2.toFixed(2)} m/s²`,
      peakForce: `${Math.max(...demand.samples.map(s => Math.abs(s.motor_force_n))).toFixed(3)} N`,
    },
    electrical: {
      phasePeak: amps(demand.sampled_phase_peak_a),
      phasePeakIncludingRipple: phasePeakWithRipple === null ? null : amps(phasePeakWithRipple),
      phaseCurrentVersusSupply: "Phase current drives the winding. Supply current at the DC link is lower because the required winding voltage is a fraction of the bus voltage.",
    },
    checks,
    omissions,
    exclusions: options.exclusions ?? [],
    lossReferences: demand.electrical.loss_model ? [demand.electrical.loss_model.reference, demand.electrical.loss_model.ripple.reference] : [],
    notes: demand.notes,
    hasCompleteModel: complete,
  };
}
