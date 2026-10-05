//! KiCad IPC bridge commands: connection probing, board writes, board
//! diagnostics, write preconditions, and dry-run coil preview.

use crate::ipc::*;

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_export::proto::common::commands::{
    GetOpenDocuments, GetOpenDocumentsResponse, GetVersion, GetVersionResponse,
};
use pcbmotorgen_export::{BoardHandle, DocumentSpecifier, DocumentType, KiCadClient};
use pcbmotorgen_routing::{generate_sensor, SensorConfig};

// ===========================================================================
// KiCad IPC commands (Phase 7)
// ===========================================================================

/// KiCad connection result.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct KicadConnectionResult {
    pub connected: bool,
    pub board_name: String,
    pub copper_layers: u32,
}

/// KiCad write result.
///
/// `commit_id` is `"atomic-commit"` on a real write and
/// `"(dry run - no commit)"` when `write_coils_to_board` was called with
/// `dry_run = true`. In dry-run mode, `items_created` is always 0 and
/// `items_attempted` is the number of items the writer *would* have created
/// (the UI uses this to show "N items would be written" before the real
/// write).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct KicadWriteResult {
    pub items_attempted: u32,
    pub items_created: u32,
    /// Up to 1000 per-item failure messages from KiCad. Empty when
    /// `items_created == items_attempted`. The full count of failures is
    /// always `items_attempted - items_created` even if only a subset are
    /// listed here.
    /// Always empty in dry-run mode (no items are actually created).
    pub failures: Vec<String>,
    /// Summary of all rejection codes from KiCad, sorted by count descending.
    /// Each entry is `(code, count)` where `code` is the
    /// `ItemStatusCode` (1=OK, 2=invalid type, 3=existing, 4=non-existent,
    /// 5=immutable, 7=invalid data). Empty when all items succeeded.
    pub failure_summary: Vec<(i32, u32)>,
    /// Commit ID shown in KiCad's undo stack. `"atomic-commit"` on a real
    /// write, `"(dry run - no commit)"` on a dry run.
    pub commit_id: String,
}

/// KiCad ping result.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct KicadPingResult {
    pub ok: bool,
    pub version: String,
}

/// Type URL for the `GetOpenDocuments` command.
const GET_OPEN_DOCUMENTS_TYPE_URL: &str =
    "type.googleapis.com/kiapi.common.commands.GetOpenDocuments";

/// Type URL for the `GetVersion` command.
const GET_VERSION_TYPE_URL: &str = "type.googleapis.com/kiapi.common.commands.GetVersion";

/// Query the first open PCB document from KiCad.
///
/// Sends a `GetOpenDocuments` command with `DOCTYPE_PCB` and returns the
/// first `DocumentSpecifier` from the response, or an error if no board is
/// open.
fn get_open_pcb_document(client: &mut KiCadClient) -> Result<DocumentSpecifier, String> {
    let cmd = GetOpenDocuments {
        r#type: DocumentType::DoctypePcb as i32,
    };
    let resp: GetOpenDocumentsResponse = client
        .send(GET_OPEN_DOCUMENTS_TYPE_URL, &cmd)
        .map_err(|e| e.to_string())?;
    resp.documents
        .into_iter()
        .next()
        .ok_or_else(|| "No PCB document open in KiCad".to_string())
}

/// Connect to KiCad and query the open board's name and copper layer count.
///
/// Returns `connected: false` (not an `Err`) if the connection fails, so the
/// frontend can show a graceful "not connected" state.
#[tauri::command]
pub async fn connect_kicad() -> Result<KicadConnectionResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut client = KiCadClient::new(None, None, 2000);
        if let Err(e) = client.connect() {
            return Ok(KicadConnectionResult {
                connected: false,
                board_name: format!("Error: {}", e),
                copper_layers: 0,
            });
        }

        let (board_name, copper_layers) = match get_open_pcb_document(&mut client) {
            Ok(doc) => {
                let mut board = BoardHandle::new(&mut client, doc);
                let name = board.name().unwrap_or_else(|_| "(unknown)".to_string());
                let layers = board.get_copper_layer_count().unwrap_or(0);
                (name, layers)
            }
            Err(e) => (format!("No board open: {}", e), 0),
        };

        Ok(KicadConnectionResult {
            connected: true,
            board_name,
            copper_layers,
        })
    })
    .await
    .map_err(|e| format!("connect_kicad worker failed: {e}"))?
}

