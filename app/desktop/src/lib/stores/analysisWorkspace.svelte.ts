/** Simulation tab selection belongs to an editor view, never serialised. */
export class AnalysisWorkspace {
  simulationView = $state<"move" | "force" | "advanced">("move");
}
