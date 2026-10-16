import { describe, it, expect, vi, afterEach } from "vitest";
import { driverValidationError, readDrivers, saveDrivers } from "./driverLibrary";
import { DRIVER_PRESETS } from "./types/drive";

afterEach(() => vi.unstubAllGlobals());

/** Keyed in-memory localStorage stand-in that records writes. */
function keyedStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  return {
    storage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
    },
    get: (key: string) => store.get(key) ?? null,
  };
}

const DRIVERS_KEY = "pcbmotorgen.drivers.v1";

describe("driver library", () => {
  it("validates physical limits", () => {
    const driver = DRIVER_PRESETS[0];
    expect(driverValidationError(driver)).toBeNull();
    for (const patch of [{ name: " " }, { max_supply_v: 0 }, { peak_current_a: -1 },
      { continuous_rms_a: 0 }, { rds_on_ohm: -1 }, { max_pwm_hz: Infinity }]) {
      expect(driverValidationError({ ...driver, ...patch })).not.toBeNull();
    }
    expect(driverValidationError({ ...driver, supports_delta: true })).toBeNull();
    expect(driverValidationError({ ...driver, supports_delta: "yes" } as unknown as typeof driver)).not.toBeNull();
  });

  it("seeds the bundled drivers on first run", () => {
    const memory = keyedStorage();
    vi.stubGlobal("localStorage", memory.storage);
    expect(readDrivers()).toEqual(DRIVER_PRESETS);
    expect(JSON.parse(memory.get(DRIVERS_KEY)!)).toEqual(DRIVER_PRESETS);
  });

  it("replaces an old custom-only store instead of transitioning it", () => {
    const memory = keyedStorage({ [DRIVERS_KEY]: JSON.stringify([{ ...DRIVER_PRESETS[0], name: "My driver" }]) });
    vi.stubGlobal("localStorage", memory.storage);
    expect(readDrivers()).toEqual(DRIVER_PRESETS);
    expect(JSON.parse(memory.get(DRIVERS_KEY)!).map((driver: { name: string }) => driver.name))
      .toEqual(DRIVER_PRESETS.map((driver) => driver.name));
  });

  it("keeps a library that already holds bundled drivers, so deletions persist", () => {
    const remaining = [DRIVER_PRESETS[1], DRIVER_PRESETS[2]];
    const memory = keyedStorage({ [DRIVERS_KEY]: JSON.stringify(remaining) });
    vi.stubGlobal("localStorage", memory.storage);
    expect(readDrivers()).toEqual(remaining);
    expect(JSON.parse(memory.get(DRIVERS_KEY)!)).toEqual(remaining);
  });

  it("drops malformed entries and falls back to the bundled drivers", () => {
    vi.stubGlobal("localStorage", keyedStorage({ [DRIVERS_KEY]: JSON.stringify([null, {}, { name: "bad" }, DRIVER_PRESETS[0]]) }).storage);
    expect(readDrivers()).toEqual([DRIVER_PRESETS[0]]);
    vi.stubGlobal("localStorage", { getItem() { throw new Error(); }, setItem() { throw new Error(); } });
    expect(readDrivers()).toEqual(DRIVER_PRESETS);
    expect(saveDrivers(DRIVER_PRESETS)).toBe(false);
  });
});