/// Generate coils from the config and write them to the open KiCad board.
///
/// Connects to KiCad, queries the open PCB, generates geometry using the
/// selected routing pattern (which owns its layer/net semantics), and writes
/// the items atomically via `BoardHandle::write_coils` (single Ctrl+Z undo
/// step). Routing geometry reaches this writer in millimetres and is converted
/// to KiCad nanometres by the writer.
///
/// When `dry_run` is `true`, the items are still generated and counted but
/// no commit is sent to KiCad — the returned `KicadWriteResult` has
/// `commit_id = "(dry run - no commit)"` and `items_created = 0`. This is
/// the backend half of the UI's "Preview" workflow; the
/// `preview_coils` command is the more detailed dry-run that also returns
/// per-layer tallies.
///
/// Uses `config.num_layers` (not `max_layers`) for the layer count, since the
/// user may select fewer layers than the maximum.
#[tauri::command]
pub async fn write_coils_to_board(
    config: LinearMotorConfigIpc,
    dry_run: bool,
) -> Result<KicadWriteResult, String> {
    let core = config.to_core();
    tauri::async_runtime::spawn_blocking(move || {
        // Round-robin phase→layer assignment (one phase per layer).
        // See the function-level doc for the full rationale (Bug 16 fix).
        let coils = core.generate_coils_for_board();

        let mut client = KiCadClient::new(None, None, 5000);
        client
            .connect()
            .map_err(|e| format!("KiCad connection failed: {e}"))?;

        let doc = get_open_pcb_document(&mut client)
            .map_err(|e| format!("No open PCB to write to: {e}"))?;

        let mut board = BoardHandle::new(&mut client, doc);

        if dry_run {
            // No IPC commit / create; just count the items that would have
            // been written. The connection establishment above is wasted in
            // dry-run mode but harmless (no KiCad commands are sent).
            let result = board
                .write_coils_dry_run(
                    &coils,
                    core.num_layers,
                    &core.design_rules(),
                    core.active_area_length_m * 1e3,
                )
                .map_err(|e| format!("KiCad write_coils_dry_run failed: {e}"))?;
            return Ok(KicadWriteResult {
                items_attempted: result.items_attempted,
                items_created: result.items_created,
                failures: result.failures,
                failure_summary: result.failure_summary,
                commit_id: "(dry run - no commit)".to_string(),
            });
        }

        let result = board
            .write_coils(
                &coils,
                core.num_layers,
                &core.design_rules(),
                core.active_area_length_m * 1e3,
            )
            .map_err(|e| format!("KiCad write_coils failed: {e}"))?;

        Ok(KicadWriteResult {
            items_attempted: result.items_attempted,
            items_created: result.items_created,
            failures: result.failures,
            failure_summary: result.failure_summary,
            commit_id: "atomic-commit".to_string(),
        })
    })
    .await
    .map_err(|e| format!("write_coils_to_board worker failed: {e}"))?
}

/// Generate and write sensor copper to an open two-layer KiCad board.
/// The dry-run form validates the board and returns a track/via item count
/// without committing anything. Sensor terminal coordinates never become pads.
#[tauri::command]
pub async fn write_sensor_to_board(
    config: SensorConfig,
    dry_run: bool,
) -> Result<KicadWriteResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let geometry = generate_sensor(&config)?;
        let rules = DesignRules {
            min_trace_mm: config.trace_width_mm,
            min_space_mm: config.min_clearance_mm,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.2,
        };
        let mut client = KiCadClient::new(None, None, 5000);
        client
            .connect()
            .map_err(|e| format!("KiCad connection failed: {e}"))?;
        let doc = get_open_pcb_document(&mut client)
            .map_err(|e| format!("No open PCB to write to: {e}"))?;
        let mut board = BoardHandle::new(&mut client, doc);
        let copper_layers = board
            .get_copper_layer_count()
            .map_err(|e| format!("Could not read KiCad copper layers: {e}"))?;
        if copper_layers != 2 {
            return Err(format!(
                "The induction sensor requires a two-layer KiCad board; this board has {copper_layers} copper layers"
            ));
        }
        let result = board
            .write_sensor_geometry(&geometry, &rules, dry_run)
            .map_err(|e| format!("KiCad sensor write failed: {e}"))?;
        Ok(KicadWriteResult {
            items_attempted: result.items_attempted,
            items_created: result.items_created,
            failures: result.failures,
            failure_summary: result.failure_summary,
            commit_id: if dry_run {
                "(dry run - no commit)".into()
            } else {
                "atomic-commit".into()
            },
        })
    })
    .await
    .map_err(|e| format!("write_sensor_to_board worker failed: {e}"))?
}

// ===========================================================================
// Board diagnostics (Phase 7 — robust KiCad connection, WP-1.B)
// ===========================================================================

