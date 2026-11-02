//! `google.protobuf.Any` packing for KiCad board items.
//!
//! The packed items are consumed by `CreateItems`, so every emitted `Any`
//! carries the `type.googleapis.com/...` URL prefix defined in
//! [`super::TYPE_URL_PREFIX`].

use prost::Message;
use prost_types::Any;

use super::TYPE_URL_PREFIX;

/// Pack a prost message into a `google.protobuf.Any` with the given short
/// protobuf type name (e.g. `"kiapi.board.types.Track"`).
pub(crate) fn pack_any<T: Message>(full_name: &str, msg: &T) -> Any {
    let mut buf = Vec::new();
    msg.encode(&mut buf)
        .expect("encoding a KiCad board item should never fail");
    Any {
        type_url: format!("{TYPE_URL_PREFIX}/{full_name}"),
        value: buf,
    }
}
