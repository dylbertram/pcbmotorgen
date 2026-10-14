/**
 * Project persistence (kata 0cgm) — IPC contract types for save/load.
 *
 * Mirrors the Rust DTOs in `src-tauri/src/ipc/project.rs` exactly (field
 * names, order, units, snake_case). These are TRANSFER types only: all
 * serialization, versioning/migration, file I/O, and validation live in
 * the Rust backend behind the `save_document` / `load_project` commands.
 * The frontend gathers the user-facing state into a `ProjectState` (the
 * same way it builds `LinearMotorConfig` for physics calls) and renders
 * the results. ProjectState is a transfer adapter, not a disk format. Rust's
 * documents module writes only the fields owned by the document's type.
 */

import type { CommutationMode } from "./enums";
import type { CadGeometry } from "./dxf";
import type { SensorConfig } from "./sensor";
import type { DriveSettings } from "./drive";

export type DocumentKind = "motor" | "sensor";

export interface WorkspaceLoad {
  path: string;
  files: string[];
  active_file: string | null;
}

/** Every user-facing design input, in UI units (mm + SI engineering
 *  units) — mirrors the fields of the frontend `ConfigStore` one-for-one
 *  and the Rust `ProjectConfigStateIpc`. */
export interface ProjectConfigState {
  topology: string;

  // --- Active area (mm) ---
  desired_travel_mm: number;
  active_area_width_mm: number;

  // --- Multi-strand ---
  strands_per_phase: number;

  // --- Magnet array (mm) ---
  magnet_count: number;
  magnet_width_mm: number;
  magnet_cross_width_mm: number;
  magnet_height_mm: number;
  magnet_grade: string;
  magnet_remanence_t: number;
  air_gap_mm: number;

  // --- Phase-band constraint (mm) ---
  electrical_pitch_mm: number;

  // --- Coil / routing (generation settings) ---
  routing_pattern: string;
  routing_params: Record<string, number>;
  phases: number;
  num_layers: number;

  // --- Drive / electrical ---
  max_current_a: number;
  supply_voltage_v: number;

  // --- Force targets / mechanical ---
  target_force_n: number;
  peak_force_n: number;
  friction_n: number;
  carriage_mass_kg: number;
  max_accel_m_s2: number;
  capacitor_bank_uf: number;

  // --- Solver ---
  commutation: CommutationMode;
  n_positions: number;
  meshing: number;

  // --- PCB manufacturing defaults (mm) ---
  min_trace_mm: number;
  min_space_mm: number;
  min_via_drill_mm: number;
  min_via_annular_ring_mm: number;
  pcb_thickness_mm: number;
  max_layers: number;
  drive_frequency_hz: number;
  max_temperature_rise_c: number;

  // --- Driver suitability (Simulation tab) ---
  /** Missing in files saved before the driver check existed. */
  drive?: DriveSettings;
}

/** The saved working state: design inputs + mover position. */
export interface ProjectState {
  config: ProjectConfigState;
  /** Mover-centre position (mm, absolute track coordinates). */
  mover_position_mm: number;
  /** Optional authoritative imported CAD geometry; absent in older projects. */
  cad_geometry?: CadGeometry | null;
  /** Dedicated induction-sensor workflow settings; missing in older files. */
  sensor_config?: SensorConfig;
  /** Imported sensor geometry, separate from motor CAD geometry. */
  sensor_cad_geometry?: CadGeometry | null;
}

/** Design-level validation findings reported by the backend on load.
 *  Informational — they do not block the restore. */
export interface ProjectValidation {
  errors: string[];
  warnings: string[];
}

/** Result of the `load_project` command. */
export interface LoadProjectResult {
  project: ProjectState;
  /** Format version stamped on the file. */
  source_format_version: number;
  /** Version after migration (= current on success). */
  format_version: number;
  validation: ProjectValidation;
  active_version_id: number;
  versions: ProjectVersionInfo[];
}

/** Result of the `save_project` command. */
export interface SaveProjectResult {
  path: string;
  format_version: number;
  saved_at_unix_ms: number;
  active_version_id: number;
  versions: ProjectVersionInfo[];
}

export interface ProjectVersionInfo {
  id: number;
  description: string;
  created_at_unix_ms: number;
  last_edited_at_unix_ms: number;
}
