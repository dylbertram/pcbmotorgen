import { cancelMovePower, evaluateMovePower } from "./ipc/physics";
import { isTauriAvailable } from "./ipc/core";
import type { MovePowerInputs, NativeMoveResult } from "./types/movePower";

/** Canonical input identity ignores object-key order, never geometry or values. */
export function moveInputKey(value: unknown): string {
  return JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

type Status = "idle" | "pending" | "ready" | "error" | "cancelled";
interface Dependencies {
  native: () => boolean;
  start: typeof evaluateMovePower;
  cancel: typeof cancelMovePower;
  id: () => string;
}

/** Request ownership only. All motion and electrical calculations stay native. */
export class MovePowerJob {
  status: Status = "idle";
  result: NativeMoveResult | null = null;
  error: string | null = null;
  private inputs: MovePowerInputs | null = null;
  private key = "null";
  private generation = 0;
  private running: string | null = null;
  private disposed = false;

  constructor(private changed: () => void = () => {}, private deps: Dependencies = {
    native: isTauriAvailable, start: evaluateMovePower, cancel: cancelMovePower,
    id: () => crypto.randomUUID(),
  }) {}

  setInputs(inputs: MovePowerInputs | null): void {
    const key = moveInputKey(inputs);
    if (key === this.key) return;
    this.invalidate("idle");
    this.inputs = inputs ? JSON.parse(JSON.stringify(inputs)) : null;
    this.key = key;
    this.changed();
  }

  private invalidate(status: Status): void {
    this.generation++;
    const running = this.running;
    this.running = null;
    this.result = null;
    this.error = null;
    this.status = status;
    if (running) void this.deps.cancel(running).catch(() => {
      // Publication is already invalidated. A failed cancellation request may
      // leave bounded native work running, but cannot resurrect its result.
    });
  }

  async run(): Promise<void> {
    if (this.disposed || this.status === "pending") return;
    this.invalidate("pending");
    const generation = this.generation, key = this.key, inputs = this.inputs;
    if (!this.deps.native() || !inputs) {
      this.status = "error";
      this.error = !this.deps.native() ? "Move power requires native desktop simulation; no browser result is available."
        : "Define an explicit move, load and source model before calculating power.";
      this.changed();
      return;
    }
    const id = this.deps.id();
    this.running = id;
    this.changed();
    try {
      const result = await this.deps.start(id, inputs);
      if (this.disposed || generation !== this.generation || key !== this.key) return;
      if (result.request_id !== id || result.provenance !== "simulated_not_measured"
        || !/^[0-9a-f]{64}$/.test(result.input_sha256) || moveInputKey(result.inputs) !== key) {
        throw new Error("Move result identity does not match the active design and move; result withheld.");
      }
      this.result = result;
      this.status = "ready";
    } catch (error) {
      if (this.disposed || generation !== this.generation || key !== this.key) return;
      this.result = null;
      this.status = "error";
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      if (generation === this.generation) {
        this.running = null;
        this.changed();
      }
    }
  }

  cancel(): void { this.invalidate("cancelled"); this.changed(); }
  dispose(): void { this.invalidate("cancelled"); this.disposed = true; }
}
