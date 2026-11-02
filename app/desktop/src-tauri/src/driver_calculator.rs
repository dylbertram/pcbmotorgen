//! Independent calculator window. Seeds cross the boundary only on open or an
//! explicit import; calculator edits never mutate a motor document.
use std::sync::Mutex;
use tauri::{Emitter, Manager};

const LABEL: &str = "driver-calculator";
#[derive(Default)]
pub struct DriverCalculatorSeed(Mutex<Option<serde_json::Value>>);

#[tauri::command]
pub async fn open_driver_calculator(app: tauri::AppHandle, window: tauri::WebviewWindow, snapshot: Option<serde_json::Value>, state: tauri::State<'_, DriverCalculatorSeed>) -> Result<(), String> {
    if window.label() != "main" { return Err("Only the motor workspace can open the calculator".into()); }
    if let Some(existing) = app.get_webview_window(LABEL) {
        existing.unminimize().map_err(|e| e.to_string())?;
        return existing.set_focus().map_err(|e| e.to_string());
    }
    *state.0.lock().map_err(|e| e.to_string())? = snapshot;
    tauri::WebviewWindowBuilder::new(&app, LABEL, tauri::WebviewUrl::App("index.html?tool=driver-calculator".into()))
        .title("Driver calculator").inner_size(1100.0, 800.0).min_inner_size(520.0, 400.0)
        .build().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn driver_calculator_seed(window: tauri::WebviewWindow, state: tauri::State<'_, DriverCalculatorSeed>) -> Result<Option<serde_json::Value>, String> {
    if window.label() != LABEL { return Err("Not a calculator window".into()); }
    Ok(state.0.lock().map_err(|e| e.to_string())?.clone())
}

#[tauri::command]
pub fn request_driver_calculator_import(app: tauri::AppHandle, window: tauri::WebviewWindow, request_id: String) -> Result<(), String> {
    if window.label() != LABEL { return Err("Not a calculator window".into()); }
    if request_id.is_empty() || request_id.len() > 128 { return Err("Invalid calculator request id".into()); }
    app.emit_to("main", "driver-calculator:import", request_id).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn provide_driver_calculator_import(app: tauri::AppHandle, window: tauri::WebviewWindow, result: serde_json::Value) -> Result<(), String> {
    if window.label() != "main" { return Err("Only the motor workspace can provide winding data".into()); }
    app.emit_to(LABEL, "driver-calculator:result", result).map_err(|e| e.to_string())
}
