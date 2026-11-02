//! High-level handle to an open KiCad board document.
//!
//! [`BoardHandle`] wraps a borrowed [`KiCadClient`] and a target
//! [`DocumentSpecifier`] (the open board). It provides convenience methods for
//! querying board properties and writing coil geometry atomically.
//!
//! ## Submodules
//! - [`edge_bbox`] — pure edge-cut bounding-box math (no IPC) backing
//!   [`BoardHandle::get_edge_cut_bbox_mm`].
//! - [`write`] — coil-writing orchestration under `BoardHandle` (real write
//!   + dry-run).
//! - [`tally`] — pure per-item failure tallying for write results.

use crate::errors::KiCadError;
use crate::proto::common::types::document_specifier::Identifier;
use crate::proto::common::types::DocumentSpecifier;
use crate::KiCadClient;

mod edge_bbox;
mod tally;
mod write;

// Type URLs for board-level queries.
const GET_BOARD_ENABLED_LAYERS_TYPE_URL: &str =
    "type.googleapis.com/kiapi.board.commands.GetBoardEnabledLayers";
const GET_NETS_TYPE_URL: &str = "type.googleapis.com/kiapi.board.commands.GetNets";
const GET_NET_CLASS_FOR_NETS_TYPE_URL: &str =
    "type.googleapis.com/kiapi.board.commands.GetNetClassForNets";
const GET_ITEMS_TYPE_URL: &str = "type.googleapis.com/kiapi.common.commands.GetItems";
const GET_BOARD_ORIGIN_TYPE_URL: &str =
    "type.googleapis.com/kiapi.board.commands.GetBoardOrigin";

/// KiCad `ItemStatusCode::ISC_OK` (from the `.proto` enum). Per-item
/// `ItemStatus.code == ISC_OK` is the only success indicator — the outer
/// `ItemRequestStatus` reports the *request* status, not the per-item
/// outcomes.
const ITEM_STATUS_OK: i32 = 1;

/// Maximum number of per-item failure messages to surface to the caller.
///
/// Set high enough that, for any realistic failure count, every individual
/// rejection message fits in the IPC response. The previous value of 10
/// silently dropped 89 of the user's 99 failures — the user only saw the
/// first 10 strings and had no way to know what the other 89 were
/// (grouped by error code, message shape, etc.). 1000 is effectively
/// unbounded for any real KiCad write (a typical coil set has a few
/// hundred items at most; even a worst-case 50k-item write would
/// only hit the cap if *every* item failed, in which case the cap is
/// the right behaviour to keep the IPC payload bounded).
const MAX_FAILURES_TO_REPORT: usize = 1000;

/// Result of a [`BoardHandle::write_coils`] call.
///
/// `items_attempted` is the number of items we sent to KiCad;
/// `items_created` is the number KiCad actually accepted (i.e. returned
/// `ISC_OK` in their `ItemStatus`). The two can differ if KiCad rejects
/// individual items (e.g. invalid data, missing layer).
///
/// `failures` contains the first [`MAX_FAILURES_TO_REPORT`] rejection
/// messages verbatim. The total failure count is always recoverable as
/// `items_attempted - items_created`, even if some were truncated.
///
/// `failure_summary` is a compact, **code-grouped** summary of all
/// rejections (not just the surfaced ones): each entry is `(code, count)`
/// where `code` is the `ItemStatus.code` value KiCad returned (e.g. 7 for
/// `ISC_INVALID_DATA`, 2 for `ISC_INVALID_TYPE`) and `count` is the
/// number of items rejected with that code. This is the most useful
/// diagnostic for the UI: instead of listing 99 individual messages that
/// all say the same thing, the UI can render
/// `"99× code=7 (no overlapping layers with the board)"` and the user
/// immediately sees the root cause. Sorted by `(code, count)` descending
/// so the most common failure appears first.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WriteCoilsResult {
    pub items_attempted: u32,
    pub items_created: u32,
    pub failures: Vec<String>,
    /// `(ItemStatus.code, count)` pairs, one entry per distinct
    /// rejection code seen. Sorted by count descending (most-frequent
    /// failure first); ties broken by `code` ascending. Empty when
    /// `items_created == items_attempted`.
    pub failure_summary: Vec<(i32, u32)>,
}

