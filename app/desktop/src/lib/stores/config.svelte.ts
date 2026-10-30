/**
 * pcbmotorgen — central configuration store (Svelte 5 runes class).
 *
 * Keeps user-facing values in mm (the natural unit for PCB design) and
 * exposes a `toIpc()` builder that converts to the SI LinearMotorConfig
 * expected by the Tauri backend. Derived geometry (pole pitch, mover span,
 * travel) is computed with `$derived` so every consumer updates live.
 */

import type {
  LinearMotorConfig,
  CommutationMode,
  RoutingPatternInfo,
  RoutingParamDef,
  MagnetGrade,
  DriveSettings,
  BackplaneStack,
} from "../types";
import { getRemanence, MAGNET_GRADES, extractBaseGrade, DEFAULT_DRIVE_SETTINGS } from "../types";
import {
  layerOptions as layerOptionsFor,
  nearestLayer,
  patternLayerRange,
} from "../layerConstraints";
import { mm, listRoutingPatterns, routingPatternParameters, loadInstalledPlugins, fetchMagnetGrades } from "../ipc";
import { readPreferences } from "../preferences";
import { MAX_PCB_LAYERS } from "../types/simulationLimits";
import type { RoutedMoveRequest } from "../types/movePower";
import { magnetMass } from "../carriageMass";

export class ConfigStore {
  constructor() {
    Object.assign(this, readPreferences().rules);
  }

  // --- Topology ----------------------------------------------------------
  topology = $state<"linear" | "radial">("linear");

  // --- Active area (mm) --------------------------------------------------
  // The travel-axis length of the copper active area is DERIVED from the
  // desired center-to-center travel (set in the overview constraints) plus
  // the mover's coil span. Only the cross-axis width is a free general
  // input.
  desired_travel_mm = $state(75);
  active_area_width_mm = $state(20);

  // --- Multi-strand (default matches the Rust core) ---
  strands_per_phase = $state(2);

  // --- Magnet array (mm) -------------------------------------------------
  /** Number of magnetic poles on the mover (`N_poles`). Even counts are
   *  strongly recommended so the mover has no net unbalanced normal force. */
  magnet_count = $state(12);
  /** X length of one magnet along the travel axis (`W_m`, mm). This is the
   *  SOURCE OF TRUTH for the travel-axis magnet geometry; the pole fill
   *  factor `k_fill = W_m / τ_p` is DERIVED from it (see the derived
   *  section below). 4.5 mm at the 6 mm pole-pitch default gives
   *  k_fill = 0.75 (135° electrical), the classic optimum; the value may
   *  reach the full pole pitch (k = 1.0, end-to-end magnets, no gap). */
  magnet_width_mm = $state(4.5);
  /** Y width across the stator (mm) — independent of the travel-axis X length. */
  magnet_cross_width_mm = $state(10);
  /** Z thickness default = T_m = 0.5 × pole pitch (3.0 mm at the 12 mm
   *  electrical-pitch default). User-adjustable afterwards. */
  magnet_height_mm = $state(3.0);
  magnet_grade = $state("N44");
  magnet_remanence_t = $state(1.34);
  air_gap_mm = $state(0.5);

  // --- Phase-band constraint (mm) ---------------------------------------
  /** Electrical pitch P_e: length of one full electrical cycle (360°) =
   *  2 × pole pitch. A full cycle contains two alternating poles, so
   *  pole_pitch_mm = electrical_pitch_mm / 2. NOTE: this is NOT a slot
   *  dimension — a slot houses one active leg. The per-slot conductor-band
   *  widths are reported in the Coil Preview diagnostics. */
  electrical_pitch_mm = $state(12.0);

  // --- Coil --------------------------------------------------------------
  /** Routing-pattern id sent to the backend (one of `routing_patterns`). */
  routing_pattern = $state<string>("infinity-braid");
  /** Routing patterns offered by the backend (`list_routing_patterns`). */
  routing_patterns = $state<RoutingPatternInfo[]>([]);
  /** User-editable routing-pattern parameter values, keyed by `def.key`
   *  (e.g. `num_strands`, `n_periods`). Empty = pattern defaults. Sent to
   *  the backend as `routing_params`. */
  routing_params = $state<Record<string, number>>({ connection: 2 });
  /** Declared user-editable parameter definitions for the currently
   *  selected routing pattern (`routing_pattern_parameters`). */
  routing_param_defs = $state<RoutingParamDef[]>([]);
  /** Monotonic bump counter for `routing_params` edits. `$state` proxies
   *  only track the exact property read, so mutating `routing_params[key]`
   *  in place would NOT re-trigger dependent scheduling `$effect`s. Bumping
   *  this counter after every param write gives the debounced preview and
   *  simulation effects a stable signal to react to. */
  routing_params_version = $state(0);
  phases = $state(3);
  num_layers = $state(4);

