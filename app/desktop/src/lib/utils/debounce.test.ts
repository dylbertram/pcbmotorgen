import { afterEach, describe, expect, it, vi } from "vitest";
import { debounce } from "./debounce";

describe("debounce", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("cancels work that has not started", () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const scheduled = debounce(callback, 150);

    scheduled();
    scheduled.cancel();
    vi.advanceTimersByTime(150);

    expect(callback).not.toHaveBeenCalled();
  });

  it("only invokes the latest scheduled call", () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const scheduled = debounce(callback, 150);

    scheduled("old");
    scheduled("new");
    vi.advanceTimersByTime(150);

    expect(callback).toHaveBeenCalledOnce();
    expect(callback).toHaveBeenCalledWith("new");
  });
});
