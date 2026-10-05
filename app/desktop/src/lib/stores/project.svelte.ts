/**
 * Project persistence controller (kata 0cgm) — the frontend HALF of
 * save/load.
 *
 * Architecture boundary: this class contains NO persistence logic. It
 * (a) gathers the user-facing store fields into the `ProjectState` DTO
 * (the same data-mapping job `ConfigStore.toIpc()` does for physics) and
 * (b) applies a loaded DTO back onto the stores. Serialization, artifact
 * versioning/migration, file I/O, and load validation all happen in Rust
 * behind the `save_project` / `load_project` commands (see
 * `src-tauri/src/ipc/project.rs`).
 *
 * Dirty-state tracking compares a canonical JSON snapshot of the persisted
 * fields against the baseline captured at the last successful save/load —
 * no timers, no listeners on individual inputs.
 */

import type {
  CadGeometry,
  LoadProjectResult,
  ProjectState,
  ProjectValidation,
} from "../types";
import {
  DEFAULT_PROJECT_FILE_NAME,
  confirmDiscardChanges,
  loadProject,
  pickProjectOpenPath,
  pickProjectSavePath,
  saveProject,
} from "../ipc";
import type { ConfigStore } from "./config.svelte";
import type { MotionStore } from "./motion.svelte";
import type { RecentFilesStore } from "./recentFiles.svelte";

/** Normalise any thrown value into a display string. */
function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** File name portion of a path (handles both separators). */
function baseName(path: string): string {
  const idx = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return idx === -1 ? path : path.slice(idx + 1);
}

export class ProjectStore {
  /** Absolute path of the project file backing the current state. */
  currentPath = $state<string | null>(null);
  /** True while a save/open round-trip is in flight. */
  busy = $state(false);
  /** Last failed-operation message (cleared by the next action/dismiss). */
  error = $state<string | null>(null);
  /** Last successful-operation notice (cleared by the next action/dismiss). */
  notice = $state<string | null>(null);
  /** Design-level findings the backend reported for the last load. */
  loadIssues = $state<ProjectValidation | null>(null);
  /**
   * Canonical snapshot at the last successful save/load. `null` until the
   * first baseline — a fresh untitled design is not "dirty".
   */
  savedSnapshot = $state<string | null>(null);
  /** Imported CAD geometry is authoritative until the user explicitly replaces it. */
  cadGeometry = $state.raw<CadGeometry | null>(null);

  constructor(
    private config: ConfigStore,
    private motion: MotionStore,
    /**
     * Open Recent tracker (kata eap8, optional for tests/minimal hosts).
     * Successfully loaded artifacts are recorded here — recents failures
     * must never affect the open flow.
     */
    private recents?: RecentFilesStore | null,
  ) {}

  // --- Derived state -----------------------------------------------------

  /**
   * Canonical serialization of the persisted fields. Any change to a saved
   * input (including routing params and the mover position) re-derives it.
   * `routing_params_version` is deliberately NOT included: it is a
   * reactivity bump counter, not user state.
   */
  snapshotJson = $derived.by(() => JSON.stringify(this.snapshotIpc()));

  /** True when the working state differs from the last saved artifact. */
  isDirty = $derived(
    this.savedSnapshot !== null && this.snapshotJson !== this.savedSnapshot,
  );

  /** Short file name for the header (null = untitled). */
  fileName = $derived(
    this.currentPath === null ? null : baseName(this.currentPath),
  );

  /** Header label: file name, or the untitled placeholder. */
  label = $derived(this.fileName ?? "untitled design");

  // --- DTO mapping (interface only — no persistence logic) ---------------

