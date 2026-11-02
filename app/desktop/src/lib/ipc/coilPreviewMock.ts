/** Decorative browser-only coil geometry, not a generated routing result. */

import type {
  LinearMotorConfig,
  CoilArcDto,
  CoilPathDto,
  CoilSegmentDto,
  PhaseCoilDto,
  PoleRegionDto,
  RoutingDimensionsDto,
  PhaseBandWidthDto,
} from "../types";

// ---------------------------------------------------------------------------
// Browser-preview constants, not calibrated or qualified solver results.
// ---------------------------------------------------------------------------

/** Arc/annular height for the decorative preview arcs (m). */
const PREVIEW_ARC_HEIGHT_M = 0.0008;

// Reference per-slot metrics pinned from a REAL infinity-braid output (kata
// mqw4) so dev-mode readouts show realistic magnitudes: 975 active leg slots
// over a 0.6 m stator track -> tau_s = L_stator/N_slots ~= 0.6154 mm; the
// braided interleave step (effective leg pitch tau_p/(phases x strands)) is
// 0.8 mm; a single-leg slot width (w_t/sin(theta)) is ~= 0.1166 mm. A slot
// houses ONE active leg — the bundle width (band_width_m) is a different,
// larger quantity.
const REF_SLOT_COUNT = 975;
const REF_SLOT_PITCH_M = 6.1538e-4;
const REF_INTERLEAVE_STEP_M = 8.0e-4;
const REF_SLOT_WIDTH_M = 1.1662e-4;

