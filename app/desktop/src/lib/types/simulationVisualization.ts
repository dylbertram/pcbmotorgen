import type { LinearMotorConfig, DriveSettings, CadGeometry } from "../types";

export interface VisualizationInput {
  config: LinearMotorConfig;
  drive: DriveSettings;
  cadGeometry: CadGeometry | null;
  moverPositionM: number;
}
export type VisualizationMode = "off" | "fields" | "heat" | "both";
export interface VisualizationRequest {
  request_id: string;
  mover_position_m: number;
  bounds_m: [[number, number], [number, number], [number, number]];
  counts: [number, number, number];
  phase_peak_a: number;
  fields: boolean;
  heat: boolean;
  field_source?: "pm" | "coils" | "coils-and-pm";
  phase_angle_deg?: number;
}
export interface FieldPreview {
  method: "analytical-pm-only-xyz" | "qualified-finite-copper-winding-xyz" | "coil-plus-pm-free-space-superposition" | "routed-current-biot-savart-xyz" | "routed-current-plus-pm-xyz";
  scope: string;
  samples: { position_m: [number, number, number]; b_t: [number, number, number]; magnitude_t: number }[];
  magnets: { center_m: [number, number, number]; size_m: [number, number, number]; positive_z: boolean }[];
}
export interface CopperLossPreview {
  method: "native-resistor-graph-rms-i2r";
  scope: string;
  phase_peak_a: number;
  phase_rms_a: number;
  winding_temperature_c: number;
  total_loss_w: number;
  power_balance_relative_error: number;
  edges: { net: string; kind: "trace" | "via"; layers: [number, number]; points_m: [number, number, number][];
    loss_w: number; rms_current_a: number; resistance_ohm: number }[];
}
export interface VisualizationReport {
  schema: "simulation-visualization-v1";
  request_id: string;
  input_sha256: string;
  implementation_sha256: string;
  app_version: string;
  coordinate_convention: string;
  field: FieldPreview | null;
  heat: CopperLossPreview | null;
  heat_unavailable_reason: string | null;
}