  // --- Drive / electrical ------------------------------------------------
  max_current_a = $state(1.0);
  supply_voltage_v = $state(5.0);

  // --- Force targets / mechanical ---------------------------------------
  target_force_n = $state(0.5);
  peak_force_n = $state(1.0);
  friction_n = $state(0.05);
  carriage_mass_source = $state<"magnets" | "assembly">("magnets");
  private assembly_mass_kg = $state(0.015);
  magnet_mass = $derived(magnetMass(
    [this.magnet_width_mm, this.magnet_cross_width_mm, this.magnet_height_mm], this.magnet_grade,
  ));
  magnet_total_mass_kg = $derived(this.magnet_mass.massG * this.magnet_count / 1000);
  get carriage_mass_kg(): number {
    return this.carriage_mass_source === "magnets" ? this.magnet_total_mass_kg : this.assembly_mass_kg;
  }
  set carriage_mass_kg(value: number) {
    this.assembly_mass_kg = value;
    this.carriage_mass_source = "assembly";
  }
  max_accel_m_s2 = $state(2.0);
  capacitor_bank_uf = $state(1000);

  // --- Solver -----------------------------------------------------------
  commutation = $state<CommutationMode>("max_thrust");
  n_positions = $state(50);
  meshing = $state(20);

  // --- PCB manufacturing defaults (mm) ---------------------------------
  min_trace_mm = $state(0.127);
  trace_width_mm = $state(0.127);
  min_space_mm = $state(0.127);
  min_via_drill_mm = $state(0.2);
  min_via_annular_ring_mm = $state(0.1);
  pcb_thickness_mm = $state(1.6);
  max_layers = $state<number>(MAX_PCB_LAYERS);
  drive_frequency_hz = $state(500);
  max_temperature_rise_c = $state(20);

  // --- Driver suitability (Simulation tab) ------------------------------
  /** Driver limits and operating assumptions for `analyze_drive`. Replace
   *  the whole object to edit it, so dependents see one change. */
  drive = $state<DriveSettings>(structuredClone(DEFAULT_DRIVE_SETTINGS));
  /** No move exists until explicitly specified by the user. */
  power_move = $state<RoutedMoveRequest | null>(null);

  // --- Backplane and housing (t707) ------------------------------------
  /** Layers below the PCB and an optional housing. `null` = none, which
   *  leaves the field model unchanged. */
  backplane = $state<BackplaneStack | null>(null);

  // ---------------------------------------------------------------------
  // Derived geometry (mm, for the UI)
  // ---------------------------------------------------------------------

  pole_pitch_mm = $derived(this.electrical_pitch_mm / 2);
  /** Upper limit on the magnet X length: a fully-filled pole pitch
   *  (k_fill = 1.0) leaves no inter-pole gap. */
  max_magnet_width_mm = $derived(Math.max(0, this.pole_pitch_mm));
  /** Magnet pole fill factor, now DERIVED from the width input:
   *  k_fill = W_m / τ_p. Kept exported under its historical name because
   *  validation.ts and MagnetsPanel.svelte consume it. */
  magnet_fill_k = $derived(
    this.pole_pitch_mm > 0 ? this.magnet_width_mm / this.pole_pitch_mm : 0,
  );
  /** Inter-pole gap is automatic: W_gap = τ_p − W_m (zero at k_fill = 1.0). */
  magnet_gap_mm = $derived(
    Math.max(0, this.pole_pitch_mm - this.magnet_width_mm),
  );
  /** Physical outer-edge span, excluding the extra trailing pitch-cell gap. */
  mover_span_mm = $derived((this.magnet_count - 1) * this.pole_pitch_mm + this.magnet_width_mm);
  /** Active-area length along the travel axis: mover span + desired travel. */
  active_area_length_mm = $derived(this.mover_span_mm + this.desired_travel_mm);
  /**
   * Total X extent of the routed PCB traces: the first-to-last segment-point
   * span returned by the routing backend. The braid routes across the active
   * area (its end turns are part of the pattern), so this is the dimension
   * the coil preview draws — keep every preview sized by THIS.
   */
  trace_total_length_mm = $derived(this.active_area_length_mm);
  travel_mm = $derived(this.active_area_length_mm - this.mover_span_mm);
  /** Vernier slot-pitch ratio. No longer user-adjustable in the UI — pinned
   *  to the standard 1:1 and passed to the backend untouched. */
  spacing_ratio = $derived(1.0);

