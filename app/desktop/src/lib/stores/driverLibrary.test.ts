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

const NAMES = DRIVER_PRESETS.map((driver) => driver.name);

describe("driver library store", () => {
  it("starts from the seeded bundled drivers and persists edits", () => {
    const memory = memoryStorage();
    vi.stubGlobal("localStorage", memory.storage);
    const library = new DriverLibrary();
    // First run seeds the bundled drivers into the library.
    expect(library.drivers.map((driver) => driver.name)).toEqual(NAMES);

    library.add({ ...DRIVER_PRESETS[0], name: "Mine" });
    expect(library.drivers).toHaveLength(4);
    expect(memory.value).toContain("Mine");

    library.update(0, { ...DRIVER_PRESETS[0], name: "Renamed", max_supply_v: 48 });
    expect(library.drivers[0]).toMatchObject({ name: "Renamed", max_supply_v: 48 });

    // Bundled entries are deletable like any other.
    library.remove(0);
    expect(library.drivers.map((driver) => driver.name)).toEqual(["DRV8316", "DRV8313", "Mine"]);
    expect(memory.value).not.toContain("Renamed");
  });

  it("replaceAll validates limits and unique names before persisting", () => {
    vi.stubGlobal("localStorage", memoryStorage().storage);
    const library = new DriverLibrary();
    expect(library.replaceAll([{ ...DRIVER_PRESETS[0], name: "  " }])).toContain("name");
    expect(library.drivers.map((driver) => driver.name)).toEqual(NAMES);
    expect(library.replaceAll([DRIVER_PRESETS[0], { ...DRIVER_PRESETS[1], name: DRIVER_PRESETS[0].name }])).toContain("unique");
    expect(library.replaceAll([DRIVER_PRESETS[0], DRIVER_PRESETS[1]])).toBeNull();
    expect(library.drivers).toHaveLength(2);
  });

  it("flags unavailable storage without dropping the in-memory list", () => {
    vi.stubGlobal("localStorage", { getItem() { throw new Error("nope"); }, setItem() { throw new Error("nope"); } });
    const library = new DriverLibrary();
    expect(library.drivers.map((driver) => driver.name)).toEqual(NAMES);
    library.add(DRIVER_PRESETS[0]);
    expect(library.storageAvailable).toBe(false);
    expect(library.drivers).toHaveLength(4);
  });
});