/// Result of a [`BoardHandle::get_edge_cut_bbox_mm`] call: the axis-aligned
/// bounding box of the board's edge-cut graphics, in millimetres.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BoardBBoxMm {
    pub x_min_mm: f64,
    pub y_min_mm: f64,
    pub x_max_mm: f64,
    pub y_max_mm: f64,
}

/// High-level handle to the open board document.
pub struct BoardHandle<'a> {
    client: &'a mut KiCadClient,
    document: DocumentSpecifier,
}

impl<'a> BoardHandle<'a> {
    /// Create a handle bound to the given document.
    pub fn new(client: &'a mut KiCadClient, document: DocumentSpecifier) -> Self {
        Self { client, document }
    }

    /// Returns a reference to the underlying document specifier.
    pub fn document(&self) -> &DocumentSpecifier {
        &self.document
    }

    /// Get the board name (filename), e.g. `"board.kicad_pcb"`.
    pub fn name(&self) -> Result<String, KiCadError> {
        match &self.document.identifier {
            Some(Identifier::BoardFilename(name)) => Ok(name.clone()),
            _ => Err(KiCadError::Protocol(
                "document is not a PCB (no board_filename identifier)".to_string(),
            )),
        }
    }

    /// Get the number of copper layers in the board.
    ///
    /// Sends a `GetBoardEnabledLayers` command and reads
    /// `BoardEnabledLayersResponse.copper_layer_count`.
    pub fn get_copper_layer_count(&mut self) -> Result<u32, KiCadError> {
        use crate::proto::board::commands::{
            BoardEnabledLayersResponse, GetBoardEnabledLayers,
        };

        let cmd = GetBoardEnabledLayers {
            board: Some(self.document.clone()),
        };
        let resp: BoardEnabledLayersResponse = self
            .client
            .send::<GetBoardEnabledLayers, BoardEnabledLayersResponse>(
                GET_BOARD_ENABLED_LAYERS_TYPE_URL,
                &cmd,
            )?;
        Ok(resp.copper_layer_count)
    }

    /// Get the names of all nets on the board.
    ///
    /// Sends a `GetNets` command (no netclass filter). Nets reported with an
    /// empty name are skipped — they carry no class information.
    pub fn get_net_names(&mut self) -> Result<Vec<String>, KiCadError> {
        use crate::proto::board::commands::{GetNets, NetsResponse};

        let cmd = GetNets {
            board: Some(self.document.clone()),
            netclass_filter: Vec::new(),
        };
        let resp: NetsResponse = self.client.send::<GetNets, NetsResponse>(GET_NETS_TYPE_URL, &cmd)?;
        Ok(resp
            .nets
            .into_iter()
            .map(|net| net.name)
            .filter(|name| !name.is_empty())
            .collect())
    }

    /// Get the distinct net classes effectively in use by the given nets,
    /// sorted alphabetically.
    ///
    /// Sends a `GetNetClassForNets` command, which returns the
    /// **effective/merged** netclass for each net (a net may belong to several
    /// classes with a priority ordering; KiCad merges them into one composite
    /// class). This is therefore the set of classes *in use on the board*, not
    /// the project's full netclass list — a class with no nets assigned does
    /// not appear (the IPC has no global netclass listing command).
    ///
    /// Composite (implicit) classes have an empty `name`; their constituent
    /// explicit class names are surfaced instead.
    pub fn get_effective_net_classes(
        &mut self,
        net_names: &[String],
    ) -> Result<Vec<String>, KiCadError> {
        use crate::proto::board::commands::{GetNetClassForNets, NetClassForNetsResponse};
        use crate::proto::board::types::Net;
        use std::collections::BTreeSet;

        if net_names.is_empty() {
            return Ok(Vec::new());
        }

        let cmd = GetNetClassForNets {
            net: net_names
                .iter()
                .map(|name| Net {
                    code: None,
                    name: name.clone(),
                })
                .collect(),
        };
        let resp: NetClassForNetsResponse = self
            .client
            .send::<GetNetClassForNets, NetClassForNetsResponse>(
                GET_NET_CLASS_FOR_NETS_TYPE_URL,
                &cmd,
            )?;

        let mut names = BTreeSet::new();
        for class in resp.classes.into_values() {
            if !class.name.is_empty() {
                names.insert(class.name);
            } else {
                // Composite (implicit) netclass: no name of its own; report
                // the explicit classes it merges.
                names.extend(class.constituents.into_iter().filter(|c| !c.is_empty()));
            }
        }
        Ok(names.into_iter().collect())
    }

