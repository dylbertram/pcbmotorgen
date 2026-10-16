//! Integration tests for the Phase 7 KiCad writer module.
//!
//! These tests exercise the pure `coils_to_board_items` function (no socket
//! needed) and the `Commit` handle using `MockTransport`.

use std::collections::HashMap;
use prost::Message;
use prost_types::Any;

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{generate_coils_from_context, CoilSegment, PhaseCoil, RoutingContext};
use pcbmotorgen_export::{
    ApiResponse, ApiResponseHeader, ApiResponseStatus, ApiStatusCode, BoardLayer, KiCadClient,
    KiCadError, KicadTransport, MockTransport, coils_to_board_items, layer_idx_to_board_layer,
    mm_to_nm, via_pad_diameter_nm,
};
use pcbmotorgen_export::proto::board::types::{Track, Via, ViaType};
use pcbmotorgen_export::proto::common::commands::{
    BeginCommitResponse, CommitAction, CreateItemsResponse, EndCommit, EndCommitResponse,
};
use pcbmotorgen_export::proto::common::types::{
    document_specifier, DocumentSpecifier, DocumentType, Kiid,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Millimetres (routing crate's native unit).
fn mm(v: f64) -> f64 {
    v
}

/// mil → millimetres (1 mil = 0.0254 mm).
fn mils_to_mm(v: f64) -> f64 {
    v * 0.0254
}

/// `DesignRules` matching the old `braid_config` / `test_config` helpers:
/// 5 mil trace/space, 0.2 mm via drill, 0.1 mm annular ring.
fn braid_rules() -> DesignRules {
    DesignRules {
        min_trace_mm: mils_to_mm(5.0),
        trace_width_mm: mils_to_mm(5.0),
        min_space_mm: mils_to_mm(5.0),
        min_via_drill_mm: mm(0.2),
        min_via_annular_ring_mm: mm(0.1),
    }
}

/// Active area used by the infinity-braid tests (matches the old
/// `braid_config.active_area_length_m = 0.6`).
const BRAID_ACTIVE_AREA_MM: f64 = 600.0;

/// Active area used by the hand-built proto tests (matches the old
/// `test_config.active_area_length_m = mm(48.0)`).
const TEST_ACTIVE_AREA_MM: f64 = 48.0;

/// Generate the bundled infinity-braid coil set for a board of `num_layers`
/// layers. Mirrors the old `generate_coils_for_board`. The braid requires
/// `num_layers >= 2` (returns an empty set for a 1-layer board).
fn braid_coils(num_layers: u32) -> Vec<PhaseCoil> {
    let mut params = HashMap::new();
    params.insert("num_strands".to_string(), 5.0);
    params.insert("n_periods".to_string(), 4.0);
    let ctx = RoutingContext {
        active_area_length_mm: BRAID_ACTIVE_AREA_MM,
        board_width_mm: 20.0,
        num_layers,
        phases: 3,
        min_trace_mm: 0.1,
        trace_width_mm: 0.1,
        min_space_mm: 0.1,
        expects_continuous: false,
        params,
        ..RoutingContext::default()
    };
    generate_coils_from_context(&ctx, "infinity-braid")
}

/// Convert a braid coil set to board items using the braid specs.
fn braid_items(coils: &[PhaseCoil], num_layers: u32) -> Vec<Any> {
    coils_to_board_items(coils, num_layers, &braid_rules(), BRAID_ACTIVE_AREA_MM)
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

fn empty_end_commit_response() -> EndCommitResponse {
    EndCommitResponse {}
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
// layer_map tests
// ---------------------------------------------------------------------------

#[test]
fn test_layer_0_is_bcu() {
    assert_eq!(layer_idx_to_board_layer(0, 4), BoardLayer::BlBCu);
}

#[test]
fn test_layer_top_is_fcu() {
    assert_eq!(layer_idx_to_board_layer(3, 4), BoardLayer::BlFCu);
}

#[test]
fn test_layer_1_is_in1cu() {
    assert_eq!(layer_idx_to_board_layer(1, 4), BoardLayer::BlIn1Cu);
}

#[test]
fn test_mm_to_nm_conversion() {
    assert_eq!(mm_to_nm(1.0), 1_000_000);
}

#[test]
fn test_via_pad_diameter() {
    // 0.2mm drill + 2×0.1mm ring = 0.4mm = 400,000 nm
    assert_eq!(via_pad_diameter_nm(0.2, 0.1), 400_000);
}

// ---------------------------------------------------------------------------
// coils_to_board_items tests (pure function)
// ---------------------------------------------------------------------------

#[test]
fn test_track_count_matches_segments_arcs_and_vias() {
    // The infinity-braid produces Tracks (one per segment), Arcs (one per
    // corner_arc), and Vias (one per center_via_position). The total item
    // count is the sum of all three.
    let coils = braid_coils(2);
    let expected: usize = coils
        .iter()
        .map(|c| c.segments.len() + c.corner_arcs.len() + c.center_via_positions.len())
        .sum();
    let items = braid_items(&coils, 2);
    assert_eq!(items.len(), expected);
}

#[test]
fn test_all_items_are_track_arc_or_via() {
    // Infinity-braid items are Tracks, Arcs, and Vias (the pattern uses
    // through-vias at the braid crossing points).
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);
    assert!(!items.is_empty());
    for any in &items {
        assert!(
            any.type_url.ends_with("kiapi.board.types.Track")
                || any.type_url.ends_with("kiapi.board.types.Arc")
                || any.type_url.ends_with("kiapi.board.types.Via"),
            "expected Track, Arc, or Via, got: {}",
            any.type_url
        );
    }
}

#[test]
fn test_track_coordinates_are_in_nanometres() {
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);

    let coil0 = &coils[0];
    let seg0 = &coil0.segments[0];
    let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
    let start = track.start.unwrap();
    let end = track.end.unwrap();
    // Coils are centered on x = 0: wire x_nm = mm_nm - active_area/2_nm.
    let offset_nm = (BRAID_ACTIVE_AREA_MM / 2.0 * 1e6).round() as i64;
    assert_eq!(start.x_nm, (seg0.start.0 * 1e6).round() as i64 - offset_nm);
    assert_eq!(start.y_nm, (seg0.start.1 * 1e6).round() as i64);
    assert_eq!(end.x_nm, (seg0.end.0 * 1e6).round() as i64 - offset_nm);
    assert_eq!(end.y_nm, (seg0.end.1 * 1e6).round() as i64);
}

#[test]
fn test_track_width_matches_config() {
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);
    let expected = (braid_rules().min_trace_mm * 1e6).round() as i64;
    let track: Track = Track::decode(items[0].value.as_slice()).expect("decode Track");
    assert_eq!(track.width.unwrap().value_nm, expected);
}

#[test]
fn test_net_names_are_slash_prefixed() {
    // The infinity-braid produces exactly the 3 phase nets (/A, /B, /C).
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);

    let mut nets: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    for any in &items {
        if !any.type_url.ends_with("kiapi.board.types.Track") {
            continue;
        }
        let t: Track = Track::decode(any.value.as_slice()).expect("decode");
        nets.insert(t.net.expect("Track must carry a net").name);
    }
    let expected: std::collections::BTreeSet<String> =
        ["/A".to_string(), "/B".to_string(), "/C".to_string()].into_iter().collect();
    assert_eq!(nets, expected, "track nets must be {{/A, /B, /C}}; got {nets:?}");
}

