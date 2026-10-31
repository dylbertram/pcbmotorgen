import type { DriverSpec, LinearMotorConfig } from "./types";

/** Matches the infinity-braid connection contract on motor-coil-generator-add-inputs.
 * This is pattern-owned metadata, not a global meaning for every `connection` parameter.
 * Imported copper does not inherit the generated pattern's termination setting.
 */
export function usesDeltaConnection(config: Pick<LinearMotorConfig, "routing_pattern" | "routing_params">, importedCopper = false): boolean {
  const pattern = config.routing_pattern.trim() || "infinity-braid";
  return !importedCopper && pattern === "infinity-braid" &&
    Math.round(config.routing_params.connection ?? 0) === 1;
}

export function driverConnectionError(driver: DriverSpec, delta: boolean): string | null {
  if (!delta) return null;
  const location = "Choose a Star (Wye) routing source in Routing. For uploaded copper, set Winding connection in Coil ends.";
  if (!driver.supports_delta) {
    return `${driver.name} has no declared built-in delta handling. Star (wye) configuration is required. ${location}`;
  }
  // Hardware compatibility does not make the current star-only voltage,
  // line-current and ripple equations valid for a delta winding.
  return `Delta handling is declared for ${driver.name}, but delta electrical analysis is not yet available. ${location}`;
}
