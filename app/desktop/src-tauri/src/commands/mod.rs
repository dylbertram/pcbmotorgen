//! Tauri v2 async command handlers — the IPC bridge between the Svelte
//! frontend and the pcbmotorgen-simulation / routing / kicad sub-crates.
//!
//! ## Command inventory
//!
//! | Command                       | Status        | Notes                                    |
//! |-------------------------------|---------------|------------------------------------------|
//! | `compute_config_derived`      | REAL          | Uses core `LinearMotorConfig` methods.  |
//! | `get_magnet_grades`           | REAL          | Reads core `magnet_grades::MAGNET_GRADES`.|
//! | `compute_height_stack`        | REAL          | Uses core `HeightStackCalculator`.       |
//! | `generate_coils`              | REAL          | Resolves the selected routing pattern and returns geometry plus dimensions. |
//! | `evaluate_force_sweep`        | REAL          | Uses core `ForceEvaluator` (Lorentz).    |
//! | `compute_stackup`             | STUB          | No core `StackupCalculator` exists yet.  |
//! | `compute_power_budget`        | REAL          | Uses core `PowerEstimator`.              |
//! | `compute_friction`            | REAL          | Uses core `FrictionEstimator`.           |
//! | `validate_config`             | REAL          | Delegates to core `validate()`.          |
//! | `connect_kicad`               | REAL          | KiCad IPC: connect + query open board.   |
//! | `write_coils_to_board`        | REAL          | KiCad IPC: generate + atomic commit.     |
//! | `ping_kicad`                  | REAL          | KiCad IPC: connect + GetVersion.         |
//! | `get_board_diagnostics`       | REAL          | KiCad IPC: live board snapshot.          |
//! | `validate_write_preconditions`| REAL (pure)   | Config-vs-board rule check (no IPC).     |
//! | `preview_coils`               | REAL (pure)   | Dry-run coil geometry preview (no IPC).  |
//! | `sample_b_field`              | REAL          | Uses core `MagnetArray::bfield_grid`.    |
//! | `export_coils_dxf`            | REAL          | Pure DXF R12 ASCII export (`pcbmotorgen-export`). |
//! | `save_project`                | REAL          | Versioned `.pmproj` artifact, atomic write. |
//! | `load_project`                | REAL          | Parse + migrate + validate a `.pmproj` artifact. |
//! | `set_recent_files`            | REAL (sync)   | Mirror webview recents into the File menu (kata eap8). |
//! | `file_exists`                 | REAL (sync)   | Stat check for recents prune-on-access (kata eap8). |
//! | `list_routing_patterns`       | REAL          | Routing-pattern plugin catalog.          |
//! | `register_routing_plugin`     | REAL          | Load + persist a native/Python plugin.   |
//! | `routing_pattern_parameters`  | REAL          | User-editable pattern params.            |
//! | `check_coil_interference`     | REAL          | DRC interference checks on routed coils. |
//! | `load_installed_plugins`      | REAL          | Re-register persisted plugins at startup.|
//! | `list_installed_plugins`      | REAL          | Persistent plugin-store listing.         |
//! | `remove_routing_plugin`       | REAL          | Remove from store + runtime registry.    |
//!
//! ## Threading
//!
//! All commands are `async fn`, except the two deliberate sync exceptions
//! (`set_recent_files`, `file_exists`, kata eap8): the native menu must be
//! mutated on the main thread (macOS NSMenu) and a stat call is cheaper
//! than the async hop. Per the Tauri v2 docs, async commands
//! already run on a separate async task (not the main thread). For the
//! heavier computations (force sweep, coil generation) we additionally wrap
//! the body in `tauri::async_runtime::spawn_blocking` so the work moves to
//! the dedicated blocking thread pool — this keeps the async runtime's
//! worker threads free for IPC dispatch.
//!
//! ## Linear-only constraint
//!
//! PRODUCT_GOALS.md §7.A: radial/axial-flux mode is deferred. There is no
//! `topology` argument on these commands because the frontend sends a single
//! `LinearMotorConfigIpc` struct. If a radial variant is ever needed it will
//! be a separate command set returning `"Radial mode not yet implemented."`
//!
//! ## Module layout
//!
//! Handlers are grouped by subject area:
//! - [`routing_plugins`] — routing-pattern plugin catalog + interference.
//! - [`physics`] — config derived/validation, force, stackup, power, B-field.
//! - [`kicad`] — KiCad IPC bridge (connect, write, diagnostics, preview).
//! - [`dxf`] — DXF export.
//! - [`project`] — project save/load (versioned `.pmproj`, kata 0cgm).
//!
//! Every public item is re-exported at this level, so `main.rs` can register
//! handlers as `commands::routing_plugins::list_routing_patterns` or via the
//! flat `commands::` paths, whichever the caller prefers.

pub mod dxf;
pub mod kicad;
pub mod physics;
pub mod project;
pub mod routing_plugins;
pub mod sensor;

// Flat re-exports keep `commands::Foo` paths working for any consumer that
// does not want to name the submodule. `main.rs` currently registers handlers
// with the explicit submodule paths, so these globs are referenced by the
// compatibility contract rather than by code in this binary.
#[allow(unused_imports)]
pub use dxf::*;
#[allow(unused_imports)]
pub use kicad::*;
#[allow(unused_imports)]
pub use physics::*;
#[allow(unused_imports)]
pub use project::*;
#[allow(unused_imports)]
pub use routing_plugins::*;
