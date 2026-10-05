/** Native inductive position sensor generator and preview contracts (mm). */
export interface SensorConfig {
  lambda_mm: number;
  x_start_mm: number;
  amplitude_mm: number;
  turns: number;
  trace_width_mm: number;
  trace_gap_mm: number;
  min_clearance_mm: number;
  via_size_mm: number;
  arc_step_mm: number;
  chip_lead_in_mm: number;
  end_inset_mm: number;
  bulge_apex_offset_mm: number;
  tx_enabled: boolean;
  rx_tx_gap_mm: number;
  tx_strand_pitch_mm: number;
  tx_corner_offset_mm: number;
  tx_trace_width_mm: number;
  tx_via_size_mm: number;
}

export interface SensorPoint {
  x: number;
  y: number;
}

export interface SensorRouteSegment {
  start: SensorPoint;
  end: SensorPoint;
  layer: number;
  net: string;
  is_active: boolean;
}

export interface SensorVia {
  position: SensorPoint;
  from_layer: number;
  to_layer: number;
  net: string;
}

export interface SensorNetGeometry {
  name: string;
  segments: SensorRouteSegment[];
  vias: SensorVia[];
  trace_width_mm: number;
  via_size_mm: number;
}

export interface SensorGeometry {
  nets: SensorNetGeometry[];
  /** Prototype terminal coordinates, not physical KiCad pads. */
  terminal_markers: [string, SensorPoint][];
  board_bounds_mm: [number, number, number, number];
}

export const DEFAULT_SENSOR_CONFIG: SensorConfig = {
  lambda_mm: 120,
  x_start_mm: 0,
  amplitude_mm: 5.66,
  turns: 2,
  trace_width_mm: 0.15,
  trace_gap_mm: 0.4,
  min_clearance_mm: 0.2,
  via_size_mm: 0.6,
  arc_step_mm: 0.25,
  chip_lead_in_mm: 10,
  end_inset_mm: 1,
  bulge_apex_offset_mm: 2,
  tx_enabled: true,
  rx_tx_gap_mm: 4,
  tx_strand_pitch_mm: 0.45,
  tx_corner_offset_mm: 3,
  tx_trace_width_mm: 0.15,
  tx_via_size_mm: 0.6,
};