  /** Gather the persisted working state into the IPC DTO. */
  snapshotIpc(): ProjectState {
    const params = Object.entries(this.config.routing_params)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, value]) => ({ key, value }));

    return {
      config: {
        topology: this.config.topology,
        desired_travel_mm: this.config.desired_travel_mm,
        active_area_width_mm: this.config.active_area_width_mm,
        strands_per_phase: this.config.strands_per_phase,
        magnet_count: this.config.magnet_count,
        magnet_width_mm: this.config.magnet_width_mm,
        magnet_cross_width_mm: this.config.magnet_cross_width_mm,
        magnet_height_mm: this.config.magnet_height_mm,
        magnet_grade: this.config.magnet_grade,
        magnet_remanence_t: this.config.magnet_remanence_t,
        air_gap_mm: this.config.air_gap_mm,
        electrical_pitch_mm: this.config.electrical_pitch_mm,
        routing_pattern: this.config.routing_pattern,
        routing_params: Object.fromEntries(params.map((p) => [p.key, p.value])),
        phases: this.config.phases,
        num_layers: this.config.num_layers,
        max_current_a: this.config.max_current_a,
        supply_voltage_v: this.config.supply_voltage_v,
        target_force_n: this.config.target_force_n,
        peak_force_n: this.config.peak_force_n,
        friction_n: this.config.friction_n,
        carriage_mass_kg: this.config.carriage_mass_kg,
        max_accel_m_s2: this.config.max_accel_m_s2,
        capacitor_bank_uf: this.config.capacitor_bank_uf,
        commutation: this.config.commutation,
        n_positions: this.config.n_positions,
        meshing: this.config.meshing,
        min_trace_mm: this.config.min_trace_mm,
        min_space_mm: this.config.min_space_mm,
        min_via_drill_mm: this.config.min_via_drill_mm,
        min_via_annular_ring_mm: this.config.min_via_annular_ring_mm,
        pcb_thickness_mm: this.config.pcb_thickness_mm,
        max_layers: this.config.max_layers,
        drive_frequency_hz: this.config.drive_frequency_hz,
        max_temperature_rise_c: this.config.max_temperature_rise_c,
      },
      mover_position_mm: this.motion.positionMm,
      cad_geometry: this.cadGeometry,
    };
  }

  /**
   * Apply a loaded state onto the stores. Pure field mapping — the caller
   * (open) handles pattern-def reseeding, layer re-constraining, and the
   * clean-baseline update.
   */
  applyToState(state: ProjectState): void {
    const c = state.config;
    // Clamp to the store's union: only the two known modes are accepted,
    // anything unexpected (hand-edited file) falls back to linear — the
    // only mode the backend implements (PRODUCT_GOALS §7.A).
    this.config.topology = c.topology === "radial" ? "radial" : "linear";
    this.config.desired_travel_mm = c.desired_travel_mm;
    this.config.active_area_width_mm = c.active_area_width_mm;
    this.config.strands_per_phase = c.strands_per_phase;
    this.config.magnet_count = c.magnet_count;
    this.config.magnet_width_mm = c.magnet_width_mm;
    this.config.magnet_cross_width_mm = c.magnet_cross_width_mm;
    this.config.magnet_height_mm = c.magnet_height_mm;
    this.config.magnet_grade = c.magnet_grade;
    this.config.magnet_remanence_t = c.magnet_remanence_t;
    this.config.air_gap_mm = c.air_gap_mm;
    this.config.electrical_pitch_mm = c.electrical_pitch_mm;
    this.config.routing_pattern = c.routing_pattern;
    this.config.routing_params = { ...c.routing_params };
    this.config.routing_params_version += 1;
    this.config.phases = c.phases;
    this.config.num_layers = c.num_layers;
    this.config.max_current_a = c.max_current_a;
    this.config.supply_voltage_v = c.supply_voltage_v;
    this.config.target_force_n = c.target_force_n;
    this.config.peak_force_n = c.peak_force_n;
    this.config.friction_n = c.friction_n;
    this.config.carriage_mass_kg = c.carriage_mass_kg;
    this.config.max_accel_m_s2 = c.max_accel_m_s2;
    this.config.capacitor_bank_uf = c.capacitor_bank_uf;
    this.config.commutation = c.commutation;
    this.config.n_positions = c.n_positions;
    this.config.meshing = c.meshing;
    this.config.min_trace_mm = c.min_trace_mm;
    this.config.min_space_mm = c.min_space_mm;
    this.config.min_via_drill_mm = c.min_via_drill_mm;
    this.config.min_via_annular_ring_mm = c.min_via_annular_ring_mm;
    this.config.pcb_thickness_mm = c.pcb_thickness_mm;
    this.config.max_layers = c.max_layers;
    this.config.drive_frequency_hz = c.drive_frequency_hz;
    this.config.max_temperature_rise_c = c.max_temperature_rise_c;
    this.motion.positionMm = state.mover_position_mm;
    this.cadGeometry = state.cad_geometry ?? null;
  }

  setCadGeometry(geometry: CadGeometry | null): void {
    this.cadGeometry = geometry;
  }

  /** Re-baseline the dirty tracker at the current state. */
  markClean(): void {
    this.savedSnapshot = this.snapshotJson;
  }

  /** Clear the error/notice/issue banners. */
  clearMessages(): void {
    this.error = null;
    this.notice = null;
    this.loadIssues = null;
  }

  // --- Operations ---------------------------------------------------------

  /**
   * Save the working state. With `saveAs` (or no current path) the native
   * save dialog resolves the target first. Resolves `true` on success.
   * Failures surface via `error` and leave both the in-memory state and
   * the previous artifact untouched (the backend writes atomically).
   */
  async save(saveAs = false): Promise<boolean> {
    if (this.busy) return false;
    let path = this.currentPath;
    if (saveAs || path === null) {
      try {
        path = await pickProjectSavePath(
          this.fileName ?? DEFAULT_PROJECT_FILE_NAME,
        );
      } catch (e) {
        this.error = errorMessage(e);
        return false;
      }
      // User cancelled the dialog — not an error.
      if (path === null) return false;
    }

    this.busy = true;
    this.clearMessages();
    try {
      const result = await saveProject(path, this.snapshotIpc());
      this.currentPath = result.path;
      this.markClean();
      this.notice = `Saved ${baseName(result.path)}.`;
      return true;
    } catch (e) {
      this.error = `Save failed — ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }

  /**
   * Open a `.pmproj` artifact chosen via the native dialog and restore the
   * full working state. Asks before discarding unsaved changes. On any
   * backend rejection the in-progress state is left untouched (restore
   * happens only after the command returns successfully). Resolves `true`
   * on success.
   */
  async open(): Promise<boolean> {
    if (this.busy) return false;
    if (this.isDirty) {
      const discard = await confirmDiscardChanges();
      if (!discard) {
        this.notice = "Open cancelled — unsaved changes kept.";
        return false;
      }
    }

    let path: string | null;
    try {
      path = await pickProjectOpenPath();
    } catch (e) {
      this.error = errorMessage(e);
      return false;
    }
    if (path === null) return false;

    return await this.loadFromPath(path);
  }

  /**
   * Open a specific `.pmproj` path through the same flow as File > Open —
   * the dispatch target of the native Open Recent menu entries (kata eap8).
   * Identical guards to `open()` (busy serialization + unsaved-changes
   * confirm); a vanished file is rejected by the backend and surfaces the
   * same "Open failed — could not open …" error UX.
   */
  async openPath(path: string): Promise<boolean> {
    if (this.busy) return false;
    if (this.isDirty) {
      const discard = await confirmDiscardChanges();
      if (!discard) {
        this.notice = "Open cancelled — unsaved changes kept.";
        return false;
      }
    }
    return await this.loadFromPath(path);
  }

  /**
   * The shared load half of `open` / `openPath`: busy-guarded backend load,
   * state restore, and (on success) the recents record (kata eap8).
   * Recents failures are swallowed — they only degrade the menu.
   */
  private async loadFromPath(path: string): Promise<boolean> {
    this.busy = true;
    this.clearMessages();
    try {
      const result: LoadProjectResult = await loadProject(path);
      // Backend accepted the artifact — only now replace in-memory state.
      this.applyToState(result.project);
      // Refresh the pattern catalog metadata for the restored pattern and
      // reseed any routing-param defaults the artifact did not carry.
      await this.config.loadRoutingParams(
        result.project.config.routing_pattern,
      );
      this.config.constrainLayersToPattern();
      this.currentPath = path;
      this.markClean();
      const issues = result.validation;
      const issueCount = issues.errors.length + issues.warnings.length;
      this.loadIssues = issueCount > 0 ? issues : null;
      this.notice =
        `Opened ${baseName(path)}` +
        (issueCount > 0
          ? ` — ${issues.errors.length} error(s), ${issues.warnings.length} warning(s) in the restored design.`
          : ".");
      // Record the recents entry in the background (kata eap8): the store's
      // port never rejects by contract; the catch is belt-and-braces so a
      // persistence hiccup cannot break an already-successful open.
      this.recents?.record(path).catch(() => undefined);
      return true;
    } catch (e) {
      this.error = `Open failed — ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }
}
