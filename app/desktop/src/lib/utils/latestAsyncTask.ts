interface TaskOptions<Input, Result> {
  delayMs: number;
  run: (input: Input) => Promise<Result>;
  onResult: (result: Result, input: Input) => void;
  onError?: (error: unknown, input: Input) => void;
}

/** Debounced background work: one active call, one latest pending input.
 * Cancellation drops queued work and results, not an already-running native call. */
export class LatestAsyncTask<Input, Result> {
  #generation = 0;
  #running = false;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #pending: { input: Input; generation: number; ready: boolean } | null = null;

  constructor(private options: TaskOptions<Input, Result>) {}

  request(input: Input): void {
    this.cancel();
    const job = { input, generation: this.#generation, ready: false };
    this.#pending = job;
    this.#timer = setTimeout(() => {
      this.#timer = undefined;
      job.ready = true;
      void this.#drain();
    }, this.options.delayMs);
  }

  cancel(): void {
    ++this.#generation;
    clearTimeout(this.#timer);
    this.#timer = undefined;
    this.#pending = null;
  }

  async #drain(): Promise<void> {
    if (this.#running || !this.#pending?.ready) return;
    const job = this.#pending;
    this.#pending = null;
    this.#running = true;
    try {
      const result = await this.options.run(job.input);
      if (job.generation === this.#generation) this.options.onResult(result, job.input);
    } catch (error) {
      if (job.generation === this.#generation) this.options.onError?.(error, job.input);
    } finally {
      this.#running = false;
      void this.#drain();
    }
  }
}