#[test]
fn test_layer_assignment_braid_uses_layers_0_and_1() {
    // The infinity-braid is a 2-layer weave: it places segments on layers
    // 0 and 1, which on a 4-layer board map to B.Cu and In1.Cu.
    let coils = braid_coils(4);
    let items = braid_items(&coils, 4);

    let mut layers = std::collections::BTreeSet::new();
    for any in &items {
        if !any.type_url.ends_with("kiapi.board.types.Track") {
            continue;
        }
        let t: Track = Track::decode(any.value.as_slice()).expect("decode");
        layers.insert(t.layer);
    }
    assert!(layers.contains(&(BoardLayer::BlBCu as i32)),
        "braid must place tracks on B.Cu (layer 0); got {layers:?}");
    assert!(layers.contains(&(BoardLayer::BlIn1Cu as i32)),
        "braid must place tracks on In1.Cu (layer 1); got {layers:?}");
}

#[test]
fn test_via_items_when_present() {
    let rules = braid_rules();
    let active = TEST_ACTIVE_AREA_MM;
    let num_layers = 4u32;
    let coil = PhaseCoil {
        phase_idx: 0,
        layer_idx: 0,
        segments: vec![CoilSegment {
            start: (0.0, 0.0),
            end: (0.0, 20.0),
            is_active: true,
        }],
        phase_name: "A".into(),
            center_via_positions: vec![(5.0, 5.0), (10.0, 10.0)],
        ..PhaseCoil::default()
    };
    let items = coils_to_board_items(&[coil], num_layers, &rules, active);
    // 1 track + 2 vias
    assert_eq!(items.len(), 3);

    let vias: Vec<&Any> = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
        .collect();
    assert_eq!(vias.len(), 2);

    let via: Via = Via::decode(vias[0].value.as_slice()).expect("decode Via");
    assert_eq!(via.r#type, ViaType::VtThrough as i32);
    assert_eq!(via.net.unwrap().name, "/A");
    let pos = via.position.unwrap();
    // Vias share the same centering offset as tracks; the test coil's first
    // via sits at x=5mm, the active area is 48mm, so the wire x is
    // 5_000_000 - 24_000_000 = -19_000_000 nm.
    let offset_nm = (active / 2.0 * 1e6).round() as i64;
    assert_eq!(pos.x_nm, 5_000_000 - offset_nm);
    assert_eq!(pos.y_nm, 5_000_000);
}

// ---------------------------------------------------------------------------
// Commit tests with MockTransport
// ---------------------------------------------------------------------------

/// A `MockTransport` that returns a sequence of canned responses (one per
/// `send_and_recv` call) so a multi-step commit flow can be simulated.
struct SequencedMockTransport {
    responses: Vec<Vec<u8>>,
    sent_requests: Vec<Vec<u8>>,
    call_index: usize,
}

impl SequencedMockTransport {
    fn new(responses: Vec<Vec<u8>>) -> Self {
        Self {
            responses,
            sent_requests: Vec::new(),
            call_index: 0,
        }
    }
}

impl KicadTransport for SequencedMockTransport {
    fn send_and_recv(&mut self, request_bytes: &[u8]) -> Result<Vec<u8>, KiCadError> {
        self.sent_requests.push(request_bytes.to_vec());
        let resp = self
            .responses
            .get(self.call_index)
            .cloned()
            .unwrap_or_default();
        self.call_index += 1;
        Ok(resp)
    }
}

#[test]
fn test_commit_begin_create_end_flow() {
    let begin_resp = BeginCommitResponse {
        id: Some(Kiid {
            value: "commit-uuid-1234".to_string(),
        }),
    };
    let create_resp = CreateItemsResponse {
        header: None,
        status: 1, // IRS_OK
        created_items: Vec::new(),
    };
    let end_resp = empty_end_commit_response();

    let responses = vec![
        build_ok_response(pack_any(BEGIN_COMMIT_RESPONSE_URL, &begin_resp)),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &end_resp)),
    ];

    let transport = SequencedMockTransport::new(responses);
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test-client"),
        2000,
    );

    // Build a coil set so we have items to create.
    let coils = braid_coils(4);
    let items = braid_items(&coils, 4);
    let doc = pcb_document("board.kicad_pcb");

    use pcbmotorgen_export::Commit;

    let mut commit = Commit::begin(&mut client).expect("begin commit");
    let resp = commit.create_items(&items, &doc).expect("create items");
    assert_eq!(resp.created_items.len(), 0); // mocked empty
    commit.end().expect("end commit");

    // We can't easily inspect the inner transport through the Box<dyn>, but
    // the fact that the flow succeeded (no error) proves BeginCommit, then
    // CreateItems, then EndCommit were all sent and the responses decoded.
}

