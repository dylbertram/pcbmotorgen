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
