/**
 * Per-coil persistence controller. WorkspaceStore creates one instance per
 * document and owns file tabs, workspace replacement and workspace manifests.
 *
 * Architecture boundary: this class contains NO persistence logic. It
 * (a) gathers the user-facing store fields into the `ProjectState` DTO
 * (the same data-mapping job `ConfigStore.toIpc()` does for physics) and
 * (b) applies a loaded DTO back onto the stores. Serialization, artifact
 * versioning/migration, file I/O, and load validation all happen in Rust
 * behind the `save_document` / `load_project` commands (see
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
  ProjectVersionInfo,
  DocumentKind,
} from "../types";
import { DEFAULT_DRIVE_SETTINGS, DEFAULT_SENSOR_CONFIG } from "../types";
import { readPreferences } from "../preferences";
import {
  confirmDiscardChanges,
  loadProject,
  pickProjectOpenPath,
  pickProjectSavePath,
  saveProject,
  relocateProject,
  updateProjectVersion,
  documentExtension,
} from "../ipc";
import type { ConfigStore } from "./config.svelte";
import type { MotionStore } from "./motion.svelte";
import type { RecentFilesStore } from "./recentFiles.svelte";
import type { SensorStore } from "./sensor.svelte";

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
  checkSavePath?: (path: string) => void | Promise<void>;
  private readonly initialState: ProjectState;
  /** Absolute path of the motor or sensor file backing this document. */
  currentPath = $state<string | null>(null);
  /** True while a save/open round-trip is in flight. */
  busy = $state(false);
  /** Last failed-operation message (cleared by the next action/dismiss). */
  error = $state<string | null>(null);
  /** Temporary operation notice (cleared by timeout, next action, or dismiss). */
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
  versions = $state.raw<ProjectVersionInfo[]>([]);
  activeVersionId = $state<number | null>(null);
  activeVersion = $derived(this.versions.find((v) => v.id === this.activeVersionId) ?? null);

  constructor(
    private config: ConfigStore,
    private motion: MotionStore,
    /**
     * Open Recent tracker (kata eap8, optional for tests/minimal hosts).
     * Successfully loaded artifacts are recorded here — recents failures
     * must never affect the open flow.
     */
    private recents?: RecentFilesStore | null,
    private sensor?: SensorStore,
    readonly kind: DocumentKind = "motor",
  ) {
    this.initialState = JSON.parse(JSON.stringify(this.snapshotIpc()));
  }

  // --- Derived state -----------------------------------------------------

  /**
   * Canonical serialization of the persisted fields. Any change to a saved
   * input (including routing params and the mover position) re-derives it.
   * `routing_params_version` is deliberately NOT included: it is a
   * reactivity bump counter, not user state.
   */
  snapshotJson = $derived.by(() => {
    const state = this.snapshotIpc();
    return JSON.stringify(this.kind === "motor"
      ? { config: state.config, mover_position_mm: state.mover_position_mm, cad_geometry: state.cad_geometry }
      : { sensor_config: state.sensor_config, sensor_cad_geometry: state.sensor_cad_geometry });
  });

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

  defaultFileName = $derived.by(() => `untitled.${documentExtension(this.kind)}`);

  directory = $derived.by(() => {
    if (!this.currentPath) return null;
    const index = Math.max(this.currentPath.lastIndexOf("/"), this.currentPath.lastIndexOf("\\"));
    return index < 0 ? null : this.currentPath.slice(0, index + 1);
  });

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
        routing_orientation: { ...this.config.routing_orientation },
        phases: this.config.phases,
        num_layers: this.config.num_layers,
        max_current_a: this.config.max_current_a,
        supply_voltage_v: this.config.supply_voltage_v,
        target_force_n: this.config.target_force_n,
        peak_force_n: this.config.peak_force_n,
        friction_n: this.config.friction_n,
        carriage_mass_kg: this.config.carriage_mass_kg,
        carriage_mass_source: this.config.carriage_mass_source,
        max_accel_m_s2: this.config.max_accel_m_s2,
        capacitor_bank_uf: this.config.capacitor_bank_uf,
        commutation: this.config.commutation,
        n_positions: this.config.n_positions,
        meshing: this.config.meshing,
        min_trace_mm: this.config.min_trace_mm,
        trace_width_mm: this.config.trace_width_mm,
        min_space_mm: this.config.min_space_mm,
        min_via_drill_mm: this.config.min_via_drill_mm,
        min_via_annular_ring_mm: this.config.min_via_annular_ring_mm,
        pcb_thickness_mm: this.config.pcb_thickness_mm,
        ...(this.config.pcb_stackup_mm ? { pcb_stackup_mm: $state.snapshot(this.config.pcb_stackup_mm) } : {}),
        max_layers: this.config.max_layers,
        drive_frequency_hz: this.config.drive_frequency_hz,
        max_temperature_rise_c: this.config.max_temperature_rise_c,
        drive: $state.snapshot(this.config.drive),
        power_move: $state.snapshot(this.config.power_move),
        backplane: $state.snapshot(this.config.backplane),
      },
      mover_position_mm: this.motion.positionMm,
      cad_geometry: this.cadGeometry,
      sensor_config: this.sensor?.toIpc() ?? { ...DEFAULT_SENSOR_CONFIG },
      sensor_cad_geometry: this.sensor?.cadGeometry ?? null,
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
    this.config.routing_orientation = { mirror_x: false, mirror_y: false, reverse_layers: false, ...c.routing_orientation };
    this.config.routing_params_version += 1;
    this.config.phases = c.phases;
    this.config.num_layers = c.num_layers;
    this.config.max_current_a = c.max_current_a;
    this.config.supply_voltage_v = c.supply_voltage_v;
    this.config.target_force_n = c.target_force_n;
    this.config.peak_force_n = c.peak_force_n;
    this.config.friction_n = c.friction_n;
    this.config.carriage_mass_kg = c.carriage_mass_kg;
    this.config.carriage_mass_source = c.carriage_mass_source === "magnets" ? "magnets" : "assembly";
    this.config.max_accel_m_s2 = c.max_accel_m_s2;
    this.config.capacitor_bank_uf = c.capacitor_bank_uf;
    this.config.commutation = c.commutation;
    this.config.n_positions = c.n_positions;
    this.config.meshing = c.meshing;
    this.config.min_trace_mm = c.min_trace_mm;
    // Older files have no nominal width: keep their copper width by seeding
    // it from the minimum trace width they were drawn with.
    this.config.trace_width_mm = c.trace_width_mm ?? c.min_trace_mm;
    this.config.min_space_mm = c.min_space_mm;
    this.config.min_via_drill_mm = c.min_via_drill_mm;
    this.config.min_via_annular_ring_mm = c.min_via_annular_ring_mm;
    this.config.pcb_thickness_mm = c.pcb_thickness_mm;
    this.config.pcb_stackup_mm = c.pcb_stackup_mm ? structuredClone(c.pcb_stackup_mm) : null;
    this.config.max_layers = c.max_layers;
    this.config.drive_frequency_hz = c.drive_frequency_hz;
    this.config.max_temperature_rise_c = c.max_temperature_rise_c;
    this.config.drive = c.drive
      ? { ...DEFAULT_DRIVE_SETTINGS, ...c.drive, driver: { ...DEFAULT_DRIVE_SETTINGS.driver, ...c.drive.driver } }
      : structuredClone(DEFAULT_DRIVE_SETTINGS);
    this.config.power_move = c.power_move ? structuredClone(c.power_move) : null;
    // Files saved before the backplane existed have no field: start with none.
    this.config.backplane = c.backplane ? structuredClone(c.backplane) : null;
    this.motion.positionMm = state.mover_position_mm;
    this.cadGeometry = state.cad_geometry ?? null;
    this.sensor?.apply(state.sensor_config);
    if (this.sensor) this.sensor.cadGeometry = state.sensor_cad_geometry ?? null;
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
  async relocate(name: string, directory: string): Promise<boolean> {
    if (this.busy) return false;
    this.busy = true;
    this.clearMessages();
    const source = this.currentPath;
    try {
      const snapshot = this.snapshotIpc();
      const savedSnapshot = this.snapshotJson;
      const extension = documentExtension(this.kind);
      const fileName = name.toLowerCase().endsWith(`.${extension}`) ? name : `${name}.${extension}`;
      const separator = directory.endsWith("/") || directory.endsWith("\\") ? "" : "/";
      if (this.checkSavePath) await this.checkSavePath(`${directory}${separator}${fileName}`);
      const result = await relocateProject(source, directory, fileName, snapshot, this.activeVersionId);
      this.currentPath = result.path;
      if (source === null) {
        this.versions = result.versions ?? [];
        this.activeVersionId = result.active_version_id ?? null;
        this.savedSnapshot = savedSnapshot;
      }
      this.notice = `${source === null ? "Saved" : "Moved"} ${baseName(result.path)}.`;
      if (this.recents) {
        try {
          await this.recents.record(result.path);
          if (source !== null && source !== result.path) await this.recents.remove(source);
        } catch { /* Recents must not turn a successful move into a failure. */ }
      }
      return true;
    } catch (e) {
      this.error = `Could not change project name or location: ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }

  /** Start an untitled design without replacing unsaved work silently. */
  async newProject(): Promise<boolean> {
    if (this.busy) return false;
    this.busy = true;
    try {
      if (this.isDirty && !(await confirmDiscardChanges())) return false;
      this.applyToState(this.initialState);
      Object.assign(this.config, readPreferences().rules);
      await this.config.loadRoutingParams(this.config.routing_pattern);
      this.config.constrainLayersToPattern();
      this.currentPath = null;
      this.versions = [];
      this.activeVersionId = null;
      this.clearMessages();
      this.markClean();
      return true;
    } catch (e) {
      this.error = `New project failed: ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }

  /**
   * Save the working state. With `saveAs` (or no current path) the native
   * save dialog resolves the target first. Resolves `true` on success.
   * Failures surface via `error` and leave both the in-memory state and
   * the previous artifact untouched (the backend writes atomically).
   */
  async save(saveAs = false, newVersion = false, description?: string): Promise<boolean> {
    if (this.busy) return false;
    this.busy = true;
    let path = this.currentPath;
    if (saveAs || path === null) {
      try {
        path = await pickProjectSavePath(
          this.fileName ?? this.defaultFileName,
          this.kind,
        );
      } catch (e) {
        this.error = errorMessage(e);
        this.busy = false;
        return false;
      }
      // User cancelled the dialog — not an error.
      if (path === null) {
        this.busy = false;
        return false;
      }
    }

    this.clearMessages();
    try {
      if (this.checkSavePath) await this.checkSavePath(path);
      const snapshot = this.snapshotIpc();
      const savedSnapshot = this.snapshotJson;
      const result = await saveProject(path, snapshot, {
        sourcePath: this.currentPath, activeVersionId: this.activeVersionId, newVersion, description, kind: this.kind,
      });
      this.currentPath = result.path;
      this.versions = result.versions ?? [];
      this.activeVersionId = result.active_version_id ?? null;
      this.savedSnapshot = savedSnapshot;
      this.notice = `Saved ${baseName(result.path)}${newVersion ? ` as version ${this.activeVersionId ?? 1}` : ""}.`;
      this.recents?.record(result.path).catch(() => undefined);
      return true;
    } catch (e) {
      this.error = `Save failed — ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }

  async openVersion(id: number): Promise<boolean> {
    if (!this.currentPath || this.busy) return false;
    if (id === this.activeVersionId) return true;
    if (this.isDirty && !(await confirmDiscardChanges("open another version"))) return false;
    return await this.loadFromPath(this.currentPath, id);
  }

  async describeVersion(id: number, description: string): Promise<boolean> {
    if (!this.currentPath || this.busy) return false;
    this.busy = true;
    this.clearMessages();
    try {
      const result = await updateProjectVersion(this.currentPath, id, this.activeVersionId, { description });
      this.versions = result.versions;
      this.notice = `Updated description for version ${id}.`;
      return true;
    } catch (e) {
      this.error = `Could not update version: ${errorMessage(e)}`;
      return false;
    } finally {
      this.busy = false;
    }
  }

  /** The dialog confirms deletion, including loss of an active unsaved draft. */
  async deleteVersion(id: number): Promise<boolean> {
    if (!this.currentPath || this.busy || this.versions.length <= 1) return false;
    this.busy = true;
    this.clearMessages();
    try {
      const result = await updateProjectVersion(this.currentPath, id, this.activeVersionId, { deleteVersion: true });
      if (id === this.activeVersionId) {
        this.applyToState(result.project);
        await this.config.loadRoutingParams(result.project.config.routing_pattern);
        this.config.constrainLayersToPattern();
        this.activeVersionId = result.active_version_id;
        this.loadIssues = result.validation.errors.length || result.validation.warnings.length ? result.validation : null;
        this.markClean();
      }
      this.versions = result.versions;
      this.notice = `Deleted version ${id}.`;
      return true;
    } catch (e) {
      this.error = `Could not delete version: ${errorMessage(e)}`;
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
  async loadFromPath(path: string, versionId: number | null = null): Promise<boolean> {
    this.busy = true;
    this.clearMessages();
    try {
      const result: LoadProjectResult = await loadProject(path, versionId);
      // Backend accepted the artifact — only now replace in-memory state.
      this.applyToState(result.project);
      // Refresh the pattern catalog metadata for the restored pattern and
      // reseed any routing-param defaults the artifact did not carry.
      await this.config.loadRoutingParams(
        result.project.config.routing_pattern,
      );
      this.config.constrainLayersToPattern();
      this.currentPath = path;
      this.versions = result.versions ?? [];
      this.activeVersionId = result.active_version_id ?? null;
      this.markClean();
      const issues = result.validation;
      const issueCount = issues.errors.length + issues.warnings.length;
      this.loadIssues = issueCount > 0 ? issues : null;
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
