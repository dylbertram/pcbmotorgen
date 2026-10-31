//! Optional `--metadata` fetch for Python runners.

use std::process::{Command, Stdio};

use crate::pattern::PatternParameter;

/// Fetch a Python runner's metadata by invoking it with `--metadata`.
///
/// The runner contract: when run with the `--metadata` argument, print a
/// strictly-formatted [`RunnerMeta`] JSON object to stdout and exit 0. If the
/// runner does not implement this (non-zero exit / invalid JSON), `Ok(None)` is
/// returned so the caller can fall back to defaults — a missing optional
/// metadata block is never fatal.
pub fn python_metadata(script: &std::path::Path) -> Result<Option<RunnerMeta>, String> {
    let output = Command::new("python3")
        .arg(script)
        .arg("--metadata")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("failed to run {}: {e}", script.display()))?;

    if !output.status.success() {
        return Ok(None);
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    match serde_json::from_str::<RunnerMeta>(stdout.trim()) {
        Ok(m) => Ok(Some(m)),
        Err(_) => Ok(None),
    }
}

/// Strict metadata block a Python runner may emit in `--metadata` mode.
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct RunnerMeta {
    #[serde(default)]
    pub end_type: Option<crate::pattern::GeneratorEndType>,
    /// Stable id (registry key). Falls back to the file stem if empty.
    #[serde(default)]
    pub id: String,
    /// Display name.
    #[serde(default)]
    pub display_name: String,
    /// Author.
    #[serde(default)]
    pub author: String,
    /// Semantic version.
    #[serde(default)]
    pub version: String,
    /// One-line description.
    #[serde(default)]
    pub description: String,
    /// Declared user-editable parameters.
    #[serde(default)]
    pub parameters: Vec<PatternParameter>,
    /// Optional declared layer-range metadata (`None` = unconstrained).
    #[serde(default)]
    pub min_layers: Option<u32>,
    #[serde(default)]
    pub max_layers: Option<u32>,
    #[serde(default)]
    pub layers_multiple_of: Option<u32>,
}
