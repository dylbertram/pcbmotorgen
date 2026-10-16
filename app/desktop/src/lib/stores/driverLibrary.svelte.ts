/**
 * Shared, reactive view of the saved driver library.
 *
 * The Simulation tab's driver selector/Add flow and the Settings editor both
 * read and write this one instance, so an edit in either place shows up in the
 * other without a reload. Validation and persistence stay in
 * `lib/driverLibrary.ts` (pure functions, unit-tested); this store only holds
 * the in-memory list and reports whether a write reached browser storage.
 */
import { driverValidationError, readCustomDrivers, saveCustomDrivers } from "../driverLibrary";
import type { DriverSpec } from "../types/drive";

export class DriverLibrary {
  drivers = $state<DriverSpec[]>(readCustomDrivers());
  /** False once a write fails; the current project still keeps its driver. */
  storageAvailable = $state(true);

  #persist(): void {
    this.storageAvailable = saveCustomDrivers($state.snapshot(this.drivers));
  }

  /**
   * Replace the whole library after validating each entry. Returns the first
   * problem message, or null when the list was applied and persisted.
   */
  replaceAll(drivers: DriverSpec[]): string | null {
    for (const driver of drivers) {
      const error = driverValidationError(driver);
      if (error) return `${driver.name.trim() || "Driver"}: ${error}`;
    }
    const names = drivers.map((driver) => driver.name.trim().toLowerCase());
    if (new Set(names).size !== names.length) return "Driver names must be unique.";
    this.drivers = drivers.map((driver) => ({ ...driver }));
    this.#persist();
    return null;
  }

  add(driver: DriverSpec): void {
    this.drivers = [...this.drivers, { ...driver }];
    this.#persist();
  }

  update(index: number, driver: DriverSpec): void {
    this.drivers = this.drivers.map((saved, i) => (i === index ? { ...driver } : saved));
    this.#persist();
  }

  remove(index: number): void {
    this.drivers = this.drivers.filter((_, i) => i !== index);
    this.#persist();
  }
}

export const driverLibrary = new DriverLibrary();
