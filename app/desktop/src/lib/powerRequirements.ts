import type { CadGeometry, DriveAnalysis, DriveSettings, ForceSweepResult, LinearMotorConfig } from "./types";
import { version } from "../../package.json";
import type { NativeMoveResult, RoutedMoveRequest } from "./types/movePower";
import { moveInputKey } from "./movePowerJob";

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
  moveRequest?: RoutedMoveRequest | null;
  moveResult?: NativeMoveResult | null;
}

/** Every engineering export checks identity again, not just at render time. */
export function currentMoveResult(input: PowerRequirementsInput): NativeMoveResult | null {
  const r = input.native ? input.moveResult : null;
  return r && input.moveRequest && r.provenance === "simulated_not_measured"
    && input.topology === "linear"
    && moveInputKey(r.inputs) === moveInputKey({ topology: input.topology, config: input.config, drive: input.driveSettings,
      cad_geometry: input.cadGeometry, move_request: input.moveRequest }) ? r : null;
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
  const nativeMove = currentMoveResult(input), m = nativeMove?.result.demand;
  const declaredMove = input.moveRequest, p = declaredMove?.profile;
  const source = m?.feasible ? m.source : null;
  const unavailable = m ? [...m.limiting_factors, ...m.missing_inputs].join(". ") || "No complete source model." : "No current native move result.";
  const interval = m ? `PWM-cycle-averaged scenario over [0, ${number(m.profile.duration_s, "s")}], dt ${number(m.actual_time_step_s, "s")}. Stiff source at the DC link. Positive P=VI draws power, negative returns it. Not a worst-case or switching-peak bound.` : "";
  const moveValue = (label: string, value: number | undefined, unit: string, detail: string) => source
    ? row(label, number(value, unit), "Simulated", `${detail} ${interval}`) : unknown(label, `${unavailable} ${detail}`);
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
  const sections: RequirementSection[] = [
    { title: "Power demand", rows: [
      unknown("Peak supply power during a move", `${unavailable} The current model omits switching ripple, AC copper and external-inductor losses. Partial scenario values below are not total supply demand or a maximum. Copper loss is not maximum input power.`),
      unknown("Average supply power over a move", "Total supply average remains Unknown while loss accounting is partial. Repeated-operation average also needs repetition and idle/hold inputs."),
      unknown("Electrical energy per move", "Total supply energy remains Unknown while loss accounting is partial. Signed partial scenario energy, when available, is reported separately."),
      simulated("One-motor copper loss at setpoint", d?.copper_loss_w, "W", "Sinusoidal check: 1.5 × I_amplitude² × R_phase_hot. Excludes ripple heating and driver losses; not total or average input power."),
    ] },
    { title: "Move and load", rows: [
      configured("Desired travel", input.desiredTravelMm, "mm", "Configured track travel, not a defined move trajectory or verified mechanical limit. Imported copper may have different usable bounds."),
      configured("Target speed", s.target_speed_m_s, "m/s", "Configured operating point, not a demonstrated achievable trajectory."),
      configured("Acceleration constraint", c.max_accel_m_s2, "m/s²", "Design input only; not an applied motion profile."),
      p ? row("Move duration and motion profile", number(p.duration_s, "s"), "Configured", "Imposed quintic, explicit endpoint velocities and zero endpoint acceleration. Requested motion only; not integrated achieved motion.") : unknown("Move duration and motion profile", "No position/velocity trajectory or deceleration profile is defined. The force sweep samples imposed positions, not motion calculated from force and mass."),
      configured("Configured carriage mass", c.carriage_mass_kg, "kg", "Whether this includes the complete moving assembly and fader cap is unknown."),
      configured("Friction input", c.friction_n, "N", "Configured force allowance, not a measured speed-dependent friction law."),
      p ? row("External load and damping", `${number(p.external_load_n, "N")}; ${number(p.damping_n_s_per_m, "N·s/m")}`, "Configured", "Signed external force and viscous damping for the imposed move. Configured friction remains separate.") : unknown("External load and damping", "No opposing load or damping law is defined for the move."),
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
      configured("Motor supply", c.supply_voltage_v, "V", m ? "Declared constant-voltage source directly at the DC link for this move. No upstream-source or capacitor transient model." : "Nominal source voltage; driver DC-link voltage and supply current during a move are not simulated."),
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
      declaredMove?.additional_driver_loss_w != null ? row("Additional driver losses", number(declaredMove.additional_driver_loss_w, "W"), "Configured", "Explicit constant scenario loss declaration. Zero is an idealized assumption, not a qualified hardware total or conservative upper bound.") : unknown("Additional driver losses", "Switching, dead-time and controller consumption are not included. Total electrical input power cannot be established from copper loss alone."),
      configured("Supply capacitor bank", c.capacitor_bank_uf, "µF", m ? "Stiff DC-link assumption gives zero capacitor energy change. No ESR, ripple-current, clamp or regeneration transient prediction." : "Design input only; no DC-link voltage, ESR, ripple-current or regeneration transient simulation."),
      m ? row("Braking energy and supply return path", m.electrical.source_accepts_regeneration ? "Declared source accepts return" : "Declared source cannot sink", "Configured", "Stiff DC-link source. No capacitor transient or clamp model. A non-sinking source rejects negative demand.") : unknown("Braking energy and supply return path", "No braking trajectory or regeneration model is defined; returned energy and the supply's ability to absorb it are unknown."),
    ] },
  ];
  if (m) sections.push({ title: "Move model results", rows: [
    row("Motion feasibility", m.feasible ? "Sampled envelope checks pass" : "Not achieved", "Simulated", m.limiting_factors.join(". ") || "Necessary current/voltage/motion checks only. Not controller or thermal qualification."),
    row("Requested distance", number(m.requested_distance_m, "m"), "Configured", "Absolute first-magnet-center coordinate. An imposed trajectory is not an achieved-motion simulation."),
    unknown("Achieved motion", "No force/mass-integrated trajectory or measured motion is provided. The trace contains required position, velocity and acceleration, not observed achievement."),
    row("Requested peak speed", number(m.sampled_requested_peak_speed_m_s, "m/s"), "Simulated", "Sampled imposed speed, not achieved speed or a voltage-limited threshold."),
    row("Requested signed acceleration range", `${number(m.sampled_requested_negative_acceleration_m_s2, "m/s²")} to ${number(m.sampled_requested_positive_acceleration_m_s2, "m/s²")}`, "Simulated", "Sampled imposed acceleration, not achieved acceleration."),
    row("Declared moving mass", number(m.profile.moving_mass_kg, "kg"), "Configured", m.profile.mass_includes),
    row("Move phase peak, no ripple", number(m.sampled_phase_peak_a, "A"), "Simulated", "Sampled phase current, not supply current. Excludes analytical and switching ripple."),
    row("Move phase time RMS", m.phase_rms_a.map(v => number(v, "A")).join(", "), "Simulated", "Individual phase RMS over the exact move interval; not blindly peak / sqrt(2) at a holding position."),
    row("Source model scope", "Partial declared scenario", "Model", "No switching ripple, AC copper or external-inductor loss model. Total source demand and its maximum remain Unknown. A constant driver-loss declaration does not qualify those omissions."),
    moveValue("Partial scenario peak source power", source?.sampled_positive_peak_power_w, "W", "Sampled positive scenario peak only, not total supply power or a worst-case bound."),
    moveValue("Partial scenario average source power", source?.average_power_w, "W", "Signed partial source energy divided by the exact move duration."),
    moveValue("Partial scenario net source energy", source?.net_energy_j, "J", "Partial drawn energy minus partial returned energy. Not total supply energy."),
    moveValue("Partial scenario peak source current", source?.sampled_positive_peak_current_a, "A", "Sampled positive partial source current at the stated boundary, not phase current."),
    moveValue("Partial scenario drawn source energy", source?.drawn_energy_j, "J", "Positive magnitude integral of positive partial source power."),
    moveValue("Partial scenario returned source energy", source?.returned_energy_j, "J", "Positive magnitude integral of negative partial source power."),
    row("Required copper energy", number(m.copper_energy_j, "J"), "Simulated", "Required excitation for the imposed request, including infeasible requests. Not delivered energy if motion fails."),
    row("Required driver conduction energy", number(m.conduction_energy_j, "J"), "Simulated", "Equal high/low FET on-resistance assumption. Switching/dead-time/control losses remain separate."),
    row("Required mechanical work", number(m.mechanical_work_j, "J"), "Simulated", "Integral of required motor force times imposed velocity. Not measured delivered work."),
    row("Friction and damping energy", number(m.friction_damping_energy_j, "J"), "Simulated", "Coulomb friction plus viscous dissipation, counted once."),
    row("Signed external-load work", number(m.external_load_work_j, "J"), "Simulated", "Signed external force times imposed displacement."),
    row("Kinetic energy change", number(m.kinetic_energy_change_j, "J"), "Simulated", "Final minus initial kinetic energy over the exact exported interval."),
    row("Magnetic energy change", number(m.magnetic_energy_change_j, "J"), "Simulated", "Final minus initial winding/external-inductor stored energy. Startup before the interval is excluded."),
    row("Capacitor energy change", number(m.capacitor_energy_change_j, "J"), "Model", "Zero for the explicitly stiff DC-link source. Not a capacitor or source transient simulation."),
    row("Mechanical balance residual", number(m.mechanical_balance_residual_j, "J"), "Simulated", "Mechanical work minus friction/damping, signed external-load work and kinetic-energy change. Check time/force-map convergence."),
    row("Electrical balance residual", number(m.electrical_balance_residual_j, "J"), "Simulated", "Terminal electrical energy minus mechanical work, copper/conduction losses and magnetic-energy change. No numerical residual correction."),
    row("Native model identity", m.model_version, "Model", `Input SHA-256 ${nativeMove!.input_sha256}. ${interval}`),
    ...m.notes.map((detail, i) => row(`Model limitation ${i+1}`, "Declared", "Model", detail)),
  ] });
  return sections;
}

