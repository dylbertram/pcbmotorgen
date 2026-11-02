/** KiCad board operations. Native errors propagate; mocks are browser-only. */

import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cad/cadMapping";
import type {
  CadGeometry,
  LinearMotorConfig,
  KicadConnection,
  KicadWriteResult,
  BoardDiagnostics,
  PreconditionWarning,
  CoilPreview,
} from "../types";
import { isTauriAvailable } from "./core";
import {
  mockBoardDiagnostics,
  mockPreviewCoils,
  mockKicadConnection,
  mockKicadWrite,
} from "./kicadMocks";

export async function connectKicad(): Promise<KicadConnection> {
  if (!isTauriAvailable()) return mockKicadConnection();
  return await invoke<KicadConnection>("connect_kicad");
}

/**
 * Generate coils from the config and write them to the open KiCad board.
 *
 * Pass `dryRun: true` to count the items without sending a commit
 * (`commit_id === "(dry run - no commit)"`, `items_created === 0`). The
 * Rust side still establishes a KiCad connection in dry-run mode — it
 * just skips the `Commit` / `create_items` IPC. Use [`previewCoils`]
 * for a no-IPC dry run (useful when KiCad is not open).
 *
 * Native errors propagate to the caller instead of producing a mock result.
 */
export async function writeCoilsToBoard(
  config: LinearMotorConfig,
  dryRun: boolean = false,
  cadGeometry: CadGeometry | null = null,
): Promise<KicadWriteResult> {
  assertCadMapping(cadGeometry, config);
  if (!isTauriAvailable()) return mockKicadWrite();
  return await invoke<KicadWriteResult>("write_coils_to_board", {
    config,
    dryRun,
    cadGeometry,
  });
}

/**
 * Live snapshot of the open KiCad board (name, layer count, edge-cut
 * bounding box, net classes). Connects to KiCad each call — cache in the
 * UI if you need it more than once per write.
 */
export async function getBoardDiagnostics(): Promise<BoardDiagnostics> {
  if (!isTauriAvailable()) return mockBoardDiagnostics();
  return await invoke<BoardDiagnostics>("get_board_diagnostics");
}

/**
 * Compare the user's `config` against the live `diagnostics` and return
 * a list of precondition warnings (info / warning / error). The native
 * command uses the supplied diagnostics without contacting KiCad again.
 */
export async function validateWritePreconditions(
  config: LinearMotorConfig,
  diagnostics: BoardDiagnostics,
  cadGeometry: CadGeometry | null = null,
): Promise<PreconditionWarning[]> {
  assertCadMapping(cadGeometry, config);
  // No real board is available to validate in a browser preview.
  if (!isTauriAvailable()) return [];
  return await invoke<PreconditionWarning[]>("validate_write_preconditions", {
    config,
    diagnostics,
    cadGeometry,
  });
}

/**
 * Dry-run coil preview: builds the same PhaseCoil set the writer would
 * produce, and returns a per-layer tally (phase count, track count, via
 * count). No KiCad roundtrip — safe to call without KiCad running.
 */
export async function previewCoils(
  config: LinearMotorConfig,
  cadGeometry: CadGeometry | null = null,
): Promise<CoilPreview> {
  assertCadMapping(cadGeometry, config);
  if (!isTauriAvailable()) return mockPreviewCoils(config);
  return await invoke<CoilPreview>("preview_coils", { config, cadGeometry });
}
