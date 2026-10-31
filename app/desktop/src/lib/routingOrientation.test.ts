import { describe, expect, it } from "vitest";
import { DEFAULT_ROUTING_ORIENTATION, flipCadGeometry, orientCoilPreview } from "./routingOrientation";
import { ConfigStore } from "./stores/config.svelte";
import type { CadGeometry } from "./types";
import { mockCoils } from "./ipc/mocks";

const fixture = (): CadGeometry => ({
  trace_width_mm: .2, layer_z_mm: [0, -.2, -.7, -.8], source_file_name: "reference.dxf", coil_phases: { winding: "A" },
  routing: { format_version: 2, segments: [{ start: { x: 1, y: 2 }, end: { x: 9, y: 4 }, layer: 0, net: "winding", is_active: true }],
    curves: [{ start: { x: 1, y: 2 }, mid: { x: 3, y: 4 }, end: { x: 5, y: 2 }, layer: 1, net: "winding", is_active: false }],
    splines: [{ degree: 1, knots: [0, 0, 1, 1], control_points: [{ x: 1, y: 2 }, { x: 9, y: 4 }], weights: [1, 1], layer: 2, net: "winding", is_active: false }],
    vias: [{ position: { x: 1, y: 2 }, from_layer: 0, to_layer: 3, net: "winding" }] },
  coil_terminals: { winding: { input: { position: { x: 1, y: 2 }, layer: 0 }, output: { position: { x: 9, y: 4 }, layer: 3 } } },
});

describe("routing reflections", () => {
  for (let mask = 0; mask < 8; mask++) it(`preserves all CAD primitives and picked endpoints for combination ${mask}`, () => {
    const flip = { mirror_x: !!(mask & 1), mirror_y: !!(mask & 2), reverse_layers: !!(mask & 4) };
    const source = fixture(), before = JSON.stringify(source), result = flipCadGeometry(source, flip);
    expect(result.routing.segments[0].start).toEqual({ x: flip.mirror_x ? 9 : 1, y: flip.mirror_y ? 4 : 2 });
    expect(result.routing.segments[0].layer).toBe(flip.reverse_layers ? 3 : 0);
    expect(result.coil_terminals!.winding.input).toEqual({ position: result.routing.segments[0].start, layer: result.routing.segments[0].layer });
    expect(result.routing.vias[0].to_layer).toBe(flip.reverse_layers ? 0 : 3);
    expect(result.routing.splines![0].knots).toEqual(source.routing.splines![0].knots);
    expect(result.routing.splines![0].control_points[0]).toEqual(result.routing.segments[0].start);
    expect(result.coil_phases).toEqual(source.coil_phases);
    expect(result.source_file_name).toBe(source.source_file_name);
    const twice = flipCadGeometry(result, flip);
    expect(twice.routing).toEqual(source.routing);
    twice.layer_z_mm.forEach((z, layer) => expect(z).toBeCloseTo(source.layer_z_mm[layer], 12));
    expect(JSON.stringify(source)).toBe(before);
  });

  it("reverses asymmetric stackups once and restores them on the second flip", () => {
    const config = new ConfigStore();
    config.pcb_stackup_mm = { copper_mm: [.035, .018, .07, .105], dielectric_mm: [.1, .3, .172] };
    const before = JSON.stringify(config.pcb_stackup_mm), thickness = config.pcb_thickness_mm;
    config.toggleRoutingFlip("reverse_layers");
    expect(config.pcb_stackup_mm!.copper_mm).toEqual([.105, .07, .018, .035]);
    expect(config.pcb_stackup_mm!.dielectric_mm).toEqual([.172, .3, .1]);
    expect(config.pcb_thickness_mm).toBeCloseTo(thickness, 12);
    expect(config.toIpc().routing_orientation!.reverse_layers).toBe(true);
    config.toggleRoutingFlip("reverse_layers");
    expect(JSON.stringify(config.pcb_stackup_mm)).toBe(before);
    expect(config.routing_orientation).toEqual(DEFAULT_ROUTING_ORIENTATION);
  });

  it("browser preview flips match the persisted native generation settings without changing path lengths", () => {
    const config = new ConfigStore(), input = config.toIpc(), source = mockCoils(input), before = JSON.stringify(source);
    input.routing_orientation = { mirror_x: true, mirror_y: true, reverse_layers: true };
    const result = orientCoilPreview(source, input);
    for (const old of source.phases) {
      const phase = result.phases.find(p => p.phase_idx === old.phase_idx && p.layer_idx === input.num_layers - 1 - old.layer_idx)!;
      expect(phase.segments[0].start[0]).toBeCloseTo(input.active_area_length_m - old.segments[0].start[0], 12);
      expect(phase.segments[0].start[1]).toBeCloseTo(input.board_width_m - old.segments[0].start[1], 12);
      expect(phase.total_length_m).toBe(old.total_length_m);
    }
    expect(JSON.stringify(source)).toBe(before);
  });
});
