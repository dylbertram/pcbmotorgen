import type { CadGeometry, DriveAnalysis, DriveSettings, ForceSweepResult, LinearMotorConfig } from "./types";
import { version } from "../../package.json";

export interface PowerRequirementsInput {
  config: LinearMotorConfig;
  driveSettings: DriveSettings;
  desiredTravelMm: number;
  topology: string;
  cadGeometry: CadGeometry | null;
  /** Only results matched to the current inputs may enter a report. */
  sweep: ForceSweepResult | null;
  drive: DriveAnalysis | null;
  native: boolean;
}

export interface RequirementRow {
  label: string;
  value: string;
  source: "Configured" | "Simulated" | "Model" | "Unknown";
  detail: string;
}
export interface RequirementSection { title: string; rows: RequirementRow[] }

const unknown = (label: string, detail: string): RequirementRow => ({ label, value: "Unknown", source: "Unknown", detail });
const row = (label: string, value: string, source: RequirementRow["source"], detail = ""): RequirementRow => ({ label, value, source, detail });
const number = (value: number | null | undefined, unit: string): string =>
  value != null && Number.isFinite(value) ? `${Number(value.toPrecision(7))} ${unit}` : "Unknown";

/** No inferred supply power, trajectories, operating duty cycles or measured data. */
export function powerRequirements(input: PowerRequirementsInput): RequirementSection[] {
  const { config: c, driveSettings: s, cadGeometry: cad } = input;
  // Browser fallback data are UI examples, never engineering evidence.
  const d = input.native ? input.drive : null;
  const simulated = (label: string, value: number | null | undefined, unit: string, detail: string) => {
    const formatted = number(value, unit);
    return formatted === "Unknown" ? unknown(label, "No current native simulation result. " + detail) : row(label, formatted, "Simulated", detail);
  };
  const configured = (label: string, value: number, unit: string, detail = "") => {
    const formatted = number(value, unit);
    return formatted === "Unknown" ? unknown(label, detail) : row(label, formatted, "Configured", detail);
  };
  const connection = cad
    ? cad.terminal_connection === "star" ? "Star (wye)" : cad.terminal_connection === "delta" ? "Delta" : "Unknown"
    : c.routing_pattern === "infinity-braid"
      ? ["Closed individual coils", "Delta", "Star (wye)"][Math.round(c.routing_params.connection ?? 0)] ?? "Unknown"
      : "Unknown";
  return [
    { title: "Power demand", rows: [
      unknown("Peak supply power during a move", "Requires a move trajectory, supply-current data and driver losses. Copper loss is not maximum input power."),
      unknown("Average supply power over a move", "Integral of supply voltage × supply current over the move, divided by move duration. No time-domain result available."),
      unknown("Electrical energy per move", "Integral of supply voltage × supply current over the move. No time-domain result available."),
      simulated("One-motor copper loss at setpoint", d?.copper_loss_w, "W", "Sinusoidal check: 1.5 × I_amplitude² × R_phase_hot. Excludes ripple heating and driver losses; not total or average input power."),
    ] },
    { title: "Move and load", rows: [
      configured("Desired travel", input.desiredTravelMm, "mm", "Configured track travel, not a defined move trajectory or verified mechanical limit. Imported copper may have different usable bounds."),
      configured("Target speed", s.target_speed_m_s, "m/s", "Configured operating point, not a demonstrated achievable trajectory."),
      configured("Acceleration constraint", c.max_accel_m_s2, "m/s²", "Design input only; not an applied motion profile."),
      unknown("Move duration and motion profile", "No position/velocity trajectory or deceleration profile is defined. The force sweep samples imposed positions, not motion calculated from force and mass."),
      configured("Configured carriage mass", c.carriage_mass_kg, "kg", "Whether this includes the complete moving assembly and fader cap is unknown."),
      configured("Friction input", c.friction_n, "N", "Configured force allowance, not a measured speed-dependent friction law."),
      unknown("External load and damping", "No opposing load or damping law is defined for the move."),
      configured("Target force", c.target_force_n, "N", "Design target, not simulated available thrust."),
      configured("Peak force target", c.peak_force_n, "N"),
      simulated("Available thrust at setpoint", d?.thrust_n, "N", "Force constant × phase-current amplitude. Does not establish a complete move profile."),
    ] },
    { title: "Motor electrical parameters", rows: [
      row("Winding arrangement", cad ? `Imported copper: ${cad.source_file_name}` : c.routing_pattern, "Configured", cad ? `Uses imported geometry, not generated routing parameters. Trace width ${number(cad.trace_width_mm, "mm")}; layer Z ${cad.layer_z_mm.join(", ")} mm. See snapshot for terminals and all traces.` : `Routing parameters ${JSON.stringify(c.routing_params)}; ${c.strands_per_phase} configured strands per phase.`),
      configured("Phase count", c.phases, "phases"),
      connection === "Unknown" ? unknown("Phase connection", "Not declared by this geometry/pattern. A source filename is not proof of electrical connection.") : row("Phase connection", connection, "Configured", "Connection declaration, not a measured continuity check."),
      simulated("Winding resistance per phase", d?.phase_resistance_ohm, "Ω", `Worst hot DC phase value at ${s.winding_temp_c} °C; excludes driver. Per-net values are in the electrical CSV.`),
      simulated("Phase-to-phase resistance", d?.line_resistance_ohm, "Ω", "Star-only analytical value, 2 × phase resistance."),
      simulated("Winding self-inductance per phase", d?.phase_inductance_h, "H", "Copper-only self-inductance; distinct from mutual, synchronous and external inductance."),
      simulated("Phase-to-phase inductance", d?.line_inductance_h, "H", "Copper line inductance from the backend, excluding external series inductors."),
      simulated("Synchronous inductance", d?.synchronous_inductance_h, "H", "Copper synchronous phase inductance; backplane frequency dependence is recorded in the model snapshot."),
      configured("External series inductance per phase", s.series_inductance_h, "H", "Configured driver-terminal series inductance, not winding self-inductance."),
      simulated("Force constant Kf", d?.thrust_constant_n_per_a, "N/A", "Absolute force-sweep mean thrust / sweep current. Current is the configured commutation amplitude, not DC supply current."),
      simulated("Back-EMF constant Ke", d?.back_emf_constant_v_s_per_m, "V·s/m", "Backend assumes sinusoidal FOC, id = 0: phase-peak EMF = Ke × speed and Ke = 2/3 × Kf. Not measured; applicability to other commutation is unverified."),
      configured("Electrical travel period", 2 * c.magnet_pitch_m * 1000, "mm", `360 electrical degrees; pole pitch ${number(c.magnet_pitch_m * 1000, "mm")}.`),
      configured("Assumed winding temperature", s.winding_temp_c, "°C", "Hot-resistance input, not a temperature prediction."),
      simulated("Analytical continuous-current check", d?.max_continuous_current_a, "A", `Backend suitability bound, not a validated winding rating; limiting factor: ${d?.limiting_factor ?? "unknown"}.`),
      configured("Allowed temperature rise", s.allowed_rise_c, "°C", "Input to the winding ampacity check, not a predicted rise or shutdown limit."),
      unknown("Winding current limits and peak duration", "No validated continuous/peak winding rating or permitted peak duration supplied."),
    ] },
    { title: "Supply and driver", rows: [
      configured("Motor supply", c.supply_voltage_v, "V", "Nominal source voltage; driver DC-link voltage and supply current during a move are not simulated."),
      row("Driver", s.driver.name, "Configured"),
      configured("PWM frequency", s.pwm_hz, "Hz"),
      row("Commutation assumption", c.commutation === "max_thrust" ? "Max-thrust current allocation" : "Phase A only", "Configured", "Static current model; actual controller and PWM scheme are unknown."),
      configured("Phase-current amplitude setpoint", c.max_current_a, "A", "Simulation input, not supply current or a programmed hardware trip threshold."),
      simulated("Phase ripple, peak-to-peak", d?.ripple_pp_a, "A", "Analytical 50%-duty two-phase RL square-wave approximation, not switching-resolution samples."),
      simulated("Phase peak including analytical ripple", d?.peak_current_a, "A", "I_peak = phase-current amplitude + ripple_pp/2. Includes analytical ripple, not a measured or switching-resolved peak."),
      configured("Driver continuous rating", s.driver.continuous_rms_a, "A RMS/phase", "Driver rating, not a winding-current limit."),
      configured("Driver peak / OCP rating", s.driver.peak_current_a, "A", "Driver rating, not a programmed trip threshold or permitted winding peak."),
      configured("Driver conduction-path resistance", s.driver.rds_on_ohm, "Ω", "HS + LS. Voltage check adds I × Rds_on; not a complete driver-loss calculation."),
      configured("Voltage headroom fraction", s.voltage_headroom, "fraction", "Bus-voltage fraction available to the voltage check."),
      simulated("Voltage-limited speed threshold", d?.max_speed_m_s, "m/s", "Voltage-envelope intersection at configured current. Not the target speed or fastest full-travel result."),
      unknown("Additional driver losses", "Switching, dead-time and controller consumption are not included. Total electrical input power cannot be established from copper loss alone."),
      configured("Supply capacitor bank", c.capacitor_bank_uf, "µF", "Design input only; no DC-link voltage, ESR, ripple-current or regeneration transient simulation."),
      unknown("Braking energy and supply return path", "No braking trajectory or regeneration model is defined; returned energy and the supply's ability to absorb it are unknown."),
    ] },
  ];
}