    /// Get the bounding box of the board's edge-cut graphics [mm].
    ///
    /// Sends a `GetItems` command restricted to `KOT_PCB_SHAPE`, filters the
    /// returned graphics down to the `Edge.Cuts` layer, and computes the
    /// axis-aligned bounding box client-side (exact math, including arc axis
    /// extremes and bezier interior extrema — see [`edge_bbox`]).
    ///
    /// Returns `Ok(None)` when the board has no edge-cut graphics. Note that
    /// edge-cut graphics *inside footprints* are not returned by `GetItems`
    /// at the top level and are therefore not part of this box.
    pub fn get_edge_cut_bbox_mm(&mut self) -> Result<Option<BoardBBoxMm>, KiCadError> {
        use crate::board::edge_bbox::edge_cut_bbox_nm;
        use crate::proto::board::types::BoardGraphicShape;
        use crate::proto::common::commands::{GetItems, GetItemsResponse};
        use crate::proto::common::types::{ItemHeader, KiCadObjectType, ItemRequestStatus};
        use prost::Message;

        let cmd = GetItems {
            header: Some(ItemHeader {
                document: Some(self.document.clone()),
                container: None,
                field_mask: None,
            }),
            types: vec![KiCadObjectType::KotPcbShape as i32],
        };
        let resp: GetItemsResponse = self.client.send::<GetItems, GetItemsResponse>(
            GET_ITEMS_TYPE_URL,
            &cmd,
        )?;
        if resp.status != ItemRequestStatus::IrsOk as i32 {
            return Err(KiCadError::Protocol(format!(
                "GetItems failed with ItemRequestStatus {}",
                resp.status
            )));
        }

        let shapes: Vec<BoardGraphicShape> = resp
            .items
            .iter()
            .filter_map(|any| BoardGraphicShape::decode(any.value.as_slice()).ok())
            .collect();

        const NM_PER_MM: f64 = 1e6;
        Ok(edge_cut_bbox_nm(&shapes).map(|b| BoardBBoxMm {
            x_min_mm: b.x_min / NM_PER_MM,
            y_min_mm: b.y_min / NM_PER_MM,
            x_max_mm: b.x_max / NM_PER_MM,
            y_max_mm: b.y_max / NM_PER_MM,
        }))
    }

    /// Get the board's grid or drill/place-file origin point [nm].
    ///
    /// Sends a `GetBoardOrigin` command. Note this returns a *single point*
    /// (the requested origin type), not board bounds — there is no IPC command
    /// for the edge-cut bounding box, which is instead derived from
    /// [`BoardHandle::get_edge_cut_bbox_mm`].
    pub fn get_board_origin(
        &mut self,
        origin_type: crate::proto::board::commands::BoardOriginType,
    ) -> Result<crate::proto::common::types::Vector2, KiCadError> {
        use crate::proto::board::commands::GetBoardOrigin;
        use crate::proto::common::types::Vector2;

        let cmd = GetBoardOrigin {
            board: Some(self.document.clone()),
            r#type: origin_type as i32,
        };
        self.client
            .send::<GetBoardOrigin, Vector2>(GET_BOARD_ORIGIN_TYPE_URL, &cmd)
    }
}

