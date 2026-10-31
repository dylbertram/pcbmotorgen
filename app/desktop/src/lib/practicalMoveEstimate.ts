import type { DriveAnalysis, DriveSettings, LinearMotorConfig } from "./types";
import type { DeclaredLossModel, PhaseValues, PhaseMatrix } from "./types/moveLosses";

/** Construct a declaration only. Native code still performs all move physics. */
export function practicalMoveEstimate(config: LinearMotorConfig, settings: DriveSettings, drive: DriveAnalysis): DeclaredLossModel {
  const external = settings.series_inductance_h;
  if (config.supply_voltage_v !== 12 || settings.pwm_hz !== 100000 || settings.driver.name !== "DRV8311"
      || settings.driver.rds_on_ohm !== 0.21 || (external !== 0 && external !== 47e-6)
      || drive.bus_voltage_v !== 12 || drive.pwm_hz !== settings.pwm_hz || drive.driver_name !== settings.driver.name
      || drive.series_inductance_h !== external || drive.phases.length !== 3 || drive.phases.some(p => !p.connected)
      || new Set(drive.phases.map(p => p.net)).size !== 3
      || config.backplane && (config.backplane.layers.length > 0 || config.backplane.housing != null)) {
    throw new Error("The estimate requires current native DRV8311 analysis at 12 V and 100 kHz, 0.21 Ω driver path, three connected phases, 0 or 47 µH per phase, and no backplane or housing.");
  }
  const thickness = config.pcb_stackup ? Math.max(...config.pcb_stackup.copper_m) : Math.max(drive.outer_copper_m, drive.inner_copper_m);
  const period = 2 * config.magnet_pitch_m;
  const rho = 1.724e-8 * (1 + 0.00393 * (settings.winding_temp_c - 20));
  const resistances = drive.phases.map(p => p.resistance_hot_ohm) as PhaseValues;
  if (![drive.effective_inductance_h, drive.phase_resistance_ohm, thickness, period, rho, ...resistances].every(v => Number.isFinite(v) && v > 0))
    throw new Error("A current native electrical analysis with finite copper resistance and inductance is required.");
  const hotDcr = external ? 0.0741 * (1 + 0.00393 * (settings.winding_temp_c - 25)) : 0;
  if (!Number.isFinite(hotDcr) || hotDcr < 0) throw new Error("The assumed inductor temperature is outside the model.");
  const phaseR = drive.phase_resistance_ohm + hotDcr + settings.driver.rds_on_ohm / 2;
  const pp = 12 / (2 * phaseR) * Math.tanh(phaseR / (4 * 100000 * drive.effective_inductance_h));
  const diag = 2 * pp ** 2 / 36;
  const covariance = Array.from({ length: 3 }, (_, i) => Array.from({ length: 3 }, (_, j) => i === j ? diag : -diag / 2)) as PhaseMatrix;
  const skin = (frequency: number): number => {
    const delta = Math.sqrt(rho / (Math.PI * frequency * 4 * Math.PI * 1e-7));
    const a = thickness / (2 * delta);
    return a < 0.01 ? 4 * a ** 4 / 45 : a * (Math.sinh(2 * a) + Math.sin(2 * a)) / (Math.cosh(2 * a) - Math.cos(2 * a)) - 1;
  };
  const fundamental = skin(1 / period), ripple = skin(100000);
  const qExtra = external ? Math.max(0, 2 * Math.PI * 100000 * external / 20 - 0.0741) : 0;
  const qWatts = qExtra * 2 / 3 * (Math.sqrt(8) / Math.PI ** 2 * pp) ** 2;
  const phase = (v: number): PhaseValues => [v, v, v];
  const reference = "Explicit engineering estimate, not a measured or complete hardware total: TI DRV8311 SLVSFN2B sections 7.5/12.3.1, 25 °C driver, assumed SLEW=01, DEADTIME=001, 0.7 V diode drop and sinusoidal cycle-average mapping; Bourns SRP1265WA-470M 47 µH Q=20 at 100 kHz/1 V and 74.1 mΩ typical DCR at 25 °C; inductor temperature assumed equal to winding. Q excess is combined AC-loss proxy, not isolated core loss. Isolated copper slab uses full-network DC resistance as proxy; proximity and via AC distribution omitted. 12 V stiff DC-link boundary excludes upstream wiring and board-level loads. Not a guaranteed bound or hardware qualification. Sources: https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-C826F7E8-19E5-47C8-9C09-E13912428538 and https://www.bourns.com/docs/product-datasheets/srp1265wa.pdf";
  return {
    basis: "engineering_estimate", reference,
    domain: { driver_name: settings.driver.name, source_voltage_v: 12, pwm_hz: 100000, winding_temp_c: settings.winding_temp_c,
      driver_path_resistance_ohm: 0.21, max_phase_peak_a: 20, max_speed_m_s: 1,
      geometry: { phase_resistance_hot_ohm: resistances, effective_phase_inductance_h: drive.effective_inductance_h,
        copper_thickness_m: thickness, electrical_period_m: period } },
    phase_names: drive.phases.map(p => p.net) as [string, string, string],
    winding_fundamental_ac_increment_ohm: resistances.map(r => r * fundamental) as PhaseValues,
    winding_ripple_ac_increment_ohm: resistances.map(r => r * ripple) as PhaseValues,
    external_series_resistance_ohm: phase(hotDcr), external_core_loss_w: phase(qWatts),
    ripple: { covariance_a2: covariance, peak_deviation_a: phase(pp / 2), reference: `50%-duty two-phase RL p-p used as triangular phase-pair mixture; Lphase=${drive.effective_inductance_h} H, Rphase=${phaseR} Ω, pp=${pp} A. Approximate, not actual PWM or universal bound.` },
    switching: { constant_j: 0, abs_mean_current_j_per_a: Math.PI / (2 * Math.sqrt(2)) * 12 * (0.6 * 12 / 75e6), mean_square_current_j_per_a2: 0 },
    deadtime: { constant_j: 0, abs_mean_current_j_per_a: Math.PI / Math.sqrt(2) * 0.7 * 200e-9, mean_square_current_j_per_a2: 0 },
    controller_power_w: 12 * (0.010 + (0.012 - 0.010) * (75000 / 175000)), other_dc_link_power_w: 0,
    omitted_losses: ["Winding proximity and via-specific AC loss not represented by isolated slab approximation",
      "Inductor AC loss outside 100 kHz fundamental and bias/temperature effects not characterized",
      "Board-level controller/regulator and source wiring consumption not specified"],
  };
}
