//! Native induction-position-sensor geometry generation.

use pcbmotorgen_routing::{generate_sensor, SensorConfig, SensorGeometry};

#[tauri::command]
pub async fn generate_sensor_geometry(config: SensorConfig) -> Result<SensorGeometry, String> {
    tauri::async_runtime::spawn_blocking(move || generate_sensor(&config))
        .await
        .map_err(|e| format!("generate_sensor_geometry worker failed: {e}"))?
}
