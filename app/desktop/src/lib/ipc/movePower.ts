import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cad/cadMapping";
import type { MovePowerInputs, NativeMoveResult } from "../types/movePower";
import { isTauriAvailable } from "./core";

/** No browser mock: engineering move traces require the actual native model. */
export async function evaluateMovePower(requestId: string, inputs: MovePowerInputs): Promise<NativeMoveResult> {
  if (!isTauriAvailable()) throw new Error("Move power requires the desktop app; browser previews do not produce engineering traces.");
  if (inputs.topology !== "linear") throw new Error("Move power supports one linear track, not rotary motion.");
  assertCadMapping(inputs.cad_geometry, inputs.config);
  return await invoke<NativeMoveResult>("evaluate_move_power", { requestId, inputs });
}

export async function cancelMovePower(requestId: string): Promise<boolean> {
  if (!isTauriAvailable()) return false;
  return await invoke<boolean>("cancel_move_power", { requestId });
}