  /** True when the active area is too short to cover the mover magnet-array
   *  span. */
  is_active_area_invalid = $derived(
    this.active_area_length_mm <= this.mover_span_mm,
  );

  // --- Pattern-constrained layer selection (mirrored IPC metadata) --------
  // The routing crate declares a supported layer range per pattern
  // (`min_layers` / `max_layers` / `layers_multiple_of`, additive trait
  // defaults). These deriveds only CONSTRAIN THE UI — the authoritative
  // validation stays in Rust (config validation + generate-time
  // `validate_layer_range`).

  /** Catalog entry of the active pattern (null until the backend catalog
   *  loads or the id is unknown). */
  activePatternInfo = $derived(
    this.routing_patterns.find((p) => p.id === this.routing_pattern) ?? null,
  );

  /** Layer-range metadata declared by the active pattern (nulls =
   *  unconstrained). */
  patternLayerRange = $derived(patternLayerRange(this.activePatternInfo));

  /** Copper-layer counts the layer selector may offer: even, >= 2, within
   *  `max_layers`, intersected with the active pattern's declared range. */
  layerOptions = $derived(layerOptionsFor(this.max_layers, this.patternLayerRange));

  /**
   * Constrain `num_layers` into the currently offered options (nearest valid
   * value). Called when the pattern catalog loads and whenever the pattern
   * changes, so a pattern switch can never leave an unsupported layer count
   * selected. No-op when the current value is already valid or the option
   * set is empty (the Rust validation reports that case).
   */
  constrainLayersToPattern(): void {
    // Never silently shorten an out-of-envelope imported/saved stack.
    // The backend and design validation report the unsupported geometry.
    if (this.num_layers > MAX_PCB_LAYERS) return;
    const options = this.layerOptions;
    if (options.length === 0 || options.includes(this.num_layers)) return;
    this.num_layers = nearestLayer(this.num_layers, options);
  }

  // --- Magnet-grade reference (loaded from backend at startup) -----------
  /**
   * The runtime-loaded magnet-grade table from the backend
   * (`get_magnet_grades`). The backend reads the Rust simulation crate's
   * table — the single source of truth. Empty until loaded; the static TS
   * table in `types/magnets.ts` is the offline/mock fallback.
   */
  magnet_grades = $state<MagnetGrade[]>([]);

  /** Magnet-grade names offered to the user (runtime table, else TS fallback). */
  magnetGradeNames = $derived(
    this.magnet_grades.length > 0
      ? this.magnet_grades.map((g) => g.name)
      : Object.keys(MAGNET_GRADES),
  );

  /** Look up a grade by name from the runtime table (falling back to TS). */
  getMagnetGrade(name: string): MagnetGrade | null {
    const base = extractBaseGrade(name);
    if (this.magnet_grades.length > 0) {
      return this.magnet_grades.find((g) => g.name === base) ?? null;
    }
    return MAGNET_GRADES[base] ?? null;
  }

  /** Look up a grade by name from the runtime table (falling back to TS). */
  getMagnetGradeRemanence(name: string): number {
    const grade = this.getMagnetGrade(name);
    return grade ? grade.br_typ_t : getRemanence(name);
  }

  /**
   * Load the magnet-grade table from the backend. Called during app init.
   * Failures are swallowed so a missing backend keeps the TS fallback table.
   */
  async loadMagnetGrades(): Promise<void> {
    try {
      this.magnet_grades = await fetchMagnetGrades();
    } catch {
      // backend unavailable — keep the static TS fallback table
    }
  }

  /** Sync remanence from the selected grade unless "Custom". */
  syncGrade(): void {
    if (this.magnet_grade === "Custom") return;
    try {
      this.magnet_remanence_t = this.getMagnetGradeRemanence(this.magnet_grade);
    } catch {
      // unknown grade — leave remanence untouched
    }
  }