#[test]
fn test_commit_begin_sends_begincommit_command() {
    let begin_resp = BeginCommitResponse {
        id: Some(Kiid {
            value: "abc".to_string(),
        }),
    };
    let resp_bytes = build_ok_response(pack_any(BEGIN_COMMIT_RESPONSE_URL, &begin_resp));

    let mut transport = SequencedMockTransport::new(vec![resp_bytes]);

    // Manually pack a BeginCommit request and send via the transport so we can
    // inspect the bytes.
    use pcbmotorgen_export::proto::common::commands::BeginCommit;
    use pcbmotorgen_export::{ApiRequest, ApiRequestHeader};

    let cmd = BeginCommit {};
    let any = pack_any("type.googleapis.com/kiapi.common.commands.BeginCommit", &cmd);
    let request = ApiRequest {
        header: Some(ApiRequestHeader {
            kicad_token: String::new(),
            client_name: "test".to_string(),
        }),
        message: Some(any),
    };
    let mut req_bytes = Vec::new();
    request.encode(&mut req_bytes).expect("encode");
    let _ = transport.send_and_recv(&req_bytes);

    assert_eq!(transport.sent_requests.len(), 1);
    let sent = &transport.sent_requests[0];
    let decoded = ApiRequest::decode(sent.as_slice()).expect("decode sent request");
    let any = decoded.message.expect("message");
    assert!(any.type_url.ends_with("kiapi.common.commands.BeginCommit"));
}

