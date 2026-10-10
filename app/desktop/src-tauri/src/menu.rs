//! Native application menu (kata 0cgm, eap8) — the File dropdown carries
//! project actions, Open Recent, DXF export, and Send to KiCad.
//!
//! Rust owns the menu bar. Each project item's id equals the Tauri event
//! name it is forwarded as (see `on_menu_event` in `main.rs`), where
//! `bindProjectMenuActions` (`src/lib/ipc/project.ts`) dispatches into the
//! `ProjectStore` flows — dialogs, busy-guard, and dirty tracking stay in
//! the existing frontend store.
//!
//! The Open Recent list is webview-owned (frontend recents store,
//! kata eap8); Rust only mirrors it. The frontend pushes the list through
//! the `set_recent_files` command, which rebuilds the submenu (muda menus
//! are built once — replace via remove-all + re-append). Entry item ids
//! are index-based and resolved against the `RecentFiles` state snapshot
//! at click time, avoiding path-encoding in menu ids.

use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    Wry,
};

/// Menu item id == webview event name for Open.
pub const OPEN_ID: &str = "menu:open-project";
pub const NEW_ID: &str = "menu:new-project";
pub const EXPORT_DXF_ID: &str = "menu:export-dxf";
pub const SEND_KICAD_ID: &str = "menu:send-kicad";
/// Menu item id == webview event name for Save.
pub const SAVE_ID: &str = "menu:save-project";
/// Menu item id == webview event name for Save As.
pub const SAVE_AS_ID: &str = "menu:save-project-as";
/// Menu item id == webview event name for importing CAD geometry.
pub const IMPORT_CAD_ID: &str = "menu:import-cad";

/// Submenu id of the "Open Recent" container inside the File menu. Purely
/// internal — the container itself never fires an event.
pub const RECENT_SUBMENU_ID: &str = "file:open-recent";
/// Tauri event emitted to the webview when an Open Recent entry is clicked.
/// Payload = the file path captured when the submenu was last rebuilt.
pub const OPEN_RECENT_EVENT: &str = "menu:open-project-recent";
/// Menu item id == webview event name for "Clear Recent Files".
pub const CLEAR_RECENT_ID: &str = "menu:clear-recent-files";
/// Prefix of per-entry item ids: `menu:open-recent:<index>`, where index
/// addresses the [`RecentFiles`] state snapshot taken at the last rebuild.
/// Distinct from [`OPEN_RECENT_EVENT`] (mind the `projec` vs `rece` split).
pub const OPEN_RECENT_ITEM_PREFIX: &str = "menu:open-recent:";
/// Placeholder id shown while the list is empty (never fires an event: it
/// does not carry the [`OPEN_RECENT_ITEM_PREFIX`] colon and is disabled).
pub const RECENT_EMPTY_ID: &str = "menu:open-recent-empty";

/// Managed mirror of the webview-owned recents list, as last pushed by
/// `set_recent_files`. Only read from the menu-event handler on the main
/// thread; the command mutates it there too (sync command), so a plain
/// `Mutex` suffices.
#[derive(Default)]
pub struct RecentFiles(pub Mutex<Vec<String>>);

/// Resolve a clicked entry id (`menu:open-recent:<index>`) to the path
/// captured at the last submenu rebuild. `None` for any other menu id
/// (placeholders, accelerators, predefined items).
pub fn recent_event_payload(state: &RecentFiles, id: &str) -> Option<String> {
    let index: usize = id.strip_prefix(OPEN_RECENT_ITEM_PREFIX)?.parse().ok()?;
    state.0.lock().ok()?.get(index).cloned()
}

/// File name shown as an entry label; falls back to the full path when the
/// path has no recognizable file-name component. Native tooltips do not
/// exist in the muda menu API, so the label is all the user sees — the
/// webview keeps full paths in its recents store.
fn file_label(path: &str) -> String {
    std::path::Path::new(path)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(path)
        .to_string()
}

