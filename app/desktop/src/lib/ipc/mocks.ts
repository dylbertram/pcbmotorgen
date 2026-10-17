/**
 * Deterministic, physics-flavoured mock implementations of the backend
 * commands. Used only when the Tauri runtime is unavailable (plain
 * `vite dev` in a browser) so the dashboard stays interactive.
 *
 * These are pure functions over `LinearMotorConfig` — no IPC imports.
 */

import type {
  CheckStatus,
  DriveAnalysis,
  DriveSettings,
  LinearMotorConfig,
  CoilArcDto,
  CoilPathDto,
  CoilSegmentDto,
  PhaseCoilDto,
  PoleRegionDto,
  RoutingDimensionsDto,
  PhaseBandWidthDto,
  ForceSweepResult,
  HeightStackResultDto,
  FrictionBudgetDto,
  BoardDiagnostics,
  PreconditionWarning,
  CoilPreview,
  KicadConnection,
  KicadWriteResult,
  BFieldGridDto,
  DxfExportResult,
  TravelEnvelopeDto,
  MagnetGrade,
} from "../types";
import { MAGNET_GRADES } from "../types/magnets";

// ---------------------------------------------------------------------------
// Named mock physics constants.
//
// These mirror the real backend's approximated physics so `vite dev` output
// stays plausibly close to prod. Each value is a shorthand the real solver
// computes from first principles — naming them keeps the mock's intent (and
// the fact that it is an approximation) explicit.
// ---------------------------------------------------------------------------

/** Force baseline coefficient: ~0.4 × Br × I × layers × (N/10) [N]. */
const FORCE_BASELINE_K = 0.4;
/** Friction safety multiplier applied to derive minimum-drive force. */
const FRICTION_SAFETY_K = 1.3;
/** Normal-force pull-in relative to thrust (≈1.5–1.7× ). */
const NORMAL_FORCE_K = 1.6;
/** Ripple fraction of the baseline thrust. */
const FORCE_RIPPLE_PCT = 0.08;
/** Arc/annular height for the decorative preview arcs (m). */
const PREVIEW_ARC_HEIGHT_M = 0.0008;
/** Copper protrusion per side above the substrate (m) — 1oz ≈ 35 µm. */
const COPPER_PROTRUSION_1OZ_M = 35e-6;
/** Solder-mask coating thickness (m). */
const SOLDER_MASK_M = 20e-6;
/** Assembly tolerance allowance in the height stack (m). */
const TOLERANCE_M = 0.1e-3;
/** Copper resistivity (Ω·m). */
const RHO = 1.72e-8;

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

/**
 * Mock magnet-grade table. Projects the static TS mirror of the Rust
 * `pcbmotorgen_simulation::magnet_grades::MAGNET_GRADES` table into the same
 * `MagnetGrade[]` wire shape `get_magnet_grades` returns, so `vite dev` output
 * matches prod.
 */
export function mockMagnetGrades(): MagnetGrade[] {
  return Object.values(MAGNET_GRADES).map((g) => ({ ...g }));
}

/**
 * The ONE TypeScript-side placeholder travel envelope (kata ab30) — a FIXED
 * literal, never computed from config.
 *
 * AUTHORITY for the travel-envelope math (span-aware flush clamp + rest
 * phase): `pcbmotorgen_simulation::equilibrium::travel_envelope_over_slots`
 * (kata 5c7r), reached over IPC via the `travel_envelope` Tauri command
 * (`src-tauri/src/commands/physics.rs`). Earlier mock revisions re-derived
 * that math here; the duplicate has been removed — the desktop app must not
 * re-derive envelope physics in TypeScript.
 *
 * The numbers are the pinned reference output of the authority for the UI
 * reference build (N=12, P_e=12 mm, copper [0, 147] mm): min 36 mm, max
 * 111 mm, rest phase 10 mm, period 12 mm. They exist ONLY so the UI has
 * something to draw before a backend envelope arrives (or in browser-dev
 * mock mode) — they are not valid for other configurations, so MotionStore
 * pairs this placeholder with a visible "travel envelope unavailable —
 * backend required" warning whenever it is the active envelope.
 */