export function mockCoils(c: LinearMotorConfig): CoilPathDto {
  // Decorative serpentine geometry gives each phase and layer a preview.
  const phases: PhaseCoilDto[] = [];
  // Span the active area so the preview covers the mover's travel.
  const moverSpan = (c.magnet_count - 1) * c.magnet_pitch_m + c.magnet_width_m;
  const domain = c.active_area_length_m;
  const width = c.board_width_m;
  const nLayers = Math.max(1, c.num_layers);
  const nConductors = Math.max(2, c.magnet_count * 2);
  const pitchX = domain / (nConductors - 1);
  const pole_pitch_m = c.magnet_pitch_m;
  // Match the canonical phase-band-pitch formula: (pole_pitch / phases) ×
  // spacing_ratio (Vernier ratio). The routing sidecar reports the ideal
  // phase-band pitch the same way — the earlier copy here omitted the
  // Vernier factor.
  const phase_band_pitch_m =
    (pole_pitch_m / Math.max(1, c.phases)) * (c.spacing_ratio || 1);
  const phase_clearance_m = c.min_space_m;
  const max_phase_band_width_m = phase_band_pitch_m - phase_clearance_m;
  // The mock mirrors the infinity braid, whose result declares a leg grid.
  // Other patterns report no pattern-declared per-slot metrics (null),
  // matching the real backend's pattern-dependent leg grid.
  const isBraid = c.routing_pattern === "infinity-braid";
  const trace_count = Math.max(
    1,
    Math.round(c.routing_params.num_strands ?? c.strands_per_phase ?? 1),
  );
  const band_width_m =
    trace_count * c.trace_width_m + (trace_count - 1) * c.min_space_m;
  const phase_band_widths: PhaseBandWidthDto[] = [];
  // Synthetic phase/pole bands in metres for the browser preview.
  const pole_regions: PoleRegionDto[] = [];
  {
    const regionsPerPhase = Math.max(
      1,
      Math.floor(domain / Math.max(pole_pitch_m, 1e-6)),
    );
    for (let p = 0; p < c.phases; p++) {
      const net = "ABC"[p] ?? String(p);
      const offset = (p * pole_pitch_m) / Math.max(1, c.phases);
      for (let i = 0; i < regionsPerPhase; i++) {
        const startX = offset + i * pole_pitch_m;
        const endX = Math.min(domain, offset + (i + 1) * pole_pitch_m);
        if (endX <= startX) continue;
        pole_regions.push({
          phase: net,
          pole_index: i,
          start: [startX, width / 2],
          end: [endX, width / 2],
        });
      }
    }
  }

  const corner_arcs: CoilArcDto[] = [];
  const via_positions: [number, number][] = [];
  if (nConductors >= 2 && width > 0) {
    // Two decorative corner arcs on the top edge + two via centers, purely
    // to exercise the arc/via render path in the preview (not connected).
    corner_arcs.push(
      { start: [pitchX * 0.5, width], mid: [pitchX, width + PREVIEW_ARC_HEIGHT_M], end: [pitchX * 1.5, width], is_active: false },
      { start: [domain - pitchX * 1.5, width], mid: [domain - pitchX, width + PREVIEW_ARC_HEIGHT_M], end: [domain - pitchX * 0.5, width], is_active: false },
    );
    via_positions.push([pitchX, width / 2], [domain - pitchX, width / 2]);
  }

  for (let layer = 0; layer < nLayers; layer++) {
    // Alternate serpentine orientation per layer (mirror) — the real braid's
    // top/bottom copies — so overlapping layers stay distinguishable.
    const flip = layer % 2 === 1;
    const segs: CoilSegmentDto[] = [];
    for (let i = 0; i < nConductors; i++) {
      const x = i * pitchX;
      const yTop = (i % 2 === 0) !== flip ? 0 : width;
      const yBot = (i % 2 === 0) !== flip ? width : 0;
      // active (vertical) conductor
      segs.push({ start: [x, yTop], end: [x, yBot], is_active: true });
      if (i < nConductors - 1) {
        // end-turn (horizontal) to next conductor
        segs.push({ start: [x, yBot], end: [x + pitchX, yBot], is_active: false });
      }
    }
    for (let p = 0; p < c.phases; p++) {
      const net = "ABC"[p] ?? String(p);
      phase_band_widths.push({
        layer,
        net,
        trace_count,
        trace_width_m: c.trace_width_m,
        trace_spacing_m: c.min_space_m,
        angle_rad: Math.PI / 2,
        band_width_m,
        slot_width_m: REF_SLOT_WIDTH_M,
        max_band_width_m: max_phase_band_width_m,
        margin_m: max_phase_band_width_m - band_width_m,
      });
      phases.push({
        phase_idx: p,
        layer_idx: layer,
        phase_name: net,
        pattern_id: c.routing_pattern,
        segments: segs,
        corner_arcs,
        via_positions,
        total_length_m: segs.reduce((s, sg) => s + Math.hypot(sg.end[0] - sg.start[0], sg.end[1] - sg.start[1]), 0),
        active_length_m: segs.filter((s) => s.is_active).reduce((s, sg) => s + Math.hypot(sg.end[0] - sg.start[0], sg.end[1] - sg.start[1]), 0),
        end_turn_length_m: segs.filter((s) => !s.is_active).reduce((s, sg) => s + Math.hypot(sg.end[0] - sg.start[0], sg.end[1] - sg.start[1]), 0),
        active_conductor_count: segs.filter((s) => s.is_active).length,
        bounding_box: [0, 0, domain, width] as [number, number, number, number],
        terminal_start: [0, 0] as [number, number],
        terminal_end: [domain, width] as [number, number],
      });
    }
  }
  const routing_dimensions: RoutingDimensionsDto = {
    active_area_length_m: c.active_area_length_m,
    total_routing_length_m: c.active_area_length_m,
    board_width_m: c.board_width_m,
    phases: Math.max(1, c.phases),
    magnet_array_span_m: moverSpan,
    pole_pitch_m,
    period_pitch_m: c.routing_pattern === "infinity-braid" ? pole_pitch_m : null,
    period_count:
      c.routing_pattern === "infinity-braid"
        ? Math.max(1, Math.floor(c.active_area_length_m / pole_pitch_m))
        : null,
    phase_band_pitch_m,
    phase_clearance_m,
    max_phase_band_width_m,
    slot_count: isBraid ? REF_SLOT_COUNT : null,
    slot_pitch_m: isBraid ? REF_SLOT_PITCH_M : null,
    interleave_step_m: isBraid ? REF_INTERLEAVE_STEP_M : null,
    phase_band_widths,
    pole_regions,
  };
  return { phases, layer_count: c.num_layers, routing_dimensions };
}
