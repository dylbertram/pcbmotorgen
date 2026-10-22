import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import type { VisualizationInput, VisualizationRequest, VisualizationReport } from "../types/simulationVisualization";

/** Never fabricate field or heating data in a browser preview. */
export async function sampleSimulationVisualization(input: VisualizationInput, request: VisualizationRequest): Promise<VisualizationReport> {
  if (!isTauriAvailable()) throw new Error("3D fields and losses require the desktop's native calculations. No browser substitute is shown.");
  return invoke<VisualizationReport>("sample_simulation_visualization", {
    config: input.config, driveSettings: input.drive, cadGeometry: input.cadGeometry, request,
  });
}
