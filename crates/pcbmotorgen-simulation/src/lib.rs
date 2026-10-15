//! # pcbmotorgen-simulation
//!
//! Analytical magnetic field, Lorentz force, and multiphysics simulation for
//! coreless linear PCB motors (physics / stackup / friction / driver suitability).
//!
//! This crate is **parent-free**: it does not depend on the monolithic
//! `pcbmotorgen` app crate or on `pcbmotorgen-export`. It MAY depend on the
//! sibling `pcbmotorgen-routing` crate for coil geometry ([`PhaseCoil`] /
//! [`CoilSegment`] come from there), and on `magba` for the B-field
//! computation.
//!
//! Routing geometry is supplied in millimetres and converted to SI metres at
//! the `CoilCurrentModel`/physics boundary.
//!
//! ## Module layout
//! - [`units`] — SI conversion helpers and physical constants.
//! - [`magnet_grades`] — NdFeB grade → remanence lookup.
//! - [`params`] — [`SimulationInput`] inputs + shared result types.
//! - [`physics`] — thin adapter over `magba`.
//! - [`magnetic`] — magnet arrays, coil current model, force evaluator.
//! - [`stackup`] — height stack, friction budget.
//! - [`drive`] — driver suitability from routed copper.

pub mod drive;
pub mod magnet_grades;
pub mod magnetic;
pub mod params;
pub mod equilibrium;
pub mod physics;
pub mod stackup;
pub mod units;

// Re-export public types from the moved modules.
pub use magnetic::{CommutationMode, ForceEvaluator, ForceResult, MagnetArray, BFieldSample2D};
pub use magnetic::coil_model::{CoilCurrentModel, ConductorSample};
pub use params::{
    phase_bands_from_routing, BearingType, FrictionBudget, HeightStackResult, PhaseBandPosition,
    SimulationError, SimulationInput,
};
pub use stackup::{FrictionEstimator, HeightStackCalculator};

/// Re-export the coil presentation types the simulation consumes, which the
/// sibling `pcbmotorgen-routing` crate owns.
pub use pcbmotorgen_routing::{CoilArc, CoilSegment, PhaseCoil, PHASE_NAMES};
