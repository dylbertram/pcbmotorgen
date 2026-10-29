import { describe, expect, it } from "vitest";
import { ConfigStore } from "./stores/config.svelte";
import { mockDriveAnalysis, mockForceSweep } from "./ipc/mocks";
import type { CadGeometry } from "./types";
import { powerRequirements, powerReportMarkdown, powerRequirementsCsv, powerModelSnapshot, forceSweepCsv, phaseElectricalCsv, currentMoveResult, moveTraceCsv, type PowerRequirementsInput } from "./powerRequirements";
import { declaredLossFixture } from "./testFixtures/moveLosses";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Inputs transcribed from the user's Fader-traces-workspace.pmmotor. This
// fixture deliberately does not claim to reproduce its imported trace solver.
function fixture(): PowerRequirementsInput {
  const config = new ConfigStore();
  Object.assign(config, { desired_travel_mm: 63, active_area_width_mm: 8,
    magnet_count: 5, magnet_width_mm: 5, magnet_cross_width_mm: 5,
    magnet_height_mm: 3, electrical_pitch_mm: 12, supply_voltage_v: 12, carriage_mass_kg: 0.015,
    routing_params: { num_strands: 3, connection: 0 } });
  const driveSettings = { ...config.drive, series_inductance_h: 47e-6 };
  return { config: config.toIpc(), driveSettings, desiredTravelMm: 63,
    topology: "linear", cadGeometry: null, sweep: null, drive: null, native: true };
}

const rows = (input: PowerRequirementsInput) => powerRequirements(input).flatMap(section => section.rows);
const item = (input: PowerRequirementsInput, label: string) => rows(input).find(row => row.label === label)!;