export const PLACEHOLDER_TRAVEL_ENVELOPE: TravelEnvelopeDto = {
  min_position_m: 0.036,
  max_position_m: 0.111,
  rest_phase_m: 0.01,
  electrical_period_m: 0.012,
};

/**
 * True when `dto` IS the shared placeholder instance (object identity). A
 * real backend envelope is always a fresh object decoded from the IPC
 * bridge, so it can never collide with the constant; the mock returns this
 * exact constant, which keeps the "unavailable" warning visible in
 * browser-dev mock mode.
 */
export function isPlaceholderEnvelope(
  dto: TravelEnvelopeDto | null | undefined,
): boolean {
  return dto === PLACEHOLDER_TRAVEL_ENVELOPE;
}

/**
 * Mock travel envelope — returns the fixed placeholder above. NO math is
 * re-derived here: the authority is
 * `equilibrium::travel_envelope_over_slots` (see PLACEHOLDER_TRAVEL_ENVELOPE).
 * The config parameter is kept for call-site parity with the real
 * `travel_envelope` command but is intentionally unused.
 */
export function mockTravelEnvelope(_c: LinearMotorConfig): TravelEnvelopeDto {
  return PLACEHOLDER_TRAVEL_ENVELOPE;
}

export function mockCoils(c: LinearMotorConfig): CoilPathDto {
  // Build a serpentine per (phase × layer) pair so the dev-mode preview
  // mirrors the real backend's multi-layer output (the real infinity-braid
  // exhausts 2 layers — top braid + mirrored bottom braid). Without this,
  // the preview in browser dev mode only ever rendered layer 0 while the
  // header advertised `num_layers` — i.e. "missing layer segments".
  const phases: PhaseCoilDto[] = [];
  // The mock mirrors the real infinity braid: traces (and their pattern-made
  // pole regions) are routed across the active area — the whole routing
  // domain, whose end turns are part of the pattern. The mover must have
  // conductors beneath it for every position along its travel, exactly like
  // the real backend.
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
  // Pattern-owned pole-region bands (the routing sidecar's authoritative
  // phase/pole boundaries). The mock mirrors the infinity braid: one region
  // per phase per pole pitch, each phase interleaved by a phase-band-pitch
  // offset so the alternating red/blue zones overlap the interleaved wave
  // bands. Coordinates are metres (the Tauri adapter converts routing mm →
  // SI).
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

export function mockForceSweep(c: LinearMotorConfig): ForceSweepResult {
  const n = c.n_positions;
  const span = (c.magnet_count - 1) * c.magnet_pitch_m + c.magnet_width_m;
  const travel = Math.max(0, c.active_area_length_m - span);
  const positions = Array.from({ length: n }, (_, i) => c.magnet_width_m / 2 + (travel * i) / (n - 1));
  // Sinusoidal-ish force with ripple + a normal-force baseline.
  const br = c.magnet_remanence_t;
  const ipeak = c.max_current_a;
  const baseline = FORCE_BASELINE_K * br * ipeak * c.num_layers * (c.magnet_count / 10);
  const ripple = baseline * FORCE_RIPPLE_PCT;
  const force_x = positions.map(
    (x) => baseline + ripple * Math.sin((x / Math.max(c.magnet_pitch_m, 1e-6)) * 2 * Math.PI * c.phases),
  );
  const force_y = positions.map((_, idx) => 0.01 * Math.sin(idx));
  const force_z = positions.map(() => baseline * NORMAL_FORCE_K); // pull-in ~ 1.5–1.7× thrust
  const mean = force_x.reduce((a, b) => a + b, 0) / n;
  const peak = Math.max(...force_x);
  const min = Math.min(...force_x);
  const ripplePct = Math.abs(mean) < 1e-12 ? 0 : ((peak - min) / Math.abs(mean)) * 100;
  return {
    positions_m: positions,
    force_x_n: force_x,
    force_y_n: force_y,
    force_z_n: force_z,
    per_phase_force_x: force_x.map((f) => [f / c.phases, f / c.phases, f / c.phases]),
    commutation: c.commutation,
    current_a: ipeak,
    mean_thrust_n: mean,
    peak_thrust_n: peak,
    min_thrust_n: min,
    ripple_pct: ripplePct,
    n_positions: n,
  };
}

export function mockHeightStack(c: LinearMotorConfig): HeightStackResultDto {
  // Backplane heights mirror `BackplaneStack`. The mock skips the image-method
  // analysis, so `backplane_analysis` is always null here.
  const backplane_m = c.backplane?.layers.reduce((sum, l) => sum + l.thickness_m, 0) ?? 0;
  const housing_gap_m = c.backplane?.housing?.gap_m ?? 0;
  const housing_m = c.backplane?.housing?.thickness_m ?? 0;
  return {
    pcb_thickness_m: c.pcb_thickness_m,
    cu_protrusion_m: COPPER_PROTRUSION_1OZ_M * (c.num_layers >= 6 ? 2 : 1),
    solder_mask_m: SOLDER_MASK_M,
    air_gap_m: c.air_gap_m,
    magnet_height_m: c.magnet_height_m,
    tolerance_m: TOLERANCE_M,
    backplane_m,
    housing_gap_m,
    housing_m,
    total_height_m:
      c.pcb_thickness_m + COPPER_PROTRUSION_1OZ_M + SOLDER_MASK_M + c.air_gap_m + c.magnet_height_m + TOLERANCE_M +
      backplane_m + housing_gap_m + housing_m,
    backplane_analysis: null,
  };
}

export function mockFriction(c: LinearMotorConfig): FrictionBudgetDto {
  const total = c.friction_n;
  return {
    bearing_friction_n: total * 0.5,
    cable_drag_n: total * 0.3,
    wiper_contact_n: total * 0.2,
    cogging_n: 0,
    total_n: total,
    minimum_drive_force_n: total * FRICTION_SAFETY_K,
  };
}

// ---------------------------------------------------------------------------
// Board diagnostics / preconditions / preview mocks (frontend-only dev)
// ---------------------------------------------------------------------------

/**
 * Mock board snapshot for `vite dev` (no Tauri). All edge-cut bounds
 * and net classes are 0 / empty (matching the real backend's
 * not-yet-queryable placeholders), and `copper_layer_count` mirrors
 * the user's `num_layers` so the validate/preview flows have
 * something realistic to check against.
 */
export function mockBoardDiagnostics(): BoardDiagnostics {
  return {
    board_name: "(mock board — backend not connected)",
    copper_layer_count: 4,
    board_x_min_mm: 0.0,
    board_x_max_mm: 0.0,
    board_y_min_mm: 0.0,
    board_y_max_mm: 0.0,
    available_net_classes: [],
  };
}

/** Mock KiCad connection state — no board is open in dev mode. */
export function mockKicadConnection(): KicadConnection {
  return { connected: false, board_name: "(not connected)", copper_layers: 0 };
}

/** Mock write result — surfacing that no backend exists. */
export function mockKicadWrite(): KicadWriteResult {
  return {
    items_attempted: 0,
    items_created: 0,
    failures: ["Backend not available — open the Tauri shell to write to KiCad"],
    failure_summary: [],
    commit_id: "",
  };
}

/**
 * Mock precondition check. In dev mode we don't have a real board to
 * compare against, so we return an empty list — the UI shows the green
 * "all clear" state. The real Rust validator runs the rule set from
 * `pcbmotorgen_export::validate_write_preconditions`.
 */
export function mockValidatePreconditions(
  _config: LinearMotorConfig,
  _diagnostics: BoardDiagnostics,
): PreconditionWarning[] {
  return [];
}

/**
 * Mock coil preview. Builds a per-layer tally that mirrors the shape
 * the Rust side would produce, so the UI's preview card has something
 * to render in dev mode.
 */
export function mockPreviewCoils(config: LinearMotorConfig): CoilPreview {
  const numLayers = Math.max(1, config.num_layers);
  // Heuristic segment count: ~2 active conductors per magnet per phase,
  // plus one end-turn per conductor pair. Matches the mockCoils() shape
  // closely enough for the "X tracks, Y vias" summary to look real.
  const segsPerLayer =
    Math.max(2, config.magnet_count * 2) * 2 - 1; // conductors + end-turns
  const totalTracks = segsPerLayer * config.phases * numLayers;
  const layers = Array.from({ length: numLayers }, (_, i) => ({
    layer_idx: i,
    phase_count: config.phases,
    segment_count: segsPerLayer * config.phases,
    via_count: 0,
  }));
  return {
    num_layers: numLayers,
    pattern_id: config.routing_pattern,
    layers,
    total_tracks: totalTracks,
    total_vias: 0,
  };
}

/**
 * Mock DXF export for frontend-only dev. Returns a minimal valid DXF
 * file header with a note that the backend is not connected.
 */
export function mockDxfExportResult(config: LinearMotorConfig): DxfExportResult {
  const header = [
    "0",
    "SECTION",
    "2",
    "HEADER",
    "9",
    "$INSUNITS",
    "70",
    "4",
    "0",
    "ENDSEC",
    "0",
    "SECTION",
    "2",
    "ENTITIES",
    // A simple note line indicating mock mode.
    "0",
    "TEXT",
    "8",
    "Notes",
    "10",
    "0.0",
    "20",
    "0.0",
    "40",
    "3.0",
    "1",
    `(Mock DXF — backend not connected. Config: ${config.routing_pattern}, ${config.num_layers} layers)`,
    "0",
    "ENDSEC",
    "0",
    "EOF",
    "",
  ].join("\n");
  return {
    dxf_content: header,
    summary: {
      total_lines: 0,
      total_arcs: 0,
      total_circles: 0,
      layer_count: 1,
    },
  };
}

/**
 * Mock B-field grid: sinusoidal Bz, magnitude ∝ Br. Sufficient for
 * visualising the alternating-pole field in the absence of a backend.
 */
export function mockBFieldGrid(
  c: LinearMotorConfig,
  n_x: number,
  n_z: number,
  x_extent_m: [number, number],
  z_extent_m: [number, number],
): BFieldGridDto {
  const xs = Array.from({ length: n_x }, (_, i) =>
    x_extent_m[0] + (x_extent_m[1] - x_extent_m[0]) * (i / Math.max(n_x - 1, 1)),
  );
  const zs = Array.from({ length: n_z }, (_, i) =>
    z_extent_m[0] + (z_extent_m[1] - z_extent_m[0]) * (i / Math.max(n_z - 1, 1)),
  );
  const samples: BFieldGridDto["samples"] = [];
  for (const z of zs) {
    for (const x of xs) {
      const br = c.magnet_remanence_t;
      const k = (2 * Math.PI) / Math.max(c.magnet_pitch_m, 1e-6);
      const bz = 0.4 * br * Math.sin(k * x) * Math.exp(-z / 0.003);
      const bx = 0.05 * br * Math.cos(k * x) * Math.exp(-z / 0.003);
      const by = 0.0;
      const mag = Math.sqrt(bx * bx + by * by + bz * bz);
      samples.push({ x_m: x, z_m: z, bx_t: bx, by_t: by, bz_t: bz, mag_t: mag });
    }
  }
  return {
    samples,
    x_extent_m,
    z_extent_m,
  };
}

/**
 * Mock driver analysis for `vite dev`: a single-strand, two-layer estimate
 * with the same check formulas as the backend. The geometry is NOT measured.
 */
export function mockDriveAnalysis(
  c: LinearMotorConfig,
  d: DriveSettings,
  kf: number | null,
): DriveAnalysis {
  const rho = RHO * (1 + 0.00393 * (d.winding_temp_c - 20));
  const length = c.active_area_length_m * (c.board_width_m / (c.magnet_pitch_m / 2)) * 2;
  const t = d.outer_copper_oz * 35e-6;
  const r = (rho * length) / (c.trace_width_m * t);
  const l = 2e-6;
  const lEff = l + Math.max(0, d.series_inductance_h);
  const i = c.max_current_a;
  const vBus = c.supply_voltage_v;
  const available = d.voltage_headroom * vBus;
  const ke = kf !== null ? (2 / 3) * kf : null;
  const pe = 2 * c.magnet_pitch_m;
  const required = (v: number) =>
    Math.sqrt(3) * Math.hypot(i * r + (ke ?? 0) * v, ((2 * Math.PI * v) / pe) * lEff * i) + i * d.driver.rds_on_ohm;
  const ripple = r > 1e-12 ? vBus / (2 * r) * Math.tanh(r / (4 * d.pwm_hz * lEff)) : vBus / (8 * d.pwm_hz * lEff);
  const rippleLimit = d.ripple_limit_fraction * i;
  const requiredFL = rippleLimit <= 0 || vBus <= 0 ? Infinity
    : r <= 1e-12 ? vBus / (8 * rippleLimit)
    : 2 * r * rippleLimit >= vBus ? 0
    : r / (4 * Math.atanh(2 * r * rippleLimit / vBus));
  const ampacity = 0.048 * d.allowed_rise_c ** 0.44 * ((c.trace_width_m / 25.4e-6) * (t / 25.4e-6)) ** 0.725;
  const vLimitedI = available / (Math.sqrt(3) * r + d.driver.rds_on_ohm);
  const maxCont = Math.min(d.driver.continuous_rms_a, ampacity, vLimitedI);
  const st = (ok: boolean, warn: boolean): CheckStatus => (ok ? "pass" : warn ? "warn" : "fail");
  const check = (id: string, label: string, status: CheckStatus, value: number, limit: number, unit: string) =>
    ({ id, label, status, value, limit, unit, detail: "Mock value: backend not connected." });
  const hold = required(0);
  const atSpeed = ke !== null ? required(d.target_speed_m_s) : null;
  return {
    driver_name: d.driver.name,
    phases: ["A", "B", "C"].slice(0, c.phases).map((net) => ({
      net,
      strands: 1,
      layers: [0, 1],
      strand_length_m: length,
      total_length_m: length,
      active_length_m: length * 0.8,
      vias_per_strand: 0,
      vias_total: 0,
      resistance_20c_ohm: (r * RHO) / rho,
      resistance_hot_ohm: r,
      via_resistance_ohm: 0,
      self_inductance_h: l,
      max_trace_share: 1,
      connected: true,
    })),
    trace_width_m: c.trace_width_m,
    outer_copper_m: t,
    inner_copper_m: d.inner_copper_oz * 35e-6,
    via_resistance_each_ohm: 0.0015,
    phase_resistance_ohm: r,
    phase_inductance_h: l,
    mutual_inductance_h: 0,
    line_inductance_h: 2 * l,
    synchronous_inductance_h: l,
    series_inductance_h: Math.max(0, d.series_inductance_h),
    effective_inductance_h: lEff,
    line_resistance_ohm: 2 * r,
    time_constant_s: lEff / r,
    bus_voltage_v: vBus,
    phase_current_a: i,
    pwm_hz: d.pwm_hz,
    target_speed_m_s: d.target_speed_m_s,
    thrust_constant_n_per_a: kf,
    back_emf_constant_v_s_per_m: ke,
    holding_voltage_v: hold,
    speed_voltage_v: atSpeed,
    available_voltage_v: available,
    voltage_limited_current_a: vLimitedI,
    max_speed_m_s: ke !== null ? Math.max(0, (available / Math.sqrt(3) - i * r) / Math.max(ke, 1e-9)) : null,
    ripple_pp_a: ripple,
    min_pwm_hz: requiredFL / lEff,
    added_inductance_h: Math.max(0, requiredFL / d.pwm_hz - lEff),
    peak_current_a: i + ripple / 2,
    trace_ampacity_a: ampacity,
    copper_loss_w: 1.5 * i * i * r,
    thrust_n: kf !== null ? kf * i : null,
    max_continuous_current_a: maxCont,
    limiting_factor: "mock",
    max_continuous_thrust_n: kf !== null ? kf * maxCont : null,
    checks: [
      check("supply", "Bus voltage within driver rating", st(vBus >= d.driver.min_supply_v && vBus <= d.driver.max_supply_v, false), vBus, d.driver.max_supply_v, "V"),
      check("holding_voltage", "Voltage to hold the phase current", st(hold <= available, hold <= vBus), hold, available, "V"),
      check("ripple", "PWM current ripple estimate (50% duty)", st(ripple <= rippleLimit, ripple <= i), ripple, rippleLimit, "A"),
      check("ampacity", "Trace ampacity", st(i <= ampacity, i <= 1.25 * ampacity), i, ampacity, "A"),
    ],
    speed_curve: Array.from({ length: 41 }, (_, k) => {
      const v = (Math.max(d.target_speed_m_s, 0.1) * 1.4 * k) / 40;
      return { speed_m_s: v, required_v: required(v) };
    }),
    notes: ["Mock analysis: backend not connected, geometry not measured."],
  };
}
