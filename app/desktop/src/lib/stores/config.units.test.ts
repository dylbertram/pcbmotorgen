import { expect, it } from "vitest";
import { ConfigStore } from "./config.svelte";

it("converts user-facing millimetres to metres at the IPC boundary", () => {
  const config = new ConfigStore();
  config.magnet_width_mm = 5;
  config.magnet_cross_width_mm = 8;
  config.magnet_height_mm = 2;
  config.air_gap_mm = 0.75;
  config.min_trace_mm = 0.12;
  config.trace_width_mm = 0.2;
  config.min_space_mm = 0.15;
  config.min_via_drill_mm = 0.3;
  config.min_via_annular_ring_mm = 0.1;
  const ipc = config.toIpc();
  for (const [actual, expected] of [
    [ipc.active_area_length_m, config.active_area_length_mm / 1000],
    [ipc.board_width_m, config.active_area_width_mm / 1000],
    [ipc.pcb_thickness_m, config.pcb_thickness_mm / 1000],
    [ipc.magnet_width_m, 0.005],
    [ipc.magnet_cross_width_m, 0.008],
    [ipc.magnet_height_m, 0.002],
    [ipc.magnet_gap_m, config.magnet_gap_mm / 1000],
    [ipc.magnet_pitch_m, config.pole_pitch_mm / 1000],
    [ipc.air_gap_m, 0.00075],
    [ipc.min_trace_m, 0.00012],
    [ipc.trace_width_m, 0.0002],
    [ipc.min_space_m, 0.00015],
    [ipc.min_via_drill_m, 0.0003],
    [ipc.min_via_annular_ring_m, 0.0001],
  ]) expect(actual).toBeCloseTo(expected, 12);
});
