import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LinearMotorConfig } from "../types";

const { invoke, available } = vi.hoisted(() => ({ invoke: vi.fn(), available: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("./core", () => ({ isTauriAvailable: available }));
import { analyzeHousingMotion } from "./physics";

const config = { routing_pattern: "infinity-braid", routing_params: { connection: 1 }, backplane: { layers: [], housing: { material: "aluminum6061", thickness_m: .001, gap_m: .001 } } } as unknown as LinearMotorConfig;

describe("independent housing-motion IPC", () => {
  beforeEach(() => { vi.resetAllMocks(); available.mockReturnValue(true); });
  it("does not substitute browser physics results", async () => {
    available.mockReturnValue(false);
    await expect(analyzeHousingMotion(config, { duration_s: .1 }, 3)).rejects.toThrow("require the desktop app");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("sends actual geometry/profile independently of unsupported driver delta handling", async () => {
    const result = { status: "unavailable", reason: "numerical check failed" };
    invoke.mockResolvedValue(result);
    expect(await analyzeHousingMotion(config, { duration_s: .2 }, -3)).toEqual(result);
    expect(invoke).toHaveBeenCalledWith("analyze_housing_motion", { config, profile: { duration_s: .2 }, speed: -3, cadGeometry: null });
  });
  it("propagates solver errors instead of returning zero heat or a previous result", async () => {
    invoke.mockRejectedValue(new Error("housing solver failure"));
    await expect(analyzeHousingMotion(config, { duration_s: .1 }, 3)).rejects.toThrow("housing solver failure");
    expect(invoke).toHaveBeenCalledTimes(1);
  });
});
