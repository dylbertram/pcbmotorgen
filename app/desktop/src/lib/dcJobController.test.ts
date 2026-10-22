import { describe, expect, it, vi } from "vitest";
import { DcJobController, type DcViewState } from "./dcJobController";
import type { DcJobStatus } from "./types/dcCoupling";

function deferred<T>() { let resolve!: (value:T)=>void, reject!: (error:Error)=>void;
  const promise = new Promise<T>((ok,no)=>{resolve=ok;reject=no;});return {promise,resolve,reject}; }
const CASE = {case_id:"case-a",label:"Case A",audit_sha256:"audit-hash"};
const running = (id="one"): DcJobStatus => ({request_id:id,job_id:`job-${id}`,state:"running",elapsed_seconds:0,
  evidence_directory:"/evidence",request_sha256:"content-hash",error:null,result:null});
const complete = (id="one"): DcJobStatus => ({...running(id),state:"completed",result:{
  status:"passed-fresh-qualified-geometry-dc-request-only",pm_array_force_n:[1,2,3],
  input_request_sha256:"content-hash",fresh_solution_sha256:"solution-hash",qualified_case:CASE,
  eligibility:{request_id:id,current_a:0.1,pm_offset_x_m:0,qualified_case:CASE}}});
function setup() {
  const views:DcViewState[]=[];
  const transport = {start:vi.fn().mockResolvedValue(running()),poll:vi.fn().mockResolvedValue(complete()),
    cancel:vi.fn().mockResolvedValue({...running(),state:"cancelling"})};
  const controller = new DcJobController(transport,view=>views.push(view));
  return {controller,transport,views,last:()=>views.at(-1)!};
}

describe("managed DC request lifecycle",()=>{
  it("clears previous force immediately when a new calculation starts or fails",async()=>{
    const {controller,transport,last}=setup();
    await controller.start("one");await controller.poll();expect(last().phase).toBe("completed");
    const next=deferred<DcJobStatus>();transport.start.mockReturnValue(next.promise);
    const pending=controller.start("two");expect(last()).toEqual({phase:"starting",job:null,error:null});
    next.reject(new Error("unsupported geometry"));await pending;
    expect(last().phase).toBe("failed");expect(last().job).toBeNull();
  });

  it("cancels a start response arriving after edit or unmount",async()=>{
    const {controller,transport,last}=setup();const start=deferred<DcJobStatus>();transport.start.mockReturnValue(start.promise);
    const pending=controller.start("one");await controller.invalidate();
    start.resolve(running());await pending;
    expect(transport.cancel).toHaveBeenCalledWith("job-one");expect(last().job).toBeNull();expect(last().phase).toBe("idle");
  });

  it("cannot replace a newer failed request with a late old force",async()=>{
    const {controller,transport,last}=setup();await controller.start("one");
    const poll=deferred<DcJobStatus>();transport.poll.mockReturnValue(poll.promise);const pending=controller.poll();
    await controller.invalidate();transport.start.mockRejectedValue(new Error("bad new geometry"));await controller.start("two");
    poll.resolve(complete());await pending;expect(last().phase).toBe("failed");expect(last().job).toBeNull();
  });

  it("keeps cancellation pending until host confirms stop and never shows racing success",async()=>{
    const {controller,transport,last}=setup();await controller.start("one");await controller.cancel();
    expect(last().phase).toBe("cancelling");expect(last().job).toBeNull();
    transport.poll.mockResolvedValue(complete());await controller.poll();
    expect(last().phase).toBe("cancelled");expect(last().job).toBeNull();
  });

  it("rejects duplicate starts and serializes polls",async()=>{
    const {controller,transport}=setup();await controller.start("one");
    await expect(controller.start("two")).rejects.toThrow("already");
    const poll=deferred<DcJobStatus>();transport.poll.mockReturnValue(poll.promise);const pending=controller.poll();
    await controller.poll();expect(transport.poll).toHaveBeenCalledTimes(1);poll.resolve(complete());await pending;
  });

  it("rejects mismatched IDs, failed status, stale hashes and nonfinite forces",async()=>{
    const mutations:Array<(job:DcJobStatus)=>void> = [job=>{job.job_id="other";},job=>{job.request_id="other";},
      job=>{job.result!.input_request_sha256="changed";},job=>{job.result!.pm_array_force_n[0]=Number.NaN;},
      job=>{job.state="failed";},job=>{job.result!.qualified_case={...CASE,case_id:"other-case"};},
      job=>{(job.result as {status:string}).status="passed-fresh-recorded-geometry-dc-request-only";}];
    for (const mutate of mutations) {
      const {controller,transport,last}=setup();await controller.start("one");
      const bad=complete();mutate(bad);transport.poll.mockResolvedValue(bad);await controller.poll();
      expect(last().phase).toBe("failed");expect(last().job).toBeNull();
      expect(transport.cancel).toHaveBeenCalledWith("job-one");
    }
  });

  it("does not claim that an IPC cancellation failure stopped the worker",async()=>{
    const {controller,transport,last}=setup();await controller.start("one");
    transport.cancel.mockRejectedValue(new Error("connection lost"));await controller.cancel();
    expect(last().phase).toBe("failed");expect(last().error).toContain("could not be confirmed");
    expect(last().job).toBeNull();
  });
});
