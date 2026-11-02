import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import type { LinearMotorConfig } from "../types";
import { isTauriAvailable } from "./core";
import { fetchTravelEnvelope } from "./physics";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));

beforeEach(() => vi.resetAllMocks());

it("forwards the config and returns the native travel envelope", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  const config = { magnet_count: 6 } as LinearMotorConfig;
  const nativeResult = { min_position_m: 0.123 };
  vi.mocked(invoke).mockResolvedValue(nativeResult);

  await expect(fetchTravelEnvelope(config)).resolves.toBe(nativeResult);
  expect(invoke).toHaveBeenCalledWith("travel_envelope", { config });
});

it("propagates a native failure rather than using the browser placeholder", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  vi.mocked(invoke).mockRejectedValue(new Error("Native envelope failed"));

  await expect(fetchTravelEnvelope({} as LinearMotorConfig)).rejects.toThrow("Native envelope failed");
});
