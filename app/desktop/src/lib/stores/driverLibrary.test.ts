import { afterEach, describe, expect, it, vi } from "vitest";
import { DriverLibrary } from "./driverLibrary.svelte";
import { DRIVER_PRESETS } from "../types/drive";

afterEach(() => vi.unstubAllGlobals());

function memoryStorage() {
  let saved: string | null = null;
  return {
    storage: {
      getItem: () => saved,
      setItem: (_key: string, value: string) => { saved = value; },
    },
    get value() { return saved; },
  };
}

describe("driver library store", () => {
  it("adds, updates and removes drivers, persisting every change", () => {
    const memory = memoryStorage();
    vi.stubGlobal("localStorage", memory.storage);
    const library = new DriverLibrary();
    expect(library.drivers).toEqual([]);

    library.add(DRIVER_PRESETS[0]);
    expect(library.drivers).toEqual([DRIVER_PRESETS[0]]);
    expect(memory.value).toContain("DRV8311");

    library.update(0, { ...DRIVER_PRESETS[0], name: "Renamed", max_supply_v: 48 });
    expect(library.drivers[0]).toMatchObject({ name: "Renamed", max_supply_v: 48 });
    expect(memory.value).toContain("Renamed");

    library.remove(0);
    expect(library.drivers).toEqual([]);
    expect(memory.value).toBe("[]");
  });

  it("replaceAll validates limits and unique names before persisting", () => {
    vi.stubGlobal("localStorage", memoryStorage().storage);
    const library = new DriverLibrary();
    expect(library.replaceAll([{ ...DRIVER_PRESETS[0], name: "  " }])).toContain("name");
    expect(library.replaceAll([DRIVER_PRESETS[0], { ...DRIVER_PRESETS[1], name: DRIVER_PRESETS[0].name }])).toContain("unique");
    expect(library.drivers).toEqual([]);
    expect(library.replaceAll([DRIVER_PRESETS[0], DRIVER_PRESETS[1]])).toBeNull();
    expect(library.drivers).toHaveLength(2);
  });

  it("flags unavailable storage without dropping the in-memory list", () => {
    vi.stubGlobal("localStorage", { getItem() { throw new Error("nope"); }, setItem() { throw new Error("nope"); } });
    const library = new DriverLibrary();
    library.add(DRIVER_PRESETS[0]);
    expect(library.storageAvailable).toBe(false);
    expect(library.drivers).toHaveLength(1);
  });
});
