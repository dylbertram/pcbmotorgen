# pcbmotorgen-export — Public API reference

`pcbmotorgen-export` is the single Rust crate that turns the routing crate's
generic coil geometry into **physical output artifacts**. It is the successor
to the former `pcbmotorgen-dxf` and `pcbmotorgen-kicad` crates, which are now
one crate.

Everything below is a **public, stable API** intended for external consumers
(such as the `pcbmotorgen` Tauri host). Both exporter families consume
[`pcbmotorgen-routing`] types — [`PhaseCoil`], [`RoutingResult`] — plus the
[`DesignRules`] sizing snapshot from [`pcbmotorgen-dfm`] (kata 0rgs), and use
**millimetres** as the canonical unit.

---

## Adding the dependency

```toml
[dependencies]
pcbmotorgen-export = { path = "crates/pcbmotorgen-export" }
pcbmotorgen-dfm    = { path = "crates/pcbmotorgen-dfm" }   # DesignRules
# or, inside the workspace:
pcbmotorgen-export = { workspace = true }
pcbmotorgen-dfm    = { workspace = true }
```

```rust
use pcbmotorgen_export::*;          // shorthand for the re-exports below
use pcbmotorgen_export::proto;      // full KiCad IPC protobuf type tree
```

---

## 1. DXF exporter (pure, no IPC)

Two entry points; both return a complete DXF R12 ASCII string.

### `routing_result_to_dxf`

```rust
pub fn routing_result_to_dxf(
    result: &RoutingResult,     // routing geometry from any pattern plugin
    rules: &DesignRules,        // via pad diameter derived from min_via_drill + annular ring
    active_area_length_mm: f64, // used only when centre_x = true
    centre_x: bool,             // shift x by -active_area_length_mm/2 to straddle x=0
) -> String
```

Produces a DXF file with `HEADER` (`$INSUNITS = 4`, mm), `TABLES`
(layer definitions), `ENTITIES`, and `EOF`.

| Routing element | DXF entity | Layer                                                  |
| --------------- | ---------- | ------------------------------------------------------ |
| `RouteSegment`  | `LINE`     | `L<layer>_<net>`                                       |
| `RouteCurve`    | `ARC`      | `L<layer>_<net>` (falls back to `LINE` when collinear) |
| `Via`           | `CIRCLE`   | `Via`                                                  |
| `IoTrace`       | `LINE`     | `L<layer>_<net>` (IO fanout traces emit as normal tracks) |
| `IoPad`         | `CIRCLE` / 4×`LINE` | `IO_Pad` (circle for round pads, closed rectangle outline for rectangular pads) |

Payloads **without** IO elements produce byte-identical output to previous
releases — the IO emission loops are no-ops when the additive
`io_pads` / `io_traces` fields are empty. `tests/golden_compat.rs` pins this
with goldens captured from the pre-IO implementation.

### `phase_coils_to_dxf`

```rust
pub fn phase_coils_to_dxf(
    coils: &[PhaseCoil],        // per-phase simplified coil model
    num_layers: u32,            // used to derive via from/to layers
    rules: &DesignRules,
    active_area_length_mm: f64, // always centres on x=0 (centre_x=true)
) -> String
```

Reconstructs a `RoutingResult` from the `PhaseCoil` presentation model and
delegates to `routing_result_to_dxf` with centring enabled.

### Example

```rust
use pcbmotorgen_export::phase_coils_to_dxf;
use pcbmotorgen_dfm::DesignRules;

let dxf = phase_coils_to_dxf(&coils, num_layers, &DesignRules::default(), 48.0);
std::fs::write("coils.dxf", dxf)?;
```

---

## 2. KiCad 10 IPC adapter

### 2.1 Client — `KiCadClient`

```rust
// Construction
pub fn new(socket_path: Option<&str>, client_name: Option<&str>, timeout_ms: u32) -> Self
pub fn with_transport(transport: Box<dyn KicadTransport>, client_name: Option<&str>, timeout_ms: u32) -> Self

// Lifecycle
pub fn connect(&mut self) -> Result<(), KiCadError>
pub fn connected(&self) -> bool
pub fn kicad_token(&self) -> &str
pub fn client_name(&self) -> &str

// Core RPC
pub fn send<Cmd, Resp>(&mut self, type_url: &str, command: &Cmd) -> Result<Resp, KiCadError>
//   where Cmd: prost::Message, Resp: prost::Message + Default
```

