import { describe, expect, it } from "vitest";
import { ConfigStore } from "./stores/config.svelte";
import { mockDriveAnalysis, mockForceSweep } from "./ipc/mocks";
import type { CadGeometry } from "./types";
import { powerRequirements, powerReportMarkdown, powerRequirementsCsv, powerModelSnapshot, forceSweepCsv, phaseElectricalCsv, type PowerRequirementsInput } from "./powerRequirements";

// Inputs transcribed from the user's Fader-traces-workspace.pmmotor. This
// fixture deliberately does not claim to reproduce its imported trace solver.
function fixture(): PowerRequirementsInput {
  const config = new ConfigStore();
  Object.assign(config, { desired_travel_mm: 63, active_area_width_mm: 8,
    magnet_count: 5, magnet_width_mm: 5, magnet_cross_width_mm: 5,
    magnet_height_mm: 3, electrical_pitch_mm: 12, supply_voltage_v: 12,
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
    expect(item(input, "Configured carriage mass").detail).toContain("fader cap is unknown");
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
      expect(content).not.toMatch(/scribble|LED|USB|grid|adapter|17 faders|60 W|haptic|65 mm|1\.15 A|Source and dependencies|Remaining system decisions/i);
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
