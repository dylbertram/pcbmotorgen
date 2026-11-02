/**
 * DXF export IPC + native file dialog helpers.
 */

import { invoke } from "@tauri-apps/api/core";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import type { CadGeometry, CadImportResult, LinearMotorConfig, DxfExportResult } from "../types";
import { isTauriAvailable } from "./core";

/** Browser-only DXF skeleton, explicitly marked as having no backend. */
function mockDxfExportResult(config: LinearMotorConfig): DxfExportResult {
  const dxf_content = [
    "0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
    "0", "SECTION", "2", "ENTITIES", "0", "TEXT", "8", "Notes", "10", "0.0",
    "20", "0.0", "40", "3.0", "1",
    `(Mock DXF — backend not connected. Config: ${config.routing_pattern}, ${config.num_layers} layers)`,
    "0", "ENDSEC", "0", "EOF", "",
  ].join("\n");
  return {
    dxf_content,
    summary: { total_lines: 0, total_arcs: 0, total_circles: 0, layer_count: 1 },
  };
}

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
  sourceLayerCoils: Record<string, string> = {},
  preferDetectedUnits = false,
): Promise<CadImportResult> {
  if (!isTauriAvailable()) throw new Error("CAD import requires the desktop app");
  return await invoke<CadImportResult>("import_cad_dxf", {
    path,
    unitsToMm,
    zToleranceMm,
    defaultTraceWidthMm,
    legacyLayerCount,
    legacyPcbThicknessMm,
    sourceLayerCoils,
    preferDetectedUnits,
  });
}

export async function exportCadGeometryDxf(geometry: CadGeometry): Promise<DxfExportResult> {
  if (!isTauriAvailable()) throw new Error("CAD export requires the desktop app");
  return await invoke<DxfExportResult>("export_cad_geometry_dxf", { geometry });
}

export async function editableCoilGeometry(config: LinearMotorConfig): Promise<CadGeometry> {
  if (!isTauriAvailable()) throw new Error("Editing generated segments requires the desktop app");
  return await invoke<CadGeometry>("editable_coil_geometry", { config });
}