/// Build and install the application menu.
///
/// A custom menu replaces the platform default, so the standard macOS app
/// submenu and an Edit submenu (clipboard) are provided explicitly to keep
/// copy/paste working in text inputs.
pub fn install(app: &tauri::AppHandle) -> tauri::Result<()> {
    let file = file_submenu(app)?;
    let edit = edit_submenu(app)?;

    #[cfg(target_os = "macos")]
    let menu = {
        let app_menu = app_submenu(app)?;
        Menu::with_items(app, &[&app_menu, &file, &edit])?
    };
    #[cfg(not(target_os = "macos"))]
    let menu = Menu::with_items(app, &[&file, &edit])?;

    app.set_menu(menu)?;
    Ok(())
}

/// File menu with project actions, import, and a shared export block.
/// The recents list starts empty and disabled; the
/// frontend pushes the real contents through `set_recent_files`.
fn file_submenu(app: &tauri::AppHandle) -> tauri::Result<Submenu<Wry>> {
    let new = MenuItem::with_id(app, NEW_ID, "New", true, Some("CmdOrCtrl+N"))?;
    let open = MenuItem::with_id(app, OPEN_ID, "Open…", true, Some("CmdOrCtrl+O"))?;
    let save = MenuItem::with_id(app, SAVE_ID, "Save", true, Some("CmdOrCtrl+S"))?;
    let save_as = MenuItem::with_id(app, SAVE_AS_ID, "Save As…", true, Some("CmdOrCtrl+Shift+S"))?;
    let sep = PredefinedMenuItem::separator(app)?;
    let import_cad = MenuItem::with_id(app, IMPORT_CAD_ID, "Import CAD…", true, None::<&str>)?;
    let sep_after_import = PredefinedMenuItem::separator(app)?;
    let dxf = MenuItem::with_id(app, EXPORT_DXF_ID, "DXF", true, None::<&str>)?;
    let export = Submenu::with_id_and_items(app, "file:export", "Export as…", true, &[&dxf])?;
    let send_kicad = MenuItem::with_id(app, SEND_KICAD_ID, "Send to KiCad", true, None::<&str>)?;

    // Placeholder until the first `set_recent_files` push — a disabled
    // item so the submenu shape is stable across rebuilds.
    let empty = MenuItem::with_id(app, RECENT_EMPTY_ID, "No Recent Files", false, None::<&str>)?;
    let recent =
        Submenu::with_id_and_items(app, RECENT_SUBMENU_ID, "Open Recent", false, &[&empty])?;

    Submenu::with_id_and_items(
        app,
        "file",
        "File",
        true,
        &[
            &new,
            &open,
            &recent,
            &save,
            &save_as,
            &sep,
            &import_cad,
            &sep_after_import,
            &export,
            &send_kicad,
        ],
    )
}