Connection defaults: socket `ipc:///tmp/kicad/api.sock` (or
`KICAD_API_SOCKET` env var; Windows `%TEMP%\kicad\api.sock`; flatpak path
auto-detected), token from `KICAD_API_TOKEN` env var (auto-negotiated on first
reply), random client name `pcbmotorgen-<8 chars>`.

`send` packs the command into a protobuf `Any`, wraps it in an `ApiRequest`
envelope, sends over the transport, decodes the `ApiResponse`, checks the API
status (`AS_OK`), caches the token, and unpacks the reply into `Resp`.

The transport is abstracted behind the [`KicadTransport`] trait:

- `nng::Socket` (`Req0`) — production transport (default).
- [`MockTransport`] — records sent bytes, returns canned replies (testing).

### 2.2 Errors — `KiCadError`

```rust
pub enum KiCadError {
    Connection(String),                 // socket unreachable / dial / send / recv
    Api { code: i32, message: String }, // non-OK ApiStatusCode
    Protocol(String),                   // encode/decode/packing failure
    NotConnected,                       // must connect() first
}
```

Implements `Display`, `Error`, and `From<std::io::Error>`.

### 2.3 Board items — `coils_to_board_items` (pure)

```rust
pub fn coils_to_board_items(
    coils: &[PhaseCoil],
    num_layers: u32,          // the ACTUAL board layer count (not a DFM ceiling)
    rules: &DesignRules,
    active_area_length_mm: f64,
) -> Vec<prost_types::Any>    // Track / Arc / Via messages ready for CreateItems
```

Pure converter, no socket I/O:

- each `CoilSegment` → `Track` (width from `rules.trace_width_mm`; the
  `min_trace_mm` floor is a separate DRC input; layer via
  `layer_idx_to_board_layer`, net `/<phaseName>`);
- each `corner_arc` → `Arc`;
- each `center_via_position` → through `Via` (drill + pad from design rules,
  pad stack layer set matching the board, non-sentinel enum values);
- all x-coords shifted by `-active_area_length_mm/2` so the coil straddles x=0;
- units converted mm → nm (`mm_to_nm`).

The additive counterpart for the routing result's IO elements (kata htcq —
connector/IC pads + terminal fanout traces; see the routing API §5.3).
Since kata xa0f these elements are typically **generated host-side** by the
routing crate's opt-in `generate_routing_*_with_io` entry points — the
writers consume them unchanged, so generated fanouts round-trip through this
crate's KiCad and DXF paths exactly like pattern-declared ones (see
`tests/io_export_roundtrip.rs`):

```rust
pub fn io_elements_to_board_items(
    result: &RoutingResult,     // reads result.io_pads / result.io_traces only
    num_layers: u32,            // the ACTUAL board layer count
    rules: &DesignRules,        // trace width for fanout tracks (sizing authority)
    active_area_length_mm: f64, // same centering shift as coils_to_board_items
) -> Vec<prost_types::Any>      // FootprintInstance / Track messages ready for CreateItems
```

- one `FootprintInstance` per `io_pads[]` entry: a single-pad `Footprint`
  (`pcbmotorgen:io_pad_<net>_<n>`, `not_in_schematic`, excluded from the BOM)
  whose `Pad` maps the declared stack — `PadType` from the pad kind
  (`smd` → `PT_SMD`, `tht` → `PT_PTH`, `board_edge` → `PT_EDGE_CONNECTOR`),
  a `PstNormal` padstack (single `PadStackLayer` with the `ALL_LAYERS`
  sentinel, circle shape for equal x/y sizes, rectangle otherwise), the
  drill for THT pads, and the pad's copper layer set (declared `layers`
  mapped onto the board, or the kind's default set when empty: all copper
  layers for THT, `F_Cu` for surface pads);
- one `Track` per `io_traces[]` entry — IO fanout traces emit as normal
  tracks, sized from `rules.trace_width_mm`;
- a result without IO elements produces an empty item list.

**Sizing authority:** the writer reads pad sizes from the declared elements
and trace width from `DesignRules` — it never decides dimensions.

### 2.4 High-level board handle — `BoardHandle`

