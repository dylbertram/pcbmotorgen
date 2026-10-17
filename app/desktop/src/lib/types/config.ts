/**
 * Config (IPC wire format — SI units) and the derived-value contract.
 */

import type { BackplaneStack } from "./backplane";
import type { CommutationMode } from "./enums";

/** The full design configuration sent to the Tauri backend on every call. */
export interface LinearMotorConfig {
  active_area_length_m: number;
  board_width_m: number;
  pcb_thickness_m: number;
  /** Number of parallel serpentine paths (strands) per phase on the same
   *  layer, stacked in y. 1 = single-strand. Distinct from a winding: a
   *  winding (coil) is one complete conductive loop. */
  strands_per_phase: number;

  magnet_count: number;
  magnet_width_m: number; // travel-axis dimension
  magnet_cross_width_m: number; // across-stator dimension
  magnet_height_m: number;
  magnet_gap_m: number; // derived: pitch - width (kept for clarity)
  magnet_pitch_m: number; // = magnet_width + magnet_gap (= pole pitch τp for the alternating array)

  magnet_remanence_t: number;
  magnet_grade: string;
  air_gap_m: number;

  /** Routing-pattern id the backend should use to generate the coils,
   *  e.g. `"infinity-braid"`. See `RoutingPatternInfo`. */
  routing_pattern: string;
  /** User-editable parameters for the selected routing pattern (e.g.
   *  `num_strands`). Amplitude / total-length and magnet-aligned period count are derived
   *  from the active area and are NOT user-settable. Empty = defaults. */
  routing_params: Record<string, number>;
  phases: number;
  spacing_ratio: number;

  max_current_a: number;
  supply_voltage_v: number;

  num_layers: number;
  min_trace_m: number;
  trace_width_m: number;
  min_space_m: number;
  min_via_drill_m: number;
  min_via_annular_ring_m: number;
  max_layers: number;
  drive_frequency_hz: number;
  max_temperature_rise_c: number;

  target_force_n: number;
  peak_force_n: number;
  friction_n: number;
  carriage_mass_kg: number;
  max_accel_m_s2: number;
  capacitor_bank_uf: number;

  commutation: CommutationMode;
  n_positions: number;
  meshing: number;

  /** Backplane and housing below the PCB (t707). `null` = none, which
   *  leaves the field model unchanged. */
  backplane: BackplaneStack | null;

  name: string | null;
}