/// Replace the Open Recent submenu contents with `paths`
/// (most-recent-first, already capped/pruned by the frontend store).
///
/// The state snapshot MUST be updated before the items are rebuilt: entry
/// ids are index-based and resolve at click time against the snapshot.
/// Item text is the file's basename (muda has no per-item tooltip);
/// "Clear Recent Files" sits under a separator at the bottom, and the
/// whole submenu is disabled while the list is empty.
pub fn rebuild_recent_submenu(
    app: &tauri::AppHandle,
    recent: &RecentFiles,
    paths: &[String],
) -> Result<(), String> {
    // Poisoned lock is unrecoverable for this app shape; a display string is
    // enough for the command-level report.
    *recent
        .0
        .lock()
        .map_err(|e| format!("recents state poisoned: {e}"))? = paths.to_vec();

    let menu = app
        .menu()
        .ok_or_else(|| "application menu not installed".to_string())?;
    let kind = menu
        .get(RECENT_SUBMENU_ID)
        .ok_or_else(|| "Open Recent submenu missing from the menu bar".to_string())?;
    let submenu = kind
        .as_submenu()
        .ok_or_else(|| "Open Recent id is not a submenu".to_string())?;
    let rebuild = |e: tauri::Error| format!("failed to rebuild Open Recent: {e}");

    // muda has no replace-children API: drop the current items from the
    // back so the surviving indexes stay stable, then append fresh.
    loop {
        let count = submenu.items().map_err(rebuild)?.len();
        if count == 0 {
            break;
        }
        submenu.remove_at(count - 1).map_err(rebuild)?;
    }

    if paths.is_empty() {
        let empty = MenuItem::with_id(app, RECENT_EMPTY_ID, "No Recent Files", false, None::<&str>)
            .map_err(rebuild)?;
        submenu.append(&empty).map_err(rebuild)?;
    } else {
        for (index, path) in paths.iter().enumerate() {
            let item = MenuItem::with_id(
                app,
                format!("{OPEN_RECENT_ITEM_PREFIX}{index}"),
                file_label(path),
                true,
                None::<&str>,
            )
            .map_err(rebuild)?;
            submenu.append(&item).map_err(rebuild)?;
        }
    }

    let sep = PredefinedMenuItem::separator(app).map_err(rebuild)?;
    submenu.append(&sep).map_err(rebuild)?;
    let clear = MenuItem::with_id(
        app,
        CLEAR_RECENT_ID,
        "Clear Recent Files",
        !paths.is_empty(),
        None::<&str>,
    )
    .map_err(rebuild)?;
    submenu.append(&clear).map_err(rebuild)?;

    // The disabled state when empty greys the whole submenu (macOS-style
    // "Open Recent" behaviour); entries become reachable with the first push.
    submenu.set_enabled(!paths.is_empty()).map_err(rebuild)?;
    Ok(())
}

/// Edit menu with the standard clipboard items.
fn edit_submenu(app: &tauri::AppHandle) -> tauri::Result<Submenu<Wry>> {
    #[cfg(target_os = "macos")]
    {
        let undo = PredefinedMenuItem::undo(app, None)?;
        let redo = PredefinedMenuItem::redo(app, None)?;
        let sep1 = PredefinedMenuItem::separator(app)?;
        let cut = PredefinedMenuItem::cut(app, None)?;
        let copy = PredefinedMenuItem::copy(app, None)?;
        let paste = PredefinedMenuItem::paste(app, None)?;
        let sep2 = PredefinedMenuItem::separator(app)?;
        let select_all = PredefinedMenuItem::select_all(app, None)?;
        Submenu::with_id_and_items(
            app,
            "edit",
            "Edit",
            true,
            &[&undo, &redo, &sep1, &cut, &copy, &paste, &sep2, &select_all],
        )
    }
    #[cfg(not(target_os = "macos"))]
    {
        let cut = PredefinedMenuItem::cut(app, None)?;
        let copy = PredefinedMenuItem::copy(app, None)?;
        let paste = PredefinedMenuItem::paste(app, None)?;
        let sep = PredefinedMenuItem::separator(app)?;
        let select_all = PredefinedMenuItem::select_all(app, None)?;
        Submenu::with_id_and_items(
            app,
            "edit",
            "Edit",
            true,
            &[&cut, &copy, &paste, &sep, &select_all],
        )
    }
}

/// macOS application submenu (About / Hide / Quit) so the custom menu keeps
/// the standard platform shape.
#[cfg(target_os = "macos")]
fn app_submenu(app: &tauri::AppHandle) -> tauri::Result<Submenu<Wry>> {
    let about = PredefinedMenuItem::about(app, None, None)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let services = PredefinedMenuItem::services(app, None)?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let hide = PredefinedMenuItem::hide(app, None)?;
    let hide_others = PredefinedMenuItem::hide_others(app, None)?;
    let show_all = PredefinedMenuItem::show_all(app, None)?;
    let sep3 = PredefinedMenuItem::separator(app)?;
    let quit = PredefinedMenuItem::quit(app, None)?;
    Submenu::with_id_and_items(
        app,
        "app",
        "pcbmotorgen",
        true,
        &[
            &about,
            &sep1,
            &services,
            &sep2,
            &hide,
            &hide_others,
            &show_all,
            &sep3,
            &quit,
        ],
    )
}
