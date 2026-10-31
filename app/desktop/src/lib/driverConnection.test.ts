import { describe, it, expect } from "vitest";
import { driverConnectionError, usesDeltaConnection } from "./driverConnection";
import { DRIVER_PRESETS } from "./types/drive";

describe("winding connection compatibility", () => {
  it("uses the other branch's pattern-owned connection values", () => {
    const config = { routing_pattern: "infinity-braid", routing_params: { connection: 1 } };
    expect(usesDeltaConnection(config)).toBe(true);
    expect(usesDeltaConnection({ ...config, routing_pattern: "" })).toBe(true);
    expect(usesDeltaConnection({ ...config, routing_pattern: " infinity-braid " })).toBe(true);
    expect(usesDeltaConnection(config, true)).toBe(false);
    expect(usesDeltaConnection({ ...config, routing_pattern: "another-pattern" })).toBe(false);
    for (const connection of [0, 2]) {
      expect(usesDeltaConnection({ ...config, routing_params: { connection } })).toBe(false);
    }
  });

  it("requires star/wye for presets and legacy custom drivers", () => {
    for (const driver of [...DRIVER_PRESETS, { ...DRIVER_PRESETS[0], supports_delta: undefined }]) {
      expect(driverConnectionError(driver, false)).toBeNull();
      expect(driverConnectionError(driver, true)).toContain("Star (wye) configuration is required");
      expect(driverConnectionError(driver, true)).toContain("Star (Wye) routing source in Routing");
      expect(driverConnectionError(driver, true)).toContain("Winding connection in Coil ends");
    }
  });

  it("does not confuse declared hardware support with delta model availability", () => {
    const driver = { ...DRIVER_PRESETS[0], supports_delta: true };
    expect(driverConnectionError(driver, true)).toContain("delta electrical analysis is not yet available");
    expect(driverConnectionError(driver, true)).not.toContain("no declared built-in delta handling");
  });
});
