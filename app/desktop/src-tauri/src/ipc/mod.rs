//! IPC contract layer between the Svelte frontend and the Rust physics core.
//!
//! These DTOs are the *only* types that cross the Tauri IPC bridge. They are
//! intentionally decoupled from `crate::config::LinearMotorConfig`
//! (the internal SI representation) because:
//!
//! 1. The frontend (`app/src/lib/types.ts`) speaks **snake_case** field names
//!    with SI units (metres, Tesla, Amperes) — every struct here carries
//!    `#[serde(rename_all = "snake_case")]` to match exactly.
//! 2. The enum wire formats differ from the core: `CommutationModeIpc` is
//!    snake_case on the wire and PascalCase in the core; the coil
//!    routing-pattern is a free-form `String` id (e.g. `"infinity-braid"`)
//!    on the wire, resolved against the `pcbmotorgen-routing` registry in
//!    the core (see `docs/adr/0009`).
//! 3. The IPC config is a **superset** of the core config — it carries
//!    UI-only fields (`num_layers`, `commutation`, `n_positions`, `meshing`,
//!    `magnet_gap_m`, `magnet_cross_width_m`) that the core does not yet
//!    model. These are consumed directly by the stub handlers; once Phases
//!    C/D/E land they will flow into the real core calculators.
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
//!   and `ConfigDerivedIpc` (+ `from_core`).
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

pub use coils::*;
pub use config::*;
pub use enums::*;
pub use kicad::*;
pub use magnets::*;
pub use physics::*;
pub use project::*;
pub use project_versions::*;
