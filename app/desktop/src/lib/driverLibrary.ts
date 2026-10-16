import type { DriverSpec } from "./types/drive";
import { DRIVER_PRESETS } from "./types/drive";

/**
 * Persisted driver library. Bundled drivers and user-added ones live together;
 * bundled entries are ordinary, DELETABLE entries rather than a separate list.
 *
 * Storage keeps the original `v1` key. The store used to hold only custom
 * drivers, so an old-only store is simply REPLACED by the bundled library
 * rather than transitioned. Once the bundled drivers are present, the stored
 * library is used as-is, so edits and deletions persist.
 */
const STORAGE_KEY = "pcbmotorgen.drivers.v1";

export function driverValidationError(driver: DriverSpec): string | null {
  if (!driver.name.trim()) return "Enter a driver name.";
  if (driver.supports_delta !== undefined && typeof driver.supports_delta !== "boolean")
    return "Delta handling must be explicitly enabled or disabled.";
  const values = [driver.min_supply_v, driver.max_supply_v, driver.peak_current_a,
    driver.continuous_rms_a, driver.rds_on_ohm, driver.max_pwm_hz];
  if (!values.every(Number.isFinite)) return "Enter a finite number for every parameter.";
  if (driver.min_supply_v < 0 || driver.max_supply_v <= driver.min_supply_v)
    return "Maximum supply must be greater than minimum supply.";
  if (driver.peak_current_a <= 0 || driver.continuous_rms_a <= 0 || driver.max_pwm_hz <= 0)
    return "Current ratings and maximum PWM frequency must be greater than zero.";
  if (driver.rds_on_ohm < 0) return "On-resistance cannot be negative.";
  return null;
}

/** Parse a stored array, dropping malformed entries. Null/garbage -> empty. */
function parseStored(raw: string | null): DriverSpec[] {
  try {
    const saved: unknown = JSON.parse(raw ?? "null");
    if (!Array.isArray(saved)) return [];
    return saved.filter((driver): driver is DriverSpec =>
      driver !== null && typeof driver === "object" &&
      typeof (driver as { name?: unknown }).name === "string" && !driverValidationError(driver));
  } catch {
    return [];
  }
}

function bundled(): DriverSpec[] {
  return DRIVER_PRESETS.map((driver) => ({ ...driver }));
}

/**
 * The saved driver library. An absent or pre-bundled store is replaced by the
 * bundled drivers; a store that already holds them is used as-is.
 */
export function readDrivers(): DriverSpec[] {
  if (typeof localStorage === "undefined") return bundled();
  try {
    const stored = parseStored(localStorage.getItem(STORAGE_KEY));
    const hasBundled = stored.some((driver) =>
      DRIVER_PRESETS.some((preset) => preset.name.toLowerCase() === driver.name.toLowerCase()));
    if (!hasBundled) {
      const seeded = bundled();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(seeded));
      return seeded;
    }
    return stored;
  } catch {
    return bundled();
  }
}

/** Return false when browser storage is unavailable; the project still keeps the selected driver. */
export function saveDrivers(drivers: DriverSpec[]): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(drivers));
    return true;
  } catch {
    return false;
  }
}
