import { describe, expect, it } from "vitest";
import { ConfigStore } from "./stores/config.svelte";
import { mockDriveAnalysis } from "./ipc/mocks";
import { buildMoveRequest, defaultMoveForm, type MoveDesignDefaults } from "./moveForm";
import { summariseMove } from "./moveSummary";
import { moveReportHtml, moveReportMarkdown } from "./moveReport";
import type { NativeMoveResult, MovePowerSample, RoutedMoveRequest } from "./types/movePower";

const design: MoveDesignDefaults = { fullTravelMm: 63, magnetWidthMm: 4, massG: 15, frictionN: 0.05, massSource: "assembly" };

function request(toMm = 60): RoutedMoveRequest {
  const form = defaultMoveForm(design);
  form.toMm = toMm;
  return buildMoveRequest(form, { design });
}

function sample(time: number, sourcePower: number | null, partial: number, lineV = 3): MovePowerSample {
  return {
    time_s: time, position_m: 0.002 + time * 0.1, velocity_m_s: 0.2, acceleration_m_s2: 1,
    motor_force_n: 0.07, q_current_phase_peak_a: 0.35, phase_currents_a: [0.35, -0.17, -0.17],
    required_q_voltage_v: 1.7, required_d_voltage_v: 0, required_line_voltage_v: lineV,
    required_phase_voltages_v: [1, -0.5, -0.5], mechanical_power_w: 0.014, copper_loss_w: 0.8,
    driver_conduction_loss_w: 0.02, friction_damping_loss_w: 0.01, external_load_power_w: 0,
    kinetic_energy_j: 0, magnetic_energy_j: 0, magnetic_power_w: 0, partial_dc_link_power_w: partial,
    required_source_voltage_v: 12, required_source_current_a: sourcePower === null ? null : sourcePower / 12,
    required_source_power_w: sourcePower,
  } as MovePowerSample;
}

function result(options: { scope?: "engineering_estimate" | "partial_declared_scenario"; source?: boolean; omissions?: string[]; voltage?: number } = {}): NativeMoveResult {
  const scope = options.scope ?? "engineering_estimate";
  const includeSource = options.source ?? true;
  const req = request();
  const config = new ConfigStore();
  const settings = { ...config.drive, series_inductance_h: 64e-6 };
  const ipc = config.toIpc();
  const drive = mockDriveAnalysis(ipc, settings, null);
  const samples = [sample(0, includeSource ? 1 : null, 0.9), sample(0.25, includeSource ? 1.16 : null, 0.88, options.voltage ?? 3), sample(0.5, includeSource ? 1.1 : null, 0.6)];
  const energy = 0.35;
  return {
    request_id: "fixture", input_sha256: "a".repeat(64), provenance: "simulated_not_measured",
    inputs: { topology: "linear", config: ipc, drive: settings, cad_geometry: null, move_request: req },
    result: {
      drive, full_overlap_bounds_m: [0.002, 0.062], conductor_samples: 100, force_map_step_m: 0.0005, meshing: 12,
      demand: {
        model_version: "fixture", source_model_scope: scope,
        profile: { ...req.profile, mass_includes: "Full moving assembly estimate" },
        electrical: {
          winding: "balanced_star_sinusoidal", phase_resistance_hot_ohm: 4.49, effective_phase_inductance_h: 69.25e-6,
          electrical_period_m: 0.012, electrical_angle_at_zero_rad: Math.PI / 2, force_map: [], phase_peak_limit_a: 0,
          source_voltage_v: 12, voltage_headroom: 0.85, driver_path_resistance_ohm: 0.21,
          additional_driver_loss_w: null, source_accepts_regeneration: true,
          loss_model: scope === "engineering_estimate" ? { reference: "Estimator fixture", ripple: { reference: "Ripple fixture" } } : null,
        } as never,
        actual_time_step_s: 0.00025, feasible: (options.voltage ?? 3) <= 12,
        limiting_factors: (options.voltage ?? 3) > 12 ? ["Required line voltage exceeds the physical DC-link voltage; demand is calculated for imposed motion, not achieved tracking"] : [],
        missing_inputs: (options.omissions ?? []).map(item => `Declared omitted loss: ${item}`),
        requested_distance_m: 0.06, sampled_requested_peak_speed_m_s: 0.225,
        sampled_requested_positive_acceleration_m_s2: 1.39, sampled_requested_negative_acceleration_m_s2: -1.39,
        achieved_distance_m: null, sampled_phase_peak_a: 0.357, phase_rms_a: [0.16, 0.19, 0.19],
        copper_energy_j: 0.22, conduction_energy_j: 0.005, mechanical_work_j: 0.003, friction_damping_energy_j: 0.003,
        external_load_work_j: 0, kinetic_energy_change_j: 0, magnetic_energy_change_j: 0, capacitor_energy_change_j: 0,
        mechanical_balance_residual_j: 0, electrical_balance_residual_j: 0, source_balance_residual_j: includeSource ? 0 : null,
        loss_energy: null, accounted_loss_energy_j: 0.23,
        phase_rms_including_declared_ripple_a: scope === "engineering_estimate" ? [0.17, 0.2, 0.2] : null,
        sampled_phase_peak_including_declared_ripple_a: scope === "engineering_estimate" ? 0.464 : null,
        source: includeSource ? {
          sampled_positive_peak_power_w: 1.16, sampled_positive_peak_current_a: 1.16 / 12,
          average_power_w: 0.7, drawn_energy_j: 0.35, returned_energy_j: 0, net_energy_j: energy,
        } : null,
        notes: ["Imposed motion fixture."], samples,
      },
    },
  } as unknown as NativeMoveResult;
}

