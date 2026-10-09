//! # pcbmotorgen-routing
//!
//! Routing-pattern plugin contract for PCB stator coil generation. This crate
//! owns everything about trace generation: the pattern plugin interface,
//! generator loading (Rust `cdylib` + Python runners), and the strict wire
//! -contract validation. Manufacturability is deliberately NOT a routing
//! concern (kata 0rgs): patterns may generate any geometry, and the DFM rules
//! plus DRC interference diagnostics live downstream in
//! `pcbmotorgen-dfm` (which depends on this crate).
//!
//! It is a leaf crate — it depends on nothing internal, so it can be developed
//! and tested independently of the physics simulation, the KiCad adapter, the
//! DFM checks, and the parent `pcbmotorgen` app.
//!
//! Per the crate division (see `PRODUCT_ARCHITECTURE.md`):
//! - [`model`] — the canonical [`RoutingResult`] (segments, curves, vias),
//!   each element carrying its own `layer` and `net`.
//! - [`coil`] — the [`PhaseCoil`] presentation model (grouped by layer+net)
//!   that the simulation crate and the KiCad writer consume.
//! - [`dimensions`] — pole pitch, phase-band budget, bottom-up phase-band
//!   width calculations, and the resolved phase-band geometry (declared or
//!   host-derived) returned in [`RoutingReport`].
//! - [`io`] — additive IO result elements (connector/IC pads + terminal
//!   fanout traces), typed distinctly from active conductors.
//! - [`generate`] — the app-facing facade: registry, plugin loading, and
//!   `RoutingContext` → `RoutingResult`/`PhaseCoil` generation.
//! - [`pattern`] — the [`RoutingPattern`] trait that crate plugins and Python
//!   runners implement.
//! - [`context`] — the flat [`RoutingContext`] snapshot fed to every pattern.
//! - [`validator`] — the single strict-shape gate every result must pass.
//! - [`registry`] — the [`RoutingRegistry`] patterns register into.
//! - [`loaders`] — dynamic loading of patterns (Rust `cdylib` + Python).
//! - [`patterns`] — bundled reference patterns (the `infinity` braid).
//! - [`report`] — the validated geometry plus its design-dimension sidecar.
//!
//! All coordinates and design dimensions are in millimetres; x = travel axis,
//! y = across board width.

pub mod coil;
pub mod context;
pub mod dimensions;
pub mod error;
pub mod generate;
pub mod induction_sensor;
pub mod io;
pub mod loaders;
pub mod model;
pub mod pattern;
pub mod patterns;
pub mod registry;
pub mod report;
pub mod validator;

pub use coil::{CoilArc, CoilSegment, PhaseCoil, PHASE_NAMES};
pub use context::RoutingContext;
pub use dimensions::{
    max_phase_band_width_from_pole_pitch_mm, phase_band_width_from_trace_geometry_mm,
    slot_pitch_from_leg_grid_mm, slot_width_from_leg_geometry_mm, PhaseBandWidth,
    ResolvedPhaseBand, RoutingDimensions,
};
pub use error::RoutingError;
pub use generate::{
    available_pattern_ids, available_pattern_metadata, bundled_registry,
    generate_coils_from_context, generate_io_fanout, generate_routing_report,
    generate_routing_report_with_io, generate_routing_result, generate_routing_result_with_io,
    pattern_metadata, pattern_parameters, register_native_plugin, register_python_runner,
    register_runtime_pattern, routing_result_to_phase_coils, unregister_runtime_pattern,
    validate_routing_params, IoFanoutEdge, IoFanoutOptions,
};
pub use induction_sensor::{generate_sensor, SensorConfig, SensorGeometry, SensorNetGeometry};
pub use io::{IoPad, IoPadKind, IoTrace, IoTraceRole, PadSize};
pub use model::{
    Layer, LegGrid, Net, PhaseBand, PhaseBandShape, Point, PoleRegion, RouteCurve, RouteSegment,
    RoutingResult, Via,
};
pub use pattern::{ParamType, PatternParameter, PluginMetadata, RoutingPattern};
pub use registry::{RoutingErrorKind, RoutingRegistry};
pub use report::RoutingReport;
pub use validator::Validator;
