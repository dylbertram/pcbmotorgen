//! End-to-end routing → export integration test with **generated** IO
//! elements (kata xa0f).
//!
//! Proves the full host pipeline: a routing pattern generates its geometry,
//! the host appends IO fanout (connector pads + traces) via
//! `generate_routing_result_with_io`, the strict validator accepts the
//! combined result, and the export crate emits it through both exporters:
//!
//! - KiCad IPC board items (`io_elements_to_board_items`): one
//!   `FootprintInstance` per IO pad, one `Track` per IO fanout trace — and
//!   the high-level `BoardHandle::write_io_elements` commit flow over a mock
//!   transport;
//! - DXF R12 (`routing_result_to_dxf`): `LINE` per IO trace on the
//!   `L<layer>_<net>` layer, `CIRCLE` per round IO pad on the `IO_Pad` layer.

use prost::Message;
use prost_types::Any;

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{
    RoutingContext, RoutingResult, Validator, generate_routing_result_with_io,
    routing_result_to_phase_coils,
};
use pcbmotorgen_export::{
    ApiResponse, ApiResponseHeader, ApiResponseStatus, ApiStatusCode, BoardHandle,
    FootprintInstance, KiCadClient, KiCadError, KicadTransport, Pad, Track,
    io_elements_to_board_items, mm_to_nm, routing_result_to_dxf,
};
use pcbmotorgen_export::proto::board::types::PadType;
use pcbmotorgen_export::proto::common::commands::{
    BeginCommitResponse, CreateItemsResponse, EndCommitResponse, ItemCreationResult, ItemStatus,
};
use pcbmotorgen_export::proto::common::types::{Kiid, document_specifier, DocumentSpecifier, DocumentType};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ACTIVE_AREA_MM: f64 = 600.0;
const BOARD_WIDTH_MM: f64 = 20.0;
const NUM_LAYERS: u32 = 2;

fn rules() -> DesignRules {
    DesignRules {
        min_trace_mm: 0.1,
        trace_width_mm: 0.1,
        min_space_mm: 0.1,
        min_via_drill_mm: 0.2,
        min_via_annular_ring_mm: 0.1,
    }
}

/// The bundled infinity-braid context (2 layers, 3 phases).
fn braid_ctx() -> RoutingContext {
    let mut params = std::collections::HashMap::new();
    params.insert("num_strands".to_string(), 5.0);
    params.insert("n_periods".to_string(), 4.0);
    RoutingContext {
        active_area_length_mm: ACTIVE_AREA_MM,
        board_width_mm: BOARD_WIDTH_MM,
        num_layers: NUM_LAYERS,
        phases: 3,
        min_trace_mm: 0.1,
        min_space_mm: 0.1,
        expects_continuous: false,
        params,
        ..RoutingContext::default()
    }
}

/// Generate the braid WITH host IO fanout, sized from the DFM rules bridge,
/// and pass it through the strict validator — the exact production pipeline.
fn braid_result_with_io() -> RoutingResult {
    let ctx = braid_ctx();
    let io = rules().io_fanout_options();
    let result = generate_routing_result_with_io(&ctx, "infinity-braid", &io)
        .expect("routing → IO fanout → validation pipeline succeeds");
    Validator::validate(&result, &ctx, false).expect("generated IO passes the strict validator");
    result
}

fn pack_any<T: Message>(type_url: &str, msg: &T) -> Any {
    let mut buf = Vec::new();
    msg.encode(&mut buf).expect("encode");
    Any {
        type_url: type_url.to_string(),
        value: buf,
    }
}

fn build_ok_response(payload: Any) -> Vec<u8> {
    let resp = ApiResponse {
        header: Some(ApiResponseHeader {
            kicad_token: "test-token".to_string(),
        }),
        status: Some(ApiResponseStatus {
            status: ApiStatusCode::AsOk as i32,
            error_message: String::new(),
        }),
        message: Some(payload),
    };
    let mut buf = Vec::new();
    resp.encode(&mut buf).expect("encode response");
    buf
}

const BEGIN_COMMIT_RESPONSE_URL: &str =
    "type.googleapis.com/kiapi.common.commands.BeginCommitResponse";
const CREATE_ITEMS_RESPONSE_URL: &str =
    "type.googleapis.com/kiapi.common.commands.CreateItemsResponse";
const END_COMMIT_RESPONSE_URL: &str =
    "type.googleapis.com/kiapi.common.commands.EndCommitResponse";