export function powerReportMarkdown(sections: RequirementSection[]): string {
  const escape = (text: string) => text.replaceAll("|", "\\|").replaceAll(/\r?\n/g, " ");
  return "# Linear-drive power requirements\n\nScope: one linear drive. Values are configured inputs or native model results, not measurements. Move results, when present, are imposed PWM-cycle-averaged scenarios, not hardware totals or guaranteed maxima.\n\nUnknown means unavailable, not zero.\n\n" + sections.map(section =>
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
  return JSON.stringify({ format: "pcbmotorgen-power-requirements", format_version: 2, app_version: version,
    generated_at: new Date().toISOString(), results_provenance: input.native ? "simulated_not_measured" : "demo_results_withheld",
    ...input, sweep: input.native ? input.sweep : null, drive: input.native ? input.drive : null,
    moveResult: currentMoveResult(input),
    sections: powerRequirements(input),
  }, (_key, value) => typeof value === "number" && !Number.isFinite(value) ? null : value, 2) + "\n";
}

export function moveTraceCsv(input: PowerRequirementsInput): string | null {
  const native = currentMoveResult(input);
  if (!native) return null;
  const r = native.result.demand;
  const names = r.electrical.phase_model?.phase_names ?? ["Unknown", "Unknown", "Unknown"];
  return csv([["model_version", "input_sha256", "provenance", "scenario_feasible", "time_s",
    "first_magnet_center_position_m", "requested_velocity_m_s", "requested_acceleration_m_s2", "required_motor_force_N",
    "required_source_voltage_V", "required_source_current_A", "required_source_power_W", "q_phase_amplitude_A",
    "phase_0_current_A", "phase_1_current_A", "phase_2_current_A", "phase_0_voltage_V", "phase_1_voltage_V", "phase_2_voltage_V",
    "required_line_voltage_V", "copper_loss_W", "conduction_loss_W", "mechanical_power_W", "friction_damping_loss_W",
    "external_load_power_W", "kinetic_energy_J", "magnetic_energy_J", "magnetic_power_W", "partial_dc_link_power_W",
    "additional_driver_loss_W", "phase_0_name", "phase_1_name", "phase_2_name", "stage", "averaging", "source_boundary", "source_model_scope"],
  ...r.samples.map(s => [r.model_version, native.input_sha256, native.provenance, r.feasible, s.time_s,
    s.position_m, s.velocity_m_s, s.acceleration_m_s2, s.motor_force_n,
    s.required_source_voltage_v, s.required_source_current_a, s.required_source_power_w, s.q_current_phase_peak_a,
    ...s.phase_currents_a, ...s.required_phase_voltages_v, s.required_line_voltage_v, s.copper_loss_w,
    s.driver_conduction_loss_w, s.mechanical_power_w, s.friction_damping_loss_w, s.external_load_power_w,
    s.kinetic_energy_j, s.magnetic_energy_j, s.magnetic_power_w, s.partial_dc_link_power_w,
    r.electrical.additional_driver_loss_w, ...names, "imposed_move", "pwm_cycle_averaged_no_ripple", "stiff_dc_link", "partial_declared_scenario"])]);
}
