import type { MoveProfile, RoutedMoveRequest } from "./types/movePower";

/** Form units stay human-readable; conversion to the native SI request happens once. */
export interface MoveAdvancedInput {
  initialVelocityMPerS: number;
  finalVelocityMPerS: number;
  dampingNsPerM: number;
  externalLoadN: number;
  acceptsRegeneration: boolean;
  electricalAngleRad: number;
  forcePositions: number;
  /** null selects a bounded automatic step from the move duration. */
  timeStepS: number | null;
}

export interface MoveFormInput {
  fromMm: number | null | undefined;
  toMm: number | null | undefined;
  durationS: number | null | undefined;
  loadMode: "design" | "custom";
  massG: number | null | undefined;
  frictionN: number | null | undefined;
  advanced: MoveAdvancedInput;
}

export interface MoveDesignDefaults {
  fullTravelMm: number;
  magnetWidthMm: number;
  massG: number;
  frictionN: number;
  massSource: "magnets" | "assembly";
}

export const DESIGN_MASS_INCLUDES = {
  magnets: "Magnet-only estimate; excludes carrier, bushings, enclosure, knob and other moving parts",
  assembly: "Full moving assembly estimate including magnets, carrier, bushings, moving enclosure, knob and attached load",
} as const;

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** Automatic sampling stays inside the native force-map and interval budgets. */
export function automaticTimeStep(durationS: number): number {
  return Math.min(1e-3, Math.max(1e-4, durationS / 2000));
}

export function defaultMoveForm(design: MoveDesignDefaults): MoveFormInput {
  return {
    fromMm: 0,
    toMm: Number(design.fullTravelMm.toFixed(6)),
    durationS: 0.5,
    loadMode: "design",
    massG: design.massG,
    frictionN: design.frictionN,
    advanced: {
      initialVelocityMPerS: 0,
      finalVelocityMPerS: 0,
      dampingNsPerM: 0,
      externalLoadN: 0,
      acceptsRegeneration: true,
      electricalAngleRad: Math.PI / 2,
      forcePositions: 129,
      timeStepS: null,
    },
  };
}

function round(value: number, places = 9): number {
  return Number(value.toFixed(places));
}

/** Existing saved moves open with their own values; nothing is inferred or replaced. */
export function moveFormFromRequest(request: RoutedMoveRequest, design: MoveDesignDefaults): MoveFormInput {
  const baseMm = design.magnetWidthMm / 2;
  const p = request.profile;
  const massG = p.moving_mass_kg * 1000;
  const usesDesign = Math.abs(massG - design.massG) < 1e-6
    && Math.abs(p.coulomb_friction_n - design.frictionN) < 1e-9
    && p.mass_includes === DESIGN_MASS_INCLUDES[design.massSource];
  return {
    fromMm: round(p.start_m * 1000 - baseMm),
    toMm: round(p.end_m * 1000 - baseMm),
    durationS: p.duration_s,
    loadMode: usesDesign ? "design" : "custom",
    massG,
    frictionN: p.coulomb_friction_n,
    advanced: {
      initialVelocityMPerS: p.initial_velocity_m_s,
      finalVelocityMPerS: p.final_velocity_m_s,
      dampingNsPerM: p.damping_n_s_per_m,
      externalLoadN: p.external_load_n,
      acceptsRegeneration: request.source.accepts_regeneration,
      electricalAngleRad: request.electrical_angle_at_zero_rad,
      forcePositions: request.force_positions,
      timeStepS: p.time_step_s,
    },
  };
}

