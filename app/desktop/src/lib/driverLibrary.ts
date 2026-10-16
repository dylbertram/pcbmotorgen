import type { DriverSpec } from "./types/drive";

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

export function readCustomDrivers(): DriverSpec[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(saved)) return [];
    return saved.filter((driver): driver is DriverSpec =>
      driver !== null && typeof driver === "object" &&
      typeof driver.name === "string" && !driverValidationError(driver));
  } catch {
    return [];
  }
}

/** Return false when browser storage is unavailable; the project still keeps the selected driver. */
export function saveCustomDrivers(drivers: DriverSpec[]): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(drivers));
    return true;
  } catch {
    return false;
  }
}
