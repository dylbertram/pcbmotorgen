//! KiCad IPC API client — NNG req/rep transport, protobuf envelope packing,
//! and transport abstraction for testing.
//!
//! ## Architecture
//! - [`KicadTransport`] trait abstracts the raw socket so tests can inject a
//!   [`MockTransport`].
//! - [`nng_transport::NngTransport`] is the production transport using the
//!   `nng` crate's `Req0` protocol over an IPC socket.
//! - [`KiCadClient`] is the high-level client that packs commands into
//!   `ApiRequest` envelopes, sends them via the transport, and unpacks
//!   `ApiResponse` replies into typed response messages.
//!
//! ## Submodules
//! - [`nng_transport`] — production NNG transport.
//! - [`mock_transport`] — [`MockTransport`] for offline testing.
//! - [`socket_path`] — default socket path resolution + client naming.

use std::fmt;

use prost::Message;
use prost_types::Any;

use crate::errors::KiCadError;
use crate::{
    ApiRequest, ApiRequestHeader, ApiResponse, ApiStatusCode,
};

mod mock_transport;
mod nng_transport;
mod socket_path;

pub use mock_transport::MockTransport;

use nng_transport::NngTransport;
use socket_path::{default_socket_path, random_client_name};

// ---------------------------------------------------------------------------
// KicadTransport trait
// ---------------------------------------------------------------------------

/// Transport abstraction for the KiCad IPC socket.
///
/// Implementations:
/// - [`nng_transport::NngTransport`] — production, uses the `nng` crate's
///   `Req0` protocol.
/// - [`MockTransport`] — testing, records sent bytes and returns canned
///   responses.
///
/// The default `connect` implementation is a no-op, suitable for transports
/// that don't need explicit connection management (e.g. the mock).
pub trait KicadTransport {
    /// Opens the transport connection.
    ///
    /// The default implementation is a no-op, suitable for transports that
    /// either connect lazily or don't need a connection at all (e.g.
    /// [`MockTransport`]).
    fn connect(&mut self) -> Result<(), KiCadError> {
        Ok(())
    }

    /// Sends `request_bytes` to KiCad and returns the raw reply bytes.
    fn send_and_recv(&mut self, request_bytes: &[u8]) -> Result<Vec<u8>, KiCadError>;
}

impl fmt::Debug for dyn KicadTransport {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("KicadTransport").finish()
    }
}

// ---------------------------------------------------------------------------
// KiCadClient
// ---------------------------------------------------------------------------

/// High-level KiCad IPC API client.
///
/// Wraps a [`KicadTransport`] and handles protobuf envelope packing/unpacking:
///
/// 1. Encodes the command into a [`prost_types::Any`] message.
/// 2. Builds an [`ApiRequest`] envelope with `kicad_token` and `client_name`.
/// 3. Serializes the envelope, sends it via the transport, receives the reply.
/// 4. Decodes the [`ApiResponse`], checks the status code, caches the token,
///    and unpacks the `Any` payload into the expected response type.
pub struct KiCadClient {
    transport: Box<dyn KicadTransport>,
    client_name: String,
    kicad_token: String,
    connected: bool,
}

impl KiCadClient {
    /// Creates a new client that will connect to the given socket path (or the
    /// default path resolved from `KICAD_API_SOCKET` / platform default).
    ///
    /// The `kicad_token` is read from the `KICAD_API_TOKEN` environment
    /// variable (empty string if unset). If `client_name` is `None`, a random
    /// name is generated.
    pub fn new(socket_path: Option<&str>, client_name: Option<&str>, timeout_ms: u32) -> Self {
        let socket_path = socket_path
            .map(String::from)
            .or_else(|| std::env::var("KICAD_API_SOCKET").ok())
            .unwrap_or_else(default_socket_path);

        let client_name = client_name
            .map(String::from)
            .unwrap_or_else(random_client_name);

        let kicad_token = std::env::var("KICAD_API_TOKEN").unwrap_or_default();

        let transport: Box<dyn KicadTransport> =
            Box::new(NngTransport::new(socket_path, timeout_ms));

        Self {
            transport,
            client_name,
            kicad_token,
            connected: false,
        }
    }

    /// Creates a client with a pre-injected transport (for testing).
    ///
    /// The supplied transport owns its timeout; the timeout argument is kept
    /// for API compatibility and does not modify an injected transport.
    /// The client starts in the "connected" state, so [`send`](Self::send) can
    /// be called immediately without calling [`connect`](Self::connect).
    pub fn with_transport(
        transport: Box<dyn KicadTransport>,
        client_name: Option<&str>,
        _timeout_ms: u32,
    ) -> Self {
        let client_name = client_name
            .map(String::from)
            .unwrap_or_else(random_client_name);

        let kicad_token = std::env::var("KICAD_API_TOKEN").unwrap_or_default();

        Self {
            transport,
            client_name,
            kicad_token,
            connected: true,
        }
    }

    /// Opens the NNG socket connection.
    ///
    /// If already connected, this is a no-op.
    pub fn connect(&mut self) -> Result<(), KiCadError> {
        if self.connected {
            return Ok(());
        }
        self.transport.connect()?;
        self.connected = true;
        Ok(())
    }

    /// Returns `true` if the client is connected.
    pub fn connected(&self) -> bool {
        self.connected
    }

