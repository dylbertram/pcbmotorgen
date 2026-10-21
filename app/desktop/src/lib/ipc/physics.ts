/**
 * Physics IPC calls with deterministic mock fallback.
 *
 * The UI schedules coil generation independently for the design reflection
 * and gates Simulation-tab calculations on the active tab. Errors propagate
 * so controllers clear old results. Some legacy previews have a browser-only
 * mock; housing motion and the periodic reference never fabricate one.
 */

import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cadMapping";
import { driverConnectionError, usesDeltaConnection } from "../driverConnection";
import type {
  LinearMotorConfig,
  CoilPathDto,
  ForceSweepResult,
  HeightStackResultDto,
  FrictionBudgetDto,
  BFieldGridDto,
  TravelEnvelopeDto,
  MagnetGrade,
  DriveSettings,
  DriveAnalysis,
  CadGeometry,
} from "../types";
import type { HousingMotionAnalysis } from "../types/drive";
import { isTauriAvailable } from "./core";
import type { PeriodicStaticReference } from "../types/periodicReference";
import {
  mockCoils,
  mockForceSweep,
  mockHeightStack,
  mockFriction,
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
  drive: DriveSettings | null = null,
): Promise<ForceSweepResult> {
  assertCadMapping(cadGeometry, config);
  if (cadGeometry?.terminal_connection === "delta") throw new Error("Imported delta force analysis is not available. Select Star (wye) coil terminals.");
  if (!drive) throw new Error("Force analysis requires explicit drive settings matching driver analysis.");
  if (!isTauriAvailable()) return mockForceSweep(config);
  return await invoke<ForceSweepResult>("evaluate_force_sweep", { config, cadGeometry, drive });
}

export async function computeHeightStack(
  config: LinearMotorConfig,
): Promise<HeightStackResultDto> {
  if (!isTauriAvailable()) return mockHeightStack(config);
  return await invoke<HeightStackResultDto>("compute_height_stack", { config });
}

/** No mock fallback: a reference result must come from the real solver. */
export async function periodicBackplaneReference(
  config: LinearMotorConfig,
): Promise<PeriodicStaticReference> {
  if (!isTauriAvailable()) {
    throw new Error("The periodic reference requires the desktop app. Browser previews do not run this solver.");
  }
  return await invoke<PeriodicStaticReference>("periodic_backplane_reference", { config });
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
  assertCadMapping(cadGeometry, config);
  const delta = cadGeometry ? cadGeometry.terminal_connection === "delta" : usesDeltaConnection(config);
  const connectionError = driverConnectionError(drive.driver, delta);
  if (connectionError) throw new Error(connectionError);
  if (!isTauriAvailable()) return mockDriveAnalysis(config, drive, kf);
  return await invoke<DriveAnalysis>("analyze_drive", {
    config,
    drive,
    thrustConstantNPerA: kf,
    cadGeometry,
  });
}

/** Independent PM/housing capability. Never fabricates a browser substitute. */
export async function analyzeHousingMotion(
  config: LinearMotorConfig,
  profile: { duration_s: number },
  speed: number,
  cadGeometry: CadGeometry | null = null,
): Promise<HousingMotionAnalysis> {
  assertCadMapping(cadGeometry, config);
  if (!isTauriAvailable()) {
    throw new Error("Housing motion estimates require the desktop app. Browser previews do not substitute physics results.");
  }
  return await invoke<HousingMotionAnalysis>("analyze_housing_motion", { config, profile, speed, cadGeometry });
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