describe("power requirements", () => {
  it("preserves the user's operating inputs without inventing a move or 65 mm travel", () => {
    const input = fixture();
    expect(item(input, "Target speed").value).toBe("0.5 m/s");
    expect(item(input, "Desired travel").value).toBe("63 mm");
    expect(item(input, "Motor supply").value).toBe("12 V");
    expect(item(input, "PWM frequency").value).toBe("100000 Hz");
    expect(item(input, "External series inductance per phase").value).toBe("0.000047 H");
    expect(item(input, "Electrical travel period").value).toBe("12 mm");
    expect(item(input, "Electrical travel period").detail).toContain("pole pitch 6 mm");
    expect(item(input, "Configured carriage mass").value).toBe("0.015 kg");
    expect(item(input, "Configured carriage mass").detail).toContain("full-assembly override");
  });

  it("separates target speed and ripple-inclusive analytical phase peak from supply demand", () => {
    const input = fixture();
    input.drive = { ...mockDriveAnalysis(input.config, input.driveSettings, 0.6), max_speed_m_s: 16.99, peak_current_a: 1.15, ripple_pp_a: 0.3 };
    expect(item(input, "Target speed").value).toBe("0.5 m/s");
    expect(item(input, "Voltage-limited speed threshold").value).toBe("16.99 m/s");
    expect(item(input, "Phase peak including analytical ripple").value).toBe("1.15 A");
    expect(item(input, "Phase peak including analytical ripple").detail).toContain("ripple_pp/2");
    for (const label of ["Peak supply power during a move", "Average supply power over a move", "Electrical energy per move", "Move duration and motion profile", "External load and damping", "Additional driver losses", "Braking energy and supply return path"])
      expect(item(input, label).value).toBe("Unknown");
    expect(item(input, "One-motor copper loss at setpoint").detail).toContain("not total or average input power");
  });

  it("never promotes demo numbers to simulation evidence or snapshot results", () => {
    const input = fixture();
    input.native = false;
    input.sweep = mockForceSweep(input.config);
    input.drive = mockDriveAnalysis(input.config, input.driveSettings, 0.6);
    expect(rows(input).some(row => row.source === "Simulated")).toBe(false);
    const snapshot = JSON.parse(powerModelSnapshot(input));
    expect(snapshot.sweep).toBeNull();
    expect(snapshot.drive).toBeNull();
    expect(snapshot.results_provenance).toBe("demo_results_withheld");
    expect(snapshot.config.supply_voltage_v).toBe(12);
  });

  it("uses imported geometry metadata without inferring a connection from a filename", () => {
    const input = fixture();
    input.cadGeometry = { source_file_name: "star-wye_4-layer.dxf", trace_width_mm: 0.2,
      layer_z_mm: [-4.8, -3.2, -1.6, 0], routing: { segments: [], curves: [], vias: [] } } as unknown as CadGeometry;
    expect(item(input, "Phase connection").value).toBe("Unknown");
    expect(item(input, "Winding arrangement").detail).toContain("0.2 mm");
    expect(item(input, "Winding arrangement").detail).toContain("-4.8, -3.2, -1.6, 0 mm");
    input.cadGeometry.terminal_connection = "star";
    expect(item(input, "Phase connection").value).toBe("Star (wye)");
    expect(JSON.parse(powerModelSnapshot(input)).cadGeometry).toEqual(input.cadGeometry);
  });

  it("respects generated pattern-owned connection options", () => {
    const input = fixture();
    expect(item(input, "Phase connection").value).toBe("Closed individual coils");
    input.config.routing_params.connection = 1;
    expect(item(input, "Phase connection").value).toBe("Delta");
    input.config.routing_params.connection = 2;
    expect(item(input, "Phase connection").value).toBe("Star (wye)");
    input.config.routing_pattern = "custom";
    expect(item(input, "Phase connection").value).toBe("Unknown");
  });

  it("exports only the single-drive calculation data, definitions and essential unknowns", () => {
    const sections = powerRequirements(fixture());
    expect(sections.map(section => section.title)).toEqual(["Power demand", "Move and load", "Motor electrical parameters", "Supply and driver"]);
    const markdown = powerReportMarkdown(sections);
    expect(markdown).toContain("Unknown means unavailable, not zero");
    expect(markdown).toContain("Peak supply power during a move | Unknown");
    expect(markdown).toContain("Additional driver losses | Unknown");
    expect(markdown).toContain("Scope: one linear drive");
    const csv = powerRequirementsCsv(sections);
    expect(csv).toContain('"value_with_units","source","definition_or_limitation"');
    expect(csv).toContain('"Desired travel","63 mm","Configured"');
    expect(csv).toContain("\r\n");
    const snapshot = JSON.parse(powerModelSnapshot(fixture()));
    expect(snapshot.sections).toEqual(sections);
    for (const content of [markdown, csv, JSON.stringify(snapshot.sections)]) {
      // Exclude the peripheral, not words such as "sampled" or "modeled".
      expect(content).not.toMatch(/scribble|\bLED\b|USB|grid|adapter|17 faders|60 W|haptic|65 mm|1\.15 A|Source and dependencies|Remaining system decisions/i);
    }
  });

  it("exports position-domain data without fabricating time/current/velocity columns", () => {
    const input = fixture();
    const sweep = { ...mockForceSweep(input.config), positions_m: [0.0025, 0.0655], force_x_n: [0.2, 0.3], force_y_n: [0, 0], force_z_n: [0, 0] };
    const csv = forceSweepCsv(sweep);
    expect(csv.split("\r\n")[0]).toBe('"first_magnet_center_position_m","force_x_N","force_y_N","force_z_N"');
    expect(csv).toContain('"0.0025","0.2","0","0"');
    expect(csv).not.toMatch(/time|current|velocity/);
    expect(csv.split("\r\n")).toHaveLength(4);
  });

  it("handles missing/nonfinite results as unknown and quotes spreadsheet text safely", () => {
    const input = fixture();
    const drive = mockDriveAnalysis(input.config, input.driveSettings, null);
    drive.phase_resistance_ohm = Infinity;
    drive.phases[0].net = '=HYPERLINK("url")';
    drive.phases[0].self_inductance_h = NaN;
    input.drive = drive;
    expect(item(input, "Winding resistance per phase").source).toBe("Unknown");
    expect(phaseElectricalCsv(drive)).toContain("'=HYPERLINK(\"\"url\"\")");
    expect(phaseElectricalCsv(drive)).toContain('"Unknown"');
    expect(JSON.parse(powerModelSnapshot(input)).drive.phase_resistance_ohm).toBeNull();
  });
});

