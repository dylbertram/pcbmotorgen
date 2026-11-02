//! Tauri v2 async command handlers — the IPC bridge between the Svelte
//! frontend and the pcbmotorgen-simulation / routing / kicad sub-crates.
//!
//! ## Selected commands
//!
//! | Command                       | Status        | Notes                                    |
//! |-------------------------------|---------------|------------------------------------------|
//! | `get_magnet_grades`           | REAL          | Reads core `magnet_grades::MAGNET_GRADES`.|
//! | `compute_height_stack`        | REAL          | Uses core `HeightStackCalculator`.       |
//! | `prepare_dc_winding_geometry` | REAL (pure)   | Actual routed copper/terminal/depth snapshot only; no force or return substitution. |
//! | `start_dc_coupling`           | EXPERIMENTAL | Opt-in installed worker; exact registered geometry only; fresh magnetic solve. |
//! | `dc_coupling_status`          | REAL (sync)  | Request-bound supervised status, verified fresh result only. |
//! | `cancel_dc_coupling`          | REAL (sync)  | Cancels the owned numerical process group; no cancelled force. |
//! | `dc_coupling_capability`      | REAL (sync)  | Host installation availability, not general geometry qualification. |
//! | `inspect_dc_coupling`         | REAL (async) | Rebuild copper and inspect exact qualified-case applicability; no magnetic job or force. |
//! | `generate_coils`              | REAL          | Resolves the selected routing pattern and returns geometry plus dimensions. |
//! | `evaluate_force_sweep`        | REAL          | Uses core `ForceEvaluator` (Lorentz).    |
//! | `compute_friction`            | REAL          | Uses core `FrictionEstimator`.           |
//! | `evaluate_move_power`         | NATIVE partial | Bounded actual-copper prescribed motion; explicit loss omissions, no browser substitute. |
//! | `cancel_move_power`           | REAL (sync)   | Identity-bound cooperative cancellation; retains ownership until the worker exits. |
//! | `connect_kicad`               | REAL          | KiCad IPC: connect + query open board.   |
//! | `write_coils_to_board`        | REAL          | KiCad IPC: generate + atomic commit.     |
//! | `get_board_diagnostics`       | REAL          | KiCad IPC: live board snapshot.          |
//! | `validate_write_preconditions`| REAL (pure)   | Config-vs-board rule check (no IPC).     |
//! | `preview_coils`               | REAL (pure)   | Dry-run coil geometry preview (no IPC).  |
//! | `export_coils_dxf`            | REAL          | Pure DXF R12 ASCII export (`pcbmotorgen-export`). |
//! | `save_document`               | REAL          | Versioned document artifact, atomic write. |
//! | `load_project`                | REAL          | Parse + migrate + validate a saved document. |
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
//! Commands use async handlers where appropriate; synchronous handlers include
//! menu updates, file existence checks, cancellation and job status. Heavy
//! computations use `tauri::async_runtime::spawn_blocking` to keep the async
//! runtime available for IPC dispatch.
//!
//! ## Linear-only constraint
//!
//! Radial/axial-flux simulation is deferred. Move-power requests explicitly
//! reject non-linear topologies rather than treating them as linear motors.
//!
//! ## Module layout
//!
//! Handlers are grouped by subject area:
//! - [`routing_plugins`] — routing-pattern plugin catalog + interference.
//! - [`physics`] — force, stackup, drive and native reference calculations.
//! - [`move_power`] — prescribed-move calculation and cancellation.
//! - [`dc_jobs`] and [`visualization`] — supervised DC jobs and field sampling.
//! - [`kicad`] — KiCad IPC bridge (connect, write, diagnostics, preview).
//! - [`dxf`] — DXF import and export.
//! - [`project`] and [`workspace`] — document and workspace persistence.
//! - [`sensor`] — induction-sensor geometry.

pub mod cad_source;
pub mod dc_jobs;
pub mod visualization;
pub mod dxf;
pub mod kicad;
pub mod physics;
pub mod move_power;
pub mod project;
pub mod workspace;
pub mod routing_plugins;
pub mod sensor;

#[cfg(test)]
mod braid_reference_tests;

#[cfg(test)]
mod compact_star_reference_tests;

#[cfg(test)]
mod pcb_stackup_tests;
#[cfg(test)]
mod routing_orientation_tests;
