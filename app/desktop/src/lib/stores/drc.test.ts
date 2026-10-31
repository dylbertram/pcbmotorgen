import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigStore } from "./config.svelte";
import { DrcController } from "./drc.svelte";
import { checkCoilInterference } from "../ipc";
import type { InterferenceViolation } from "../types";

vi.mock("../ipc", { spy: true });
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const violation: InterferenceViolation = { layer: 0, net_a: "A", net_b: "B", kind: "clearance", gap_mm: 0, message: "Old layout" };

describe("background DRC scheduling", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.mocked(checkCoilInterference).mockReset(); });
  afterEach(() => { vi.useRealTimers(); });

  it("runs one check at a time and skips intermediate edits without opening the export gate", async () => {
    const config = new ConfigStore();
    const first = deferred<InterferenceViolation[]>(), latest = deferred<InterferenceViolation[]>();
    vi.mocked(checkCoilInterference).mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
    const drc = new DrcController({ config, getLayoutKey: () => String(config.trace_width_mm) });
    drc.request(); await vi.advanceTimersByTimeAsync(300);
    expect(checkCoilInterference).toHaveBeenCalledTimes(1);
    for (const width of [.2, .3, .4]) {
      config.trace_width_mm = width; drc.request(); await vi.advanceTimersByTimeAsync(300);
      expect(drc.ready).toBe(false); expect(drc.loading).toBe(true);
    }
    expect(checkCoilInterference).toHaveBeenCalledTimes(1);
    first.resolve([violation]); await vi.advanceTimersByTimeAsync(0);
    expect(checkCoilInterference).toHaveBeenCalledTimes(2);
    expect(vi.mocked(checkCoilInterference).mock.calls[1][0].trace_width_m).toBe(.0004);
    expect(drc.violations).toEqual([]); expect(drc.checkedLayoutKey).toBeNull(); expect(drc.ready).toBe(false);
    latest.resolve([]); await vi.advanceTimersByTimeAsync(0);
    expect(drc.ready).toBe(true); expect(drc.checkedLayoutKey).toBe("0.4"); expect(drc.loading).toBe(false);
  });

  it("preserves the edit debounce when an old check finishes and discards its error", async () => {
    const config = new ConfigStore(), old = deferred<InterferenceViolation[]>();
    vi.mocked(checkCoilInterference).mockReturnValueOnce(old.promise).mockResolvedValueOnce([]);
    const drc = new DrcController({ config, getLayoutKey: () => String(config.trace_width_mm) });
    drc.request(); await vi.advanceTimersByTimeAsync(300);
    config.trace_width_mm = .3; drc.request();
    old.reject(new Error("Stale failure")); await vi.advanceTimersByTimeAsync(0);
    expect(drc.error).toBeNull(); expect(drc.ready).toBe(false);
    await vi.advanceTimersByTimeAsync(299); expect(checkCoilInterference).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1); expect(checkCoilInterference).toHaveBeenCalledTimes(2); expect(drc.ready).toBe(true);
  });

  it("cancels queued checks on document departure and never publishes an in-flight result", async () => {
    const config = new ConfigStore(), old = deferred<InterferenceViolation[]>();
    vi.mocked(checkCoilInterference).mockReturnValueOnce(old.promise);
    const drc = new DrcController({ config, getLayoutKey: () => String(config.trace_width_mm) });
    drc.request(); await vi.advanceTimersByTimeAsync(300);
    config.trace_width_mm = .3; drc.request(); await vi.advanceTimersByTimeAsync(300);
    drc.cancel(); old.resolve([violation]); await vi.advanceTimersByTimeAsync(1000);
    expect(checkCoilInterference).toHaveBeenCalledTimes(1);
    expect(drc.ready).toBe(false); expect(drc.loading).toBe(false); expect(drc.violations).toEqual([]);
    drc.request(); drc.cancel(); await vi.advanceTimersByTimeAsync(1000);
    expect(checkCoilInterference).toHaveBeenCalledTimes(1);
  });
});