// Synthetic DTOs test report mapping only, not numerical solver validation.
function withMove(): PowerRequirementsInput {
  const input = fixture();
  input.moveRequest = { profile: { duration_s: 1, mass_includes: "Test assembly only", moving_mass_kg: 0.015,
    start_m: 0.0025, end_m: 0.0655, initial_velocity_m_s: 0, final_velocity_m_s: 0,
    travel_min_m: 0.0025, travel_max_m: 0.0655, max_speed_m_s: 0.5,
    max_acceleration_m_s2: 2, max_deceleration_m_s2: 2, coulomb_friction_n: 0.05, time_step_s: 0.001,
    external_load_n: 0, damping_n_s_per_m: 0 }, control: "balanced_star_sinusoidal",
    electrical_angle_at_zero_rad: 0, phase_peak_limit_a: 1,
    source: { boundary: "stiff_dc_link", accepts_regeneration: true }, additional_driver_loss_w: 0, force_positions: 65 };
  input.moveResult = { request_id: "test", input_sha256: "a".repeat(64), provenance: "simulated_not_measured",
    inputs: { topology: input.topology, config: input.config, drive: input.driveSettings, cad_geometry: input.cadGeometry, move_request: input.moveRequest },
    result: { drive: mockDriveAnalysis(input.config, input.driveSettings, null), full_overlap_bounds_m: [0.0025, 0.062833333],
      conductor_samples: 10, force_map_step_m: 0.001, meshing: 4,
      demand: { model_version: "report-test-only", source_model_scope: "partial_declared_scenario", profile: input.moveRequest.profile,
      electrical: { additional_driver_loss_w: 0, source_accepts_regeneration: true,
        winding: "balanced_star_sinusoidal", phase_resistance_hot_ohm: 1, effective_phase_inductance_h: 47e-6,
        electrical_period_m: 0.012, electrical_angle_at_zero_rad: 0, force_map: [], phase_peak_limit_a: 1,
        source_voltage_v: 12, voltage_headroom: 0.85, driver_path_resistance_ohm: 0.21 }, feasible: true,
      source: { sampled_positive_peak_power_w: 2, sampled_positive_peak_current_a: 1/6, average_power_w: 1,
        drawn_energy_j: 1.2, returned_energy_j: 0.2, net_energy_j: 1 },
      actual_time_step_s: 0.001, requested_distance_m: 0.063, sampled_phase_peak_a: 0.8, phase_rms_a: [0.4, 0.5, 0.6],
      sampled_requested_peak_speed_m_s: 0.1, sampled_requested_positive_acceleration_m_s2: 1,
      sampled_requested_negative_acceleration_m_s2: -1, achieved_distance_m: null, conduction_energy_j: 0.01,
      mechanical_work_j: 0.002, friction_damping_energy_j: 0.001, external_load_work_j: 0,
      kinetic_energy_change_j: 0, magnetic_energy_change_j: 0, capacitor_energy_change_j: 0,
      copper_energy_j: 0.1, mechanical_balance_residual_j: 1e-9, electrical_balance_residual_j: 2e-9,
      source_balance_residual_j: null, loss_energy: null, accounted_loss_energy_j: 0.11,
      phase_rms_including_declared_ripple_a: null, sampled_phase_peak_including_declared_ripple_a: null,
      limiting_factors: [], missing_inputs: [], notes: ["Synthetic report-mapping test, not engineering evidence."],
      samples: [{ time_s: 0, position_m: 0.0025, velocity_m_s: 0, acceleration_m_s2: 0, motor_force_n: 0,
        required_source_voltage_v: 12, required_source_current_a: 1/6, required_source_power_w: 2,
        q_current_phase_peak_a: 0.8, phase_currents_a: [0.8, -0.4, -0.4], required_phase_voltages_v: [1, -0.5, -0.5],
        required_line_voltage_v: 1.5, required_d_voltage_v: 0, required_q_voltage_v: 1,
        copper_loss_w: 0.1, driver_conduction_loss_w: 0.01, mechanical_power_w: 0,
        friction_damping_loss_w: 0, external_load_power_w: 0, kinetic_energy_j: 0, magnetic_energy_j: 1e-5,
        magnetic_power_w: 0, partial_dc_link_power_w: 1.9, losses: null }] } } };
  return input;
}

