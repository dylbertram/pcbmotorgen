import { beforeEach, describe, it, expect, vi } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));
import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import { sampleSimulationVisualization } from "./simulationVisualization";
import type { VisualizationInput, VisualizationRequest } from "../types/simulationVisualization";

describe("native visualization IPC", () => {
  beforeEach(() => vi.resetAllMocks());
  it("has no fabricated browser field or heating fallback", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    await expect(sampleSimulationVisualization({} as VisualizationInput, {} as VisualizationRequest)).rejects.toThrow("No browser substitute");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("passes actual source configuration, drive, imported geometry and explicit XYZ request", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    const input = { config: { actual: true }, drive: { actual: true }, cadGeometry: null } as unknown as VisualizationInput;
    const request = { request_id: "exact-xyz" } as VisualizationRequest;
    await sampleSimulationVisualization(input, request);
    expect(invoke).toHaveBeenCalledWith("sample_simulation_visualization", { config: input.config, driveSettings: input.drive, cadGeometry: null, request });
  });
});
