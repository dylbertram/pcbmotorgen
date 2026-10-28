/** Geometry preparation only. No force result or implicit eligibility claim. */
export interface DcWindingGeometry {
  schema: "finite-dc-winding-geometry-v1";
  sim: Record<string, unknown>;
  routing: Record<string, unknown>;
  drive: Record<string, unknown>;
  geometry_hints: { layer_z_m: number[]; terminals: Record<string, unknown> };
  networks: Array<{
    net: string;
    node_count: number;
    terminal: number[];
    star: number[];
    edges: Array<{ a: number; b: number; r_ohm: number; geometry: Record<string, unknown> }>;
    rust_current_share: number[];
    rust_resistance_ohm: number;
  }>;
  finite_copper: {
    layers: Array<{ layer: number; centre_z_m: number; thickness_m: number; trace_width_m: number }>;
    via_drill_m: number;
    via_annular_ring_m: number;
    via_plating_m: number;
    resistivity_ohm_m: number;
    temperature_c: number;
  };
  coordinate_convention: string;
  scope: string;
}

/** Physical placement and finite return are explicit inputs, never UI defaults. */
export interface DcStudy {
  request_id: string;
  material_model: Record<string, unknown>;
  return_geometry: Record<string, unknown>;
  current_a: number;
  pm_offset_x_m: number;
  placement_acknowledged: boolean;
}

export interface DcJobStatus {
  request_id: string;
  job_id: string;
  state: "running" | "cancelling" | "completed" | "prepared" | "cancelled" | "timed_out" | "failed";
  operation?: "force" | "preparation" | "winding-field";
  winding_field?: DcWindingFieldResult | null;
  preparation?: DcPreparedSource | null;
  preparation_progress?: { stage: "geometry" | "source" | "active" | "passive" | "return" | "independent" | "rt0"; stage_timeout_s: number } | null;
  elapsed_seconds: number;
  evidence_directory: string;
  request_sha256: string;
  error: string | null;
  result: null | {
    status: "passed-fresh-qualified-geometry-dc-request-only";
    pm_array_force_n: [number, number, number];
    fresh_solution_sha256: string;
    input_request_sha256: string;
    qualified_case: DcQualifiedCaseIdentity;
    eligibility: { request_id: string; current_a: number; pm_offset_x_m: number; qualified_case: DcQualifiedCaseIdentity };
  };
}

export interface DcQualifiedCaseIdentity { case_id: string; label: string; audit_sha256: string }

export interface WindingFieldSampling { bounds_m: [[number, number], [number, number], [number, number]]; counts: [number, number, number] }
export interface DcWindingFieldResult {
  status: "sampled-qualified-finite-copper-winding-field-only";
  request_id: string;
  input_request_sha256: string;
  qualified_case: DcQualifiedCaseIdentity;
  sampling: WindingFieldSampling;
  loop_current_a: number;
  phase_currents_a: Record<string, number>;
  source_basis_sha256: string;
  source_translation_m: [number, number, number];
  source_elements: number;
  field: import("./simulationVisualization").FieldPreview;
  evidence_hashes: Record<string, string>;
}

/** Audited explicit placement/return for one registered case. Listing it is not admission. */
export interface DcQualifiedCase extends DcQualifiedCaseIdentity {
  declaration: { material_model: Record<string, unknown>; return_geometry: Record<string, unknown> };
}

export interface DcPreparedSource {
  status: "prepared-request-bound-current-source-not-qualified";
  input_request_sha256: string;
  request_id: string;
  source_status: "prepared-baseline-needs-refinement";
  force_status: "unqualified";
  remaining: string[];
  artifacts: Record<string, string>;
  evidence_hashes: Record<string, string>;
}

export interface DcCapability {
  available: boolean; reason?: string; scope?: string; qualified_cases?: DcQualifiedCase[];
  preparation_available?: boolean; preparation_reason?: string; preparation_timeout_s?: number;
  winding_field_available?: boolean;
}

/** Read-only applicability, never a numerical force or implicit preparation. */
export interface DcApplicability {
  schema: "finite-dc-applicability-v1";
  request_id: string;
  request_sha256: string;
  state: "qualified" | "preparation-required" | "unsupported";
  source_status: "qualified-exact-basis" | "unqualified";
  force_status: "qualified-sampled-states" | "unqualified";
  reason: string;
  qualified_case: DcQualifiedCaseIdentity | null;
}
