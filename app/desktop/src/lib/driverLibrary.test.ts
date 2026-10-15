import { describe, it, expect, vi, afterEach } from "vitest";
import { driverValidationError, readCustomDrivers, saveCustomDrivers } from "./driverLibrary";
import { DRIVER_PRESETS } from "./types/drive";

afterEach(() => vi.unstubAllGlobals());

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

  it("round trips custom drivers and ignores malformed saved entries", () => {
    let saved = "[]";
    vi.stubGlobal("localStorage", {
      getItem: () => saved,
      setItem: (_key: string, value: string) => { saved = value; },
    });
    expect(saveCustomDrivers(DRIVER_PRESETS)).toBe(true);
    expect(readCustomDrivers()).toEqual(DRIVER_PRESETS);
    saved = JSON.stringify([null, {}, { name: "bad" }, DRIVER_PRESETS[0]]);
    expect(readCustomDrivers()).toEqual([DRIVER_PRESETS[0]]);
    saved = "invalid JSON";
    expect(readCustomDrivers()).toEqual([]);
  });

  it("handles unavailable storage", () => {
    vi.stubGlobal("localStorage", { getItem() { throw new Error(); }, setItem() { throw new Error(); } });
    expect(readCustomDrivers()).toEqual([]);
    expect(saveCustomDrivers(DRIVER_PRESETS)).toBe(false);
  });
});
