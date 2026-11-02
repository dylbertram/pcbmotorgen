import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SensorStore } from "./sensor.svelte";
import type { CadGeometry, SensorGeometry } from "../types";
import { SensorGeometryController } from "./sensorGeometryController";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

describe("SensorGeometryController", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces requests and publishes only the current configuration", async () => {
    const store = new SensorStore();
    const result = {} as SensorGeometry;
    const generate = vi.fn().mockResolvedValue(result);
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    store.config.lambda_mm = 240;
    controller.update(true);
    expect(store.loading).toBe(true);
    await vi.advanceTimersByTimeAsync(150);
    expect(generate).toHaveBeenCalledOnce();
    expect(generate.mock.calls[0][0].lambda_mm).toBe(240);
    expect(store.generatedGeometry).toBe(result);
    expect(store.loading).toBe(false);
    controller.dispose();
  });

  it("ignores an older failure after a newer request succeeds", async () => {
    const store = new SensorStore();
    const old = deferred<SensorGeometry>();
    const latest = {} as SensorGeometry;
    const generate = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(latest);
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    old.reject(new Error("stale failure"));
    await Promise.resolve();
    expect(store.loading).toBe(false);
    expect(store.generatedGeometry).toBe(latest);
    expect(store.error).toBeNull();
    controller.dispose();
  });

  it("keeps the latest request loading when an older request succeeds", async () => {
    const store = new SensorStore();
    const old = deferred<SensorGeometry>();
    const latest = deferred<SensorGeometry>();
    const generate = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise);
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    old.resolve({} as SensorGeometry);
    await Promise.resolve();
    expect(store.generatedGeometry).toBeNull();
    expect(store.loading).toBe(true);
    const result = {} as SensorGeometry;
    latest.resolve(result);
    await Promise.resolve();
    expect(store.generatedGeometry).toBe(result);
    expect(store.loading).toBe(false);
    controller.dispose();
  });

  it("keeps imported CAD authoritative and ignores a pending result", async () => {
    const store = new SensorStore();
    const pending = deferred<SensorGeometry>();
    const generate = vi.fn().mockReturnValue(pending.promise);
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    store.cadGeometry = {} as CadGeometry;
    controller.update(true);
    pending.resolve({} as SensorGeometry);
    await Promise.resolve();
    expect(store.generatedGeometry).toBeNull();
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
    controller.dispose();
  });

  it("cancels queued work and reports current native errors", async () => {
    const store = new SensorStore();
    const generate = vi.fn().mockRejectedValue("native failure");
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    controller.update(false);
    await vi.advanceTimersByTimeAsync(150);
    expect(generate).not.toHaveBeenCalled();
    expect(store.loading).toBe(false);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    expect(store.error).toBe("native failure");
    expect(store.generatedGeometry).toBeNull();
    expect(store.loading).toBe(false);
    controller.dispose();
  });

  it("cancels queued generation when CAD is imported", async () => {
    const store = new SensorStore();
    const generate = vi.fn();
    const controller = new SensorGeometryController(store, generate);
    controller.update(true);
    store.cadGeometry = {} as CadGeometry;
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    expect(generate).not.toHaveBeenCalled();
    expect(store.loading).toBe(false);
    controller.dispose();
  });

  it.each(["deactivated", "disposed"])("ignores an in-flight result when %s", async (action) => {
    const store = new SensorStore();
    const pending = deferred<SensorGeometry>();
    const controller = new SensorGeometryController(store, () => pending.promise);
    controller.update(true);
    await vi.advanceTimersByTimeAsync(150);
    if (action === "deactivated") controller.update(false);
    else controller.dispose();
    pending.resolve({} as SensorGeometry);
    await Promise.resolve();
    expect(store.generatedGeometry).toBeNull();
    if (action === "deactivated") expect(store.loading).toBe(false);
    controller.dispose();
  });
});
