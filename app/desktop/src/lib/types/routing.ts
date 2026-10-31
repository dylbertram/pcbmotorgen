/**
 * Routing-pattern plugin contract: catalog metadata, user-editable
 * parameter definitions, installed plugins, and DRC interference results.
 */

export type WindingConnection = "star" | "delta" | "closed";

/** Optional generator contract. The default matches absent legacy parameters. */
export type GeneratorEndType =
  | { kind: "fixed"; connection: WindingConnection }
  | { kind: "parameter"; key: string; default: number; options: { value: number; connection: WindingConnection }[] };

/** One selectable coil routing pattern offered by the backend. */
export interface RoutingPatternInfo {
  /** Stable machine id, e.g. `"infinity-braid"`. Stored on the config as
   *  `routing_pattern`. */
  id: string;
  /** Human-friendly label shown in the UI, e.g. "Infinity Braid (pcbBraid)". */
  display_name: string;
  /**
   * Pattern-declared supported layer range (mirrored backend metadata;
   * null/absent = unconstrained). The UI only CONSTRAINS ITS INPUTS with
   * these — the routing crate re-validates authoritatively at generate time.
   */
  min_layers?: number | null;
  max_layers?: number | null;
  /** Layer count must be a multiple of this (e.g. 2 = even-only stacks). */
  layers_multiple_of?: number | null;
  end_type?: GeneratorEndType | null;
}

/** Routing-pattern parameter value type (int = whole number, float = real). */
export type ParamType = "int" | "float";

/** One user-editable parameter exposed by a routing-pattern plugin. */
export interface RoutingParamDef {
  key: string;
  label: string;
  description: string;
  param_type: ParamType;
  default: number;
  min?: number;
  max?: number;
  step?: number;
  /**
   * "Valid values are multiples of this" constraint declared by the pattern
   * (null/absent = unconstrained). Mirrored onto the input's step + invalid
   * state so an incorrect value cannot be submitted; the routing crate
   * re-validates authoritatively at generate time.
   */
  multiple_of?: number | null;
  /**
   * Closed set of allowed values declared by the pattern (absent/empty = any
   * value in range). When present the UI renders a choice; the routing crate
   * rejects any other value at generate time.
   */
  options?: RoutingParamOption[];
}

/** One allowed value of a choice parameter. */
export interface RoutingParamOption {
  value: number;
  label: string;
}

/** One installed routing-pattern plugin (from the persistent store). */
export interface InstalledPlugin {
  id: string;
  kind: "native" | "python";
  display_name: string;
  author: string;
  version: string;
  description: string;
}

/** One DRC interference violation reported by the core (clearance checks). */
export interface InterferenceViolation {
  layer: number;
  net_a: string;
  net_b: string;
  /** `"clearance"` | `"via_clearance"` */
  kind: string;
  /** Measured gap [mm]. */
  gap_mm: number;
  message: string;
}
