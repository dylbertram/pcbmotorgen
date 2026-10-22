/** View-independent lifecycle. Edits/tab changes/unmount call invalidate().
 * Invalidation hides forces immediately, cancels both known and late-starting
 * jobs, and prevents out-of-order responses from replacing current results.
 */
import type { DcJobStatus } from "./types/dcCoupling";

export interface DcJobTransport {
  start: () => Promise<DcJobStatus>;
  poll: (id: string) => Promise<DcJobStatus>;
  cancel: (id: string) => Promise<DcJobStatus>;
}

export interface DcViewState {
  phase: "idle" | "starting" | "running" | "cancelling" | "completed" | "prepared" | "failed" | "cancelled";
  job: DcJobStatus | null;
  error: string | null;
}

const active = (job: DcJobStatus) => job.state === "running" || job.state === "cancelling";

export class DcJobController {
  private generation = 0;
  private job: DcJobStatus | null = null;
  private busy = false;
  private expectedRequest = "";
  private cancelRequested = false;
  private pollingGeneration: number | null = null;
  constructor(private transport: DcJobTransport, private update: (state: DcViewState) => void) {}

  private async stop(id: string): Promise<void> {
    // Failed cancellation must be visible: a lost IPC response is not proof
    // that the numerical worker stopped. The host timeout remains in force.
    await this.transport.cancel(id);
  }

  async invalidate(): Promise<void> {
    ++this.generation;
    const previous = this.job;
    this.job = null;
    this.busy = false;
    this.pollingGeneration = null;
    this.update({ phase: "idle", job: null, error: null });
    if (previous && active(previous)) {
      const generation = this.generation;
      try { await this.stop(previous.job_id); }
      catch (error) {
        if (generation === this.generation) this.update({ phase: "failed", job: null, error: `Cancellation could not be confirmed. ${String(error)}` });
      }
    }
  }

  async start(requestId: string): Promise<void> {
    if (this.busy) throw new Error("A DC request is already starting or running");
    const generation = ++this.generation;
    this.busy = true;this.job = null;this.expectedRequest = requestId;this.cancelRequested = false;
    this.update({ phase: "starting", job: null, error: null });
    try {
      const job = await this.transport.start();
      if (generation !== this.generation) {
        if (active(job)) {
          try { await this.stop(job.job_id); }
          catch (error) {
            if (this.generation === generation + 1 && !this.job && !this.busy) {
              this.update({phase:"failed",job:null,error:`Stale DC job cancellation could not be confirmed. ${String(error)}`});
            }
          }
        }
        return;
      }
      try { this.accept(job); }
      catch (error) {
        if (active(job)) await this.stop(job.job_id);
        throw error;
      }
    } catch (error) {
      if (generation === this.generation) {
        this.busy = false;
        this.update({ phase: "failed", job: null, error: String(error) });
      }
    }
  }

  async poll(): Promise<void> {
    if (!this.job || !active(this.job) || this.pollingGeneration === this.generation) return;
    const generation = this.generation, id = this.job.job_id;
    this.pollingGeneration = generation;
    try {
      const job = await this.transport.poll(id);
      if (generation !== this.generation) return;
      if (job.job_id !== id) throw new Error("Mismatched DC job response");
      this.accept(job);
    } catch (error) {
      if (generation !== this.generation) return;
      // Invalidate first so another outstanding poll cannot resurrect a force.
      await this.invalidate();
      if (this.generation === generation + 1) this.update({ phase: "failed", job: null, error: `DC job status failed; no force displayed. ${String(error)}` });
    } finally {
      if (this.pollingGeneration === generation) this.pollingGeneration = null;
    }
  }

  async cancel(): Promise<void> {
    const previous = this.job;
    const generation = ++this.generation;
    this.job = null;this.busy = true;this.cancelRequested = true;this.pollingGeneration = null;
    this.update({ phase: "cancelling", job: null, error: null });
    try {
      const cancelled = previous && active(previous) ? await this.transport.cancel(previous.job_id) : null;
      if (generation === this.generation) {
        if (cancelled) this.accept(cancelled);
        else { this.busy = false;this.update({ phase: "cancelled", job: null, error: null }); }
      }
    } catch (error) {
      if (generation === this.generation) {
        this.busy = false;this.update({ phase: "failed", job: null, error: `Cancellation could not be confirmed. ${String(error)}` });
      }
    }
  }

