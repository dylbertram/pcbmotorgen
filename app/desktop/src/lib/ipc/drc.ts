import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cad/cadMapping";
import type { CadGeometry, InterferenceViolation, LinearMotorConfig } from "../types";
import { isTauriAvailable } from "./core";

/** Check generated or imported copper using the configured trace and via rules. */
export async function checkCoilInterference(
  config: LinearMotorConfig,
  cadGeometry: CadGeometry | null = null,
): Promise<InterferenceViolation[]> {
  assertCadMapping(cadGeometry, config);
  if (!isTauriAvailable()) return [];
  return await invoke<InterferenceViolation[]>("check_coil_interference", {
    config,
    cadGeometry,
  });
}
