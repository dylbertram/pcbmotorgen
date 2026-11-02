/**
 * Physics IPC calls for previews and simulation analysis.
 *
 * The UI schedules coil generation separately from simulation. Errors
 * propagate so controllers clear old results. Some legacy previews have a browser-only
 * mock; housing motion and the periodic reference never fabricate one.
 * Native-only move-power commands live in `movePower.ts`.
 */

import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cad/cadMapping";
import { driverConnectionError, usesDeltaConnection } from "../driver/driverConnection";
import type {
  LinearMotorConfig,
  CoilPathDto,
  ForceSweepResult,
  HeightStackResultDto,
  TravelEnvelopeDto,
  MagnetGrade,
  DriveSettings,
  DriveAnalysis,
  CadGeometry,
} from "../types";
import type { HousingMotionAnalysis } from "../types/drive";
import { isTauriAvailable } from "./core";
import { orientCoilPreview } from "../routing/routingOrientation";
import type { PeriodicStaticReference } from "../types/periodicReference";
import { PLACEHOLDER_TRAVEL_ENVELOPE } from "../simulation/travelEnvelopePlaceholder";
import { mockHeightStack } from "./heightStackMock";
import { mockForceSweep } from "./forceSweepMock";
import { mockDriveAnalysis } from "./driveAnalysisMock";
import { mockCoils } from "./coilPreviewMock";
import { MAGNET_GRADES } from "../types/magnets";

/**
 * Fetch the magnet-grade reference table (NdFeB) from the backend. The Rust
 * side reads `pcbmotorgen_simulation::magnet_grades`, the single source of
 * truth; the static TS table is only the offline/mock fallback.
 */
export async function fetchMagnetGrades(): Promise<MagnetGrade[]> {
  if (!isTauriAvailable()) return Object.values(MAGNET_GRADES).map((grade) => ({ ...grade }));
  return await invoke<MagnetGrade[]>("get_magnet_grades");
}

export async function generateCoils(
  config: LinearMotorConfig,
): Promise<CoilPathDto> {
  if (!isTauriAvailable()) return orientCoilPreview(mockCoils(config), config);
  return await invoke<CoilPathDto>("generate_coils", { config });
}

/** Travel limits of the mover array centre (see TravelEnvelopeDto). */
export async function fetchTravelEnvelope(
  config: LinearMotorConfig,
): Promise<TravelEnvelopeDto> {
  if (!isTauriAvailable()) return PLACEHOLDER_TRAVEL_ENVELOPE;
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
