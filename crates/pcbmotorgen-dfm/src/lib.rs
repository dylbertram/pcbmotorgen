//! # pcbmotorgen-dfm
//!
//! Design-for-manufacturing (DFM) rules and diagnostics, extracted from the
//! routing crate (kata 0rgs) so that manufacturability is a **downstream**
//! concern: any routing is allowed in the generator, and DFM is checked
//! later, downstream, as diagnostics only.
//!
//! This crate owns:
//!
//! - [`rules`] — [`DesignRules`]: the trace width / clearance / via sizing
//!   authority (including the plated IO pad sizing helper
//!   `io_tht_pad_diameter_mm`). Downstream consumers (the KiCad writer, the
//!   DXF exporter) read sizes from this spec — they never decide them.
//! - [`interference`] — [`check_interference`] / [`InterferenceViolation`]:
//!   DRC copper-clearance diagnostics (segment-to-segment and via-pad-to-
//!   trace) run over a validated
//!   [`RoutingResult`](pcbmotorgen_routing::model::RoutingResult).
//!
//! ## Dependency direction
//!
//! `pcbmotorgen-dfm → pcbmotorgen-routing`: the checks need the canonical
//! geometry model, so the DFM crate sits downstream of routing. The routing
//! crate keeps **no** DFM types — the strict-shape validator (bounds, finite,
//! degenerate, continuity) is wire-contract validation and stays in routing.
//!
//! ## Relationship to the routing context
//!
//! [`RoutingContext`](pcbmotorgen_routing::context::RoutingContext) carries
//! `min_trace_mm`, `min_space_mm`, and `phase_clearance_mm` (`g_phase`) as
//! part of the routing wire contract — patterns consume them for layout and
//! phase-band math (routing API §10.1). Those fields stay where they are.
//! The application mirrors the same config values into a [`DesignRules`]
//! snapshot (`LinearMotorConfig::design_rules()` bridge); the DFM crate reads
//! that snapshot for sizing and clearance diagnostics and never re-derives or
//! mutates geometry. Phase clearance is a band-budget concept owned by the
//! routing dimension math; it is not a DRC input here.
//!
//! All values are in millimetres.

pub mod interference;
pub mod rules;
mod series_vias;

pub use interference::{check_interference, InterferenceViolation};
pub use rules::DesignRules;
