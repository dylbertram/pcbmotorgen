//! pcbmotorgen Tauri host — entry point.
//!
//! Registers all `#[tauri::command]` async handlers from the `commands/`
//! module tree and the `ipc/` DTO layer with the Tauri v2 `Builder`. The
//! frontend (`app/src/`) calls these via `invoke("command_name", { config })`
//! (see `app/src/lib/tauri.ts`).
//!
//! Linear mode only (PRODUCT_GOALS.md §7.A). No radial commands are exposed.

use tauri::{Emitter, Manager};

mod commands;
mod config;
mod ipc;
mod menu;
mod plugins;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            // The Open Recent mirror state (kata eap8) must exist before the
            // menu is installed / any command resolves it.
            app.manage(menu::RecentFiles::default());
            menu::install(app.handle())?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let id = event.id().as_ref();
            if matches!(
                id,
                menu::OPEN_ID
                    | menu::NEW_ID
                    | menu::EXPORT_DXF_ID
                    | menu::SEND_KICAD_ID
                    | menu::SAVE_ID
                    | menu::SAVE_AS_ID
                    | menu::CLEAR_RECENT_ID
                    | menu::IMPORT_CAD_ID
            ) {
                // File-menu project actions run in the webview flows
                // (ProjectStore); forward the item ids as events — ids equal
                // event names (see `menu.rs` / `bindProjectMenuActions`).
                // The "Clear Recent Files" entry is handled by the frontend
                // recents store, the single owner of the list.
                let _ = app.emit(id, ());
            } else if let Some(path) =
                menu::recent_event_payload(&app.state::<menu::RecentFiles>(), id)
            {
                // An Open Recent entry was clicked — forward the path that
                // was displayed when the submenu was last rebuilt.
                let _ = app.emit(menu::OPEN_RECENT_EVENT, path);
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::physics::compute_config_derived,
            commands::physics::validate_config,
            commands::physics::get_magnet_grades,
            commands::physics::compute_height_stack,
            commands::physics::generate_coils,
            commands::physics::evaluate_force_sweep,
            commands::physics::sample_b_field,
            commands::physics::travel_envelope,
            commands::physics::compute_stackup,
            commands::physics::compute_power_budget,
            commands::physics::compute_friction,
            commands::kicad::connect_kicad,
            commands::kicad::write_coils_to_board,
            commands::kicad::write_sensor_to_board,
            commands::kicad::ping_kicad,
            commands::kicad::get_board_diagnostics,
            commands::kicad::validate_write_preconditions,
            commands::kicad::preview_coils,
            commands::dxf::export_coils_dxf,
            commands::dxf::export_sensor_dxf,
            commands::dxf::import_cad_dxf,
            commands::dxf::export_cad_geometry_dxf,
            commands::project::save_project,
            commands::project::load_project,
            commands::project::set_recent_files,
            commands::project::file_exists,
            commands::routing_plugins::list_routing_patterns,
            commands::routing_plugins::register_routing_plugin,
            commands::routing_plugins::routing_pattern_parameters,
            commands::routing_plugins::check_coil_interference,
            commands::routing_plugins::load_installed_plugins,
            commands::routing_plugins::list_installed_plugins,
            commands::routing_plugins::remove_routing_plugin,
            commands::sensor::generate_sensor_geometry,
        ])
        .run(tauri::generate_context!())
        .expect("error while running pcbmotorgen tauri application");
}