describe("move summary", () => {
  it("leads with the estimate and says what it does not include", () => {
    const summary = summariseMove(result({ omissions: ["External series inductor DCR and core loss are unspecified for 64.000 µH per phase; they are excluded from the reported power"] }));
    expect(summary.scope).toBe("Engineering estimate");
    expect(summary.headline).toEqual({ peakPower: "1.16 W", averagePower: "700 mW", energy: "350 mJ", peakSupplyCurrent: "96.7 mA" });
    expect(summary.omissions).toEqual(["External series inductor DCR and core loss are unspecified for 64.000 µH per phase; they are excluded from the reported power"]);
    expect(summary.checks.find(c => c.label === "Winding temperature rise")?.status).toBe("unknown");
    expect(summary.checks.find(c => c.label === "External inductor losses")?.status).toBe("unknown");
    expect(summary.checks.find(c => c.label === "Copper and magnet overlap")?.status).toBe("pass");
  });

  it("labels a motor-and-FET result partial instead of a total", () => {
    const summary = summariseMove(result({ scope: "partial_declared_scenario", source: false }));
    expect(summary.scope).toBe("Partial estimate");
    expect(summary.hasCompleteModel).toBe(false);
    expect(summary.scopeText).toContain("not total supply demand");
  });

  it("reports a voltage shortfall as a failed finding", () => {
    const summary = summariseMove(result({ voltage: 18 }));
    const voltage = summary.checks.find(c => c.label === "Voltage for this move");
    expect(voltage?.status).toBe("fail");
    expect(voltage?.reading).toContain("18.0 V required of 12.0 V");
  });

  it("carries recorded exclusions into the result", () => {
    const summary = summariseMove(result(), { exclusions: ["Backplane and housing are left out of this calculation."] });
    expect(summary.exclusions).toEqual(["Backplane and housing are left out of this calculation."]);
  });
});

describe("move report", () => {
  it("uses the same summary values and escapes design text", () => {
    const summary = summariseMove(result());
    const meta = {
      designName: "Fader <script>alert(1)</script>", geometrySource: "Generated infinity-braid",
      appVersion: "0.5.0", inputSha256: "b".repeat(64), driverName: "DRV8311",
      supplyVoltageV: 12, pwmHz: 100000, windingTempC: 75, modelVersion: "linear-move-demand-v12",
      generatedAt: "2026-11-01T00:00:00.000Z", request: request(),
    };
    const html = moveReportHtml(summary, meta);
    expect(html).toContain("1.16 W");
    expect(html).toContain("700 mW");
    expect(html).toContain("Engineering estimate");
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
    const markdown = moveReportMarkdown(summary, meta);
    expect(markdown).toContain("| Peak supply power | 1.16 W |");
    expect(markdown).toContain("## Findings");
  });
});
