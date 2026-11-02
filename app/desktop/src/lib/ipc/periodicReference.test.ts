import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LinearMotorConfig } from "../types";

const { invoke, available } = vi.hoisted(() => ({ invoke: vi.fn(), available: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("./core", () => ({ isTauriAvailable: available }));
import { periodicBackplaneReference } from "./physics";

describe("periodic backplane reference", () => {
  beforeEach(() => vi.clearAllMocks());

  it("never substitutes a mock for a missing solver", async () => {
    available.mockReturnValue(false);
    await expect(periodicBackplaneReference({} as LinearMotorConfig)).rejects.toThrow("requires the desktop app");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("forwards explicit input to the real reference command", async () => {
    available.mockReturnValue(true);
    const config = { backplane: { layers: [], housing: null } } as unknown as LinearMotorConfig;
    invoke.mockResolvedValue({ scope: "periodic static only" });
    await expect(periodicBackplaneReference(config)).resolves.toEqual({ scope: "periodic static only" });
    expect(invoke).toHaveBeenCalledWith("periodic_backplane_reference", { config });
  });

  it("propagates rejected physics instead of showing plausible fallback values", async () => {
    available.mockReturnValue(true);
    invoke.mockRejectedValue(new Error("refinement gate failed"));
    await expect(periodicBackplaneReference({} as LinearMotorConfig)).rejects.toThrow("refinement gate failed");
  });

});
