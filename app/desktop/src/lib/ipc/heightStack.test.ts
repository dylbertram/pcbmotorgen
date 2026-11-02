import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import type { HeightStackResultDto, LinearMotorConfig } from "../types";
import { isTauriAvailable } from "./core";
import { mockHeightStack } from "./heightStackMock";
import { computeHeightStack } from "./physics";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));
vi.mock("./heightStackMock", () => ({ mockHeightStack: vi.fn() }));

beforeEach(() => vi.resetAllMocks());

it("uses the height-stack mock only in a browser", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(false);
  const config = {} as LinearMotorConfig;
  const preview = { backplane_analysis: null } as HeightStackResultDto;
  vi.mocked(mockHeightStack).mockReturnValue(preview);

  await expect(computeHeightStack(config)).resolves.toBe(preview);
  expect(mockHeightStack).toHaveBeenCalledWith(config);
  expect(invoke).not.toHaveBeenCalled();
});

it("forwards native results and errors without falling back to the mock", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  const config = {} as LinearMotorConfig;
  const result = { total_height_m: 0.01 };
  vi.mocked(invoke).mockResolvedValueOnce(result).mockRejectedValueOnce(new Error("Native stack failed"));

  await expect(computeHeightStack(config)).resolves.toBe(result);
  expect(invoke).toHaveBeenCalledWith("compute_height_stack", { config });
  await expect(computeHeightStack(config)).rejects.toThrow("Native stack failed");
  expect(mockHeightStack).not.toHaveBeenCalled();
});
