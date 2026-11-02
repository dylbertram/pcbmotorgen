//! Atomic commit handle for the KiCad IPC API.
//!
//! All items created between [`Commit::begin`] and [`Commit::end`] appear as a
//! single Ctrl+Z undo step in the KiCad PCB editor. This mirrors the
//! `BeginCommit` / `CreateItems` / `EndCommit` sequence described in the
//! KiCad IPC API.

use prost_types::Any;

use crate::errors::KiCadError;
use crate::proto::common::commands::{
    BeginCommit, BeginCommitResponse, CommitAction, CreateItems, CreateItemsResponse, EndCommit,
    EndCommitResponse,
};
use crate::proto::common::types::{DocumentSpecifier, ItemHeader, Kiid};
use crate::KiCadClient;

/// Type URLs for the commit-related commands.
const BEGIN_COMMIT_TYPE_URL: &str = "type.googleapis.com/kiapi.common.commands.BeginCommit";
const END_COMMIT_TYPE_URL: &str = "type.googleapis.com/kiapi.common.commands.EndCommit";
const CREATE_ITEMS_TYPE_URL: &str = "type.googleapis.com/kiapi.common.commands.CreateItems";

/// Commit message shown in the KiCad undo stack.
const COMMIT_MESSAGE: &str = "pcbmotorgen coil generation";

/// An atomic commit — all items created between `begin` and `end` appear as a
/// single Ctrl+Z undo step in the KiCad PCB editor.
///
/// Borrows the [`KiCadClient`] mutably for the lifetime of the commit so that
/// `create_items` calls can be batched into the same commit.
pub struct Commit<'a> {
    client: &'a mut KiCadClient,
    commit_id: Kiid,
}

impl<'a> Commit<'a> {
    /// Begin a new atomic commit.
    ///
    /// Sends a `BeginCommit` command and stores the returned commit ID.
    pub fn begin(client: &'a mut KiCadClient) -> Result<Self, KiCadError> {
        let resp: BeginCommitResponse =
            client.send(BEGIN_COMMIT_TYPE_URL, &BeginCommit {})?;
        let commit_id = resp.id.unwrap_or_default();
        Ok(Self { client, commit_id })
    }

    /// Create items within this commit.
    ///
    /// Builds a `CreateItems` command targeting `document` with the given
    /// `Any`-wrapped items and sends it.
    pub fn create_items(
        &mut self,
        items: &[Any],
        document: &DocumentSpecifier,
    ) -> Result<CreateItemsResponse, KiCadError> {
        let cmd = CreateItems {
            header: Some(ItemHeader {
                document: Some(document.clone()),
                container: None,
                field_mask: None,
            }),
            items: items.to_vec(),
            container: None,
        };
        self.client
            .send::<CreateItems, CreateItemsResponse>(CREATE_ITEMS_TYPE_URL, &cmd)
    }

    /// End the commit, finalising it in KiCad (single Ctrl+Z step).
    ///
    /// Sends `EndCommit` with `CMA_COMMIT` and the commit message.
    pub fn end(self) -> Result<(), KiCadError> {
        let cmd = EndCommit {
            id: Some(self.commit_id),
            action: CommitAction::CmaCommit as i32,
            message: COMMIT_MESSAGE.to_string(),
        };
        let _resp: EndCommitResponse =
            self.client
                .send::<EndCommit, EndCommitResponse>(END_COMMIT_TYPE_URL, &cmd)?;
        Ok(())
    }

    /// Abort the commit, dropping pending changes.
    ///
    /// Sends `EndCommit` with `CMA_DROP` and an empty message.
    pub fn abort(self) -> Result<(), KiCadError> {
        let cmd = EndCommit {
            id: Some(self.commit_id),
            action: CommitAction::CmaDrop as i32,
            message: String::new(),
        };
        let _resp: EndCommitResponse =
            self.client
                .send::<EndCommit, EndCommitResponse>(END_COMMIT_TYPE_URL, &cmd)?;
        Ok(())
    }

    /// Returns the opaque commit ID assigned by KiCad.
    pub fn commit_id(&self) -> &Kiid {
        &self.commit_id
    }
}
