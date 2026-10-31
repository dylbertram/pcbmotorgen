//! Native checkmarks mirror the active viewport; they never own design state.
use std::sync::Mutex;
use tauri::{menu::{CheckMenuItem, PredefinedMenuItem, Submenu}, Manager, Wry};

pub const VIEW_EVENT: &str = "menu:view";
#[derive(serde::Deserialize)]
pub struct Definition { pub id: String, pub label: String }
pub fn groups() -> Vec<Vec<Definition>> {
    serde_json::from_str(include_str!("../../src/lib/viewMenu.json")).expect("bundled View menu schema")
}
#[derive(Clone, Default, serde::Deserialize)]
pub struct ViewMenuState { pub owner: Option<String>, pub items: Vec<ItemState> }
#[derive(Clone, serde::Deserialize)]
pub struct ItemState { pub id: String, pub checked: bool, pub enabled: bool }
#[derive(Default)]
pub struct ActiveViewMenu(pub Mutex<ViewMenuState>);
#[derive(Clone, serde::Serialize)]
pub struct ViewAction { pub owner: String, pub id: String }

pub fn submenu(app: &tauri::AppHandle) -> tauri::Result<Submenu<Wry>> {
    let menu = Submenu::with_id(app, "view", "View", true)?;
    for (index, group) in groups().iter().enumerate() {
        if index > 0 { menu.append(&PredefinedMenuItem::separator(app)?)?; }
        for item in group {
            menu.append(&CheckMenuItem::with_id(app, &item.id, &item.label, false, false, None::<&str>)?)?;
        }
    }
    Ok(menu)
}

fn validate(state: &ViewMenuState) -> Result<(), String> {
    let expected: std::collections::BTreeSet<_> = groups().into_iter().flatten().map(|item| item.id).collect();
    let actual: std::collections::BTreeSet<_> = state.items.iter().map(|item| item.id.clone()).collect();
    if actual != expected || state.items.len() != expected.len() {
        return Err("View menu state must contain each declared item exactly once".into());
    }
    if state.owner.as_ref().is_some_and(|owner| owner.is_empty() || owner.len() > 128)
        || (state.owner.is_none() && state.items.iter().any(|item| item.enabled || item.checked)) {
        return Err("Invalid View menu owner".into());
    }
    Ok(())
}

pub fn event_payload(state: &ActiveViewMenu, id: &str) -> Option<ViewAction> {
    let state = state.0.lock().ok()?;
    if !state.items.iter().any(|item| item.id == id && item.enabled) { return None; }
    Some(ViewAction { owner: state.owner.clone()?, id: id.to_string() })
}

/// Synchronous so native menu mutation runs on the platform's main thread.
#[tauri::command]
pub fn set_view_menu_state(app: tauri::AppHandle, state: ViewMenuState) -> Result<(), String> {
    validate(&state)?;
    let root = app.menu().ok_or("Application menu missing")?;
    let kind = root.get("view").ok_or("View menu missing")?;
    let menu = kind.as_submenu().ok_or("View menu is not a submenu")?;
    for item in &state.items {
        let kind = menu.get(&item.id).ok_or("View menu item missing")?;
        let check = kind.as_check_menuitem().ok_or("View item is not checkable")?;
        check.set_checked(item.checked).map_err(|e| e.to_string())?;
        check.set_enabled(item.enabled).map_err(|e| e.to_string())?;
    }
    *app.state::<ActiveViewMenu>().0.lock().map_err(|e| e.to_string())? = state;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn snapshot() -> ViewMenuState {
        ViewMenuState { owner: Some("viewport-1".into()), items: groups().into_iter().flatten()
            .map(|item| ItemState { id: item.id, checked: false, enabled: true }).collect() }
    }
    #[test]
    fn menu_groups_include_display_controls_but_no_layer_or_phase_filters() {
        let groups = groups();
        assert_eq!(groups.len(), 6);
        assert_eq!(groups[3].iter().map(|item| item.id.as_str()).collect::<Vec<_>>(),
            ["view:pole-pitch", "view:band-widths", "view:pole-regions"]);
        let ids: Vec<_> = groups.iter().flatten().map(|item| item.id.as_str()).collect();
        assert_eq!(ids.len(), 14);
        assert!(ids.contains(&"view:pcb"));
        assert!(!ids.iter().any(|id| id.contains("layer") || id.contains("phase")));
        assert!(validate(&snapshot()).is_ok());
    }
    #[test]
    fn unknown_duplicate_and_partial_menu_snapshots_are_rejected() {
        let mut state = snapshot();
        state.items[0].id = "view:layer-0".into();
        assert!(validate(&state).is_err());
        state = snapshot(); state.items.pop(); assert!(validate(&state).is_err());
        state = snapshot(); state.items[0] = state.items[1].clone(); assert!(validate(&state).is_err());
    }
    #[test]
    fn events_are_scoped_to_the_current_enabled_document() {
        let state = ActiveViewMenu(Mutex::new(snapshot()));
        assert_eq!(event_payload(&state, "view:top").unwrap().owner, "viewport-1");
        state.0.lock().unwrap().items[0].enabled = false;
        assert!(event_payload(&state, "view:top").is_none());
        assert!(event_payload(&state, "view:layer-0").is_none());
    }
}
