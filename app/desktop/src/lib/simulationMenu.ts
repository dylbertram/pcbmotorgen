import items from "./simulationMenu.json";

export type SimulationAction = "driver" | "run" | "move" | "force" | "fields" | "advanced";
export const SIMULATION_MENU = items as { id: SimulationAction; label: string }[];
export function isSimulationAction(value: unknown): value is SimulationAction {
  return typeof value === "string" && SIMULATION_MENU.some(item => item.id === value);
}