Borrows the `KiCadClient` mutably and is bound to a target
[`DocumentSpecifier`].

```rust
pub struct BoardHandle<'a> { /* private */ }

impl<'a> BoardHandle<'a> {
    pub fn new(client: &'a mut KiCadClient, document: DocumentSpecifier) -> Self;
    pub fn document(&self) -> &DocumentSpecifier;
    pub fn name(&self) -> Result<String, KiCadError>;            // "board.kicad_pcb"
    pub fn get_copper_layer_count(&mut self) -> Result<u32, KiCadError>;
    // Diagnostics queries (kata ze9f):
    pub fn get_net_names(&mut self) -> Result<Vec<String>, KiCadError>;
    pub fn get_effective_net_classes(&mut self, net_names: &[String]) -> Result<Vec<String>, KiCadError>;
    pub fn get_edge_cut_bbox_mm(&mut self) -> Result<Option<BoardBBoxMm>, KiCadError>;
    pub fn get_board_origin(&mut self, origin_type: BoardOriginType) -> Result<Vector2, KiCadError>;
    pub fn write_coils(
        &mut self,
        coils: &[PhaseCoil], num_layers: u32, rules: &DesignRules, active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError>;                   // real write
    pub fn write_coils_dry_run(
        &mut self,
        coils: &[PhaseCoil], num_layers: u32, rules: &DesignRules, active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError>;                   // no IPC traffic
    pub fn write_io_elements(
        &mut self,
        result: &RoutingResult, num_layers: u32, rules: &DesignRules, active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError>;                   // IO pads + fanout traces, atomic
    pub fn write_io_elements_dry_run(
        &mut self,
        result: &RoutingResult, num_layers: u32, rules: &DesignRules, active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError>;                   // no IPC traffic
}
```

The diagnostics queries (added in kata ze9f):

- `get_net_names` — `GetNets` (no netclass filter); nets with an empty name
  are skipped.
- `get_effective_net_classes` — `GetNetClassForNets`, returning the distinct,
  sorted names of the net classes **effectively in use** by the given nets. A
  net's effective class is KiCad's merged/composite class when the net belongs
  to several classes; composite classes have no name of their own, so their
  constituent explicit class names are surfaced. This is *not* the project's
  global netclass list — the IPC has no such command, and classes with no nets
  assigned do not appear here.
- `get_edge_cut_bbox_mm` — `GetItems` restricted to `KOT_PCB_SHAPE`, filtered
  client-side to the `Edge.Cuts` layer, with the axis-aligned bounding box
  computed client-side in exact geometry (arc axis extremes and bezier
  interior extrema included). The IPC has no `GetBoardBounds` command, so this
  derivation is the real source of the diagnostics bounding box. Returns
  `Ok(None)` when the board has no edge-cut graphics. Edge-cut graphics inside
  footprints are not returned by `GetItems` at the top level and are not part
  of the box.
- `get_board_origin` — `GetBoardOrigin` for the grid (`BotGrid`) or
  drill/place-file (`BotDrill`) origin point. This is a single *point*, not
  board bounds, and no `BoardDiagnostics` field represents one; it is exposed
  for callers that need the origin and is deliberately not folded into the
  edge-cut bounding box.

```rust
pub struct BoardBBoxMm {          // result of get_edge_cut_bbox_mm
    pub x_min_mm: f64, pub y_min_mm: f64,
    pub x_max_mm: f64, pub y_max_mm: f64,
}
```

`WriteCoilsResult`:

```rust
pub struct WriteCoilsResult {
    pub items_attempted: u32,
    pub items_created: u32,
    pub failures: Vec<String>,            // first 1000 rejection messages, verbatim
    pub failure_summary: Vec<(i32, u32)>, // (ItemStatus.code, count) sorted by count desc
}
```

Note: the outer request may succeed even if individual items were rejected;
per-item rejections surface in `failures` / `failure_summary`.

### 2.5 Atomic commit — `Commit`

All items created between `Commit::begin` and `Commit::end` appear as a single
Ctrl+Z undo step in the KiCad editor.