  /**
   * Load the routing patterns the backend can generate and populate
   * `routing_patterns`. Call during app init; failures are swallowed so a
   * missing backend leaves an empty list (the selector shows "Loading…"
   * until the list is populated).
   */
  async loadRoutingPatterns(): Promise<void> {
    try {
      this.routing_patterns = await listRoutingPatterns();
    } catch {
      // backend unavailable or errored — keep the current (possibly empty) list
    }
    // The catalog carries the pattern-declared layer ranges: re-constrain
    // the selected layer count now that the metadata is available.
    this.constrainLayersToPattern();
    // Startup re-registration: reload patterns first, then re-register any
    // persisted plugins so the freshly-loaded catalog includes them. Errors
    // are per-plugin strings (empty = all ok); surface as a console warn so a
    // broken persisted plugin doesn't break startup but is still observable.
    try {
      const loadErrors = await loadInstalledPlugins();
      if (loadErrors.length > 0) {
        console.warn(
          `[plugins] ${loadErrors.length} installed plugin(s) failed to load:`,
          loadErrors,
        );
      }
    } catch (e) {
      console.warn("[plugins] loadInstalledPlugins failed:", e);
    }
  }

  /**
   * Load the declared user-editable parameter definitions for a routing
   * pattern and reseed `routing_params` so every declared parameter has a
   * value in the UI.
   *
   * For each declared `def` we only write a value when the user hasn't
   * already set one for *this* pattern (tracked by key). This keeps the
   * user's tweaks across pattern switches while still showing a sensible
   * default for newly-exposed parameters.
   */
  async loadRoutingParams(patternId: string): Promise<void> {
    // The pattern changed: re-constrain the layer count against the new
    // pattern's declared range before (and regardless of) the IPC fetch.
    this.constrainLayersToPattern();
    try {
      this.routing_param_defs = await routingPatternParameters(patternId);
    } catch {
      // backend unavailable or errored — leave current defs in place
      this.routing_param_defs = [];
      return;
    }
    const userSet = new Set(Object.keys(this.routing_params));
    for (const def of this.routing_param_defs) {
      if (!userSet.has(def.key)) {
        this.routing_params[def.key] = def.default;
      }
    }
    this.routing_params_version += 1;
  }

  /**
   * Set one routing-pattern parameter value and bump the version counter so
   * the App.svelte preview/simulation scheduling effects re-run. Use this
   * instead of mutating `routing_params[key]` directly (which won't propagate
   * to effects).
   */
  setRoutingParam(key: string, value: number): void {
    this.routing_params[key] = value;
    this.routing_params_version += 1;
  }

  /** Build the SI LinearMotorConfig for the Tauri backend. */
  toIpc(): LinearMotorConfig {
    return {
      active_area_length_m: mm(this.active_area_length_mm),
      board_width_m: mm(this.active_area_width_mm),
      pcb_thickness_m: mm(this.pcb_thickness_mm),
      strands_per_phase: this.strands_per_phase,

      magnet_count: this.magnet_count,
      magnet_width_m: mm(this.magnet_width_mm),
      magnet_cross_width_m: mm(this.magnet_cross_width_mm),
      magnet_height_m: mm(this.magnet_height_mm),
      magnet_gap_m: mm(this.magnet_gap_mm),
      magnet_pitch_m: mm(this.pole_pitch_mm),

      magnet_remanence_t: this.magnet_remanence_t,
      magnet_grade: this.magnet_grade,
      air_gap_m: mm(this.air_gap_mm),

      routing_pattern: this.routing_pattern,
      routing_params: this.routing_params,
      phases: this.phases,
      spacing_ratio: this.spacing_ratio,

      max_current_a: this.max_current_a,
      supply_voltage_v: this.supply_voltage_v,

      num_layers: this.num_layers,
      min_trace_m: mm(this.min_trace_mm),
      trace_width_m: mm(this.trace_width_mm),
      min_space_m: mm(this.min_space_mm),
      min_via_drill_m: mm(this.min_via_drill_mm),
      min_via_annular_ring_m: mm(this.min_via_annular_ring_mm),
      max_layers: this.max_layers,
      drive_frequency_hz: this.drive_frequency_hz,
      max_temperature_rise_c: this.max_temperature_rise_c,

      target_force_n: this.target_force_n,
      peak_force_n: this.peak_force_n,
      friction_n: this.friction_n,
      carriage_mass_kg: this.carriage_mass_kg,
      max_accel_m_s2: this.max_accel_m_s2,
      capacitor_bank_uf: this.capacitor_bank_uf,

      commutation: this.commutation,
      n_positions: this.n_positions,
      meshing: this.meshing,

      backplane: $state.snapshot(this.backplane),

      name: null,
    };
  }
}