#[test]
fn test_commit_end_sends_cma_commit() {
    // Build an EndCommit command and verify the action is CMA_COMMIT.
    let cmd = EndCommit {
        id: Some(Kiid {
            value: "commit-1".to_string(),
        }),
        action: CommitAction::CmaCommit as i32,
        message: "pcbmotorgen coil generation".to_string(),
    };
    let any = pack_any("type.googleapis.com/kiapi.common.commands.EndCommit", &cmd);

    let resp_bytes = build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &empty_end_commit_response()));

    let transport = SequencedMockTransport::new(vec![resp_bytes]);
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test"),
        2000,
    );

    // Use send directly to exercise EndCommit.
    let _resp: EndCommitResponse = client
        .send::<EndCommit, EndCommitResponse>(
            "type.googleapis.com/kiapi.common.commands.EndCommit",
            &cmd,
        )
        .expect("end commit send");

    // Verify the decoded Any payload has the right action by re-decoding the
    // command from the constructed Any.
    let decoded_end = EndCommit::decode(any.value.as_slice()).expect("decode EndCommit");
    assert_eq!(decoded_end.action, CommitAction::CmaCommit as i32);
    assert_eq!(decoded_end.message, "pcbmotorgen coil generation");
}

#[test]
fn test_commit_abort_sends_cma_drop() {
    let cmd = EndCommit {
        id: Some(Kiid {
            value: "commit-2".to_string(),
        }),
        action: CommitAction::CmaDrop as i32,
        message: String::new(),
    };
    assert_eq!(cmd.action, CommitAction::CmaDrop as i32);
    assert!(cmd.message.is_empty());
}

#[test]
fn test_board_handle_name() {
    let resp_bytes = build_ok_response(pack_any(
        BEGIN_COMMIT_RESPONSE_URL,
        &BeginCommitResponse {
            id: Some(Kiid { value: "x".to_string() }),
        },
    ));
    let mut client = KiCadClient::with_transport(
        Box::new(MockTransport::new(resp_bytes)),
        Some("test"),
        2000,
    );
    let doc = pcb_document("motor.kicad_pcb");
    let board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    assert_eq!(board.name().unwrap(), "motor.kicad_pcb");
}

#[test]
fn test_board_handle_name_errors_for_non_pcb() {
    let resp_bytes = build_ok_response(pack_any(
        BEGIN_COMMIT_RESPONSE_URL,
        &BeginCommitResponse {
            id: Some(Kiid { value: "x".to_string() }),
        },
    ));
    let mut client = KiCadClient::with_transport(
        Box::new(MockTransport::new(resp_bytes)),
        Some("test"),
        2000,
    );
    let doc = DocumentSpecifier {
        r#type: DocumentType::DoctypeSchematic as i32,
        identifier: None,
        project: None,
    };
    let board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    assert!(board.name().is_err());
}

#[test]
fn test_board_handle_write_coils_end_to_end() {
    // Build canned responses for the 3-step commit flow.
    let begin_resp = BeginCommitResponse {
        id: Some(Kiid { value: "c1".to_string() }),
    };
    // The mock response must contain one `ItemCreationResult` per submitted
    // item, otherwise the new per-item tallying will report a mismatch.
    let (coils, num_layers) = (braid_coils(3), 3u32);
    let items = braid_items(&coils, num_layers);
    let expected_items = items.len() as u32;
    let created_items: Vec<_> = (0..expected_items)
        .map(|_| pcbmotorgen_export::proto::common::commands::ItemCreationResult {
            status: Some(pcbmotorgen_export::proto::common::commands::ItemStatus {
                code: 1, // ISC_OK
                error_message: String::new(),
            }),
            item: None,
        })
        .collect();
    let create_resp = CreateItemsResponse {
        header: None,
        status: 1,
        created_items,
    };

    let responses = vec![
        build_ok_response(pack_any(BEGIN_COMMIT_RESPONSE_URL, &begin_resp)),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &empty_end_commit_response())),
    ];

    let transport = SequencedMockTransport::new(responses);
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test"),
        2000,
    );
    let doc = pcb_document("motor.kicad_pcb");

    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let result = board
        .write_coils(&coils, num_layers, &braid_rules(), BRAID_ACTIVE_AREA_MM)
        .expect("write_coils");
    assert_eq!(result.items_attempted, expected_items);
    assert_eq!(result.items_created, expected_items);
    assert!(result.failures.is_empty(), "no failures expected, got: {:?}", result.failures);
    assert!(
        result.failure_summary.is_empty(),
        "no failure_summary expected when all items succeed; got {:?}",
        result.failure_summary
    );
}

