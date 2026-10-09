import { invoke } from "@tauri-apps/api/core";
import type {
  DxfExportResult,
  KicadWriteResult,
  SensorConfig,
  SensorGeometry,
} from "../types";
import { isTauriAvailable } from "./core";

function requireDesktop(): void {
  if (!isTauriAvailable()) {
    throw new Error("Sensor geometry and exports require the desktop app.");
  }
}

export async function generateSensorGeometry(
  config: SensorConfig,
): Promise<SensorGeometry> {
  requireDesktop();
  return await invoke<SensorGeometry>("generate_sensor_geometry", { config });
}

export async function exportSensorDxf(
  config: SensorConfig,
): Promise<DxfExportResult> {
  requireDesktop();
  return await invoke<DxfExportResult>("export_sensor_dxf", { config });
}

export async function writeSensorToBoard(
  config: SensorConfig,
  dryRun = false,
): Promise<KicadWriteResult> {
  requireDesktop();
  return await invoke<KicadWriteResult>("write_sensor_to_board", {
    config,
    dryRun,
  });
}
