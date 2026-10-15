/**
 * KiCad IPC contracts: connection state, write results, live board
 * diagnostics, write preconditions, and dry-run coil previews.
 *
 * Mirrors the Rust `BoardDiagnosticsIpc` / `CoilPreviewIpc` wire formats.
 * Field names stay snake_case here — exactly matching the Rust serde
 * `rename_all = "snake_case"` wire format — with no camelCase conversion.
 */

export interface KicadConnection {
  connected: boolean;
  board_name: string;
  copper_layers: number;
}

export interface KicadWriteResult {
  /** Number of items we sent to KiCad (tracks + vias). */
  items_attempted: number;
  /** Number of items KiCad accepted (ItemStatus.code == ISC_OK). */
  items_created: number;
  /**
   * Up to 1000 per-item failure messages from KiCad. Empty when
   * `items_created === items_attempted`. The full count of failures is
   * always `items_attempted - items_created` even if only a subset are
   * listed here.
   */
  failures: string[];
  /**
   * Summary of all rejection codes from KiCad, sorted by count descending.
   * Each entry is `[code, count]` where code is the ItemStatusCode
   * (1=OK, 2=invalid type, 3=existing, 4=non-existent, 5=immutable,
   * 7=invalid data). Empty when all items succeeded.
   */
  failure_summary: [number, number][];
  /**
   * Commit ID shown in KiCad's undo stack. `"atomic-commit"` on a real
   * write, `"(dry run - no commit)"` when written with `dry_run: true`.
   */
  commit_id: string;
}

/** Live snapshot of the open KiCad board (get_board_diagnostics). */
export interface BoardDiagnostics {
  /** File name of the open board, e.g. `"board.kicad_pcb"`. */
  board_name: string;
  /** Number of copper layers enabled on the board. */
  copper_layer_count: number;
  /** Bounding box of the board's edge cuts [mm]. 0 if not queryable. */
  board_x_min_mm: number;
  /** See board_x_min_mm. */
  board_x_max_mm: number;
  /** See board_x_min_mm. */
  board_y_min_mm: number;
  /** See board_x_min_mm. */
  board_y_max_mm: number;
  /** Net class names defined on the board. Empty if not queryable. */
  available_net_classes: string[];
}

/** Severity level for pre-condition warnings. */
export type PreconditionLevel = "info" | "warning" | "error";

/**
 * One warning / recommendation about the (config, board) pair, produced by
 * `validate_write_preconditions`. The UI renders `message` verbatim and
 * colour-codes by `level`; `field` optionally highlights the offending input.
 */
export interface PreconditionWarning {
  level: PreconditionLevel;
  field: string | null;
  message: string;
}

/** Per-layer breakdown of the coils that would be written. */
export interface CoilPreviewLayer {
  layer_idx: number;
  /** Number of phase coils on this layer. */
  phase_count: number;
  /** Total track segments (sum of `segments.length` across phases). */
  segment_count: number;
  /** Inter-layer vias on this layer. */
  via_count: number;
}

/**
 * Dry-run summary of what `write_coils_to_board` would produce (preview_coils).
 * Precondition warnings are not included — the UI calls
 * `validateWritePreconditions` separately.
 */
export interface CoilPreview {
  /** Number of layers the writer would iterate over. */
  num_layers: number;
  /** Routing-pattern id that produced the coil set. */
  pattern_id: string;
  /** Per-layer breakdown. */
  layers: CoilPreviewLayer[];
  /** Total track segments across all layers. */
  total_tracks: number;
  /** Total vias across all layers. */
  total_vias: number;
}