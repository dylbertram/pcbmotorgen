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
const prepared = (): DcJobStatus => ({...running(),operation:"preparation",state:"prepared",preparation:{
  status:"prepared-request-bound-current-source-not-qualified",input_request_sha256:"content-hash",request_id:"one",
  source_status:"prepared-baseline-needs-refinement",force_status:"unqualified",remaining:["source refinements","fields","magnetic matrix","admission"],
  artifacts:{source:"actual",active:"actual",passive:"actual",return:"actual",independent:"actual",rt0:"actual"},evidence_hashes:{actual:"hash"}}});
function setup() {
  const views:DcViewState[]=[];
  const transport = {start:vi.fn().mockResolvedValue(running()),poll:vi.fn().mockResolvedValue(complete()),
    cancel:vi.fn().mockResolvedValue({...running(),state:"cancelling"})};
  const controller = new DcJobController(transport,view=>views.push(view));
  return {controller,transport,views,last:()=>views.at(-1)!};
}

describe("managed DC request lifecycle",()=>{
  it("keeps verified finite-copper winding samples separate from forces and clears them on edits", async () => {
    const {controller,transport,last}=setup();
    const samples=[];
    for(let z=0;z<2;z++)for(let y=0;y<2;y++)for(let x=0;x<2;x++)samples.push({position_m:[x,y,z] as [number,number,number],b_t:[0,0,.001] as [number,number,number],magnitude_t:.001});
    const value:DcJobStatus={...running(),operation:"winding-field",state:"completed",winding_field:{
      status:"sampled-qualified-finite-copper-winding-field-only",request_id:"one",input_request_sha256:"content-hash",qualified_case:{...CASE,audit_sha256:"a".repeat(64)},
      sampling:{bounds_m:[[0,1],[0,1],[0,1]],counts:[2,2,2]},loop_current_a:.1,phase_currents_a:{A:.1,C:-.1},source_basis_sha256:"b".repeat(64),
      source_translation_m:[0,0,0],source_elements:1,evidence_hashes:{fixture:"c".repeat(64)},field:{method:"qualified-finite-copper-winding-xyz",scope:"Unit-test data only",magnets:[],samples}}};
    transport.start.mockResolvedValue(value);await controller.start("one");expect(last().phase).toBe("completed");expect(last().job?.result).toBeNull();expect(last().job?.winding_field?.field.samples).toHaveLength(8);
    await controller.invalidate();expect(last().job).toBeNull();
    for(const change of ["force","sha","pm","point","partial"]) {
      const changed=structuredClone(value);
      if(change==="force")changed.result=complete().result;
      if(change==="sha")changed.winding_field!.input_request_sha256="stale";
      if(change==="pm")changed.winding_field!.field.method="analytical-pm-only-xyz";
      if(change==="point")changed.winding_field!.field.samples[0].position_m[0]=.5;
      if(change==="partial")changed.winding_field!.field.samples.pop();
      transport.start.mockResolvedValue(changed);await controller.start("one");expect(last().phase).toBe("failed");
    }
  });
  it("keeps prepared sources unqualified and never renders them as force results",async()=>{
    const {controller,transport,last}=setup();transport.start.mockResolvedValue({...running(),operation:"preparation"});
    transport.poll.mockResolvedValue(prepared());await controller.start("one");await controller.poll();
    expect(last().phase).toBe("prepared");expect(last().job?.result).toBeNull();expect(last().job?.preparation?.force_status).toBe("unqualified");
    await controller.invalidate();expect(last().job).toBeNull();
  });

  it("rejects stale, incomplete or force-bearing preparation reports",async()=>{
    for (const change of ["sha","force","qualified","missing","operation"]) {
      const {controller,transport,last}=setup();await controller.start("one");const value=prepared();
      if(change==="sha")value.preparation!.input_request_sha256="stale";
      else if(change==="force")value.result=complete().result;
      else if(change==="qualified")Object.assign(value.preparation!,{qualified_case:CASE});
      else if(change==="missing")delete value.preparation!.artifacts.passive;
      else value.operation="force";
      transport.poll.mockResolvedValue(value);await controller.poll();expect(last().phase).toBe("failed");expect(last().job).toBeNull();
    }
  });

  it("cancels late preparation starts and suppresses completion racing an edit",async()=>{
    const {controller,transport,last}=setup();const start=deferred<DcJobStatus>();transport.start.mockReturnValue(start.promise);
    const pending=controller.start("one");await controller.invalidate();start.resolve({...running(),operation:"preparation"});await pending;
    expect(transport.cancel).toHaveBeenCalledWith("job-one");expect(last().job).toBeNull();
    transport.start.mockResolvedValue({...running(),operation:"preparation"});await controller.start("one");
    const poll=deferred<DcJobStatus>();transport.poll.mockReturnValue(poll.promise);const polling=controller.poll();
    await controller.invalidate();poll.resolve(prepared());await polling;expect(last().phase).toBe("idle");expect(last().job).toBeNull();
  });

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