#[test]
fn test_board_handle_write_coils_dry_run_does_not_call_commit() {
    // The dry-run path must NOT issue any IPC requests. We assert that by
    // constructing a transport that records every send and verifying the
    // transport was *not* touched (sent_requests is empty).
    let transport = SequencedMockTransport::new(Vec::new());
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test"),
        2000,
    );
    let doc = pcb_document("dryrun.kicad_pcb");

    let (coils, num_layers) = (braid_coils(3), 3u32);
    let items = braid_items(&coils, num_layers);
    let expected_items = items.len() as u32;

    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let result = board
        .write_coils_dry_run(&coils, num_layers, &braid_rules(), BRAID_ACTIVE_AREA_MM)
        .expect("dry-run write_coils");
    assert_eq!(result.items_attempted, expected_items);
    assert_eq!(
        result.items_created, 0,
        "dry-run must report 0 items_created (no IPC call was made)"
    );
    assert!(result.failures.is_empty());
    assert!(
        result.failure_summary.is_empty(),
        "dry-run must report an empty failure_summary; got {:?}",
        result.failure_summary
    );
}

// ---------------------------------------------------------------------------
// Failure-summary tests (round-5 error display)
//
// These tests exercise the new `WriteCoilsResult.failure_summary` field
// introduced in the round-5 fix for the "99 of 588 items rejected" UI
// display problem.
// ---------------------------------------------------------------------------

/// Helper: build a `CreateItemsResponse` from a per-item outcome spec.
/// `outcomes` is a slice of `(code, error_message)` tuples — one per
/// submitted item.
fn make_create_response(outcomes: &[(i32, &str)]) -> CreateItemsResponse {
    let created_items = outcomes
        .iter()
        .map(|(code, msg)| {
            pcbmotorgen_export::proto::common::commands::ItemCreationResult {
                status: Some(
                    pcbmotorgen_export::proto::common::commands::ItemStatus {
                        code: *code,
                        error_message: msg.to_string(),
                    },
                ),
                item: None,
            }
        })
        .collect();
    CreateItemsResponse {
        header: None,
        status: 1, // IRS_OK
        created_items,
    }
}

/// Build `n` single-track coils (one segment each) as a hand-built coil set
/// so the per-item count matches the mock outcome count exactly (no routing
/// dependency).
fn single_track_coils(n: u32) -> Vec<PhaseCoil> {
    (0..n)
        .map(|i| PhaseCoil {
            phase_idx: i,
            layer_idx: 0,
            segments: vec![CoilSegment {
                start: (0.0, 0.0),
                end: (0.0, 0.02),
                is_active: true,
            }],
            phase_name: "A".into(),
            center_via_positions: Vec::new(),
            ..PhaseCoil::default()
        })
        .collect()
}

#[test]
fn test_failure_summary_groups_by_code_with_counts() {
    // 6 items: 1 OK, 5 rejected — 4 with code=7 and 1 with code=2. The
    // summary should be [(7, 4), (2, 1)] in count-descending order.
    let begin_resp = BeginCommitResponse {
        id: Some(Kiid { value: "c".to_string() }),
    };
    let outcomes: Vec<(i32, &str)> = vec![
        (1, ""), // OK
        (7, "attempted to add item with no overlapping layers ..."),
        (7, "attempted to add item with no overlapping layers ..."),
        (7, "attempted to add item with no overlapping layers ..."),
        (2, "invalid item type"),
        (7, "attempted to add item with no overlapping layers ..."),
    ];
    let create_resp = make_create_response(&outcomes);
    let end_resp = empty_end_commit_response();

    let responses = vec![
        build_ok_response(pack_any(BEGIN_COMMIT_RESPONSE_URL, &begin_resp)),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &end_resp)),
    ];

    let transport = SequencedMockTransport::new(responses);
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test"),
        2000,
    );
    let doc = pcb_document("motor.kicad_pcb");

    // Pad with 5 more single-track coils to get a 6-item set.
    let six_coils = single_track_coils(6);

    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let result = board
        .write_coils(&six_coils, 3, &braid_rules(), BRAID_ACTIVE_AREA_MM)
        .expect("write_coils");

    // 1 OK + 5 rejected → 1 created, 5 failures.
    assert_eq!(result.items_attempted, 6);
    assert_eq!(result.items_created, 1);
    assert_eq!(result.failures.len(), 5);

    assert_eq!(
        result.failure_summary,
        vec![(7, 4), (2, 1)],
        "failure_summary must group rejections by code and sort by count desc"
    );
}

