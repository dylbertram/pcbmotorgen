/**
 * DXF export contract. Spline-bearing drawings use DXF 2000 ASCII.
 */

/** Summary of the exported DXF file contents. */
export interface DxfExportSummary {
  /** Number of LINE entities (straight trace segments). */
  total_lines: number;
  /** Number of ARC entities (rounded corners / curves). */
  total_arcs: number;
  /** Number of editable SPLINE entities. Absent in older app results. */
  total_splines?: number;
  /** Number of CIRCLE entities (vias). */
  total_circles: number;
  /** Number of DXF layers defined. */
  layer_count: number;
}

/** Full ASCII DXF content and entity counts. */
export interface DxfExportResult {
  /** Complete DXF file content, ready to write to a `.dxf` file. */
  dxf_content: string;
  /** Human-readable summary for UI feedback. */
  summary: DxfExportSummary;
}

export interface CadPoint { x: number; y: number }
export interface CadRouteSegment {
  start: CadPoint; end: CadPoint; layer: number; net: string; is_active: boolean;
}
export interface CadRouteCurve {
  start: CadPoint; mid: CadPoint; end: CadPoint; layer: number; net: string; is_active: boolean;
}
export interface CadRouteSpline {
  degree: number;
  knots: number[];
  control_points: CadPoint[];
  weights?: number[];
  layer: number;
  net: string;
  is_active: boolean;
}
export interface CadVia {
  position: CadPoint; from_layer: number; to_layer: number; net: string;
}
export interface CadRoutingResult {
  format_version: number;
  segments: CadRouteSegment[];
  curves: CadRouteCurve[];
  splines?: CadRouteSpline[];
  vias: CadVia[];
}
/** Saved/imported centerline geometry. All coordinates and elevations are mm. */
export interface CadGeometry {
  routing: CadRoutingResult;
  /** Copper plane heights ordered bottom-to-top. */
  layer_z_mm: number[];
  trace_width_mm: number;
  /** Original DXF source layer → assigned coil/net. Absent in older projects. */
  source_layer_coils?: Record<string, string>;
}
export interface CadImportResult {
  geometry: CadGeometry;
  warnings: string[];
}
