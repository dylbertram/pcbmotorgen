import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import { assertCadMapping } from "../cadMapping";
import type { LinearMotorConfig, DriveSettings, CadGeometry } from "../types";
import type { DcApplicability, DcCapability, DcJobStatus, DcStudy } from "../types/dcCoupling";

function requireDesktop() {
  if (!isTauriAvailable()) throw new Error("DC coupling requires the configured experimental desktop worker. Browser previews do not substitute forces.");
}

export async function dcCouplingCapability(): Promise<DcCapability> {
  if (!isTauriAvailable()) return { available: false, reason: "DC coupling requires the configured experimental desktop worker." };
  return invoke<DcCapability>("dc_coupling_capability");
}

export async function startDcCoupling(
  config: LinearMotorConfig, driveSettings: DriveSettings, cadGeometry: CadGeometry | null, study: DcStudy,
): Promise<DcJobStatus> {
  requireDesktop();
  assertCadMapping(cadGeometry, config);
  return invoke<DcJobStatus>("start_dc_coupling", { config, driveSettings, cadGeometry, study });
}

export async function inspectDcCoupling(
  config: LinearMotorConfig, driveSettings: DriveSettings, cadGeometry: CadGeometry | null, study: DcStudy,
): Promise<DcApplicability> {
  requireDesktop();
  assertCadMapping(cadGeometry, config);
  return invoke<DcApplicability>("inspect_dc_coupling", { config, driveSettings, cadGeometry, study });
}

export async function dcCouplingStatus(jobId: string): Promise<DcJobStatus> {
  requireDesktop();return invoke<DcJobStatus>("dc_coupling_status", { jobId });
}

export async function cancelDcCoupling(jobId: string): Promise<DcJobStatus> {
  requireDesktop();return invoke<DcJobStatus>("cancel_dc_coupling", { jobId });
}