export function powerReportMarkdown(sections: RequirementSection[]): string {
  const escape = (text: string) => text.replaceAll("|", "\\|").replaceAll(/\r?\n/g, " ");
  return "# Linear-drive power requirements\n\nScope: one linear drive. Values are configured inputs or static simulation results, not measurements. No time-domain move or supply-current calculation is available.\n\nUnknown means unavailable, not zero.\n\n" + sections.map(section =>
    `## ${section.title}\n\n| Item | Value | Source | Definition / limitation |\n| --- | --- | --- | --- |\n` + section.rows.map(r => `| ${[r.label, r.value, r.source, r.detail].map(escape).join(" | ")} |`).join("\n")
  ).join("\n\n") + "\n";
}

function csv(rows: (string | number | boolean | null | undefined)[][]): string {
  return rows.map(row => row.map(value => {
    let text = value == null || typeof value === "number" && !Number.isFinite(value) ? "Unknown" : String(value);
    // Text from imported net names must not execute as spreadsheet formulas.
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  }).join(",")).join("\r\n") + "\r\n";
}

export function powerRequirementsCsv(sections: RequirementSection[]): string {
  return csv([["section", "item", "value_with_units", "source", "definition_or_limitation"], ...sections.flatMap(s => s.rows.map(r => [s.title, r.label, r.value, r.source, r.detail]))]);
}

export function forceSweepCsv(sweep: ForceSweepResult): string {
  return csv([["first_magnet_center_position_m", "force_x_N", "force_y_N", "force_z_N"], ...sweep.positions_m.map((x, i) => [x, sweep.force_x_n[i], sweep.force_y_n[i], sweep.force_z_n[i]])]);
}

export function phaseElectricalCsv(drive: DriveAnalysis): string {
  return csv([["net", "resistance_20C_ohm", "resistance_hot_ohm", "self_inductance_H", "total_copper_length_m", "connected"], ...drive.phases.map(p => [p.net, p.resistance_20c_ohm, p.resistance_hot_ohm, p.self_inductance_h, p.total_length_m, p.connected])]);
}

export function powerModelSnapshot(input: PowerRequirementsInput): string {
  return JSON.stringify({ format: "pcbmotorgen-power-requirements", format_version: 1, app_version: version,
    generated_at: new Date().toISOString(), results_provenance: input.native ? "simulated_not_measured" : "demo_results_withheld",
    ...input, sweep: input.native ? input.sweep : null, drive: input.native ? input.drive : null,
    sections: powerRequirements(input),
  }, (_key, value) => typeof value === "number" && !Number.isFinite(value) ? null : value, 2) + "\n";
}
