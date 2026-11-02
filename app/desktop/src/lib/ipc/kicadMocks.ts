import type {
  BoardDiagnostics,
  CoilPreview,
  KicadConnection,
  KicadWriteResult,
  LinearMotorConfig,
} from "../types";

/** Fixed browser-only board snapshot; no real KiCad board is queried. */
export function mockBoardDiagnostics(): BoardDiagnostics {
  return {
    board_name: "(mock board — backend not connected)",
    copper_layer_count: 4,
    board_x_min_mm: 0.0,
    board_x_max_mm: 0.0,
    board_y_min_mm: 0.0,
    board_y_max_mm: 0.0,
    available_net_classes: [],
  };
}

/** No board is open in browser mode. */
export function mockKicadConnection(): KicadConnection {
  return { connected: false, board_name: "(not connected)", copper_layers: 0 };
}

/** Make the absence of a backend visible rather than reporting a successful write. */
export function mockKicadWrite(): KicadWriteResult {
  return {
    items_attempted: 0,
    items_created: 0,
    failures: ["Backend not available — open the Tauri shell to write to KiCad"],
    failure_summary: [],
    commit_id: "",
  };
}

/** Approximate per-layer counts for the browser-only preview card. */
export function mockPreviewCoils(config: LinearMotorConfig): CoilPreview {
  const numLayers = Math.max(1, config.num_layers);
  // Match the mock coil shape: active conductors plus end-turns.
  const segsPerLayer = Math.max(2, config.magnet_count * 2) * 2 - 1;
  const totalTracks = segsPerLayer * config.phases * numLayers;
  const layers = Array.from({ length: numLayers }, (_, i) => ({
    layer_idx: i,
    phase_count: config.phases,
    segment_count: segsPerLayer * config.phases,
    via_count: 0,
  }));
  return {
    num_layers: numLayers,
    pattern_id: config.routing_pattern,
    layers,
    total_tracks: totalTracks,
    total_vias: 0,
  };
}
