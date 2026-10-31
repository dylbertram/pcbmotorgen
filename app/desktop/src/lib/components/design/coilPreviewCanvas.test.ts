import { beforeAll, describe, expect, it } from "vitest";
import { CoilPreviewRenderer, type CoilPreviewDrawInput } from "./coilPreviewCanvas";
import type { CoilPathDto, PhaseCoilDto } from "../../types";

function phase(layer: number, vias: [number, number][]): PhaseCoilDto {
  return {
    phase_idx: 0, layer_idx: layer, phase_name: "A", pattern_id: "test",
    segments: [{ start: [0, 0], end: [0.001, 0], is_active: true }], corner_arcs: [],
    via_positions: vias, total_length_m: 0.001, active_length_m: 0.001, end_turn_length_m: 0,
    active_conductor_count: 1, bounding_box: [0, 0, 0.001, 0],
    terminal_start: [0, 0], terminal_end: [0.001, 0],
  };
}

function drawnVias(visibleLayers: number[], showVias = true, annotationsOnly = false, calls?:string[]): string | undefined {
  // Every 2D call is a no-op; the renderer reports what it drew in dataset.
  const ctx = new Proxy({}, { get: (_,key) => () => {calls?.push(String(key));}, set: () => true });
  const canvas = { getContext: () => ctx, dataset: {} as DOMStringMap } as unknown as HTMLCanvasElement;
  const frame = { clientWidth: 760, clientHeight: 260 } as HTMLDivElement;
  const coils = { phases: [phase(0, [[0.0005, 0]]), phase(1, [])] } as unknown as CoilPathDto;
  const input = {
    annotationsOnly,
    coils, activeAreaLengthMm: 1,
    geometry: { boardRect: { x: 0, y: 0, w: 1, h: 1 }, magnetTop: 0 },
    worldTransform: { s: 1, tx: 0, ty: 0 }, panX: 0, panY: 0, visibleMagnets: [],
    visibleSegments: new Map(), visibleArcs: new Map(),
    isPhaseVisible: () => true,
    isLayerVisible: (layer: number) => visibleLayers.includes(layer),
    isCoilLayerVisible: () => true,
    showVias, traceMode: "traces", traceWidthMm: 0.2, viaDrillMm: 0.3, viaAnnularRingMm: 0.1,
    poleRuler: null, showPolePitch: false, bandRows: [], poleRegions: [], measure: null,
  } as unknown as CoilPreviewDrawInput;
  new CoilPreviewRenderer().draw(frame, canvas, input);
  return canvas.dataset.vias;
}

describe("coil preview vias", () => {
  beforeAll(() => {
    (globalThis as { window?: unknown }).window ??= { devicePixelRatio: 1 };
  });

  it("stay visible when the layer holding them is hidden", () => {
    expect(drawnVias([0, 1])).toBe("1");
    expect(drawnVias([1])).toBe("1");
    expect(drawnVias([])).toBe("1");
  });

  it("hide with the via toggle", () => {
    expect(drawnVias([0, 1], false)).toBe("0");
  });
  it("does not draw copper or via pads in the shared renderer's annotation layer",()=>{
    const calls:string[]=[];
    expect(drawnVias([0,1],true,true,calls)).toBe("1");
    expect(calls).not.toContain("arc");
    expect(calls).not.toContain("lineTo");
    expect(calls).toContain("strokeRect");
  });
});
