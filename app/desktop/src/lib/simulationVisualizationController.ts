import type { VisualizationInput, VisualizationRequest, VisualizationReport } from "./types/simulationVisualization";

const vector = (v: number[]) => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);

export function validateVisualization(report: VisualizationReport, request: VisualizationRequest): void {
  if (report.schema !== "simulation-visualization-v1" || report.request_id !== request.request_id
    || !/^[a-f0-9]{64}$/.test(report.input_sha256) || !/^[a-f0-9]{64}$/.test(report.implementation_sha256)
    || typeof report.app_version !== "string" || !report.app_version || "pm_array_force_n" in report || "qualified_case" in report) {
    throw new Error("Unverified or stale visualization response");
  }
  if (request.fields) {
    const field = report.field;
    if (!field || field.method !== "analytical-pm-only-xyz" || field.samples.length !== request.counts.reduce((a, b) => a * b, 1)
      || field.samples.length > 2048 || field.magnets.length > 12) throw new Error("Missing bounded XYZ field samples");
    for (let i = 0; i < field.samples.length; i++) {
      const sample = field.samples[i];
      const indices = [i % request.counts[0], Math.floor(i / request.counts[0]) % request.counts[1], Math.floor(i / (request.counts[0] * request.counts[1]))];
      if (!vector(sample.position_m) || !vector(sample.b_t) || !Number.isFinite(sample.magnitude_t) || sample.magnitude_t < 0
        || Math.abs(Math.hypot(...sample.b_t) - sample.magnitude_t) > Math.max(1e-12, sample.magnitude_t * 1e-10)
        || indices.some((index, axis) => Math.abs(sample.position_m[axis] - (request.bounds_m[axis][0]
          + index * (request.bounds_m[axis][1] - request.bounds_m[axis][0]) / (request.counts[axis] - 1))) > 1e-12)) {
        throw new Error("Field positions, magnitudes or XYZ ordering differ from this physical request");
      }
    }
    if (field.magnets.some(m => !vector(m.center_m) || !vector(m.size_m) || m.size_m.some(v => v <= 0) || typeof m.positive_z !== "boolean")) {
      throw new Error("Malformed physical magnet geometry");
    }
  } else if (report.field !== null) throw new Error("Unrequested field data returned");
  if (report.heat) {
    const heat = report.heat;
    if (!request.heat || heat.method !== "native-resistor-graph-rms-i2r" || heat.phase_peak_a !== request.phase_peak_a
      || !Number.isFinite(heat.phase_rms_a) || Math.abs(heat.phase_rms_a - request.phase_peak_a / Math.SQRT2) > 1e-12
      || !Number.isFinite(heat.winding_temperature_c) || !Number.isFinite(heat.total_loss_w) || heat.total_loss_w < 0
      || !Number.isFinite(heat.power_balance_relative_error) || heat.power_balance_relative_error < 0 || heat.power_balance_relative_error > 1e-8
      || heat.edges.length === 0 || heat.edges.length > 10000) throw new Error("Unverified native copper loss response");
    let total = 0;
    for (const edge of heat.edges) {
      if (!["trace", "via"].includes(edge.kind) || !edge.net || edge.layers.length !== 2 || !edge.layers.every(v => Number.isInteger(v) && v >= 0 && v < 16)
        || edge.points_m.length < 2 || edge.points_m.length > 128 || edge.points_m.some(p => !vector(p))
        || !Number.isFinite(edge.loss_w) || edge.loss_w < 0 || !Number.isFinite(edge.rms_current_a) || !Number.isFinite(edge.resistance_ohm) || edge.resistance_ohm <= 0
        || Math.abs(edge.loss_w - edge.rms_current_a ** 2 * edge.resistance_ohm) > Math.max(1e-12, edge.loss_w * 1e-9)) {
        throw new Error("Invalid native branch I²R loss or physical coordinates");
      }
      total += edge.loss_w;
    }
    if (Math.abs(total - heat.total_loss_w) > Math.max(1e-12, total * 1e-8)) throw new Error("Mapped branch loss does not conserve total copper power");
  } else if (request.heat && !report.heat_unavailable_reason) throw new Error("Missing loss data or explicit unavailable reason");
}

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