describe("move power report consistency", () => {
  it.skipIf(!process.env.PCB_MOTOR_SCREENING_RESULTS)("maps real native partial screening receipts without promoting omitted losses", () => {
    const root = process.env.PCB_MOTOR_SCREENING_RESULTS!;
    for (const design of ["fader", "star2"]) for (const scenario of ["full-forward", "short-forward", "short-return"]) {
      const records = JSON.parse(readFileSync(join(root, `${design}-${scenario}.json`), "utf8"));
      const native = records.at(-1);
      const source = native.result.demand.source;
      const input: PowerRequirementsInput = {
        config: native.inputs.config, driveSettings: native.inputs.drive,
        desiredTravelMm: 63, topology: native.inputs.topology,
        cadGeometry: native.inputs.cad_geometry, sweep: null, drive: native.result.drive,
        native: true, moveRequest: native.inputs.move_request, moveResult: native,
      };
      expect(currentMoveResult(input)).not.toBeNull();
      expect(item(input, "Peak supply power during a move").value).toBe("Unknown");
      const peak = `${Number(source.sampled_positive_peak_power_w.toPrecision(7))} W`;
      const net = `${Number(source.net_energy_j.toPrecision(7))} J`;
      expect(item(input, "Partial scenario peak source power").value).toBe(peak);
      expect(item(input, "Partial scenario net source energy").value).toBe(net);
      expect(powerReportMarkdown(powerRequirements(input))).toContain(peak);
      expect(powerRequirementsCsv(powerRequirements(input))).toContain(`"Partial scenario net source energy","${net}"`);
      expect(JSON.parse(powerModelSnapshot(input)).moveResult.result.demand.source).toEqual(source);
      const trace = moveTraceCsv(input)!;
      expect(trace).toContain('"required_source_power_W"');
      expect(trace).toContain('"simulated_not_measured"');
      if (scenario === "full-forward") expect(item(input, "Physical tracking findings").value).toBe("Imposed demand only");
      expect(item(input, "Source model scope").detail).toContain("omissions keep totals Unknown");
    }
  });

  it("maps native scenario values consistently to report, requirements CSV, snapshot and time-series CSV", () => {
    const input = withMove();
    const sections = powerRequirements(input);
    expect(item(input, "Partial scenario peak source power").value).toBe("2 W");
    expect(item(input, "Partial scenario net source energy").value).toBe("1 J");
    expect(item(input, "Peak supply power during a move").value).toBe("Unknown");
    expect(item(input, "Electrical energy per move").value).toBe("Unknown");
    expect(item(input, "Partial scenario peak source power").detail).toContain("not total supply power");
    expect(powerReportMarkdown(sections)).toContain("2 W");
    expect(powerRequirementsCsv(sections)).toContain('"Partial scenario net source energy","1 J"');
    expect(JSON.parse(powerModelSnapshot(input)).moveResult.result.demand.source.net_energy_j).toBe(1);
    const trace = moveTraceCsv(input)!;
    expect(trace).toContain('"required_source_power_W"');
    expect(trace).toContain('"required_source_voltage_V"');
    expect(trace).toContain('"phase_0_current_A"');
    expect(trace).toContain('"simulated_not_measured","true","0","0.0025"');
  });
  it("withholds engineering results and traces in browser/demo or for stale design/move/driver inputs", () => {
    for (const change of [(i: PowerRequirementsInput) => { i.native = false; },
      (i: PowerRequirementsInput) => { i.config = { ...i.config, supply_voltage_v: 24 }; },
      (i: PowerRequirementsInput) => { i.moveRequest = { ...i.moveRequest!, force_positions: 129 }; },
      (i: PowerRequirementsInput) => { i.driveSettings = { ...i.driveSettings, series_inductance_h: 0 }; },
      (i: PowerRequirementsInput) => { i.cadGeometry = { source_file_name: "changed.dxf", trace_width_mm: 0.2,
        layer_z_mm: [0], routing: { segments: [], curves: [], vias: [] } } as unknown as CadGeometry; }]) {
      const input = withMove(); change(input);
      expect(currentMoveResult(input)).toBeNull();
      expect(moveTraceCsv(input)).toBeNull();
      expect(JSON.parse(powerModelSnapshot(input)).moveResult).toBeNull();
    }
  });
  it("reports required demand separately from physical tracking findings", () => {
    const input = withMove();
    const m = input.moveResult!.result.demand;
    m.feasible = false;
    m.limiting_factors = ["Required voltage exceeds the physical DC link"];
    expect(item(input, "Peak supply power during a move").value).toBe("Unknown");
    expect(item(input, "Physical tracking findings").value).toBe("Imposed demand only");
    expect(item(input, "Partial scenario peak source power").value).toBe("2 W");
    expect(moveTraceCsv(input)).toContain('"simulated_not_measured","false"');
  });
});

