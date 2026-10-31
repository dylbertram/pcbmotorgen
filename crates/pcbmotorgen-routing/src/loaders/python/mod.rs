//! Python runner routing-pattern loader.
//!
//! # Runner contract
//!
//! A Python runner is a `.py` script that:
//!
//! 1. Reads a JSON object from **stdin** — the flattened [`RoutingContext`]
//!    (the fields of the context plus numeric `params`).
//! 2. Emits a strict `RoutingResult` JSON object to **stdout** (see
//!    [`RoutingResult`]); nothing else may be printed to stdout.
//!
//! The emitted JSON is deserialised into [`RoutingResult`] and then run through
//! the **same** [`Validator`](crate::validator::Validator) as any other source —
//! a Python pattern cannot bypass any shape rule. Malformed output is rejected
//! with the validator's field-level error.
//!
//! The implementation is split across:
//! - the [`PythonRunnerPattern`] wrapper (this module),
//! - [runner](self::runner) — spawning the script and parsing its output,
//! - [metadata](self::metadata) — the optional `--metadata` fetch.

mod metadata;
mod runner;

use std::path::PathBuf;

use crate::context::RoutingContext;
use crate::error::RoutingError;
use crate::model::RoutingResult;
use crate::pattern::{PatternParameter, PluginMetadata, RoutingPattern};

use self::runner::run_python_runner;

pub use self::metadata::{python_metadata, RunnerMeta};

/// A [`RoutingPattern`] backed by a Python runner script.
///
/// Each `generate` call executes the runner with the given context on stdin and
/// parses/returns its `RoutingResult`. The result is validated by the caller —
/// a Python pattern can never bypass the strict-shape gate.
///
/// Metadata (author, version, description, parameters) is read from the runner
/// by invoking it with the `--metadata` argument (see [`python_metadata`]).
#[derive(Debug, Clone)]
pub struct PythonRunnerPattern {
    script: PathBuf,
    id: String,
    display_name: String,
    author: String,
    version: String,
    description: String,
    parameters: Vec<PatternParameter>,
    min_layers: Option<u32>,
    max_layers: Option<u32>,
    layers_multiple_of: Option<u32>,
    end_type: Option<crate::pattern::GeneratorEndType>,
}

impl PythonRunnerPattern {
    /// Create a runner pattern from a `.py` script.
    ///
    /// `id` is the registry key (e.g. `"my-runner"`); `script` is the runner
    /// path.
    pub fn new(id: impl Into<String>, display_name: impl Into<String>, script: impl Into<PathBuf>) -> Self {
        Self {
            script: script.into(),
            id: id.into(),
            display_name: display_name.into(),
            author: String::new(),
            version: String::new(),
            description: String::new(),
            parameters: Vec::new(),
            min_layers: None,
            max_layers: None,
            layers_multiple_of: None,
            end_type: None,
        }
    }

    /// Load a runner from a script path, deriving the id from the file stem.
    pub fn from_script(script: impl Into<PathBuf>) -> Self {
        let path = script.into();
        let stem = path
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "python-runner".to_string());
        Self::new(stem.clone(), stem, path)
    }

    /// Populate metadata from a fetched [`PluginMetadata`] block.
    pub fn set_metadata(&mut self, m: &PluginMetadata) {
        if !m.display_name.is_empty() {
            self.display_name = m.display_name.clone();
        }
        if !m.author.is_empty() {
            self.author = m.author.clone();
        }
        if !m.version.is_empty() {
            self.version = m.version.clone();
        }
        if !m.description.is_empty() {
            self.description = m.description.clone();
        }
        self.min_layers = m.min_layers;
        self.max_layers = m.max_layers;
        self.layers_multiple_of = m.layers_multiple_of;
        self.end_type = m.end_type.clone();
    }

    /// Populate the declared parameter schema.
    pub fn set_parameters(&mut self, params: Vec<PatternParameter>) {
        self.parameters = params;
    }
}

impl RoutingPattern for PythonRunnerPattern {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            id: self.id.clone(),
            display_name: self.display_name.clone(),
            author: self.author.clone(),
            version: self.version.clone(),
            description: self.description.clone(),
            min_layers: self.min_layers,
            max_layers: self.max_layers,
            layers_multiple_of: self.layers_multiple_of,
            end_type: self.end_type.clone(),
        }
    }

    fn id(&self) -> &str {
        &self.id
    }

    fn display_name(&self) -> &str {
        &self.display_name
    }

    fn author(&self) -> &str {
        &self.author
    }

    fn version(&self) -> &str {
        &self.version
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn parameters(&self) -> Vec<PatternParameter> {
        self.parameters.clone()
    }

    fn min_layers(&self) -> Option<u32> {
        self.min_layers
    }

    fn max_layers(&self) -> Option<u32> {
        self.max_layers
    }

    fn layers_multiple_of(&self) -> Option<u32> {
        self.layers_multiple_of
    }

    fn generate(&self, ctx: &RoutingContext) -> Result<RoutingResult, RoutingError> {
        run_python_runner(&self.script, ctx)
    }
}
