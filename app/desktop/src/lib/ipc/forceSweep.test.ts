import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import type { DriveSettings, ForceSweepResult, LinearMotorConfig } from "../types";
import { isTauriAvailable } from "./core";
import { mockForceSweep } from "./forceSweepMock";
import { evaluateForceSweep } from "./physics";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));
vi.mock("./forceSweepMock", () => ({ mockForceSweep: vi.fn() }));

beforeEach(() => vi.resetAllMocks());

it("uses mock forces only in the browser", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(false);
  const config = {} as LinearMotorConfig;
  const drive = {} as DriveSettings;
  const preview = {} as ForceSweepResult;
  vi.mocked(mockForceSweep).mockReturnValue(preview);

  await expect(evaluateForceSweep(config, null, drive)).resolves.toBe(preview);
  expect(mockForceSweep).toHaveBeenCalledWith(config);
  expect(invoke).not.toHaveBeenCalled();
});

it("forwards native results and errors without substituting mock forces", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  const config = {} as LinearMotorConfig;
  const drive = {} as DriveSettings;
  const result = { mean_thrust_n: 0.1 };
  vi.mocked(invoke).mockResolvedValueOnce(result).mockRejectedValueOnce(new Error("Native sweep failed"));

  await expect(evaluateForceSweep(config, null, drive)).resolves.toBe(result);
  expect(invoke).toHaveBeenCalledWith("evaluate_force_sweep", { config, cadGeometry: null, drive });
  await expect(evaluateForceSweep(config, null, drive)).rejects.toThrow("Native sweep failed");
  expect(mockForceSweep).not.toHaveBeenCalled();
});