```rust
pub struct Commit<'a> { /* private */ }

impl<'a> Commit<'a> {
    pub fn begin(client: &'a mut KiCadClient) -> Result<Self, KiCadError>;
    pub fn create_items(&mut self, items: &[Any], document: &DocumentSpecifier)
        -> Result<CreateItemsResponse, KiCadError>;
    pub fn end(self) -> Result<(), KiCadError>;   // CMA_COMMIT, message "pcbmotorgen coil generation"
    pub fn abort(self) -> Result<(), KiCadError>; // CMA_DROP
    pub fn commit_id(&self) -> &Kiid;
}
```

### 2.6 Board diagnostics & pre-write checks (Phase 7)

```rust
// Live snapshot of the open board (contacts KiCad):
pub fn get_board_diagnostics(board: &mut BoardHandle) -> Result<BoardDiagnostics, KiCadError>;

pub struct BoardDiagnostics {
    pub board_name: String,
    pub copper_layer_count: u32,
    pub board_x_min_mm: f64, pub board_x_max_mm: f64,
    pub board_y_min_mm: f64, pub board_y_max_mm: f64,
    pub available_net_classes: Vec<String>,
    // helpers: board_width_mm(), board_height_mm()
}

// Pure, no IPC — compare generation spec against live board:
pub fn validate_write_preconditions(
    rules: &DesignRules,
    num_layers: u32,
    active_area_length_m: f64,
    board_width_m: f64,
    diagnostics: &BoardDiagnostics,
) -> Vec<PreconditionWarning>;

pub struct PreconditionWarning {
    pub level: PreconditionLevel,  // Info | Warning | Error
    pub field: Option<String>,     // e.g. "num_layers", "active_area_length_m"
    pub message: String,
}

// Pure dry-run preview of what write_coils_to_board would write:
pub fn preview_coils(coils: &[PhaseCoil], num_layers: u32)
    -> Result<CoilPreview, String>;

pub struct CoilPreview {
    pub num_layers: u32,
    pub pattern_id: String,
    pub layers: Vec<CoilPreviewLayer>,
    pub total_tracks: u32,
    pub total_vias: u32,
    pub coils: Vec<PhaseCoil>,
}
pub struct CoilPreviewLayer {
    pub layer_idx: u32,
    pub board_layer: i32,   // KiCad BoardLayer enum value (e.g. BL_BCU / BL_FCU)
    pub phase_count: u32,
    pub segment_count: u32,
    pub via_count: u32,
}
```

#### Diagnostics field provenance (kata ze9f)

Since kata ze9f the snapshot is real per-field. It is **best-effort**: each
backing query degrades to its neutral default on failure (unsupported
command, empty board) without failing the whole call.

| Field | Backing IPC command(s) | Degraded default | Notes |
| ----- | ---------------------- | ---------------- | ----- |
| `board_name` | document specifier (no IPC) | `""` | always real |
| `copper_layer_count` | `GetBoardEnabledLayers` | `0` | always real |
| `board_x/y_min/max_mm` | `GetItems` (`KOT_PCB_SHAPE`) → `Edge.Cuts` filter → client-side exact bbox | `0.0` | no `GetBoardBounds` command in the KiCad IPC; zeros when the board has no edge-cut graphics or the query fails |
| `available_net_classes` | `GetNets` + `GetNetClassForNets` | `[]` | **effective per-net classes** (sorted, distinct) — not the project's global netclass list (no IPC command for that); classes with no nets assigned do not appear; composite classes surface their constituents |

`GetBoardOrigin` also exists in the IPC but returns a single grid/drill origin
*point*, not bounds; it is exposed via `BoardHandle::get_board_origin` and is
deliberately not mixed into the edge-cut bounding box.

### 2.7 Layer map / units — `layer_map`

```rust
pub fn layer_idx_to_board_layer(idx: u32, total_layers: u32) -> BoardLayer;
//   0 → B_Cu, total-1 → F_Cu, inner → In{n}_Cu
pub fn mm_to_nm(mm: f64) -> i64;                       // (mm * 1e6).round()
pub fn via_pad_diameter_nm(drill_mm: f64, annular_ring_mm: f64) -> i64;
//   (drill + 2*ring) in nm
```

### 2.8 Re-exported protobuf types

`pcbmotorgen_export::proto` exposes the full generated KiCad 10 IPC tree
(`common`, `common::types`, `common::commands`, `board`, `board::types`,
`board::commands`, `schematic`). Convenience re-exports at the crate root:

