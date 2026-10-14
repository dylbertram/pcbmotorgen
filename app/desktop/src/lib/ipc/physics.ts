/**
 * Physics IPC calls with deterministic mock fallback.
 *
 * The UI schedules coil generation independently for the design reflection
 * and gates Simulation-tab calculations on the active tab. Their failure is
 * recoverable — the user just sees stale data. When the Tauri runtime is
 * missing (plain `vite dev`), the corresponding mock is returned instead.
 */

import { invoke } from "@tauri-apps/api/core";
import type {
  LinearMotorConfig,
  CoilPathDto,
  ForceSweepResult,
  StackupResultDto,
  HeightStackResultDto,
  FrictionBudgetDto,
  PowerBudgetDto,
  BFieldGridDto,
  TravelEnvelopeDto,
  MagnetGrade,
  DriveSettings,
  DriveAnalysis,
  CadGeometry,
} from "../types";
import { isTauriAvailable } from "./core";
import {
  mockCoils,
  mockForceSweep,
  mockHeightStack,
  mockPowerBudget,
  mockFriction,
  mockStackup,
  mockBFieldGrid,
  mockTravelEnvelope,
  mockMagnetGrades,
  mockDriveAnalysis,
} from "./mocks";

/**
 * Fetch the magnet-grade reference table (NdFeB) from the backend. The Rust
 * side reads `pcbmotorgen_simulation::magnet_grades`, the single source of
 * truth; the static TS table is only the offline/mock fallback.
 */
export async function fetchMagnetGrades(): Promise<MagnetGrade[]> {
  if (!isTauriAvailable()) return mockMagnetGrades();
  return await invoke<MagnetGrade[]>("get_magnet_grades");
}

export async function generateCoils(
  config: LinearMotorConfig,
): Promise<CoilPathDto> {
  if (!isTauriAvailable()) return mockCoils(config);
  return await invoke<CoilPathDto>("generate_coils", { config });
}

/** Travel limits of the mover array centre (see TravelEnvelopeDto). */
export async function fetchTravelEnvelope(
  config: LinearMotorConfig,
): Promise<TravelEnvelopeDto> {
  if (!isTauriAvailable()) return mockTravelEnvelope(config);
  return await invoke<TravelEnvelopeDto>("travel_envelope", { config });
}

/** Thrust sweep over the generated coils, or over `cadGeometry` when set. */
export async function evaluateForceSweep(
  config: LinearMotorConfig,
  cadGeometry: CadGeometry | null = null,
): Promise<ForceSweepResult> {
  if (!isTauriAvailable()) return mockForceSweep(config);
  return await invoke<ForceSweepResult>("evaluate_force_sweep", { config, cadGeometry });
}

export async function computeHeightStack(
  config: LinearMotorConfig,
): Promise<HeightStackResultDto> {
  if (!isTauriAvailable()) return mockHeightStack(config);
  return await invoke<HeightStackResultDto>("compute_height_stack", { config });
}

export async function computePowerBudget(
  config: LinearMotorConfig,
): Promise<PowerBudgetDto> {
  if (!isTauriAvailable()) return mockPowerBudget(config);
  return await invoke<PowerBudgetDto>("compute_power_budget", { config });
}

export async function computeFriction(
  config: LinearMotorConfig,
): Promise<FrictionBudgetDto> {
  if (!isTauriAvailable()) return mockFriction(config);
  return await invoke<FrictionBudgetDto>("compute_friction", { config });
}

/**
 * Driver suitability from the routed copper (analyze_drive). `kf` is the
 * force sweep's mean thrust per ampere; null skips the speed/thrust checks.
 */
export async function analyzeDrive(
  config: LinearMotorConfig,
  drive: DriveSettings,
  kf: number | null,
  cadGeometry: CadGeometry | null = null,
): Promise<DriveAnalysis> {
  if (!isTauriAvailable()) return mockDriveAnalysis(config, drive, kf);
  return await invoke<DriveAnalysis>("analyze_drive", {
    config,
    drive,
    thrustConstantNPerA: kf,
    cadGeometry,
  });
}

export async function computeStackup(
  config: LinearMotorConfig,
): Promise<StackupResultDto> {
  if (!isTauriAvailable()) return mockStackup(config);
  return await invoke<StackupResultDto>("compute_stackup", { config });
}

/**
 * Sample the B-field on an X–Z grid for the (fixed plain alternating)
 * magnet array.
 * Returns a flat row-major array (Z slow axis) of B-vectors + positions.
 *
 * Defaults: 24×12 grid, x = [0, active_area_length_m],
 * z = [0, air_gap + magnet_height + 2 mm] (a 2 mm window above the magnet top).
 */
export async function sampleBField(
  config: LinearMotorConfig,
  n_x: number = 24,
  n_z: number = 12,
  x_extent_m: [number, number] = [0, config.active_area_length_m],
  z_extent_m: [number, number] = [
    0,
    config.air_gap_m + config.magnet_height_m + 2e-3,
  ],
): Promise<BFieldGridDto> {
  if (!isTauriAvailable()) {
    return mockBFieldGrid(config, n_x, n_z, x_extent_m, z_extent_m);
  }
  return await invoke<BFieldGridDto>("sample_b_field", {
    config,
    nX: n_x,
    nZ: n_z,
    xExtentM: x_extent_m,
    zExtentM: z_extent_m,
  });
}
