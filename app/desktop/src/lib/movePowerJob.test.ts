import { describe, expect, it, vi } from "vitest";
import { MovePowerJob, moveInputKey } from "./movePowerJob";
import type { MovePowerInputs, NativeMoveResult } from "./types/movePower";

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
// Identity-only fixtures, never exported as native engineering evidence.
const inputs = { config: { supply_voltage_v: 12 }, drive: {}, cad_geometry: null,
  move_request: { profile: { duration_s: 1 } } } as unknown as MovePowerInputs;
const response = (id: string, input = inputs) => ({ request_id: id, input_sha256: "a".repeat(64),
  inputs: input, provenance: "simulated_not_measured", result: {} }) as NativeMoveResult;

function setup(native = true) {
  let next = 0;
  const requests: ReturnType<typeof deferred<NativeMoveResult>>[] = [];
  const start = vi.fn(() => { const d = deferred<NativeMoveResult>(); requests.push(d); return d.promise; });
  const cancel = vi.fn(async () => true);
  const job = new MovePowerJob(() => {}, { native: () => native, start, cancel, id: () => `move-${++next}` });
  job.setInputs(inputs);
  return { job, start, cancel, requests };
}

describe("native move publication", () => {
  it("does not call native physics or publish browser mock evidence", async () => {
    const { job, start } = setup(false);
    await job.run();
    expect(start).not.toHaveBeenCalled();
    expect(job.result).toBeNull();
    expect(job.status).toBe("error");
  });
  it("publishes only the current exact request", async () => {
    const { job, requests } = setup();
    const run = job.run();
    expect(job.result).toBeNull();
    expect(job.status).toBe("pending");
    requests[0].resolve(response("move-1")); await run;
    expect(job.status).toBe("ready");
    expect(job.result?.request_id).toBe("move-1");
  });
  it("clears results immediately for an input edit, and ignores its late reply", async () => {
    const { job, requests, cancel } = setup();
    const run = job.run();
    job.setInputs({ ...inputs, cad_geometry: { source_file_name: "edited" } } as MovePowerInputs);
    expect(job.result).toBeNull();
    expect(cancel).toHaveBeenCalledWith("move-1");
    requests[0].resolve(response("move-1")); await run;
    expect(job.result).toBeNull();
    expect(job.status).toBe("idle");
  });
  it("does not resurrect results after cancellation or disposal", async () => {
    for (const operation of ["cancel", "dispose"] as const) {
      const { job, requests } = setup();
      const run = job.run(); job[operation]();
      requests[0].resolve(response("move-1")); await run;
      expect(job.result).toBeNull();
      expect(job.status).toBe("cancelled");
    }
  });
  it("rejects mismatched request ids, inputs, hash and provenance", async () => {
    for (const bad of [{ request_id: "other" }, { input_sha256: "missing" },
      { provenance: "browser_mock" }, { inputs: { ...inputs, cad_geometry: {} } }]) {
      const { job, requests } = setup(); const run = job.run();
      requests[0].resolve({ ...response("move-1"), ...bad } as NativeMoveResult); await run;
      expect(job.result).toBeNull(); expect(job.status).toBe("error");
    }
  });
  it("does not retain the previous successful result while a retry is pending or failed", async () => {
    const { job, requests } = setup();
    let run = job.run(); requests[0].resolve(response("move-1")); await run;
    run = job.run(); expect(job.result).toBeNull();
    requests[1].reject(new Error("native failure")); await run;
    expect(job.result).toBeNull(); expect(job.error).toBe("native failure");
  });
  it("ignores old errors without overwriting a newer successful request", async () => {
    const { job, requests } = setup(); const old = job.run();
    const changed = { ...inputs, cad_geometry: { source_file_name: "new" } } as MovePowerInputs;
    job.setInputs(changed); const current = job.run();
    requests[1].resolve(response("move-2", changed)); await current;
    requests[0].reject(new Error("old failure")); await old;
    expect(job.status).toBe("ready"); expect(job.error).toBeNull();
  });
  it("canonical identity ignores key order but includes nested geometry and move values", () => {
    expect(moveInputKey({ a: 1, b: { x: 3, y: 4 } })).toBe(moveInputKey({ b: { y: 4, x: 3 }, a: 1 }));
    expect(moveInputKey({ depth: -4.8 })).not.toBe(moveInputKey({ depth: 0 }));
  });
});