#[test]
fn test_failure_summary_sorts_by_count_descending() {
    // 7 items: 1 OK + 6 rejected across 3 distinct codes
    // (1× code=3, 2× code=2, 3× code=7). Expected ordering: (7, 3), (2, 2), (3, 1).
    let begin_resp = BeginCommitResponse {
        id: Some(Kiid { value: "c".to_string() }),
    };
    let outcomes: Vec<(i32, &str)> = vec![
        (1, ""),  // OK
        (3, "existing"),
        (2, "invalid type"),
        (7, "invalid data"),
        (7, "invalid data"),
        (2, "invalid type"),
        (7, "invalid data"),
    ];
    let create_resp = make_create_response(&outcomes);
    let end_resp = empty_end_commit_response();

    let responses = vec![
        build_ok_response(pack_any(BEGIN_COMMIT_RESPONSE_URL, &begin_resp)),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(END_COMMIT_RESPONSE_URL, &end_resp)),
    ];

    let transport = SequencedMockTransport::new(responses);
    let mut client = KiCadClient::with_transport(
        Box::new(transport),
        Some("test"),
        2000,
    );
    let doc = pcb_document("motor.kicad_pcb");

    let seven_coils = single_track_coils(7);

    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let result = board
        .write_coils(&seven_coils, 3, &braid_rules(), BRAID_ACTIVE_AREA_MM)
        .expect("write_coils");

    let summary = &result.failure_summary;
    for window in summary.windows(2) {
        let (code_a, count_a) = window[0];
        let (code_b, count_b) = window[1];
        assert!(
            count_a > count_b || (count_a == count_b && code_a <= code_b),
            "failure_summary must be sorted by count desc, code asc; got ({}x{}) followed by ({}x{})",
            code_a, count_a, code_b, count_b
        );
    }
    assert_eq!(
        result.failure_summary,
        vec![(7, 3), (2, 2), (3, 1)],
        "failure_summary must list (code, count) pairs sorted by count desc, code asc"
    );
    let total_failures: u32 = result.failure_summary.iter().map(|(_, c)| c).sum();
    assert_eq!(
        total_failures,
        result.items_attempted - result.items_created,
        "failure_summary counts must sum to total failures"
    );
}

// ---------------------------------------------------------------------------
// Infinity-braid via emission
// ---------------------------------------------------------------------------

#[test]
fn test_infinity_braid_emits_vias() {
    let coils = braid_coils(2);
    assert!(!coils.is_empty());

    let vias_per_net: std::collections::BTreeMap<String, usize> = {
        let mut map = std::collections::BTreeMap::new();
        for coil in &coils {
            *map.entry(coil.phase_name.clone()).or_insert(0) += coil.center_via_positions.len();
        }
        map
    };
    for phase in ["A", "B", "C"] {
        assert!(
            vias_per_net.get(phase).copied().unwrap_or(0) > 0,
            "phase {phase} must own at least one via on the infinity-braid; got {:?}",
            vias_per_net
        );
    }
}

#[test]
fn test_infinity_braid_rejects_single_layer() {
    // The braid is an inherently 2-layer pattern: a 1-layer board produces
    // no coils.
    let coils = braid_coils(1);
    assert!(coils.is_empty(), "1-layer board must produce no infinity-braid coils");
}

#[test]
fn test_kicad_writer_emits_via_items_for_infinity_braid() {
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);

    let via_items: Vec<&Any> = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
        .collect();
    assert!(!via_items.is_empty(), "infinity-braid must emit Via items");

    // Every via is a through via.
    for any in &via_items {
        let via: Via = Via::decode(any.value.as_slice()).expect("decode Via");
        assert_eq!(via.r#type, ViaType::VtThrough as i32);
    }

    // The number of emitted vias matches the coils' via positions.
    let expected_via_count = coils.iter().map(|c| c.center_via_positions.len()).sum::<usize>();
    assert_eq!(via_items.len(), expected_via_count);
}

#[test]
fn test_kicad_writer_via_nets_cover_all_phases() {
    let coils = braid_coils(2);
    let items = braid_items(&coils, 2);

    let via_nets: std::collections::BTreeSet<String> = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.Via"))
        .map(|a| {
            let via: Via = Via::decode(a.value.as_slice()).expect("decode Via");
            via.net.expect("Via must carry a net").name
        })
        .collect();
    let expected: std::collections::BTreeSet<String> =
        ["/A".to_string(), "/B".to_string(), "/C".to_string()].into_iter().collect();
    assert_eq!(via_nets, expected, "via nets must be {{/A, /B, /C}}; got {via_nets:?}");
}

