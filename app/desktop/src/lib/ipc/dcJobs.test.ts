import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("@tauri-apps/api/core",()=>({invoke:vi.fn()}));
vi.mock("./core",()=>({isTauriAvailable:vi.fn()}));
import { invoke } from "@tauri-apps/api/core";
import { isTauriAvailable } from "./core";
import { dcCouplingCapability, startDcCoupling, dcCouplingStatus, cancelDcCoupling } from "./dcJobs";
import type { LinearMotorConfig } from "../types";
import { DEFAULT_DRIVE_SETTINGS } from "../types/drive";

const config={routing_pattern:"infinity-braid",routing_params:{connection:2}} as unknown as LinearMotorConfig;
const study={request_id:"actual-1",material_model:{},return_geometry:{},current_a:0.1,pm_offset_x_m:0,placement_acknowledged:true};

describe("managed DC desktop IPC",()=>{
  beforeEach(()=>{vi.resetAllMocks();vi.mocked(isTauriAvailable).mockReturnValue(true);});
  it("does not offer a numerical browser substitute",async()=>{
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    expect((await dcCouplingCapability()).available).toBe(false);
    await expect(startDcCoupling(config,DEFAULT_DRIVE_SETTINGS,null,study)).rejects.toThrow("requires");
    await expect(dcCouplingStatus("job")).rejects.toThrow("requires");
    await expect(cancelDcCoupling("job")).rejects.toThrow("requires");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("sends actual source design/settings and explicit study, not a caller winding snapshot",async()=>{
    vi.mocked(invoke).mockResolvedValue({state:"running"});
    await startDcCoupling(config,DEFAULT_DRIVE_SETTINGS,null,study);
    expect(invoke).toHaveBeenCalledWith("start_dc_coupling",{config,driveSettings:DEFAULT_DRIVE_SETTINGS,cadGeometry:null,study});
    await dcCouplingStatus("exact-job");expect(invoke).toHaveBeenCalledWith("dc_coupling_status",{jobId:"exact-job"});
    await cancelDcCoupling("exact-job");expect(invoke).toHaveBeenCalledWith("cancel_dc_coupling",{jobId:"exact-job"});
  });
  it("propagates unsupported/failing desktop jobs",async()=>{
    vi.mocked(invoke).mockRejectedValue(new Error("Actual geometry not qualified"));
    await expect(startDcCoupling(config,DEFAULT_DRIVE_SETTINGS,null,study)).rejects.toThrow("not qualified");
  });
});
