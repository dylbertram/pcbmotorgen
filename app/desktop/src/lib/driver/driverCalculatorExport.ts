import { calculateDriver, type DriverCalculatorInput, type DriverCalculatorSnapshot } from "./driverCalculator";

export const DRIVER_MODEL_NOTES = [
  "Screening model, not hardware qualification. Constant hot phase resistance and synchronous inductance; balanced sinusoidal three-phase star currents.",
  "Force = Kf × phase-current amplitude. Phase back-EMF amplitude = Ke × speed; entered phase-peak Ke overrides the estimate (2/3) × Kf. Line-to-line peak = √3 × phase peak; line-to-line RMS = line peak / √2. Entering Ke does not infer Kf.",
  "Voltage margins compare peak line-to-line demand with bus voltage × usable bus share. The back-EMF-only speed ceiling excludes resistive and inductive drops. The loaded speed limit includes winding resistance, inductance and driver drop at target phase-current amplitude. Zero loaded speed means the bus cannot support any positive speed at that current. Missing constants remain unevaluated.",
  "Passing back-EMF and loaded-voltage checks does not qualify regeneration or back-driving safety. Check absolute maximum driver voltage, bus clamps, braking circuitry and the supply's ability to absorb energy separately.",
  "PWM ripple uses a 50%-duty RL estimate. Phase RMS approximates ripple as triangular. Trace ampacity is an entered limit, not a new thermal solve.",
  "Supply-current demand, regeneration, switching losses, inductor DCR/core losses, frequency-dependent material effects and temperatures are not calculated. Verify datasheet limits and hardware.",
];

export function buildDriverExport(input: DriverCalculatorInput, source: DriverCalculatorSnapshot | null, exportedAt = new Date().toISOString()) {
  return {
    schemaVersion: 1,
    exportedAt,
    provenance: {
      source: source?.source ?? "Manual inputs",
      capturedAt: source?.capturedAt ?? null,
      native: source?.native ?? null,
      edited: source !== null && JSON.stringify(input) !== JSON.stringify(source.input),
      importedInput: source ? structuredClone(source.input) : null,
      notes: source ? [...source.notes] : [],
    },
    units: {
      resistanceOhm: "Ω, per phase, hot", inductanceH: "H, synchronous winding per phase",
      seriesInductanceH: "H, external per phase", effectiveH: "H, winding + external per phase",
      currentA: "A, phase amplitude", busV: "V", pwmHz: "Hz", speedMS: "m/s",
      forceConstant: "N/A of phase-current amplitude", electricalPeriodM: "m", ampacityA: "A",
      backEmfConstant: "V·s/m, phase-to-neutral peak", backEmfSource: "source of phase-peak Ke",
      headroom: "fraction", rippleFraction: "fraction of phase-current amplitude",
      forceN: "N, ideal thrust", phaseBackEmfV: "V, phase amplitude", lineBackEmfV: "V, line-to-line amplitude",
      lineBackEmfRmsV: "V, line-to-line RMS", availableV: "V, usable line-to-line peak",
      backEmfMarginV: "V, usable minus open-circuit line peak", voltageMarginV: "V, usable minus loaded demand",
      backEmfSpeedLimitMS: "m/s, back-EMF only", maxSpeedMS: "m/s, voltage-limited at target current",
      copperW: "W, winding before ripple", rippleA: "A, peak-to-peak", holdingV: "V, required bus",
      speedV: "V, required bus", minPwmHz: "Hz", addedInductanceH: "H, additional per phase",
      driver: "Supply limits in V, peak and continuous RMS current in A, on-resistance in Ω, PWM limit in Hz",
    },
    input: structuredClone(input),
    result: calculateDriver(input),
    modelNotes: [...DRIVER_MODEL_NOTES],
  };
}

type DriverExport = ReturnType<typeof buildDriverExport>;
const escapeHtml = (value: unknown) => String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const display = (value: unknown) => value == null ? "Not evaluated" : typeof value === "number" ? String(Number(value.toPrecision(8))) : String(value);

