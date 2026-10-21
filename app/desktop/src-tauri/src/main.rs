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
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            // The Open Recent mirror state (kata eap8) must exist before the
            // menu is installed / any command resolves it.
            app.manage(menu::RecentFiles::default());
            app.manage(commands::workspace::ExitApproval::default());
            menu::install(app.handle())?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let id = event.id().as_ref();
            if matches!(
                id,
                menu::OPEN_ID
                    | menu::NEW_ID
                    | menu::NEW_PROJECT_ID
                    | menu::SAVE_WORKSPACE_ID
                    | menu::SAVE_WORKSPACE_AS_ID
                    | menu::SAVE_ALL_ID
                    | menu::CLOSE_FILE_ID
                    | menu::EXPORT_DXF_ID
                    | menu::SEND_KICAD_ID
                    | menu::SAVE_ID
                    | menu::SAVE_AS_ID
                    | menu::SAVE_NEW_VERSION_ID
                    | menu::SETTINGS_ID
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
            commands::physics::get_magnet_grades,
            commands::physics::compute_height_stack,
            commands::physics::periodic_backplane_reference,
            commands::physics::generate_coils,
            commands::physics::evaluate_force_sweep,
            commands::physics::sample_b_field,
            commands::physics::travel_envelope,
            commands::physics::compute_friction,
            commands::physics::analyze_drive,
            commands::physics::analyze_housing_motion,
            commands::physics::prepare_dc_winding_geometry,
            commands::kicad::connect_kicad,
            commands::kicad::write_coils_to_board,
            commands::kicad::write_sensor_to_board,
            commands::kicad::get_board_diagnostics,
            commands::kicad::validate_write_preconditions,
            commands::kicad::preview_coils,
            commands::dxf::export_coils_dxf,
            commands::dxf::export_sensor_dxf,
            commands::dxf::import_cad_dxf,
            commands::dxf::export_cad_geometry_dxf,
            commands::dxf::editable_coil_geometry,
            commands::project::save_document,
            commands::project::resolve_document_path,
            commands::project::relocate_project,
            commands::project::load_project,
            commands::project::update_project_version,
            commands::project::set_recent_files,
            commands::project::file_exists,
            commands::workspace::load_workspace,
            commands::workspace::save_workspace,
            commands::workspace::list_coil_files,
            commands::workspace::reveal_in_finder,
            commands::workspace::quit_app,
            commands::routing_plugins::list_routing_patterns,
            commands::routing_plugins::register_routing_plugin,
            commands::routing_plugins::routing_pattern_parameters,
            commands::routing_plugins::check_coil_interference,
            commands::routing_plugins::load_installed_plugins,
            commands::routing_plugins::list_installed_plugins,
            commands::routing_plugins::remove_routing_plugin,
            commands::sensor::generate_sensor_geometry,
        ])
        .build(tauri::generate_context!())
        .expect("error while running pcbmotorgen tauri application");
    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            let approval = app.state::<commands::workspace::ExitApproval>();
            if !approval.inner().0.load(std::sync::atomic::Ordering::SeqCst) {
                api.prevent_exit();
                let _ = app.emit("app:request-quit", ());
            }
        }
    });
}