```rust
// envelope
ApiRequest, ApiRequestHeader, ApiResponse, ApiResponseHeader,
ApiResponseStatus, ApiStatusCode,
// common commands
BeginCommit, BeginCommitResponse, CommitAction, CreateItems, CreateItemsResponse,
EndCommit, EndCommitResponse,
// common types
AxisAlignment, DocumentSpecifier, DocumentType, Distance, ItemHeader,
ItemRequestStatus, Kiid, KiCadVersion, LibraryIdentifier, LockedState,
ProjectSpecifier, Vector2, Vector3,
// board types
Arc, BoardLayer, BoardOriginType, Footprint, FootprintInstance, Net, Pad, PadType, Track, Via,
// diagnostics (kata ze9f)
BoardBBoxMm,
```

---

## 3. Transport abstraction (for testing / custom transports)

```rust
pub trait KicadTransport {
    fn connect(&mut self) -> Result<(), KiCadError> { Ok(()) }
    fn send_and_recv(&mut self, request_bytes: &[u8]) -> Result<Vec<u8>, KiCadError>;
}
```

Implement this to inject a fake transport into `KiCadClient::with_transport`
(e.g. [`MockTransport`], which records `sent_requests` and returns a canned
`response_to_return`).

---

## 4. Typical external workflow

```rust
use pcbmotorgen_export::{
    BoardHandle, KiCadClient, DocumentSpecifier, DocumentType,
    get_board_diagnostics, validate_write_preconditions,
};
use pcbmotorgen_export::proto::common::commands::{
    GetOpenDocuments, GetOpenDocumentsResponse,
};

// 1. Connect
let mut client = KiCadClient::new(None, None, 5000);
client.connect()?;

// 2. Find the open PCB
let cmd = GetOpenDocuments { r#type: DocumentType::DoctypePcb as i32 };
let resp: GetOpenDocumentsResponse = client.send(
    "type.googleapis.com/kiapi.common.commands.GetOpenDocuments", &cmd)?;
let doc = resp.documents.into_iter().next().ok_or("no board open")?;

// 3. Diagnose + validate
let mut board = BoardHandle::new(&mut client, doc.clone());
let diags = get_board_diagnostics(&mut board)?;
let warnings = validate_write_preconditions(&rules, num_layers, active_m, width_m, &diags);

// 4. Write (or dry-run)
let result = board.write_coils(&coils, num_layers, &rules, active_area_mm)?;
// or: let result = board.write_coils_dry_run(...)?;
```

---

## 5. Module index

| Module        | Origin | Contents                                    |
| ------------- | ------ | ------------------------------------------- |
| `entities`    | DXF    | `LINE` / `ARC` / `CIRCLE` emitters          |
| `sections`    | DXF    | `HEADER` / `TABLES` emitters                |
| `groups`      | DXF    | DXF group code/value codec                  |
| `helpers`     | DXF    | unit + three-point circle helpers           |
| `proto`       | KiCad  | prost-generated IPC types (see §2.8)        |
| `client`      | KiCad  | `KiCadClient`, `KicadTransport`, transports |
| `errors`      | KiCad  | `KiCadError`                                |
| `layer_map`   | KiCad  | layer mapping + mm/nm conversion            |
| `writer`      | KiCad  | `coils_to_board_items` / `io_elements_to_board_items` + item emitters (`track_writer`, `via_writer`, `pad_writer`) |
| `commit`      | KiCad  | `Commit` atomic commit handle               |
| `board`       | KiCad  | `BoardHandle`, `WriteCoilsResult`, `BoardBBoxMm` |
| `diagnostics` | KiCad  | diagnostics, preconditions, preview         |

---

[`pcbmotorgen-routing`]: ../pcbmotorgen-routing/
[`pcbmotorgen-dfm`]: ../pcbmotorgen-dfm/
[`PhaseCoil`]: ../pcbmotorgen-routing/src/coil.rs
[`RoutingResult`]: ../pcbmotorgen-routing/src/coil.rs
[`DesignRules`]: ../pcbmotorgen-dfm/src/rules.rs
[`KicadTransport`]: ../pcbmotorgen-export/src/client/mod.rs
[`MockTransport`]: ../pcbmotorgen-export/src/client/mock_transport.rs
[`DocumentSpecifier`]: ../pcbmotorgen-export/src/proto/common.rs