/// Get the current board's diagnostics (layer count, edge cuts, net classes).
///
/// Connects to KiCad, queries the open PCB, and returns a `BoardDiagnosticsIpc`
/// snapshot. The edge-cut bounding box and net-class list are not yet
/// queryable via the KiCad 10 IPC, so they default to `0.0` / empty — a
/// `// TODO` in the core marks the spot for the real query.
#[tauri::command]
pub async fn get_board_diagnostics() -> Result<BoardDiagnosticsIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut client = KiCadClient::new(None, None, 5000);
        client
            .connect()
            .map_err(|e| format!("KiCad connection failed: {e}"))?;
        let doc = get_open_pcb_document(&mut client).map_err(|e| format!("No open PCB: {e}"))?;
        let mut board = BoardHandle::new(&mut client, doc);
        pcbmotorgen_export::get_board_diagnostics(&mut board)
            .map(|d| BoardDiagnosticsIpc::from_core(&d))
            .map_err(|e| format!("get_board_diagnostics failed: {e}"))
    })
    .await
    .map_err(|e| format!("get_board_diagnostics worker failed: {e}"))?
}

/// Validate the config against the current board and return a list of
/// warnings/recommendations. Pure (no IPC); just runs the rules.
///
/// The frontend typically calls `get_board_diagnostics` first, then passes
/// the result back into this command before showing the "Write to Board"
/// button. The returned `PreconditionWarningIpc` entries are colour-coded
/// by `level` (info / warning / error) and may include a `field` key the
/// UI uses to highlight the offending input control.
#[tauri::command]
pub async fn validate_write_preconditions(
    config: LinearMotorConfigIpc,
    diagnostics: BoardDiagnosticsIpc,
) -> Result<Vec<PreconditionWarningIpc>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let core = config.to_core();
        let diags_core = pcbmotorgen_export::BoardDiagnostics {
            board_name: diagnostics.board_name,
            copper_layer_count: diagnostics.copper_layer_count,
            board_x_min_mm: diagnostics.board_x_min_mm,
            board_x_max_mm: diagnostics.board_x_max_mm,
            board_y_min_mm: diagnostics.board_y_min_mm,
            board_y_max_mm: diagnostics.board_y_max_mm,
            available_net_classes: diagnostics.available_net_classes,
        };
        let warnings = pcbmotorgen_export::validate_write_preconditions(
            &core.design_rules(),
            core.num_layers,
            core.active_area_length_m,
            core.board_width_m,
            &diags_core,
        );
        Ok(warnings
            .iter()
            .map(PreconditionWarningIpc::from_core)
            .collect())
    })
    .await
    .map_err(|e| format!("validate_write_preconditions worker failed: {e}"))?
}

/// Preview the coil geometry that WOULD be written (no IPC, no KiCad
/// roundtrip). Pure dry-run: builds the same `PhaseCoil` set the writer
/// would produce, and returns a per-layer tally (phase count, track count,
/// via count) plus the routing `pattern_id` and any pre-condition warnings.
///
/// The full `PhaseCoil` geometry is *not* carried on the wire here — the
/// UI calls `generate_coils` separately if it needs the raw segments.
#[tauri::command]
pub async fn preview_coils(config: LinearMotorConfigIpc) -> Result<CoilPreviewIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let core = config.to_core();
        let num_layers = config.num_layers;
        let coils = core.generate_coils_for_board();
        match pcbmotorgen_export::preview_coils(&coils, num_layers) {
            Ok(p) => Ok(CoilPreviewIpc::from_core(&p)),
            Err(e) => Err(format!("preview_coils failed: {e}")),
        }
    })
    .await
    .map_err(|e| format!("preview_coils worker failed: {e}"))?
}

/// Ping KiCad and return the version string.
///
/// Returns `ok: false` (not an `Err`) if the connection fails, so the
/// frontend can show a graceful "not connected" state.
#[tauri::command]
pub async fn ping_kicad() -> Result<KicadPingResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut client = KiCadClient::new(None, None, 1000);
        if client.connect().is_err() {
            return Ok(KicadPingResult {
                ok: false,
                version: String::new(),
            });
        }

        let version = match client
            .send::<GetVersion, GetVersionResponse>(GET_VERSION_TYPE_URL, &GetVersion {})
        {
            Ok(resp) => resp
                .version
                .map(|v| v.full_version)
                .unwrap_or_else(|| "connected".to_string()),
            Err(_) => "connected".to_string(),
        };

        Ok(KicadPingResult { ok: true, version })
    })
    .await
    .map_err(|e| format!("ping_kicad worker failed: {e}"))?
}
