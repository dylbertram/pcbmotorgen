import { describe, it, expect, vi } from "vitest";
import { SimulationVisualizationController, validateVisualization, type VisualizationView } from "./simulationVisualizationController";
import type { VisualizationInput, VisualizationRequest, VisualizationReport } from "./types/simulationVisualization";

export const request = (id = "one"): VisualizationRequest => ({ request_id: id, mover_position_m: 0,
  bounds_m: [[0, .01], [0, .01], [-.001, .005]], counts: [2, 2, 2], phase_peak_a: 1, fields: true, heat: false });
export function report(r = request()): VisualizationReport {
  const samples = Array.from({ length: 8 }, (_, i) => ({ position_m: [i % 2 ? .01 : 0, Math.floor(i / 2) % 2 ? .01 : 0, i >= 4 ? .005 : -.001] as [number, number, number],
    b_t: [0, 0, .1] as [number, number, number], magnitude_t: .1 }));
  return { schema: "simulation-visualization-v1", request_id: r.request_id, input_sha256: "a".repeat(64), implementation_sha256: "b".repeat(64), app_version: "test-only", coordinate_convention: "SI routing, PCB topZ=0",
    field: { method: "analytical-pm-only-xyz", scope: "test data only", samples, magnets: [] }, heat: null, heat_unavailable_reason: null };
}
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
const input = {} as VisualizationInput;

describe("request-bound native visualization", () => {
  it("requires real XYZ locations, finite vectors and honest source scope", () => {
    validateVisualization(report(), request());
    for (const change of ["identity", "vector", "point", "magnitude", "scope", "force"]) {
      const value = report();
      if (change === "identity") value.request_id = "old";
      else if (change === "vector") value.field!.samples[0].b_t[1] = NaN;
      else if (change === "point") value.field!.samples[2].position_m[1] = 0;
      else if (change === "magnitude") value.field!.samples[0].magnitude_t = 99;
      else if (change === "scope") Object.assign(value.field!, { method: "qualified-coupled-field" });
      else Object.assign(value, { pm_array_force_n: [1, 2, 3] });
      expect(() => validateVisualization(value, request())).toThrow();
    }
  });
  it("clears existing data immediately on edit and suppresses old responses", async () => {
    const views: VisualizationView[] = [], pending = deferred<VisualizationReport>();
    const transport = vi.fn().mockResolvedValueOnce(report()).mockReturnValueOnce(pending.promise);
    const controller = new SimulationVisualizationController(transport, v => views.push(v));
    await controller.sample(input, request()); expect(views.at(-1)!.phase).toBe("ready");
    const work = controller.sample(input, request("old")); expect(views.at(-1)!.report).toBeNull();
    controller.invalidate(); pending.resolve(report(request("old"))); await work;
    expect(views.at(-1)!.phase).toBe("idle"); expect(views.at(-1)!.report).toBeNull();
  });
  it("checks branch I-squared-R, physical points and the total instead of distributing an aggregate loss", () => {
    const r = { ...request(), fields: false, heat: true };
    const value: VisualizationReport = { ...report(r), field: null, heat: {
      method: "native-resistor-graph-rms-i2r", scope: "unit-test data", phase_peak_a: 1, phase_rms_a: 1 / Math.SQRT2,
      winding_temperature_c: 75, total_loss_w: .5, power_balance_relative_error: 0,
      edges: [{ net: "A", kind: "trace", layers: [0, 0], points_m: [[0, 0, 0], [.01, 0, 0]], loss_w: .5, rms_current_a: .5, resistance_ohm: 2 }] } };
    validateVisualization(value, r);
    for (const change of ["total", "branch", "point", "current", "reference", "method"]) {
      const changed = structuredClone(value);
      if (change === "total") changed.heat!.total_loss_w = 99;
      else if (change === "branch") changed.heat!.edges[0].loss_w = .4;
      else if (change === "point") changed.heat!.edges[0].points_m[0][1] = Infinity;
      else if (change === "current") changed.heat!.phase_peak_a = 2;
      else if (change === "reference") changed.heat!.power_balance_relative_error = .001;
      else Object.assign(changed.heat!, { method: "inferred-temperature" });
      expect(() => validateVisualization(changed, r)).toThrow();
    }
    const unavailable = { ...value, heat: null, heat_unavailable_reason: "Actual route is disconnected" };
    validateVisualization(unavailable, r);
    expect(() => validateVisualization({ ...unavailable, heat_unavailable_reason: null }, r)).toThrow();
  });
  it("serializes work and retains only the latest request, never launching after unmount", async () => {
    const pending = deferred<VisualizationReport>(); const views: VisualizationView[] = [];
    const transport = vi.fn().mockReturnValueOnce(pending.promise).mockImplementation(async (_i, r) => report(r));
    const controller = new SimulationVisualizationController(transport, v => views.push(v));
    const work = controller.sample(input, request()); await controller.sample(input, request("two")); await controller.sample(input, request("three"));
    expect(transport).toHaveBeenCalledTimes(1); pending.resolve(report()); await work;
    expect(transport).toHaveBeenCalledTimes(2); expect(views.at(-1)!.report!.request_id).toBe("three");
    const next = deferred<VisualizationReport>(); transport.mockReturnValueOnce(next.promise);
    const running = controller.sample(input, request("four")); await controller.sample(input, request("five")); controller.invalidate();
    next.resolve(report(request("four"))); await running; expect(transport).toHaveBeenCalledTimes(3); expect(views.at(-1)!.phase).toBe("idle");
  });
});
