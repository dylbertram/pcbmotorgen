import { describe, it, expect } from "vitest";
import { generatedTerminalGeometry } from "./generatedTerminalGeometry";
import type { CoilPathDto } from "./types";
import type { CadGeometry } from "./types";
import { cadGeometryToPreview } from "./cadPreview";
import { defaultCadTerminals } from "./cadTerminals";

function seriesStar(layers: number): CadGeometry {
  const geometry: CadGeometry = { layer_z_mm: Array.from({ length: layers }, (_, i) => -i), trace_width_mm: .2,
    routing: { format_version: 2, segments: [], curves: [], vias: [] } };
  for (const [i, net] of ["A", "B", "C"].entries()) {
    const y = 100 + i * 10;
    const add = (layer: number, ax: number, ay: number, bx: number, by: number) =>
      geometry.routing.segments.push({ layer, net, start: { x: ax, y: ay }, end: { x: bx, y: by }, is_active: false });
    for (let stage = 0; stage < layers / 2; stage++) {
      const lo = layers - 2 - 2 * stage, hi = lo + 1;
      const x = stage * 20;
      add(hi, x, y, x + 15, y - 1);
      geometry.routing.vias.push({ position: { x: x + 15, y: y - 1 }, from_layer: lo, to_layer: hi, net });
      add(lo, x + 15, y - 1, x + 20, y);
      if (stage + 1 < layers / 2) {
        geometry.routing.vias.push({ position: { x: x + 20, y }, from_layer: 0, to_layer: layers - 1, net });
      } else add(0, x + 20, y, 100, 0);
    }
  }
  return geometry;
}

describe("generated display depths match native physics", () => {
  it("keeps layer0 at PCB top and later layers at negative physical depths", () => {
    const coils = { phases: [] } as unknown as CoilPathDto;
    expect(generatedTerminalGeometry(coils, 3, .8, .2).layer_z_mm).toEqual([0, -.4, -.8]);
    expect(generatedTerminalGeometry(coils, 1, .8, .2).layer_z_mm).toEqual([0]);
  });
});

describe("generated terminal via topology", () => {
  for (const layers of [2, 4, 6, 8]) {
    it(`keeps mixed pair and full-stack barrels and automatic ends across ${layers} layers`, () => {
      const original = seriesStar(layers);
      const preview = cadGeometryToPreview(original);
      const geometry = generatedTerminalGeometry(preview, layers, 1.6, .2, 2);
      expect(geometry.routing.vias).toHaveLength(original.routing.vias.length);
      for (const via of original.routing.vias) {
        const actual = geometry.routing.vias.find((v) => v.net === via.net
          && v.from_layer === via.from_layer && v.to_layer === via.to_layer
          && Math.hypot(v.position.x - via.position.x, v.position.y - via.position.y) < 1e-9);
        expect(actual).toBeDefined();
      }
      for (const [i, net] of ["A", "B", "C"].entries()) {
        expect(geometry.coil_terminals?.[net]).toEqual({
          input: { layer: layers - 1, position: { x: 0, y: 100 + 10 * i } },
          output: { layer: 0, position: { x: 100, y: 0 } },
        });
      }
      if (layers > 2) {
        const broken = structuredClone(geometry);
        broken.routing.vias = broken.routing.vias.filter((v) => !(v.net === "A" && v.to_layer - v.from_layer > 1));
        expect(defaultCadTerminals(broken, "A")).toBeNull();
      }
    });
  }

  it("treats an exact empty list as authoritative and retains the position-only legacy fallback", () => {
    const phase = { phase_name: "A", layer_idx: 0, segments: [], via_positions: [[.001, .002]], routed_vias: [] };
    const exact = generatedTerminalGeometry({ phases: [phase] } as unknown as CoilPathDto, 2, 1.6, .2);
    expect(exact.routing.vias).toEqual([]);
    const legacyPhase = { ...phase, routed_vias: undefined };
    const legacy = generatedTerminalGeometry({ phases: [legacyPhase] } as unknown as CoilPathDto, 2, 1.6, .2);
    expect(legacy.routing.vias).toEqual([{ position: { x: 1, y: 2 }, net: "A", from_layer: 0, to_layer: 1 }]);
  });
});