function withDeclaredLosses(): PowerRequirementsInput {
  const input = withMove();
  const model = declaredLossFixture(input.driveSettings.driver.name, input.driveSettings.driver.rds_on_ohm);
  input.moveRequest!.additional_driver_loss_w = null;
  input.moveRequest!.loss_model = model;
  const m = input.moveResult!.result.demand;
  m.source_model_scope = "declared_loss_model";
  m.electrical.loss_model = model;
  m.electrical.additional_driver_loss_w = null;
  m.loss_energy = { winding_dc_ripple_energy_j: 0.00012, winding_ac_energy_j: 0.03756,
    external_series_energy_j: 0.075015, external_core_energy_j: 0.006,
    switching_energy_j: 0.013614, deadtime_energy_j: 0.003732, controller_energy_j: 0.02, other_dc_link_energy_j: 0.03 };
  m.accounted_loss_energy_j = 0.9; m.source_balance_residual_j = 1e-10;
  m.phase_rms_including_declared_ripple_a = [0.41, 0.51, 0.61];
  m.sampled_phase_peak_including_declared_ripple_a = 0.82;
  m.samples[0].losses = { mean_square_phase_current_a2: [0.6401, 0.1601, 0.1601],
    phase_peak_envelope_a: [0.82, 0.42, 0.42], winding_dc_ripple_loss_w: 0.00012,
    winding_ac_loss_w: 0.03756, external_series_loss_w: 0.075015, external_core_loss_w: 0.006,
    switching_loss_w: 0.013614, deadtime_loss_w: 0.003732, controller_loss_w: 0.02, other_dc_link_loss_w: 0.03 };
  return input;
}

describe("declared loss-model reports", () => {
  it("maps conditional total W/A/J and loss terms identically to UI sections, report, CSV and snapshot", () => {
    const input = withDeclaredLosses();
    const sections = powerRequirements(input);
    expect(item(input, "Peak supply power during a move").value).toBe("2 W");
    expect(item(input, "Average supply power over a move").value).toBe("1 W");
    expect(item(input, "Electrical energy per move").value).toBe("1 J");
    expect(item(input, "Guaranteed maximum source power").value).toBe("Unknown");
    expect(item(input, "Peak supply power during a move").detail).toContain("declared loss model");
    expect(item(input, "Source model scope").value).toBe("Declared loss-model total");
    expect(item(input, "Controller energy").value).toBe("0.02 J");
    expect(powerReportMarkdown(sections)).toContain("Declared loss-model total");
    expect(powerRequirementsCsv(sections)).toContain('"Electrical energy per move","1 J"');
    const snapshot = JSON.parse(powerModelSnapshot(input));
    expect(snapshot.sections).toEqual(sections);
    expect(snapshot.moveResult.result.demand.loss_energy.controller_energy_j).toBe(0.02);
    const trace = moveTraceCsv(input)!;
    expect(trace).toContain('"driver_deadtime_loss_W"');
    expect(trace).toContain('"phase_0_mean_square_current_A2"');
    expect(trace).toContain('"declared_loss_model"');
    expect(trace).toContain('"0.6401","0.1601","0.1601"');
  });
  it("never promotes idealized, incomplete, failed or browser results into total rows", () => {
    for (const mutate of [(i: PowerRequirementsInput) => { i.moveResult!.result.demand.electrical.loss_model!.basis = "idealized"; },
      (i: PowerRequirementsInput) => { i.moveResult!.result.demand.loss_energy = null; },
      (i: PowerRequirementsInput) => { i.moveResult!.result.demand.missing_inputs = ["Unknown core law"]; },
      (i: PowerRequirementsInput) => { i.native = false; }]) {
      const input = withDeclaredLosses(); mutate(input);
      expect(item(input, "Peak supply power during a move").value).toBe("Unknown");
      expect(item(input, "Electrical energy per move").value).toBe("Unknown");
    }
  });
  it("keeps complete-model required totals available despite tracking findings", () => {
    const input = withDeclaredLosses();
    input.moveResult!.result.demand.feasible = false;
    input.moveResult!.result.demand.limiting_factors = ["Physical voltage cannot track imposed motion"];
    expect(item(input, "Peak supply power during a move").value).toBe("2 W");
    expect(item(input, "Electrical energy per move").value).toBe("1 J");
    expect(item(input, "Physical tracking findings").value).toBe("Imposed demand only");
    expect(powerReportMarkdown(powerRequirements(input))).toContain("Physical voltage cannot track imposed motion");
  });
  it("invalidates totals and trace export after loss inputs change", () => {
    const input = withDeclaredLosses();
    input.moveRequest = structuredClone(input.moveRequest!);
    input.moveRequest.loss_model!.switching.constant_j = 9e-7;
    expect(currentMoveResult(input)).toBeNull();
    expect(moveTraceCsv(input)).toBeNull();
    expect(JSON.parse(powerModelSnapshot(input)).moveResult).toBeNull();
  });
});
