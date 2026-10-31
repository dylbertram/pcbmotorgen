//! Native checkmarks mirror the active viewport; they never own design state.
use std::sync::Mutex;
use tauri::{menu::{CheckMenuItem, MenuItem, PredefinedMenuItem, Submenu}, Manager, Wry};

pub const VIEW_EVENT: &str = "menu:view";
#[derive(serde::Deserialize)]
pub struct Definition {
    pub id: String,
    pub label: String,
    pub submenu: Option<String>,
    pub action: Option<String>,
}
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
        let nested = group.first().and_then(|item| item.submenu.as_ref())
            .map(|label| Submenu::with_id(app, "view:zoom", label, true)).transpose()?;
        let target = nested.as_ref().unwrap_or(&menu);
        for item in group {
            if item.action.is_some() {
                target.append(&MenuItem::with_id(app, &item.id, &item.label, false, None::<&str>)?)?;
            } else {
                target.append(&CheckMenuItem::with_id(app, &item.id, &item.label, false, false, None::<&str>)?)?;
            }
        }
        if let Some(nested) = nested { menu.append(&nested)?; }
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
    let definitions = groups().into_iter().flatten().collect::<Vec<_>>();
    for item in &state.items {
        let definition = definitions.iter().find(|entry| entry.id == item.id).ok_or("View definition missing")?;
        let nested = if definition.submenu.is_some() {
            let kind = menu.get("view:zoom").ok_or("Zoom submenu missing")?;
            Some(kind.as_submenu().ok_or("Zoom item is not a submenu")?.clone())
        } else { None };
        let kind = nested.as_ref().unwrap_or(menu).get(&item.id).ok_or("View menu item missing")?;
        if definition.action.is_some() {
            kind.as_menuitem().ok_or("View action is not a command")?
                .set_enabled(item.enabled).map_err(|e| e.to_string())?;
        } else {
            let check = kind.as_check_menuitem().ok_or("View item is not checkable")?;
            check.set_checked(item.checked).map_err(|e| e.to_string())?;
            check.set_enabled(item.enabled).map_err(|e| e.to_string())?;
        }
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
        assert_eq!(groups.len(), 7);
        assert_eq!(groups[3].iter().map(|item| item.id.as_str()).collect::<Vec<_>>(),
            ["view:pole-pitch", "view:band-widths", "view:pole-regions"]);
        let ids: Vec<_> = groups.iter().flatten().map(|item| item.id.as_str()).collect();
        assert_eq!(ids.len(), 16);
        assert!(ids.contains(&"view:pcb"));
        assert_eq!(groups[6].iter().map(|item| item.submenu.as_deref()).collect::<Vec<_>>(), [Some("Zoom"), Some("Zoom")]);
        assert_eq!(groups[6][0].action.as_deref(), Some("fitExtents"));
        assert_eq!(groups[6][1].action, None);
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