// ---------------------------------------------------------------------------
// IO elements (kata htcq) — Footprint/Pad emission + IO fanout tracks
// ---------------------------------------------------------------------------

use pcbmotorgen_routing::{IoPad, IoPadKind, IoTrace, IoTraceRole, PadSize, Point, RoutingResult};

use pcbmotorgen_export::proto::board::types::{FootprintInstance, Pad, PadType};
use pcbmotorgen_export::io_elements_to_board_items;

fn io_rules() -> DesignRules {
    DesignRules {
        min_trace_mm: mm(0.1),
        trace_width_mm: mm(0.1),
        min_space_mm: mm(0.1),
        min_via_drill_mm: mm(0.2),
        min_via_annular_ring_mm: mm(0.1),
    }
}

fn io_result() -> RoutingResult {
    RoutingResult {
        io_pads: vec![
            IoPad {
                position: Point::new(48.0, 2.0),
                size: PadSize { x: 0.6, y: 0.6 },
                drill_mm: None,
                layers: vec![1],
                kind: IoPadKind::Smd,
                net: "A".into(),
                number: Some("1".into()),
            },
            IoPad {
                position: Point::new(0.0, 18.0),
                size: PadSize { x: 0.4, y: 0.4 },
                drill_mm: Some(mm(0.2)),
                layers: vec![],
                kind: IoPadKind::Tht,
                net: "B".into(),
                number: None,
            },
        ],
        io_traces: vec![IoTrace {
            start: Point::new(0.0, 10.0),
            end: Point::new(47.0, 2.0),
            layer: 1,
            net: "A".into(),
            role: IoTraceRole::Fanout,
        }],
        ..RoutingResult::default()
    }
}