  private accept(job: DcJobStatus) {
    if (job.request_id !== this.expectedRequest) throw new Error("Mismatched DC request identity");
    if (this.cancelRequested) {
      this.job = active(job) ? {...job, state:"cancelling", result:null} : null;
      this.busy = this.job !== null;
      this.update({phase:this.busy ? "cancelling" : "cancelled",job:null,error:job.error});
      return;
    }
    if (job.state === "prepared") {
      const prepared = job.preparation;
      if (job.operation !== "preparation" || job.result !== null || !prepared
        || prepared.status !== "prepared-request-bound-current-source-not-qualified"
        || prepared.input_request_sha256 !== job.request_sha256 || prepared.request_id !== job.request_id
        || prepared.force_status !== "unqualified" || prepared.source_status !== "prepared-baseline-needs-refinement"
        || prepared.remaining.length !== 4 || Object.keys(prepared.artifacts).sort().join(",") !== "active,independent,passive,return,rt0,source"
        || Object.keys(prepared.evidence_hashes).length === 0 || "pm_array_force_n" in prepared || "qualified_case" in prepared) {
        throw new Error("Unverified or improperly qualified DC preparation response");
      }
    } else if (job.preparation != null) throw new Error("Non-prepared DC job returned source artifacts");
    if (job.state === "completed" && job.operation === "winding-field") {
      const value = job.winding_field;
      if (job.result !== null || !value || value.status !== "sampled-qualified-finite-copper-winding-field-only"
        || value.request_id !== job.request_id || value.input_request_sha256 !== job.request_sha256
        || !/^[a-f0-9]{64}$/.test(value.source_basis_sha256) || !/^[a-f0-9]{64}$/.test(value.qualified_case?.audit_sha256)
        || !value.qualified_case.case_id || ![0, .1, -.1, .5, -.5].includes(value.loop_current_a)
        || value.field.method !== "qualified-finite-copper-winding-xyz" || value.field.magnets.length !== 0
        || !value.evidence_hashes || !Object.keys(value.evidence_hashes).length
        || "pm_array_force_n" in value || "force_n" in value
        || value.field.samples.length > 96 || value.field.samples.length !== value.sampling.counts.reduce((a,b) => a*b,1)
        || value.field.samples.some(s => !Number.isFinite(s.magnitude_t) || Math.abs(Math.hypot(...s.b_t) - s.magnitude_t) > Math.max(1e-12, s.magnitude_t * 1e-10))) {
        throw new Error("Unverified qualified finite-copper winding field");
      }
      const { counts, bounds_m: bounds } = value.sampling;
      if (counts.length !== 3 || counts.some(n => !Number.isInteger(n) || n < 2 || n > 16)
        || bounds.length !== 3 || bounds.some(v => v.length !== 2 || !v.every(Number.isFinite) || v[0] >= v[1])
        || value.field.samples.some((s,i) => {
          const indices = [i % counts[0], Math.floor(i / counts[0]) % counts[1], Math.floor(i / (counts[0] * counts[1]))];
          return s.b_t.length !== 3 || !s.b_t.every(Number.isFinite) || s.position_m.length !== 3
            || s.position_m.some((p,axis) => !Number.isFinite(p) || Math.abs(p - (bounds[axis][0] + indices[axis] * (bounds[axis][1] - bounds[axis][0]) / (counts[axis] - 1))) > 1e-12);
        })) throw new Error("Winding-field coordinates do not match the bound observation grid");
    } else if (job.winding_field != null) throw new Error("A non-field DC operation returned winding samples");
    if (job.state === "completed" && job.operation !== "winding-field") {
      const result = job.result;
      if (job.operation === "preparation" || !result || result.status !== "passed-fresh-qualified-geometry-dc-request-only"
        || result.input_request_sha256 !== job.request_sha256
        || result.eligibility.request_id !== job.request_id
        || typeof result.qualified_case?.case_id !== "string"
        || result.qualified_case.case_id !== result.eligibility.qualified_case?.case_id
        || result.pm_array_force_n.length !== 3 || !result.pm_array_force_n.every(Number.isFinite)) {
        throw new Error("Unverified DC force response");
      }
    } else if (job.result !== null) throw new Error("Non-completed DC job returned a force");
    this.job = job;this.busy = active(job);
    this.update({ phase: active(job) ? job.state as "running" | "cancelling" : job.state === "completed" ? "completed"
      : job.state === "prepared" ? "prepared" : job.state === "cancelled" ? "cancelled" : "failed", job: job.state === "completed" || job.state === "prepared" || active(job) ? job : null, error: job.error });
  }
}
