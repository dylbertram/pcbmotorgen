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
  phase: "idle" | "starting" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
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
    if (job.state === "completed") {
      const result = job.result;
      if (!result || result.status !== "passed-fresh-qualified-geometry-dc-request-only"
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
      : job.state === "cancelled" ? "cancelled" : "failed", job: job.state === "completed" || active(job) ? job : null, error: job.error });
  }
}