/** Inline problems keep Calculate disabled and explain the exact fix. */
export function moveFormIssues(form: MoveFormInput, design: MoveDesignDefaults): string[] {
  const issues: string[] = [];
  const { fromMm, toMm, durationS, massG, frictionN, advanced } = form;
  if (!finite(fromMm) || !finite(toMm)) issues.push("Enter both move positions in mm.");
  else if (Math.abs(toMm - fromMm) < 1e-6) issues.push("The end position must differ from the start position.");
  if (finite(fromMm) && finite(toMm)) {
    for (const [name, value] of [["start", fromMm], ["end", toMm]] as const) {
      if (value < -1e-6 || value > design.fullTravelMm + 1e-6)
        issues.push(`Move ${name} is outside the ${round(design.fullTravelMm, 3)} mm usable travel.`);
    }
  }
  if (!finite(durationS) || durationS <= 0) issues.push("Set a move duration greater than zero.");
  if (form.loadMode === "custom") {
    if (!finite(massG) || massG <= 0) issues.push("Set the moving mass in grams.");
    if (!finite(frictionN) || frictionN < 0) issues.push("Set sliding friction in newtons (zero is allowed).");
  }
  if (!finite(advanced.electricalAngleRad)) issues.push("Set the controller electrical reference in radians.");
  if (!Number.isInteger(advanced.forcePositions) || advanced.forcePositions < 2 || advanced.forcePositions > 513)
    issues.push("Use between 2 and 513 force-map positions.");
  if (advanced.timeStepS !== null) {
    if (!finite(advanced.timeStepS) || advanced.timeStepS <= 0) issues.push("Set a positive time step, or leave it automatic.");
    else if (finite(durationS) && durationS / advanced.timeStepS > 20_000) issues.push("The time step gives more than 20,000 samples; increase it.");
  }
  for (const [label, value] of [["initial speed", advanced.initialVelocityMPerS], ["final speed", advanced.finalVelocityMPerS],
    ["damping", advanced.dampingNsPerM], ["external load", advanced.externalLoadN]] as const) {
    if (!finite(value)) issues.push(`Set ${label} to a finite number.`);
  }
  if (advanced.dampingNsPerM < 0) issues.push("Damping cannot be negative.");
  return issues;
}

export function massIncludes(form: MoveFormInput, design: MoveDesignDefaults): string {
  if (form.loadMode === "design") return DESIGN_MASS_INCLUDES[design.massSource];
  return `Custom move load of ${round(form.massG ?? 0, 3)} g; assembly coverage stated by the user, not independently established`;
}

export interface MoveContext {
  design: MoveDesignDefaults;
  /** Optional advanced override for the controller reference. */
  timeStepS?: number | null;
}

/**
 * Convert the visible form to the native request exactly once. Positions are
 * relative to the start of travel; the native model uses the first magnet
 * centre as its absolute origin.
 */
export function buildMoveRequest(form: MoveFormInput, context: MoveContext): RoutedMoveRequest {
  const issues = moveFormIssues(form, context.design);
  if (issues.length) throw new Error(issues.join(" "));
  const baseMm = context.design.magnetWidthMm / 2;
  const fromMm = form.fromMm as number, toMm = form.toMm as number, durationS = form.durationS as number;
  const massG = form.loadMode === "design" ? context.design.massG : form.massG;
  const friction = form.loadMode === "design" ? context.design.frictionN : form.frictionN;
  if (!finite(massG) || !finite(friction)) throw new Error("The selected load is unavailable. Enter a custom mass and friction.");
  const step = context.timeStepS ?? form.advanced.timeStepS ?? automaticTimeStep(durationS);
  const profile: MoveProfile = {
    start_m: (baseMm + fromMm) / 1000,
    end_m: (baseMm + toMm) / 1000,
    initial_velocity_m_s: form.advanced.initialVelocityMPerS,
    final_velocity_m_s: form.advanced.finalVelocityMPerS,
    duration_s: durationS,
    travel_min_m: (baseMm + Math.min(fromMm, toMm)) / 1000,
    travel_max_m: (baseMm + Math.max(fromMm, toMm)) / 1000,
    moving_mass_kg: massG / 1000,
    mass_includes: massIncludes(form, context.design),
    coulomb_friction_n: friction,
    damping_n_s_per_m: form.advanced.dampingNsPerM,
    external_load_n: form.advanced.externalLoadN,
    time_step_s: step,
  };
  return {
    profile,
    control: "balanced_star_sinusoidal",
    electrical_angle_at_zero_rad: form.advanced.electricalAngleRad,
    phase_peak_limit_a: 0,
    source: { boundary: "stiff_dc_link", accepts_regeneration: form.advanced.acceptsRegeneration },
    additional_driver_loss_w: null,
    loss_model: null,
    force_positions: form.advanced.forcePositions,
  };
}

/** Full travel in mm for the design, used by the Full travel action and bounds. */
export function designFullTravelMm(config: { desired_travel_mm: number; active_area_length_mm: number }): number {
  return Math.max(0, config.desired_travel_mm > 0 ? config.desired_travel_mm : config.active_area_length_mm);
}

/**
 * Analysis-only copy. The saved design is never modified; the result records
 * that the stack was excluded through this copy.
 */
export function moveAnalysisConfig<T extends { backplane: unknown }>(config: T, excludeStack: boolean): T {
  return excludeStack && config.backplane ? { ...config, backplane: null } : config;
}
