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
  /** Thickness of the magnetic material only (no adhesive or film) [m]. */
  thickness_m: number;
  /** Datasheet relative permeability. Absent or null = material default. */
  mu_r?: number | null;
  /** Datasheet saturation flux density [T]. Absent or null = default. */
  bsat_t?: number | null;
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

/** Magnetic state of one layer or the housing under the magnets. */
export interface MagneticState {
  mu_initial: number;
  /** Null for linear material. */
  bsat_t: number | null;
  /** Effective μr for the magnet field, with saturation. */
  mu_effective: number;
  /** Small-signal μr the coil sees under the magnets. */
  mu_incremental: number;
  /** Peak |B| of the linear model [T]: what it would take, not what happens. */
  linear_peak_b_t: number;
  /** Thickness-mean in-plane flux density of the linear model [T]. */
  linear_mean_b_t: number;
  /** Peak |B| at the solved, saturation-aware state [T]. */
  peak_b_t: number;
  /** Linear flux over the flux carried at Bsat. Above 1 = saturated. */
  flux_overload: number;
  /** Thickness of this material that carries the flux at Bsat [m]. */
  required_thickness_m: number | null;
  /** The same for sintered MnZn ferrite [m]. */
  mnzn_thickness_m: number | null;
}

/** Derived backplane quantities (present only when a backplane is set). */
export interface BackplaneAnalysis {
  stack_thickness_m: number;
  /** Composite reflection `R` at the PCB bottom for the magnets, saturated. */
  image_strength: number;
  /** `R` with every layer at its initial μr. */
  linear_image_strength: number;
  /** 2-D fundamental normal field of the bare array at the stack top [T]. */
  b0_t: number;
  /** Copper sheet count used for `inductance_factor`. */
  copper_layers: number;
  /** Height of each copper sheet above the PCB bottom [m], bottom first. */
  copper_depths_m: number[];
  /** Share of the winding length under the magnets. */
  magnet_coverage: number;
  /** Low-frequency inductance factor, with the magnets' bias. */
  inductance_factor: number;
  /** At standstill. Positive pulls the mover toward the stack [N]. */
  attraction_n: number;
  /** Peak flux density per layer at the solved state [T], same order as `layers`. */
  layer_peak_b_t: number[];
  housing_peak_b_t: number;
  /** Same order as `layers`. */
  layer_states: MagneticState[];
  housing_state: MagneticState | null;
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
  flex_ferrite: 0.1e-3,
};

/** Typical relative permeability (`LayerMaterial::mu_r`). */
export const LAYER_DEFAULT_MU_R: Record<LayerMaterial, number> = {
  fr4: 1,
  silicon_steel: 4000,
  mn_zn_ferrite: 2500,
  ni_zn_ferrite: 500,
  flex_ferrite: 130,
};

/** Typical saturation flux density [T] (`LayerMaterial::bsat_t`); null = non-magnetic. */
export const LAYER_DEFAULT_BSAT_T: Record<LayerMaterial, number | null> = {
  fr4: null,
  silicon_steel: 1.8,
  mn_zn_ferrite: 0.45,
  ni_zn_ferrite: 0.35,
  flex_ferrite: 0.25,
};

/** Largest accepted μr override (`MAX_MU_R`). */
export const BACKPLANE_MAX_MU_R = 1e6;

/** Largest accepted Bsat override [T] (`MAX_BSAT_T`). */
export const BACKPLANE_MAX_BSAT_T = 3;

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