/// A `MockTransport` returning one canned response per `send_and_recv` call
/// (BeginCommit → CreateItems → EndCommit), so the full
/// `BoardHandle::write_io_elements` commit flow runs without a socket.
struct SequencedMockTransport {
    responses: Vec<Vec<u8>>,
    call_index: usize,
}

impl SequencedMockTransport {
    fn new(responses: Vec<Vec<u8>>) -> Self {
        Self {
            responses,
            call_index: 0,
        }
    }
}

impl KicadTransport for SequencedMockTransport {
    fn send_and_recv(&mut self, _request_bytes: &[u8]) -> Result<Vec<u8>, KiCadError> {
        let idx = self.call_index;
        self.call_index += 1;
        Ok(self.responses.get(idx).cloned().unwrap_or_default())
    }
}

fn pcb_document(filename: &str) -> DocumentSpecifier {
    DocumentSpecifier {
        r#type: DocumentType::DoctypePcb as i32,
        identifier: Some(document_specifier::Identifier::BoardFilename(
            filename.to_string(),
        )),
        project: None,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// The generated braid carries one IO pad + trace per coil terminal
/// (2 layers × 3 phases = 6 coils × 2 terminals) with the phase nets.
#[test]
fn generated_io_has_one_pad_and_trace_per_coil_terminal() {
    let result = braid_result_with_io();
    let coils = routing_result_to_phase_coils(&result, "infinity-braid");
    let terminals = coils.len() * 2;

    assert_eq!(coils.len(), 6, "2 layers × 3 phase nets");
    assert_eq!(result.io_pads.len(), terminals, "one pad per terminal");
    assert_eq!(result.io_traces.len(), terminals, "one fanout per terminal");

    // Nets carry through: the multiset of pad nets equals the coil nets,
    // each net appearing once per terminal.
    let mut pad_nets: Vec<&str> = result.io_pads.iter().map(|p| p.net.as_str()).collect();
    let mut coil_nets: Vec<&str> =
        coils.iter().flat_map(|c| std::iter::repeat(c.phase_name.as_str()).take(2)).collect();
    pad_nets.sort();
    coil_nets.sort();
    assert_eq!(pad_nets, coil_nets);

    // Every fanout is a strictly non-degenerate single-layer trace from a
    // coil terminal to its pad, on a valid layer.
    for t in &result.io_traces {
        let dx = t.end.x - t.start.x;
        let dy = t.end.y - t.start.y;
        assert!((dx * dx + dy * dy).sqrt() > 1e-6, "non-degenerate fanout");
        assert!(t.layer < NUM_LAYERS);
    }
}

/// The KiCad writer emits one FootprintInstance (with a THT Pad) per
/// generated IO pad and one rule-sized Track per generated IO trace.
#[test]
fn kicad_writer_emits_generated_io_pads_and_traces() {
    let result = braid_result_with_io();
    let (pads, traces) = (result.io_pads.len(), result.io_traces.len());
    assert!(pads > 0 && traces > 0);

    let items = io_elements_to_board_items(&result, NUM_LAYERS, &rules(), ACTIVE_AREA_MM);
    assert_eq!(items.len(), pads + traces);

    let mut footprints = 0;
    let mut tracks = 0;
    let mut track_nets = std::collections::BTreeSet::new();
    for any in &items {
        if any.type_url.ends_with("kiapi.board.types.FootprintInstance") {
            footprints += 1;
            let fp = FootprintInstance::decode(any.value.as_slice()).expect("decode footprint");
            let definition = fp.definition.expect("definition");
            let pad = Pad::decode(definition.items[0].value.as_slice()).expect("decode pad");
            assert_eq!(pad.r#type, PadType::PtPth as i32, "rule-bridged pads are THT");
            let ps = pad.pad_stack.expect("padstack");
            assert!(ps.drill.is_some(), "THT padstack carries the drill");
            assert_eq!(
                ps.layers.len(),
                NUM_LAYERS as usize,
                "generated THT pads declare all copper layers"
            );
        } else if any.type_url.ends_with("kiapi.board.types.Track") {
            tracks += 1;
            let track = Track::decode(any.value.as_slice()).expect("decode track");
            track_nets.insert(track.net.expect("net").name);
            assert_eq!(
                track.width.expect("width").value_nm,
                mm_to_nm(rules().min_trace_mm),
                "fanout tracks are sized from the design rules"
            );
        }
    }
    assert_eq!(footprints, pads);
    assert_eq!(tracks, traces);
    assert_eq!(
        track_nets,
        std::collections::BTreeSet::from(["/A".to_string(), "/B".to_string(), "/C".to_string()]),
        "phase nets are slash-prefixed like coil nets"
    );
}

/// The full `BoardHandle::write_io_elements` commit flow (Begin → Create →
/// End) round-trips the generated IO elements over a mock transport.
#[test]
fn board_write_io_elements_round_trips_generated_io() {
    let result = braid_result_with_io();
    let expected = result.io_pads.len() + result.io_traces.len();

    let create_resp = CreateItemsResponse {
        header: None,
        status: 1, // IRS_OK
        created_items: (0..expected)
            .map(|_| ItemCreationResult {
                status: Some(ItemStatus {
                    code: 1, // ISC_OK
                    error_message: String::new(),
                }),
                item: None,
            })
            .collect(),
    };
    let transport = SequencedMockTransport::new(vec![
        build_ok_response(pack_any(
            BEGIN_COMMIT_RESPONSE_URL,
            &BeginCommitResponse {
                id: Some(Kiid { value: "commit-uuid".to_string() }),
            },
        )),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &EndCommitResponse {})),
    ]);
    let mut client = KiCadClient::with_transport(Box::new(transport), Some("test-client"), 2000);
    let mut board = BoardHandle::new(&mut client, pcb_document("io_board.kicad_pcb"));

    let out = board
        .write_io_elements(&result, NUM_LAYERS, &rules(), ACTIVE_AREA_MM)
        .expect("the IO commit flow succeeds");
    assert_eq!(out.items_attempted, expected as u32);
    assert_eq!(out.items_created, expected as u32);
    assert!(out.failures.is_empty());
}

/// The DXF exporter emits the generated IO elements: a `CIRCLE` per round pad
/// on the `IO_Pad` layer and a `LINE` per fanout trace on `L<layer>_<net>`.
#[test]
fn dxf_export_contains_generated_io_entities() {
    let result = braid_result_with_io();
    let (pads, traces) = (result.io_pads.len(), result.io_traces.len());

    let dxf = routing_result_to_dxf(&result, &rules(), ACTIVE_AREA_MM, true);

    // Layer bookkeeping: IO pads get the dedicated IO_Pad layer; fanout
    // traces join the L<layer>_<net> layers.
    assert!(dxf.contains("IO_Pad"), "IO_Pad layer defined in TABLES");
    assert!(dxf.contains("L0_A") && dxf.contains("L1_A"), "fanout trace layers");

    // Every generated pad is round (copper diameter from the rules bridge)
    // → one CIRCLE entity per pad, alongside the braid's via circles.
    let circle_entities = count_entities(&dxf, "CIRCLE");
    assert_eq!(
        circle_entities,
        result.vias.len() + pads,
        "vias + round IO pads are CIRCLE entities"
    );
    // The pad circles sit on the IO_Pad layer.
    assert_eq!(count_layer_refs(&dxf, "IO_Pad"), pads);

    // One LINE per segment and per IO fanout trace.
    let line_entities = count_entities(&dxf, "LINE");
    assert_eq!(line_entities, result.segments.len() + traces);
}

/// The IO-free braid export is unaffected: a result generated without the IO
/// entry points produces no IO entities (payloads stay byte-identical).
#[test]
fn io_free_generation_keeps_exports_unchanged() {
    use pcbmotorgen_routing::generate_routing_result;

    let ctx = braid_ctx();
    let plain = generate_routing_result(&ctx, "infinity-braid").expect("braid generates");
    assert!(plain.io_pads.is_empty() && plain.io_traces.is_empty());

    let items = io_elements_to_board_items(&plain, NUM_LAYERS, &rules(), ACTIVE_AREA_MM);
    assert!(items.is_empty(), "no IO elements → no IO export items");

    let dxf = routing_result_to_dxf(&plain, &rules(), ACTIVE_AREA_MM, true);
    assert!(!dxf.contains("IO_Pad"), "no IO_Pad layer without IO pads");
}

/// Count DXF entity markers (`0\nCIRCLE` / `0\nLINE` group-code pairs).
fn count_entities(dxf: &str, entity: &str) -> usize {
    let marker = format!("0\n{entity}\n");
    dxf.match_indices(&marker).count()
}

/// Count occurrences of a layer name in group-code 8 values (`8\n<layer>\n`).
fn count_layer_refs(dxf: &str, layer: &str) -> usize {
    let marker = format!("8\n{layer}\n");
    dxf.match_indices(&marker).count()
}