    /// Returns the cached `kicad_token` (may be empty until a response is
    /// received from KiCad).
    pub fn kicad_token(&self) -> &str {
        &self.kicad_token
    }

    /// Returns the client name used in request headers.
    pub fn client_name(&self) -> &str {
        &self.client_name
    }

    /// Sends a command to KiCad and unpacks the response.
    ///
    /// ## Type parameters
    /// - `Cmd` — the command message type (must implement [`prost::Message`]).
    /// - `Resp` — the expected response message type (must implement
    ///   [`prost::Message`] + [`Default`]).
    ///
    /// ## Arguments
    /// - `type_url` — the protobuf type URL for the command, e.g.
    ///   `"type.googleapis.com/kiapi.common.commands.Ping"`.
    /// - `command` — the command message to send.
    ///
    /// ## Protocol
    /// 1. Encodes `command` to bytes and packs into [`prost_types::Any`].
    /// 2. Builds an [`ApiRequest`] envelope with the current `kicad_token` and
    ///    `client_name`.
    /// 3. Serializes the envelope, sends via [`KicadTransport::send_and_recv`].
    /// 4. Decodes the reply as [`ApiResponse`].
    /// 5. Checks `status.status == AS_OK`; returns [`KiCadError::Api`] on
    ///    non-OK status.
    /// 6. Caches `kicad_token` from the response header (if previously empty).
    /// 7. Unpacks `response.message` (Any) into `Resp` and returns it.
    pub fn send<Cmd, Resp>(
        &mut self,
        type_url: &str,
        command: &Cmd,
    ) -> Result<Resp, KiCadError>
    where
        Cmd: Message,
        Resp: Message + Default,
    {
        if !self.connected {
            self.connect()?;
        }

        // 1. Encode the command to bytes.
        let mut cmd_buf = Vec::new();
        command
            .encode(&mut cmd_buf)
            .map_err(|e| KiCadError::Protocol(format!("failed to encode command: {e}")))?;

        // 2. Pack into google.protobuf.Any.
        let any = Any {
            type_url: type_url.to_string(),
            value: cmd_buf,
        };

        // 3. Build the ApiRequest envelope.
        let request = ApiRequest {
            header: Some(ApiRequestHeader {
                kicad_token: self.kicad_token.clone(),
                client_name: self.client_name.clone(),
            }),
            message: Some(any),
        };

        // 4. Serialize the envelope.
        let mut req_bytes = Vec::new();
        request
            .encode(&mut req_bytes)
            .map_err(|e| KiCadError::Protocol(format!("failed to encode ApiRequest: {e}")))?;

        // 5. Send via transport and receive reply.
        let resp_bytes = self.transport.send_and_recv(&req_bytes)?;

        // 6. Decode the reply as ApiResponse.
        let response = ApiResponse::decode(resp_bytes.as_slice())
            .map_err(|e| KiCadError::Protocol(format!("failed to decode ApiResponse: {e}")))?;

        // 7. Check status code.
        let status = response.status.unwrap_or_default();
        if status.status != ApiStatusCode::AsOk as i32 {
            return Err(KiCadError::Api {
                code: status.status,
                message: status.error_message,
            });
        }

        // 8. Cache kicad_token from response header (if previously empty).
        if let Some(header) = &response.header {
            if self.kicad_token.is_empty() {
                self.kicad_token = header.kicad_token.clone();
            }
        }

        // 9. Unpack the Any payload into the expected Resp type.
        let any = response.message.ok_or_else(|| {
            KiCadError::Protocol("response message (Any) is None".to_string())
        })?;
        let resp = Resp::decode(any.value.as_slice())
            .map_err(|e| KiCadError::Protocol(format!("failed to decode response: {e}")))?;

        Ok(resp)
    }
}

// ---------------------------------------------------------------------------
// Tests (client construction + codec smoke tests)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// `with_transport` starts in the connected state and honours an
    /// explicit client name (covers the construction path that the
    /// integration tests rely on).
    #[test]
    fn test_client_with_transport_starts_connected() {
        let client = KiCadClient::with_transport(
            Box::new(MockTransport::new(Vec::new())),
            Some("test-client"),
            2000,
        );
        assert!(client.connected(), "with_transport must start connected");
        assert_eq!(client.client_name(), "test-client");
        assert!(client.kicad_token().is_empty());
    }

    /// `MockTransport` must be usable as the trait object backing a
    /// client: a `send` returns the canned bytes decoded as `Resp`.
    #[test]
    fn test_client_send_decodes_canned_response() {
        use crate::proto::common::commands::{EndCommitResponse, Ping};

        let response = crate::ApiResponse {
            header: None,
            status: Some(crate::ApiResponseStatus {
                status: ApiStatusCode::AsOk as i32,
                error_message: String::new(),
            }),
            message: Some(Any {
                type_url: "type.googleapis.com/kiapi.common.commands.Ping".to_string(),
                value: Vec::new(), // Empty message encodes to zero bytes
            }),
        };
        let mut resp_bytes = Vec::new();
        response.encode(&mut resp_bytes).expect("encode envelope");

        let mut client = KiCadClient::with_transport(
            Box::new(MockTransport::new(resp_bytes)),
            Some("test-client"),
            2000,
        );
        let resp: EndCommitResponse = client
            .send("type.googleapis.com/kiapi.common.commands.Ping", &Ping {})
            .expect("send");
        let _ = resp;
    }
}
