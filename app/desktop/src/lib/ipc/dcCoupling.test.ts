import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));

import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import { prepareDcWindingGeometry } from "./physics";
import type { LinearMotorConfig } from "../types";
import { DEFAULT_DRIVE_SETTINGS } from "../types/drive";

const config = { routing_pattern: "infinity-braid", routing_params: { connection: 2 } } as unknown as LinearMotorConfig;

describe("finite DC actual geometry preparation", () => {
  beforeEach(() => vi.resetAllMocks());

  it("does not fabricate winding geometry in browser preview", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    await expect(prepareDcWindingGeometry(config, DEFAULT_DRIVE_SETTINGS)).rejects.toThrow("require");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("passes the exact caller copper settings and never returns a mock force", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    const result = { schema: "finite-dc-winding-geometry-v1", scope: "geometry only" };
    vi.mocked(invoke).mockResolvedValue(result);
    expect(await prepareDcWindingGeometry(config, DEFAULT_DRIVE_SETTINGS)).toBe(result);
    expect(invoke).toHaveBeenCalledWith("prepare_dc_winding_geometry", {
      config, driveSettings: DEFAULT_DRIVE_SETTINGS, cadGeometry: null,
    });
  });

  it("propagates unsupported geometry failures without a generated fallback", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    vi.mocked(invoke).mockRejectedValue(new Error("Unqualified curved copper"));
    await expect(prepareDcWindingGeometry(config, DEFAULT_DRIVE_SETTINGS)).rejects.toThrow("Unqualified curved copper");
    expect(invoke).toHaveBeenCalledTimes(1);
  });
});
