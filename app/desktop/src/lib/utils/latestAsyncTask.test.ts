import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LatestAsyncTask } from "./latestAsyncTask";

const deferred = () => {
  let resolve!: (value: number) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<number>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

describe("latest-only background tasks", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("coalesces edits both before launch and during a slow call", async () => {
    const old = deferred(), latest = deferred();
    const run = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise);
    const onResult = vi.fn(), onError = vi.fn();
    const task = new LatestAsyncTask<number, number>({ delayMs: 300, run, onResult, onError });
    task.request(1); await vi.advanceTimersByTimeAsync(200); task.request(2);
    await vi.advanceTimersByTimeAsync(299); expect(run).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1); expect(run).toHaveBeenCalledExactlyOnceWith(2);
    task.request(3); await vi.advanceTimersByTimeAsync(300);
    task.request(4); await vi.advanceTimersByTimeAsync(300);
    expect(run).toHaveBeenCalledTimes(1);
    old.resolve(20); await vi.advanceTimersByTimeAsync(0);
    expect(run).toHaveBeenLastCalledWith(4); expect(onResult).not.toHaveBeenCalled();
    latest.resolve(40); await vi.advanceTimersByTimeAsync(0);
    expect(onResult).toHaveBeenCalledExactlyOnceWith(40, 4); expect(onError).not.toHaveBeenCalled();
  });

  it("ignores obsolete failures and continues the latest job", async () => {
    const old = deferred(), onResult = vi.fn(), onError = vi.fn();
    const run = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(2);
    const task = new LatestAsyncTask<number, number>({ delayMs: 300, run, onResult, onError });
    task.request(1); await vi.advanceTimersByTimeAsync(300);
    task.request(2); await vi.advanceTimersByTimeAsync(300);
    old.reject(new Error("Old failure")); await vi.advanceTimersByTimeAsync(0);
    expect(onError).not.toHaveBeenCalled(); expect(onResult).toHaveBeenCalledExactlyOnceWith(2, 2);
  });

  it("cancels queued work and suppresses completed results, then allows reactivation", async () => {
    const old = deferred(), onResult = vi.fn();
    const run = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(3);
    const task = new LatestAsyncTask<number, number>({ delayMs: 300, run, onResult });
    task.request(1); await vi.advanceTimersByTimeAsync(300);
    task.request(2); await vi.advanceTimersByTimeAsync(300); task.cancel();
    old.resolve(1); await vi.advanceTimersByTimeAsync(1000);
    expect(run).toHaveBeenCalledTimes(1); expect(onResult).not.toHaveBeenCalled();
    task.request(3); await vi.advanceTimersByTimeAsync(300);
    expect(onResult).toHaveBeenCalledExactlyOnceWith(3, 3);
  });

  it("reports only current failures and accepts requests after failure", async () => {
    const error = new Error("Current failure"), onError = vi.fn(), onResult = vi.fn();
    const run = vi.fn().mockRejectedValueOnce(error).mockResolvedValueOnce(2);
    const task = new LatestAsyncTask<number, number>({ delayMs: 300, run, onResult, onError });
    task.request(1); await vi.advanceTimersByTimeAsync(300);
    expect(onError).toHaveBeenCalledExactlyOnceWith(error, 1);
    task.request(2); await vi.advanceTimersByTimeAsync(300);
    expect(onResult).toHaveBeenCalledExactlyOnceWith(2, 2);
  });
});