export function driverExportHtml(data: DriverExport): string {
  const table = (headers: string[], rows: unknown[][]) => `<table><thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(v => `<td>${escapeHtml(display(v))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const units = data.units as Record<string, string>;
  const labels: Record<string, string> = {
    resistanceOhm: "Hot phase resistance", inductanceH: "Synchronous winding inductance", seriesInductanceH: "External series inductance",
    currentA: "Phase-current amplitude", busV: "Bus voltage", pwmHz: "PWM frequency", speedMS: "Target speed", forceConstant: "Force constant",
    electricalPeriodM: "Electrical period", ampacityA: "Trace ampacity", headroom: "Usable bus share", rippleFraction: "Ripple limit",
    effectiveH: "Effective phase inductance", forceN: "Ideal thrust", phaseBackEmfV: "Phase back-EMF", lineBackEmfV: "Line-to-line back-EMF",
    backEmfConstant: "Phase-peak back-EMF constant", backEmfSource: "Ke source", lineBackEmfRmsV: "Line-to-line back-EMF RMS",
    availableV: "Usable line-to-line voltage", backEmfMarginV: "Voltage margin after back-EMF only", voltageMarginV: "Voltage margin at target current and speed",
    backEmfSpeedLimitMS: "Back-EMF-only speed ceiling", maxSpeedMS: "Voltage-limited speed at target current",
    copperW: "Winding copper loss before ripple", rippleA: "PWM ripple", holdingV: "Voltage to hold phase current", speedV: "Voltage at target speed",
    minPwmHz: "Minimum PWM for ripple limit", addedInductanceH: "Additional inductance needed per phase",
  };
  const quantities = (values: object) => Object.entries(values).filter(([key]) => key in units && key !== "driver").map(([key, value]) => [labels[key] ?? key, value, units[key]]);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Driver calculator report</title><style>body{font:14px system-ui,sans-serif;color:#172033;max-width:1000px;margin:32px auto;padding:0 20px}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #cbd5e1;padding:8px;text-align:left;overflow-wrap:anywhere}th{background:#f1f5f9}li{margin:8px 0}@media print{body{margin:0}tr{break-inside:avoid}}</style></head><body>
<h1>Driver calculator report</h1><p>Exported ${escapeHtml(data.exportedAt)}</p>
<p>Source: ${escapeHtml(data.provenance.source)}. ${data.provenance.capturedAt ? `Captured ${escapeHtml(data.provenance.capturedAt)}. ${data.provenance.native ? "Native winding analysis." : "Browser demo estimates, not native copper measurements."}` : "Manually entered coefficients."} ${data.provenance.edited ? "Edited in calculator after import." : ""}</p>
${data.provenance.notes.map(note => `<p>${escapeHtml(note)}</p>`).join("")}
<h2>Inputs</h2><p>${escapeHtml(data.input.phaseCount)} phases, ${escapeHtml(data.input.connection)} connection. Driver: ${escapeHtml(data.input.driver.name)}</p>
${table(["Quantity", "Value", "Unit / convention"], quantities(data.input))}
<h2>Driver limits</h2>${table(["Limit", "Value"], [
  ["Minimum supply (V)", data.input.driver.min_supply_v], ["Maximum supply (V)", data.input.driver.max_supply_v],
  ["Peak current (A)", data.input.driver.peak_current_a], ["Continuous phase RMS (A)", data.input.driver.continuous_rms_a],
  ["Current-path on-resistance (Ω)", data.input.driver.rds_on_ohm], ["Maximum PWM (Hz)", data.input.driver.max_pwm_hz],
])}
<h2>Results</h2>${data.result.errors.length ? `<p>Not evaluated due to invalid or unsupported inputs.</p><ul>${data.result.errors.map(e => `<li>${escapeHtml(e)}</li>`).join("")}</ul>` : table(["Quantity", "Value", "Unit / convention"], quantities(data.result)) + table(["Check", "Demand", "Limit", "Unit", "Result"], data.result.checks.map(c => [c.label, c.value, c.limit, c.unit, c.status === "unknown" ? "Not evaluated" : c.status === "pass" ? "Pass" : "Fail"]))}
<h2>Model limits</h2><ul>${data.modelNotes.map(note => `<li>${escapeHtml(note)}</li>`).join("")}</ul></body></html>`;
}
