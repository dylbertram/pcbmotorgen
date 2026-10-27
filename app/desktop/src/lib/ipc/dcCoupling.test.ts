import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));

import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import { prepareDcWindingGeometry } from "./physics";
import { inspectDcCoupling } from "./dcJobs";
import type { DcStudy } from "../types/dcCoupling";
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

  it("inspects exact caller settings without a browser applicability fallback", async () => {
    const study: DcStudy = {request_id:"inspect",material_model:{},return_geometry:{},current_a:0.1,pm_offset_x_m:0,placement_acknowledged:true};
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    await expect(inspectDcCoupling(config, DEFAULT_DRIVE_SETTINGS, null, study)).rejects.toThrow("requires");
    expect(invoke).not.toHaveBeenCalled();
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    const result = {schema:"finite-dc-applicability-v1",state:"preparation-required"};
    vi.mocked(invoke).mockResolvedValue(result);
    expect(await inspectDcCoupling(config, DEFAULT_DRIVE_SETTINGS, null, study)).toBe(result);
    expect(invoke).toHaveBeenCalledWith("inspect_dc_coupling", {config,driveSettings:DEFAULT_DRIVE_SETTINGS,cadGeometry:null,study});
  });
});
