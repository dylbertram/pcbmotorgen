//! IPC contract layer between the Svelte frontend and the Rust physics core.
//!
//! These DTOs define frontend/backend wire formats separately from
//! `crate::config::LinearMotorConfig`, the internal SI representation.
//! Frontend counterparts live in `app/desktop/src/lib/types/`. Wire fields
//! generally use snake_case and SI units; routing patterns use registered
//! string IDs such as `"infinity-braid"`.
//!
//! Conversions to/from `crate::config::LinearMotorConfig` live in this module
//! (`to_core()` / `From<&LinearMotorConfig>`).
//!
//! ## Module layout
//!
//! DTOs are grouped by subject area, with every public item re-exported at
//! this level so `use crate::ipc::*;` in the command handlers keeps resolving:
//! - [`enums`] — `CommutationModeIpc`, `PreconditionLevelIpc`.
//! - [`config`] — `LinearMotorConfigIpc` (+ `to_core`/`From<&CoreConfig>`)
//! - [`coils`] — `CoilSegmentIpc` / `PhaseCoilIpc` / `CoilPathIpc` geometry.
//! - [`physics`] — B-field grid, force sweep, stackup/height/power/friction.
//! - [`magnets`] — `MagnetGradeIpc` + `magnet_grades()` + temp tables.
//! - [`project`] — project persistence: versioned `.pmproj` envelope,
//!   state DTOs, parse/migrate/validate (kata 0cgm).
//! - [`kicad`] — board diagnostics, write preconditions, coil preview.

pub mod coils;
pub mod config;
pub mod enums;
pub mod kicad;
pub mod magnets;
pub mod physics;
pub mod project;
pub mod project_versions;
pub mod documents;

pub use coils::*;
pub use config::*;
pub use enums::*;
pub use kicad::*;
pub use magnets::*;
pub use physics::*;
pub use project::*;
pub use project_versions::*;
pub use documents::*;