// ---------------------------------------------------------------------------
// Tests (query methods)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::board::commands::{BoardOriginType, NetClassForNetsResponse, NetsResponse};
    use crate::proto::board::types::Net;
    use crate::proto::common::commands::GetItemsResponse;
    use crate::proto::common::project::NetClass;
    use crate::proto::common::types::DocumentType;
    use prost::Message;
    use prost_types::Any;

    fn pcb_document() -> DocumentSpecifier {
        DocumentSpecifier {
            r#type: DocumentType::DoctypePcb as i32,
            identifier: Some(Identifier::BoardFilename("motor.kicad_pcb".to_string())),
            project: None,
        }
    }

    /// Builds an `ApiResponse` envelope with AS_OK and the given payload.
    fn ok_response(payload: Any) -> Vec<u8> {
        let response = crate::ApiResponse {
            header: None,
            status: Some(crate::ApiResponseStatus {
                status: crate::ApiStatusCode::AsOk as i32,
                error_message: String::new(),
            }),
            message: Some(payload),
        };
        let mut buf = Vec::new();
        response.encode(&mut buf).expect("encode envelope");
        buf
    }

    fn pack_any<T: Message>(type_url: &str, msg: &T) -> Any {
        let mut buf = Vec::new();
        msg.encode(&mut buf).expect("encode message");
        Any {
            type_url: type_url.to_string(),
            value: buf,
        }
    }

    /// Client bound to a mock returning `response_bytes` for every send.
    fn mock_client(response_bytes: Vec<u8>) -> KiCadClient {
        KiCadClient::with_transport(
            Box::new(crate::MockTransport::new(response_bytes)),
            Some("test"),
            2000,
        )
    }

    #[test]
    fn test_board_handle_query_methods() {
        let mut client = mock_client(Vec::new());
        let board = BoardHandle::new(&mut client, pcb_document());
        assert_eq!(board.name().expect("name"), "motor.kicad_pcb");
        assert!(matches!(
            board.document().identifier,
            Some(Identifier::BoardFilename(_))
        ));
    }

    #[test]
    fn test_board_handle_name_errors_for_non_pcb() {
        let mut client = mock_client(Vec::new());
        let doc = DocumentSpecifier {
            r#type: DocumentType::DoctypeSchematic as i32,
            identifier: None,
            project: None,
        };
        let board = BoardHandle::new(&mut client, doc);
        assert!(board.name().is_err());
    }

    #[test]
    fn test_get_net_names_returns_names_and_skips_empty() {
        const NETS_RESPONSE_URL: &str =
            "type.googleapis.com/kiapi.board.commands.NetsResponse";
        let resp = NetsResponse {
            nets: vec![
                Net { code: None, name: "/A".into() },
                Net { code: None, name: String::new() },
                Net { code: None, name: "GND".into() },
            ],
        };
        let mut client = mock_client(ok_response(pack_any(NETS_RESPONSE_URL, &resp)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let nets = board.get_net_names().expect("get_net_names");
        assert_eq!(nets, vec!["/A".to_string(), "GND".to_string()]);
    }

    #[test]
    fn test_get_effective_net_classes_sorted_deduped() {
        const NETCLASS_RESPONSE_URL: &str =
            "type.googleapis.com/kiapi.board.commands.NetClassForNetsResponse";
        let mut classes = std::collections::HashMap::new();
        classes.insert(
            "/A".to_string(),
            NetClass {
                name: "Default".into(),
                ..NetClass::default()
            },
        );
        classes.insert(
            "/B".to_string(),
            NetClass {
                name: "Motor".into(),
                ..NetClass::default()
            },
        );
        classes.insert(
            "/C".to_string(),
            NetClass {
                name: "Motor".into(),
                ..NetClass::default()
            },
        );
        let resp = NetClassForNetsResponse { classes };
        let mut client = mock_client(ok_response(pack_any(NETCLASS_RESPONSE_URL, &resp)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let names = board
            .get_effective_net_classes(&["/A".into(), "/B".into(), "/C".into()])
            .expect("get_effective_net_classes");
        assert_eq!(names, vec!["Default".to_string(), "Motor".to_string()]);
    }

    #[test]
    fn test_get_effective_net_classes_composite_uses_constituents() {
        const NETCLASS_RESPONSE_URL: &str =
            "type.googleapis.com/kiapi.board.commands.NetClassForNetsResponse";
        let mut classes = std::collections::HashMap::new();
        classes.insert(
            "/A".to_string(),
            NetClass {
                name: String::new(), // composite/implicit class
                constituents: vec!["Power".into(), String::new(), "Motor".into()],
                ..NetClass::default()
            },
        );
        let resp = NetClassForNetsResponse { classes };
        let mut client = mock_client(ok_response(pack_any(NETCLASS_RESPONSE_URL, &resp)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let names = board
            .get_effective_net_classes(&["/A".into()])
            .expect("get_effective_net_classes");
        // Sorted, empty constituents dropped.
        assert_eq!(names, vec!["Motor".to_string(), "Power".to_string()]);
    }

    #[test]
    fn test_get_effective_net_classes_empty_input_sends_nothing() {
        let mut client = mock_client(Vec::new());
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let names = board.get_effective_net_classes(&[]).expect("empty input");
        assert!(names.is_empty());
    }

    #[test]
    fn test_get_edge_cut_bbox_mm_returns_box() {
        use crate::board::edge_bbox::BBoxNm;

        const ITEMS_RESPONSE_URL: &str =
            "type.googleapis.com/kiapi.common.commands.GetItemsResponse";
        const SHAPE_URL: &str = "type.googleapis.com/kiapi.board.types.BoardGraphicShape";

        // One edge-cut segment: (1 mm, 2 mm) → (4 mm, 6 mm).
        let shape = crate::proto::board::types::BoardGraphicShape {
            shape: Some(crate::proto::common::types::GraphicShape {
                attributes: None,
                geometry: Some(crate::proto::common::types::graphic_shape::Geometry::Segment(
                    crate::proto::common::types::GraphicSegmentAttributes {
                        start: Some(crate::proto::common::types::Vector2 {
                            x_nm: 1_000_000,
                            y_nm: 2_000_000,
                        }),
                        end: Some(crate::proto::common::types::Vector2 {
                            x_nm: 4_000_000,
                            y_nm: 6_000_000,
                        }),
                    },
                )),
            }),
            layer: crate::proto::board::types::BoardLayer::BlEdgeCuts as i32,
            net: None,
            id: None,
            locked: 0,
        };
        let resp = GetItemsResponse {
            header: None,
            status: crate::proto::common::types::ItemRequestStatus::IrsOk as i32,
            items: vec![pack_any(SHAPE_URL, &shape)],
        };
        let mut client = mock_client(ok_response(pack_any(ITEMS_RESPONSE_URL, &resp)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let bbox = board.get_edge_cut_bbox_mm().expect("bbox").expect("some");
        let expected_mm = BBoxNm {
            x_min: 1.0e6,
            y_min: 2.0e6,
            x_max: 4.0e6,
            y_max: 6.0e6,
        };
        let to_mm = |b: BBoxNm| BoardBBoxMm {
            x_min_mm: b.x_min / 1e6,
            y_min_mm: b.y_min / 1e6,
            x_max_mm: b.x_max / 1e6,
            y_max_mm: b.y_max / 1e6,
        };
        assert_eq!(bbox, to_mm(expected_mm));
    }

    #[test]
    fn test_get_edge_cut_bbox_mm_none_when_no_shapes() {
        const ITEMS_RESPONSE_URL: &str =
            "type.googleapis.com/kiapi.common.commands.GetItemsResponse";
        let resp = GetItemsResponse {
            header: None,
            status: crate::proto::common::types::ItemRequestStatus::IrsOk as i32,
            items: Vec::new(),
        };
        let mut client = mock_client(ok_response(pack_any(ITEMS_RESPONSE_URL, &resp)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        assert_eq!(board.get_edge_cut_bbox_mm().expect("bbox"), None);
    }

    #[test]
    fn test_get_board_origin_returns_vector2() {
        const ORIGIN_RESPONSE_URL: &str = "type.googleapis.com/kiapi.common.types.Vector2";
        let origin = crate::proto::common::types::Vector2 { x_nm: 5, y_nm: -7 };
        let mut client = mock_client(ok_response(pack_any(ORIGIN_RESPONSE_URL, &origin)));
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let got = board
            .get_board_origin(BoardOriginType::BotGrid)
            .expect("get_board_origin");
        assert_eq!((got.x_nm, got.y_nm), (5, -7));
    }

    #[test]
    fn test_query_failure_surfaces_kicad_error() {
        // A non-OK envelope (e.g. KiCad without the handler → AS_UNHANDLED)
        // must surface as KiCadError::Api, not a placeholder.
        let response = crate::ApiResponse {
            header: None,
            status: Some(crate::ApiResponseStatus {
                status: crate::ApiStatusCode::AsUnhandled as i32,
                error_message: "no handler".into(),
            }),
            message: None,
        };
        let mut buf = Vec::new();
        response.encode(&mut buf).expect("encode envelope");
        let mut client = mock_client(buf);
        let mut board = BoardHandle::new(&mut client, pcb_document());
        let err = board.get_net_names().expect_err("must fail");
        assert!(matches!(err, KiCadError::Api { .. }));
        // The failure response also serves as the negative path for bbox
        // queries.
        let err = board.get_edge_cut_bbox_mm().expect_err("must fail");
        assert!(matches!(err, KiCadError::Api { .. }));
    }
}
