import type { CoilPathDto, CoilSegmentDto, PhaseCoilDto } from "../types";

/** Three phases on two layers, with four conductors per phase and layer. */
export function braidLikeFixture(): CoilPathDto {
  const phases: PhaseCoilDto[] = [];
  for (let layer = 0; layer < 2; layer++) {
    for (let p = 0; p < 3; p++) {
      const segs: CoilSegmentDto[] = [];
      const offset = p * 0.003;
      for (let i = 0; i < 4; i++) {
        const x = offset + i * 0.004;
        const yTop = layer % 2 === 0 ? 0 : 0.02;
        segs.push({ start: [x, yTop], end: [x, 0.02 - yTop], is_active: true });
        if (i < 3) {
          segs.push({
            start: [x, 0.02 - yTop],
            end: [x + 0.004, 0.02 - yTop],
            is_active: false,
          });
        }
      }
      phases.push({
        phase_idx: p,
        layer_idx: layer,
        phase_name: "ABC"[p],
        pattern_id: "infinity-braid",
        segments: segs,
        corner_arcs: layer === 0 && p === 0 ? [{ start: [0, 0.02], mid: [0.001, 0.021], end: [0.002, 0.02], is_active: false }] : [],
        via_positions: [],
        total_length_m: 1,
        active_length_m: 1,
        end_turn_length_m: 0,
        active_conductor_count: 4,
        bounding_box: [0, 0, 0.02, 0.02],
        terminal_start: [0, 0],
        terminal_end: [0.02, 0.02],
      });
    }
  }
  return { phases, layer_count: 4 };
}