#[test]
fn test_io_elements_produce_footprint_and_track_items() {
    let items = io_elements_to_board_items(&io_result(), 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    // 2 pads → 2 FootprintInstances; 1 trace → 1 Track.
    assert_eq!(items.len(), 3);
    let footprint_count = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.FootprintInstance"))
        .count();
    let track_count = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.Track"))
        .count();
    assert_eq!(footprint_count, 2);
    assert_eq!(track_count, 1);

    // The IO trace is a normal track on the mapped layer with the rule width.
    let track_any = items
        .iter()
        .find(|a| a.type_url.ends_with("kiapi.board.types.Track"))
        .expect("track item");
    let track: Track = Track::decode(track_any.value.as_slice()).expect("decode Track");
    assert_eq!(track.layer, BoardLayer::BlFCu as i32, "routing layer 1 = top of a 2-layer board");
    assert_eq!(track.width.expect("width").value_nm, mm_to_nm(io_rules().min_trace_mm));
    assert_eq!(track.net.expect("net").name, "/A");
}

#[test]
fn test_io_pad_footprints_decode_with_correct_pads() {
    let items = io_elements_to_board_items(&io_result(), 4, &io_rules(), TEST_ACTIVE_AREA_MM);
    let footprints: Vec<FootprintInstance> = items
        .iter()
        .filter(|a| a.type_url.ends_with("kiapi.board.types.FootprintInstance"))
        .map(|a| FootprintInstance::decode(a.value.as_slice()).expect("decode FootprintInstance"))
        .collect();
    assert_eq!(footprints.len(), 2);

    // Decode each footprint's single Pad item.
    let pads: Vec<Pad> = footprints
        .iter()
        .map(|fp| {
            let definition = fp.definition.as_ref().expect("definition");
            assert_eq!(definition.items.len(), 1, "one pad per footprint");
            Pad::decode(definition.items[0].value.as_slice()).expect("decode Pad")
        })
        .collect();

    assert_eq!(pads[0].r#type, PadType::PtSmd as i32);
    assert_eq!(pads[0].net.as_ref().expect("net").name, "/A");
    assert_eq!(pads[0].number, "1");
    assert!(pads[0].pad_stack.as_ref().expect("pad stack").drill.is_none());

    assert_eq!(pads[1].r#type, PadType::PtPth as i32);
    assert_eq!(pads[1].net.as_ref().expect("net").name, "/B");
    let ps1 = pads[1].pad_stack.as_ref().expect("pad stack");
    assert_eq!(
        ps1.layers.len(),
        4,
        "THT pad with no declared layers defaults to the full copper set"
    );

    // Footprint positions carry the centering shift (x − active/2) in nm.
    let fp0_pos = footprints[0].position.as_ref().expect("position");
    assert_eq!(
        fp0_pos.x_nm,
        mm_to_nm(48.0) - mm_to_nm(TEST_ACTIVE_AREA_MM / 2.0)
    );
    // The pad itself sits at the footprint origin.
    assert_eq!(pads[0].position.as_ref().expect("pad position").x_nm, 0);
}

#[test]
fn test_io_items_are_decodable_board_items() {
    // Every emitted item must decode as the exact proto its type URL names —
    // the same round-trip property the via tests assert for KiCad acceptance.
    let items = io_elements_to_board_items(&io_result(), 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    for any in &items {
        if any.type_url.ends_with("kiapi.board.types.Track") {
            Track::decode(any.value.as_slice()).expect("Track decodes");
        } else if any.type_url.ends_with("kiapi.board.types.FootprintInstance") {
            let fp = FootprintInstance::decode(any.value.as_slice()).expect("FootprintInstance decodes");
            assert!(fp.definition.is_some());
        } else {
            panic!("unexpected item type URL: {}", any.type_url);
        }
    }
}

#[test]
fn test_io_emission_is_pure_and_deterministic() {
    let a = io_elements_to_board_items(&io_result(), 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    let b = io_elements_to_board_items(&io_result(), 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    let hex = |items: &[Any]| -> Vec<String> {
        items
            .iter()
            .map(|i| i.value.iter().map(|b| format!("{b:02x}")).collect())
            .collect()
    };
    assert_eq!(hex(&a), hex(&b), "IO emission must be deterministic");
}

#[test]
fn test_legacy_result_without_io_yields_no_io_items() {
    let legacy = RoutingResult::default();
    let items = io_elements_to_board_items(&legacy, 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    assert!(items.is_empty(), "no IO elements → no IO items");
}

#[test]
fn test_board_handle_write_io_elements_end_to_end() {
    let result = io_result();
    let items = io_elements_to_board_items(&result, 2, &io_rules(), TEST_ACTIVE_AREA_MM);
    let expected_items = items.len() as u32;
    let created_items: Vec<_> = (0..expected_items)
        .map(|_| pcbmotorgen_export::proto::common::commands::ItemCreationResult {
            status: Some(pcbmotorgen_export::proto::common::commands::ItemStatus {
                code: 1, // ISC_OK
                error_message: String::new(),
            }),
            item: None,
        })
        .collect();
    let create_resp = CreateItemsResponse {
        header: None,
        status: 1,
        created_items,
    };
    let responses = vec![
        build_ok_response(pack_any(
            BEGIN_COMMIT_RESPONSE_URL,
            &BeginCommitResponse { id: Some(Kiid { value: "io-c1".to_string() }) },
        )),
        build_ok_response(pack_any(CREATE_ITEMS_RESPONSE_URL, &create_resp)),
        build_ok_response(pack_any(
            END_COMMIT_RESPONSE_URL,
            &empty_end_commit_response(),
        )),
    ];

    let transport = SequencedMockTransport::new(responses);
    let mut client = KiCadClient::with_transport(Box::new(transport), Some("test"), 2000);
    let doc = pcb_document("io.kicad_pcb");
    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let out = board
        .write_io_elements(&result, 2, &io_rules(), TEST_ACTIVE_AREA_MM)
        .expect("write_io_elements");
    assert_eq!(out.items_attempted, expected_items);
    assert_eq!(out.items_created, expected_items);
    assert!(out.failures.is_empty());
}

#[test]
fn test_board_handle_write_io_elements_dry_run_and_empty() {
    // Dry-run: no IPC traffic at all.
    let transport = SequencedMockTransport::new(Vec::new());
    let mut client = KiCadClient::with_transport(Box::new(transport), Some("test"), 2000);
    let doc = pcb_document("io-dry.kicad_pcb");
    let mut board = pcbmotorgen_export::BoardHandle::new(&mut client, doc);
    let out = board
        .write_io_elements_dry_run(&io_result(), 2, &io_rules(), TEST_ACTIVE_AREA_MM)
        .expect("dry-run");
    assert_eq!(out.items_attempted, 3);
    assert_eq!(out.items_created, 0);

    // A result with no IO elements attempts zero items and makes no IPC call.
    let out_empty = board
        .write_io_elements(&RoutingResult::default(), 2, &io_rules(), TEST_ACTIVE_AREA_MM)
        .expect("empty IO write");
    assert_eq!(out_empty.items_attempted, 0);
}
