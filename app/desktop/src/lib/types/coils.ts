/**
 * Generated coil geometry (generate_coils).
 */
import type { CadRouteSpline } from "./dxf";

export interface CoilSegmentDto {
  start: [number, number]; // (x, y) [m]
  end: [number, number]; // (x, y) [m]
  is_active: boolean;
}

/** One rounded corner / curve: quadratic Bézier control points (x, y) [m]. */
export interface CoilArcDto {
  start: [number, number];
  mid: [number, number];
  end: [number, number];
  /** Active force-producing curve vs end-turn connector. */
  is_active?: boolean;
}

export interface PhaseCoilDto {
  phase_idx: number;
  layer_idx: number;
  phase_name: string;
  /** Routing-pattern id this coil was generated with. */
  pattern_id: string;
  segments: CoilSegmentDto[];
  total_length_m: number;
  active_length_m: number;
  end_turn_length_m: number;
  active_conductor_count: number;
  bounding_box: [number, number, number, number]; // min_x, min_y, max_x, max_y
  terminal_start: [number, number];
  terminal_end: [number, number];
  /** Rounded corners / curves (absent for straight-line-only patterns). */
  corner_arcs?: CoilArcDto[];
  /** Editable imported splines; control point coordinates are metres here. */
  splines?: CadRouteSpline[];
  /** Center positions of inter-layer vias, (x, y) [m]. */
  via_positions?: [number, number][];
}

/**
 * Effective phase-band (conductor bundle) width for one (layer, net) group.
 * This is the full coil-side bundle width — NOT a single-slot width (a slot
 * houses one active leg); the single-leg track width is reported separately
 * as `slot_width_m`.
 */
export interface PhaseBandWidthDto {
  layer: number;
  net: string;
  trace_count: number;
  trace_width_m: number;
  trace_spacing_m: number;
  /** Angle from the travel axis, in radians. */
  angle_rad: number;
  /** Bottom-up effective bundle width along the travel axis. */
  band_width_m: number;
  /**
   * Width of the track space housing ONE active leg of this band
   * (`w_t / sin(theta)` for a single-trace leg) — glossary "Slot Width".
   * Distinct from the bundle width `band_width_m`. Null when the pattern
   * does not report per-slot geometry.
   */
  slot_width_m: number | null;
  /** Top-down maximum allowed width, when pole pitch is known. */
  max_band_width_m: number | null;
  /** max_band_width_m - band_width_m, when pole pitch is known. */
  margin_m: number | null;
}

/** Pole-pitch and phase-band handoff returned with generated geometry. */
export interface RoutingDimensionsDto {
  active_area_length_m: number;
  total_routing_length_m: number;
  board_width_m: number;
  phases: number;
  /** Full mover magnet-array span, when supplied by the config. */
  magnet_array_span_m: number | null;
  /** Centre-to-centre distance between adjacent north/south poles. */
  pole_pitch_m: number | null;
  period_pitch_m: number | null;
  period_count: number | null;
  /** Ideal phase-band pitch: pole_pitch_m / phases (spacing_ratio = 1.0). */
  phase_band_pitch_m: number | null;
  phase_clearance_m: number;
  max_phase_band_width_m: number | null;
  /**
   * Total active leg slots declared by the pattern's leg grid. Null when the
   * pattern declares no leg grid (per-slot metrics are pattern-dependent).
   */
  slot_count: number | null;
  /**
   * True slot pitch tau_s = L_stator / N_slots from the declared leg grid.
   * Distinct from `phase_band_pitch_m` — the two coincide only for uniform
   * 1-slot-per-pole-per-phase windings. Null without a declared leg grid.
   */
  slot_pitch_m: number | null;
  /**
   * Effective leg pitch of braided/slotless patterns:
   * pole_pitch_m / (phases x strands). Braided patterns have no physical
   * slots — this is the equivalent leg-pitch model of their interleaved
   * trace layout. Null without a declared leg grid.
   */
  interleave_step_m: number | null;
  phase_band_widths: PhaseBandWidthDto[];
  /** Pattern-owned pole-pitch boundaries, in metres, used by preview zones. */
  pole_regions: PoleRegionDto[];
}

export interface PoleRegionDto {
  phase: string;
  pole_index: number;
  /** Start boundary in metres, `[x, y]`. */
  start: [number, number];
  /** End boundary in metres, `[x, y]`. */
  end: [number, number];
}

export interface CoilPathDto {
  phases: PhaseCoilDto[];
  layer_count: number;
  /** Additive design-dimension sidecar for magnet-pattern calculations. */
  routing_dimensions?: RoutingDimensionsDto;
}

/**
 * Stable rest positions of the mover magnet array (travel_envelope).
 *
 * With the baseline excitation (IA = +I, IB = 0, IC = −I) the array centre
 * rests at discrete stable equilibria: every stable rest position of the
 * ARRAY CENTRE satisfies `rest_phase_m ≡ x (mod electrical_period_m)`.
 * All fields are metres in the active-area frame.
 */
export interface TravelEnvelopeDto {
  /** Smallest travel limit of the array centre (m): leading array edge
   *  flush with the copper start (kata 5c7r). */
  min_position_m: number;
  /** Largest travel limit of the array centre (m): trailing array edge
   *  flush with the copper end (kata 5c7r). */
  max_position_m: number;
  /** Rest phase φ: every stable rest centre ≡ φ (mod electrical_period_m). */
  rest_phase_m: number;
  /** Electrical period P_e = 2 × pole pitch τp (one full 360° electrical
   *  cycle, m). */
  electrical_period_m: number;
}
