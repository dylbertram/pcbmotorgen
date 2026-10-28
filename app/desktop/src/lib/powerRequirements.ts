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
  const f = input.native ? input.sweep : null;
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
    { title: "1. Simulation and assumptions", rows: [
      row("Software", `pcbmotorgen ${version}`, "Model", "Rust simulation backend with Tauri/Svelte UI. Build revision and external solver versions are unknown."),
      row("Result provenance", input.native ? "Simulated, not measured" : "Demo mode; numerical results withheld", "Model", "No measured motor or system power data are attached. Results are analytical/static calculations, not a hardware validation."),
      row("Model scope", "One motor / fader", "Model", "No coupled 17-fader supply or shared DC-link simulation."),
      row("Motion calculation", "Position sweep; speed is imposed", "Model", "No integration of force and moving mass. No trajectory, acceleration, braking or settling simulation."),
      row("Reproducibility", "Download model snapshot JSON", "Model", "Includes current SI configuration, drive settings, imported copper and available results. This is not an executable simulator or the original versioned .pmmotor file; save that separately."),
      row("Source and dependencies", "crates/pcbmotorgen-simulation/src/drive/ and magnetic/force_eval/", "Model", "Model implementation is in the repository. Cargo.toml, Cargo.lock, app/desktop/package.json and app/desktop/pnpm-lock.yaml define dependencies; source and installed binaries are not bundled. Custom routing-plugin binaries/versions are unknown."),
    ] },
    { title: "2. Motor and mechanical parameters", rows: [
      row("Motor construction", `${input.topology} coreless PCB stator; permanent-magnet mover`, "Configured", `${c.phases} phases; ${c.num_layers} configured copper layers; ${c.magnet_count} magnets, ${c.magnet_grade}, ${number(c.magnet_remanence_t, "T")}.`),
      row("Winding arrangement", cad ? `Imported copper: ${cad.source_file_name}` : c.routing_pattern, "Configured", cad ? `Uses imported geometry, not generated routing parameters. Trace width ${number(cad.trace_width_mm, "mm")}; layer Z ${cad.layer_z_mm.join(", ")} mm. See snapshot for terminals and all traces.` : `Routing parameters ${JSON.stringify(c.routing_params)}; ${c.strands_per_phase} configured strands per phase.`),
      connection === "Unknown" ? unknown("Phase connection", "Not declared by this geometry/pattern. A source filename is not proof of electrical connection.") : row("Phase connection", connection, "Configured", "Connection declaration, not a measured continuity check."),
      simulated("Winding resistance per phase", d?.phase_resistance_ohm, "Ω", `Worst hot DC phase value at ${s.winding_temp_c} °C; excludes driver. Per-net values are in the electrical CSV.`),
      simulated("Phase-to-phase resistance", d?.line_resistance_ohm, "Ω", "Star-only analytical value, 2 × phase resistance."),
      simulated("Winding self-inductance per phase", d?.phase_inductance_h, "H", "Copper-only self-inductance; distinct from mutual, synchronous and external inductance."),
      simulated("Phase-to-phase inductance", d?.line_inductance_h, "H", "Copper line inductance from the backend, excluding external series inductors."),
      simulated("Synchronous inductance", d?.synchronous_inductance_h, "H", "Copper synchronous phase inductance; see model notes for backplane frequency dependence."),
      configured("External series inductance per phase", s.series_inductance_h, "H", "Configured driver-terminal series inductance, not winding self-inductance."),
      simulated("Force constant Kf", d?.thrust_constant_n_per_a, "N/A", "Absolute force-sweep mean thrust / sweep current. Current is the configured commutation amplitude, not DC supply current."),
      simulated("Back-EMF constant Ke", d?.back_emf_constant_v_s_per_m, "V·s/m", "Backend assumes sinusoidal FOC, id = 0: phase-peak EMF = Ke × speed and Ke = 2/3 × Kf. Not measured; applicability to other commutation is unverified."),
      configured("Electrical travel period", 2 * c.magnet_pitch_m * 1000, "mm", "360 electrical degrees = two alternating pole pitches."),
      configured("Pole pitch", c.magnet_pitch_m * 1000, "mm"),
      configured("Configured carriage mass", c.carriage_mass_kg, "kg", "Whether this includes the fader cap is unknown. Mass does not drive a dynamic trajectory in this model."),
      unknown("Fader cap mass / total verified moving mass", "No mass breakdown or measured assembly mass supplied."),
      configured("Friction input", c.friction_n, "N", "Configured force allowance, not a measured speed-dependent friction law."),
      unknown("Damping and expected external load", "No damping coefficient or user-obstruction load model supplied."),
      configured("Driver continuous rating", s.driver.continuous_rms_a, "A RMS/phase", "Driver preset/input; not a validated continuous winding-current limit."),
      configured("Driver peak / OCP rating", s.driver.peak_current_a, "A", "Driver preset/input, not a programmed trip threshold or winding rating."),
      simulated("Analytical continuous-current check", d?.max_continuous_current_a, "A", `Backend suitability bound, not a validated winding rating; limiting factor: ${d?.limiting_factor ?? "unknown"}.`),
      unknown("Validated winding continuous / peak limits and peak duration", "No winding qualification, permitted peak duration or shutdown response supplied."),
      configured("Assumed winding temperature", s.winding_temp_c, "°C", "Resistance calculation input, not a simulated or measured temperature."),
      configured("Drive allowed temperature rise", s.allowed_rise_c, "°C", "Ampacity check input, not a thermal transient or shutdown limit."),
      configured("Design temperature-rise constraint", c.max_temperature_rise_c, "°C", "Separate design constraint; no measured thermal limit."),
      configured("Desired travel", input.desiredTravelMm, "mm", "Configured travel, not verified usable mechanical travel. Imported copper may have different bounds. A requested 65 mm move must not replace this value."),
      unknown("Usable mechanical travel and end stops", "No mechanical end-stop coordinates or verified travel supplied. Force sweep coordinates are absolute first-magnet-center positions, not fader end stops."),
    ] },
    { title: "3. Required movement", rows: [
      configured("Target speed", s.target_speed_m_s, "m/s", "Configured operating point, not a demonstrated achievable trajectory."),
      simulated("Voltage-limited speed threshold", d?.max_speed_m_s, "m/s", "Voltage-envelope intersection at configured current. Not the target speed or fastest full-travel result."),
      unknown("Required time for a complete 65 mm move", "No move-time requirement or force-integrated trajectory supplied; desired travel is reported separately."),
      configured("Acceleration constraint", c.max_accel_m_s2, "m/s²", "Design input only; not an applied motion profile."),
      unknown("Deceleration and jerk limits", "Not defined in the current motion model."),
      unknown("Movement frequency and longest continuous operating period", "No repeated movement recording or duty cycle supplied."),
      unknown("Full performance while touched or obstructed", "No requirement or contact-force model supplied."),
      unknown("Separate haptic force requirement", `Target force ${number(c.target_force_n, "N")} and peak force ${number(c.peak_force_n, "N")} are design targets, not a declared haptic requirement.`),
    ] },
    { title: "4. Drive and control settings", rows: [
      configured("Motor supply", c.supply_voltage_v, "V", "Nominal configured source, not a simulated driver DC-link waveform."),
      configured("PWM frequency", s.pwm_hz, "Hz"),
      row("Driver", s.driver.name, "Configured"),
      row("Commutation assumption", c.commutation === "max_thrust" ? "Max-thrust current allocation" : "Phase A only", "Configured", "Static commutation model. Firmware control loop, sensing bandwidth and actual modulation scheme are unknown."),
      row("Ripple model", "Steady-state two-phase RL square-wave approximation", "Model", "50% duty, ±Vbus/2 across the two-phase loop. This does not simulate actual PWM switching, dead time, control response or supply current."),
      configured("Phase-current amplitude setpoint", c.max_current_a, "A", "Simulation input; not a hardware current-limit setting or supply-source current."),
      simulated("Phase ripple, peak-to-peak", d?.ripple_pp_a, "A", "Analytical RL ripple, not switching-resolution samples."),
      simulated("Phase peak including analytical ripple", d?.peak_current_a, "A", "I_peak = configured phase-current amplitude + ripple_pp/2. Thus this result includes the model's ripple allowance, but is not a measured or switching-resolved peak. No fixed 1.15 A value is assumed."),
      unknown("Programmed current limit and shutdown timing", "Driver preset OCP rating does not specify actual firmware/hardware protection settings."),
      configured("Driver conduction-path resistance", s.driver.rds_on_ohm, "Ω", "HS + LS. Voltage check adds I × Rds_on; not a complete driver power-loss calculation."),
      configured("Voltage headroom fraction", s.voltage_headroom, "fraction", "Fraction of bus voltage available to the analytical voltage check."),
      d ? row("Driver suitability findings", d.checks.map(check => `${check.label}: ${check.status}`).join("; ") || "No checks returned", "Simulated", d.notes.join(" ")) : unknown("Driver suitability findings", "No current native driver analysis available."),
      unknown("Switching losses and dead time", "Not modelled; no switching energy or gate-drive loss parameters."),
      configured("Supply capacitor bank", c.capacitor_bank_uf, "µF", "Design input only; no DC-link voltage, ESR, ripple-current or regeneration transient simulation."),
      unknown("Braking / regeneration circuit", "No braking resistor, clamp, adapter sink capability or regeneration circuit defined."),
    ] },
    { title: "5. Simulation exports", rows: [
      f ? row("Position-domain force CSV", `${f.positions_m.length} samples`, "Simulated", "Absolute first-magnet-center position [m], force X/Y/Z [N]. Not a time series. Per-phase force contributions are not phase currents.") : unknown("Position-domain force CSV", "No current native force sweep available."),
      d ? row("Phase electrical CSV", `${d.phases.length} phase nets`, "Simulated", "Per-net resistance at 20 °C and hot, self-inductance, connectivity and copper length. No time axis.") : unknown("Phase electrical CSV", "No current native electrical analysis available."),
      unknown("Time", "No time-domain solver or recording available."),
      unknown("Supply-source current and sign convention", "No source-current waveform. Phase current is not supply current; no sign convention can be assigned to missing data."),
      unknown("DC-link voltage at driver", "Only nominal configured supply is known."),
      unknown("Phase A, B and C current waveforms", "Only setpoint and analytical ripple/peak checks are available."),
      unknown("Position, velocity and motor force versus time", "Force versus imposed position is available separately; no velocity trajectory."),
      unknown("PWM duty / commanded phase-voltage waveforms", "No controller or switching time trace."),
      unknown("Switching-resolution and repeated-movement recordings", "Idle, startup, acceleration, travel, braking and settling stages are not recorded. Peak/ripple validation and average supply power remain unknown."),
    ] },
    { title: "6. Operating cases", rows: [
      unknown("Peak supply power during a move", "No move trajectory, source-current waveform or complete driver-loss model. Not bounded by the static copper-loss result."),
      unknown("Average supply power over a move", "Requires integral of source voltage × source current over the specified move, divided by move duration."),
      unknown("Electrical energy per move", "Requires integral of source voltage × source current over the move. No time-domain result available."),
      ...["Fastest full-travel move", "Short move / rapid direction reversal", "Repeated simultaneous movement of 17 faders", "Blocked / stalled fader until limiting or shutdown", "Braking / externally pushed fader and regenerated energy"].map(label => unknown(label, "Not supported by the current static model. No transient result available.")),
      unknown("Conservative one-fader supply-power scaling", "No one-fader supply waveform or validated worst-case supply power to scale. Multiplying phase current by 17 would not establish supply demand."),
      simulated("One-motor copper loss at setpoint", d?.copper_loss_w, "W", "Backend sinusoidal check: 1.5 × I_amplitude² × R_phase_hot. Excludes ripple heating, driver losses and all other system loads; not total or average input power."),
      unknown("Complete-system feasibility at 60 W", "Cannot establish from copper loss alone. Requires movement duty cycle, supply traces, regeneration handling and other system loads."),
    ] },
    { title: "7. Other system loads", rows: [
      unknown("Scribble-strip displays", "Candidates, supply voltages, maximum power and backlight/OLED image dependence not supplied."),
      unknown("LED current / brightness limits", "The provisional 5 mA/channel is not confirmed; channel counts and brightness policy are unknown."),
      unknown("Master-module controls and powered components", "Button/knob counts and additional powered components not supplied."),
      unknown("Measured controller / sensor / communications idle power", "No measured idle-power data supplied."),
    ] },
    { title: "8. Remaining system decisions", rows: [
      ...["Closed electrical loops in the grid", "Maximum grid dimensions and connector spacing", "Two-adapter standby handover or power combining", "Load-shedding priority after adapter removal", "USB-data-only discovery scope", "Preserve stored targets/settings or also physical positions"].map(label => unknown(label, "System decision not recorded in the motor model.")),
    ] },
  ];
}

export function powerReportMarkdown(sections: RequirementSection[]): string {
  const escape = (text: string) => text.replaceAll("|", "\\|").replaceAll(/\r?\n/g, " ");
  return "# Power requirements\n\nUnknown means unavailable, not zero. Configured values are inputs, not measurements.\n\n" + sections.map(section =>
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
