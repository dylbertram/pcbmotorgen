import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { DEFAULT_SENSOR_CONFIG } from "../types";
import { isTauriAvailable } from "./core";
import { exportSensorDxf, generateSensorGeometry, writeSensorToBoard } from "./sensor";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", async (original) => ({
  ...await original<typeof import("./core")>(),
  isTauriAvailable: vi.fn(),
}));

beforeEach(() => vi.resetAllMocks());

describe("sensor IPC boundary", () => {
  it("rejects browser requests without fabricating geometry or export results", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    for (const request of [
      () => generateSensorGeometry(DEFAULT_SENSOR_CONFIG),
      () => exportSensorDxf(DEFAULT_SENSOR_CONFIG),
      () => writeSensorToBoard(DEFAULT_SENSOR_CONFIG, true),
    ]) await expect(request()).rejects.toThrow("require the desktop app");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("forwards the exact configuration and dry-run flag to native commands", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    const config = { ...DEFAULT_SENSOR_CONFIG, lambda_mm: 240 };
    await generateSensorGeometry(config);
    await exportSensorDxf(config);
    await writeSensorToBoard(config, true);
    await writeSensorToBoard(config);
    expect(vi.mocked(invoke).mock.calls).toEqual([
      ["generate_sensor_geometry", { config }],
      ["export_sensor_dxf", { config }],
      ["write_sensor_to_board", { config, dryRun: true }],
      ["write_sensor_to_board", { config, dryRun: false }],
    ]);
  });

  it("surfaces native errors instead of substituting a preview", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    vi.mocked(invoke).mockRejectedValue(new Error("Native sensor error"));
    for (const request of [
      () => generateSensorGeometry(DEFAULT_SENSOR_CONFIG),
      () => exportSensorDxf(DEFAULT_SENSOR_CONFIG),
      () => writeSensorToBoard(DEFAULT_SENSOR_CONFIG),
    ]) await expect(request()).rejects.toThrow("Native sensor error");
  });
});
