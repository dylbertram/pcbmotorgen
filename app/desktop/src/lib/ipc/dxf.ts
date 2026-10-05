/**
 * DXF export IPC + native file dialog helpers.
 */

import { invoke } from "@tauri-apps/api/core";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import type { CadGeometry, CadImportResult, LinearMotorConfig, DxfExportResult } from "../types";
import { isTauriAvailable } from "./core";
import { mockDxfExportResult } from "./mocks";

/**
 * Open the native file picker restricted to generator plugin types. The
 * kind is inferred from the chosen file's extension rather than
 * pre-selected. Throws when the Tauri backend is unavailable.
 */
export async function openFileDialog(): Promise<string | null> {
  if (!isTauriAvailable()) {
    throw new Error("Tauri backend unavailable");
  }
  // Accept every supported generator file type up front.
  const filters = [
    {
      name: "Generator plugin (native crate / Python runner)",
      extensions: ["dylib", "so", "dll", "py"],
    },
  ];
  return await openDialog({ filters });
}

/**
 * Generate coil geometry from the config and return it as a DXF R12 ASCII
 * string for CAD/CAM import. The returned `dxf_content` is a complete,
 * self-contained `.dxf` file — the caller writes it to disk.
 *
 * Uses the same coil generation path as `writeCoilsToBoard` so the DXF
 * geometry matches what gets written to KiCad.
 */
export async function exportCoilsDxf(
  config: LinearMotorConfig,
): Promise<DxfExportResult> {
  if (!isTauriAvailable()) return mockDxfExportResult(config);
  return await invoke<DxfExportResult>("export_coils_dxf", { config });
}

const CAD_FILE_FILTERS = [{ name: "CAD DXF (*.dxf)", extensions: ["dxf"] }];

export async function pickCadDxfPath(): Promise<string | null> {
  if (!isTauriAvailable()) throw new Error("CAD import requires the desktop app");
  return await openDialog({ multiple: false, filters: CAD_FILE_FILTERS });
}

export async function importCadDxf(
  path: string,
  unitsToMm: number,
  zToleranceMm: number,
  defaultTraceWidthMm: number,
  legacyLayerCount: number,
  legacyPcbThicknessMm: number,
): Promise<CadImportResult> {
  if (!isTauriAvailable()) throw new Error("CAD import requires the desktop app");
  return await invoke<CadImportResult>("import_cad_dxf", {
    path,
    unitsToMm,
    zToleranceMm,
    defaultTraceWidthMm,
    legacyLayerCount,
    legacyPcbThicknessMm,
  });
}

export async function exportCadGeometryDxf(geometry: CadGeometry): Promise<DxfExportResult> {
  if (!isTauriAvailable()) throw new Error("CAD export requires the desktop app");
  return await invoke<DxfExportResult>("export_cad_geometry_dxf", { geometry });
}
