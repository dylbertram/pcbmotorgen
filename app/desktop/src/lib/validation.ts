/**
 * Cross-field design validation rules.
 *
 * These checks explain conflicts between fields without changing the last
 * committed input value. NumberField handles single-field type/range
 * blocking; cross-field auto-repair is intentionally deferred to a later
 * constraint solver iteration.
 *
 * Extracted from ValidationWarning.svelte so the rule engine is unit
 * testable and reusable. `DesignConfigInput` is a structural snapshot of
 * the fields the rules read — `ConfigStore` satisfies it directly.
 */

import { MAX_MAGNET_COUNT, MAX_PCB_LAYERS } from "./types/simulationLimits";
import { validatePcbStackup, type PcbStackupMm } from "./pcbStackup";
import { BACKPLANE_MAX_LAYERS, BACKPLANE_MAX_THICKNESS_M, HOUSING_MAX_THICKNESS_M, HOUSING_MAX_GAP_M, BACKPLANE_MAX_MU_R, BACKPLANE_MAX_BSAT_T, isSupportedHousingMaterial, type BackplaneStack } from "./types/backplane";

export type FindingLevel = "error" | "warning";

export interface Finding {
  id: string;
  level: FindingLevel;
  message: string;
}

/** Structural view of the config fields the validation rules consume. */
export interface DesignConfigInput {
  travel_mm: number;
  mover_span_mm: number;
  magnet_count: number;
  /** X length of one magnet (mm) — the user-facing input. The pole fill
   *  factor is DERIVED from this and the pole pitch inside the rule below. */
  magnet_width_mm: number;
  magnet_gap_mm: number;
  /** Electrical pitch P_e (mm); the pole pitch is τp = P_e / 2. */
  electrical_pitch_mm: number;
  min_space_mm: number;
  magnet_cross_width_mm: number;
  active_area_width_mm: number;
  num_layers: number;
  max_layers: number;
  routing_pattern: string;
  strands_per_phase: number;
  min_trace_mm: number;
  /** Nominal (actual) trace width (mm); must clear `min_trace_mm`. */
  trace_width_mm: number;
  peak_force_n: number;
  target_force_n: number;
  backplane?: BackplaneStack | null;
  pcb_stackup_mm?: PcbStackupMm | null;
}

/** Explain unsupported restored settings without clamping or rewriting them. */
export function validateBackplaneInput(stack: BackplaneStack | null | undefined): Finding[] {
  if (!stack) return [];
  const findings: Finding[] = [];
  if (stack.layers.length > BACKPLANE_MAX_LAYERS) findings.push({ id: "backplane-layer-limit", level: "error", message: `Backplane supports at most ${BACKPLANE_MAX_LAYERS} layers; saved layers have not been removed.` });
  stack.layers.forEach((layer, index) => {
    if (!Number.isFinite(layer.thickness_m) || layer.thickness_m <= 0 || layer.thickness_m > BACKPLANE_MAX_THICKNESS_M) {
      findings.push({ id: `backplane-${index}-thickness`, level: "error", message: `Layer ${index + 1} thickness must be greater than 0 and at most 2 mm.` });
    }
    if (layer.mu_r != null && (!Number.isFinite(layer.mu_r) || layer.mu_r < 1 || layer.mu_r > BACKPLANE_MAX_MU_R)) findings.push({ id: `backplane-${index}-mu`, level: "error", message: `Layer ${index + 1} has an unsupported relative permeability.` });
    if (layer.bsat_t != null && (!Number.isFinite(layer.bsat_t) || layer.bsat_t <= 0 || layer.bsat_t > BACKPLANE_MAX_BSAT_T)) findings.push({ id: `backplane-${index}-bsat`, level: "error", message: `Layer ${index + 1} has an unsupported saturation flux density.` });
  });
  const housing = stack.housing;
  if (housing) {
    if (!isSupportedHousingMaterial(housing.material)) findings.push({ id: "housing-material", level: "error", message: "Housing must use aluminum or non-magnetic stainless 304/316. The saved material has not been changed." });
    if (!Number.isFinite(housing.thickness_m) || housing.thickness_m <= 0 || housing.thickness_m > HOUSING_MAX_THICKNESS_M) findings.push({ id: "housing-thickness", level: "error", message: "Housing wall thickness must be greater than 0 and at most 5 mm." });
    if (!Number.isFinite(housing.gap_m) || housing.gap_m < 0 || housing.gap_m > HOUSING_MAX_GAP_M) findings.push({ id: "housing-gap", level: "error", message: "Housing gap must be between 0 and 10 mm." });
  }
  return findings;
}

