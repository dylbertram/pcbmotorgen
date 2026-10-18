/**
 * Backplane and housing stack (t707) — IPC contract types.
 *
 * Mirrors `crates/pcbmotorgen-simulation/src/backplane/mod.rs` (snake_case
 * serde). The labels, typical values and limits below are copied from the
 * Rust source, which stays the source of truth; keep them in sync.
 */

export type LayerMaterial =
  | "fr4"
  | "silicon_steel"
  | "mn_zn_ferrite"
  | "ni_zn_ferrite"
  | "flex_ferrite";

export type HousingMaterial =
  | "aluminum6061"
  | "aluminum5052"
  | "steel1018"
  | "stainless304"
  | "stainless316"
  | "stainless430";

/** One layer of the backplane, ordered from the PCB downward. */
export interface BackplaneLayer {
  material: LayerMaterial;
  thickness_m: number;
}

/** Housing below the backplane, separated from it by an air gap. */
export interface HousingSpec {
  material: HousingMaterial;
  /** Housing wall thickness [m]. */
  thickness_m: number;
  /** Air gap between the bottom of the backplane and the housing [m]. */
  gap_m: number;
}

/** Backplane layers plus an optional housing. `null` = no backplane. */
export interface BackplaneStack {
  layers: BackplaneLayer[];
  housing: HousingSpec | null;
}

/** Derived backplane quantities (present only when a backplane is set). */
export interface BackplaneAnalysis {
  stack_thickness_m: number;
  /** Composite reflection `R` of stack and housing at the PCB bottom (0..1). */
  image_strength: number;
  /** 2-D fundamental normal field of the bare array at the stack top [T]. */
  b0_t: number;
  /** Copper sheet count used for `inductance_factor`. */
  copper_layers: number;
  /** Height of each copper sheet above the PCB bottom [m], bottom first. */
  copper_depths_m: number[];
  inductance_factor: number;
  /** Positive pulls the mover toward the stack [N]. */
  attraction_n: number;
  /** Peak flux density per layer [T], same order as `layers`. */
  layer_peak_b_t: number[];
  housing_peak_b_t: number;
  warnings: string[];
}

/** Silicon steel above this switching frequency is flagged [Hz]. */
export const SILICON_STEEL_PWM_LIMIT_HZ = 20e3;

/** Largest accepted thickness for one layer or the housing [m]. */
export const BACKPLANE_MAX_THICKNESS_M = 0.02;

export interface MaterialOption<T extends string> {
  value: T;
  label: string;
}

/** Layer materials in UI order (labels from `LayerMaterial`). */
export const LAYER_MATERIAL_OPTIONS: MaterialOption<LayerMaterial>[] = [
  { value: "fr4", label: "FR4" },
  { value: "silicon_steel", label: "Silicon steel" },
  { value: "mn_zn_ferrite", label: "Sintered MnZn ferrite" },
  { value: "ni_zn_ferrite", label: "Sintered NiZn ferrite" },
  { value: "flex_ferrite", label: "Flexible ferrite sheet" },
];

/** Thickness used when a layer is first added [m] (`LayerMaterial::default_thickness_m`). */
export const LAYER_DEFAULT_THICKNESS_M: Record<LayerMaterial, number> = {
  fr4: 1.6e-3,
  silicon_steel: 0.35e-3,
  mn_zn_ferrite: 2.0e-3,
  ni_zn_ferrite: 2.0e-3,
  flex_ferrite: 0.3e-3,
};

/** A new layer of `material` at its default thickness. */
export function newLayer(material: LayerMaterial): BackplaneLayer {
  return { material, thickness_m: LAYER_DEFAULT_THICKNESS_M[material] };
}

/** Housing materials in UI order (labels from `HousingMaterial`). */
export const HOUSING_MATERIAL_OPTIONS: MaterialOption<HousingMaterial>[] = [
  { value: "aluminum6061", label: "Aluminum 6061-T6" },
  { value: "aluminum5052", label: "Aluminum 5052-H32" },
  { value: "steel1018", label: "Mild steel 1018" },
  { value: "stainless304", label: "Stainless 304" },
  { value: "stainless316", label: "Stainless 316" },
  { value: "stainless430", label: "Stainless 430" },
];

/** Housing defaults used when the housing is first enabled [m]. */
export const DEFAULT_HOUSING: HousingSpec = {
  material: "aluminum6061",
  thickness_m: 3e-3,
  gap_m: 1e-3,
};

/** Human-readable label for a layer material. */
export function layerMaterialLabel(material: LayerMaterial): string {
  return LAYER_MATERIAL_OPTIONS.find((o) => o.value === material)?.label ?? material;
}
