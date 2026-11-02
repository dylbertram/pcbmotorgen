import type { VisualizationInput, VisualizationRequest, VisualizationReport } from "../types/simulationVisualization";
import { validateVisualization } from "./visualizationValidation";

export interface VisualizationView { phase: "idle" | "loading" | "ready" | "failed"; report: VisualizationReport | null; error: string | null }

/** No queued result can survive an edit, mode change, tab departure or unmount. */
export class SimulationVisualizationController {
  private generation = 0;
  private inFlight = false;
  private pending: { input: VisualizationInput; request: VisualizationRequest; generation: number } | null = null;
  constructor(private transport: (input: VisualizationInput, request: VisualizationRequest) => Promise<VisualizationReport>,
    private update: (view: VisualizationView) => void) {}
  invalidate() { ++this.generation; this.pending = null; this.update({ phase: "idle", report: null, error: null }); }
  async sample(input: VisualizationInput, request: VisualizationRequest) {
    const generation = ++this.generation;
    this.update({ phase: "loading", report: null, error: null });
    if (this.inFlight) { this.pending = { input, request, generation }; return; }
    await this.run(input, request, generation);
  }
  private async run(input: VisualizationInput, request: VisualizationRequest, generation: number) {
    this.inFlight = true;
    try {
      const report = await this.transport(input, request);
      if (generation !== this.generation) return;
      validateVisualization(report, request);
      this.update({ phase: "ready", report, error: null });
    } catch (error) {
      if (generation === this.generation) this.update({ phase: "failed", report: null, error: String(error) });
    } finally {
      this.inFlight = false;
      const next = this.pending; this.pending = null;
      if (next && next.generation === this.generation) await this.run(next.input, next.request, next.generation);
    }
  }
}