/** Run all cross-field checks against `config`. */
export function validateDesign(config: DesignConfigInput): Finding[] {
  const next: Finding[] = validateBackplaneInput(config.backplane);
  if (config.pcb_stackup_mm) {
    try { validatePcbStackup(config.pcb_stackup_mm, config.num_layers); }
    catch (error) { next.push({ id: "pcb-stackup", level: "error", message: error instanceof Error ? error.message : String(error) }); }
  }
  const travel = config.travel_mm;

  if (!Number.isFinite(travel) || travel <= 0) {
    next.push({
      id: "travel-negative",
      level: "error",
      message:
        `Desired center-to-center travel must be positive ` +
        `(the mover array spans ${config.mover_span_mm.toFixed(1)} mm). ` +
        `Current travel = ${Number.isFinite(travel) ? travel.toFixed(1) : "invalid"} mm.`,
    });
  }

  if (!Number.isInteger(config.magnet_count) || config.magnet_count < 2) {
    next.push({
      id: "magnet-count",
      level: "error",
      message: `Magnet count must be an integer ≥ 2 (got ${config.magnet_count}).`,
    });
  }
  if (config.magnet_count > MAX_MAGNET_COUNT) {
    next.push({ id: "magnet-count-limit", level: "error", message: `Coreless screening supports at most ${MAX_MAGNET_COUNT} magnets.` });
  }
  if (!Number.isInteger(config.max_layers) || config.max_layers < 2 || config.max_layers % 2 !== 0 || config.max_layers > MAX_PCB_LAYERS || config.num_layers > MAX_PCB_LAYERS) {
    next.push({ id: "pcb-layer-limit", level: "error", message: `PCB layer counts must be even and between 2 and ${MAX_PCB_LAYERS}. Saved geometry has not been changed.` });
  }

  if (
    config.electrical_pitch_mm <= 0 ||
    !Number.isFinite(config.electrical_pitch_mm)
  ) {
    next.push({
      id: "electrical-pitch",
      level: "error",
      message: `Electrical pitch (P_e) must be positive (got ${config.electrical_pitch_mm}).`,
    });
  }

  // Pole fill factor derived from the width input: k = W_m / τp —
  // the electrical pitch P_e is twice the pole pitch: τp = P_e / 2.
  const polePitchMm = config.electrical_pitch_mm / 2;
  const k = polePitchMm > 0 ? config.magnet_width_mm / polePitchMm : Number.NaN;
  if (!Number.isFinite(k) || k < 0.5 || k > 1.0) {
    next.push({
      id: "magnet-fill",
      level: "error",
      message:
        `Magnet X Length (${config.magnet_width_mm.toFixed(2)} mm vs ${(polePitchMm > 0 ? polePitchMm : Number.NaN).toFixed(2)} mm pole pitch) gives a fill factor outside [0.50, 1.00] ` +
        `(k = ${Number.isFinite(k) ? k.toFixed(2) : "invalid"}).`,
    });
  } else if (k > 0.85) {
    next.push({
      id: "magnet-fill-leakage",
      level: "warning",
      message:
        `Fill factor ${k.toFixed(2)} exceeds 0.85 — flux can leak between adjacent ` +
        "magnets instead of passing through the coil plane. End-to-end magnets (k = 1.00) are " +
        "allowed but expect higher spatial harmonics.",
    });
  }

  if (config.magnet_cross_width_mm > config.active_area_width_mm) {
    next.push({
      id: "magnet-cross-width",
      level: "warning",
      message:
        `Magnet Y Width (across the stator) (${config.magnet_cross_width_mm.toFixed(1)} mm) ` +
        `exceeds the active trace width (${config.active_area_width_mm.toFixed(1)} mm). ` +
        "The force-producing area will not be fully coupled.",
    });
  }

  if (config.num_layers < 2 || config.num_layers % 2 !== 0) {
    next.push({
      id: "layer-count",
      level: "error",
      message: `Layer count must be an even number ≥ 2 (got ${config.num_layers}).`,
    });
  } else if (config.num_layers > config.max_layers) {
    next.push({
      id: "layer-limit",
      level: "error",
      message:
        `Layer count (${config.num_layers}) exceeds the configured maximum ` +
        `of ${config.max_layers}.`,
    });
  }

  if (config.routing_pattern === "infinity-braid" && config.num_layers < 2) {
    next.push({
      id: "infinity-layer-requirement",
      level: "error",
      message: "Infinity Braid requires at least two copper layers.",
    });
  }

  const strandHeight = config.active_area_width_mm / Math.max(config.strands_per_phase, 1);
  const minimumStrandHeight = config.trace_width_mm + config.min_space_mm;
  if (config.strands_per_phase > 1 && strandHeight < minimumStrandHeight) {
    next.push({
      id: "strand-clearance",
      level: "warning",
      message:
        `The active width gives each strand ${strandHeight.toFixed(2)} mm, ` +
        `but trace plus clearance requires ${minimumStrandHeight.toFixed(2)} mm. ` +
        "Reduce strands or increase active width.",
    });
  }

  if (!(config.trace_width_mm > 0) || config.trace_width_mm < config.min_trace_mm) {
    next.push({
      id: "trace-width",
      level: "error",
      message:
        `Trace width must be positive and at least the minimum trace width ` +
        `(${config.min_trace_mm} mm); got ${config.trace_width_mm} mm.`,
    });
  }

  if (config.peak_force_n < config.target_force_n) {
    next.push({
      id: "force-target-order",
      level: "warning",
      message: `Peak force should be at least the continuous target (${config.target_force_n.toFixed(2)} N).`,
    });
  }

  return next;
}

/** True when any rule produced an error-severity finding. */
export function hasErrors(findings: Finding[]): boolean {
  return findings.some((finding) => finding.level === "error");
}
