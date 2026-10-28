//! Interactive, bounded preview models. No archived/FEM force substitution.
use crate::ipc::LinearMotorConfigIpc;
use pcbmotorgen_export::cad_dxf::CadGeometry;
use pcbmotorgen_simulation::{
    drive::DriveSettings,
    visualization::{CopperLossPreview, FieldPreview, VisualizationRequest},
};
use serde::Serialize;
use sha2::{Digest, Sha256};

#[derive(Serialize)]
pub struct VisualizationReport {
    schema: &'static str,
    request_id: String,
    input_sha256: String,
    implementation_sha256: String,
    app_version: &'static str,
    coordinate_convention: &'static str,
    field: Option<FieldPreview>,
    heat: Option<CopperLossPreview>,
    heat_unavailable_reason: Option<String>,
}

#[tauri::command]
pub async fn sample_simulation_visualization(
    config: LinearMotorConfigIpc,
    drive_settings: DriveSettings,
    cad_geometry: Option<CadGeometry>,
    request: VisualizationRequest,
) -> Result<VisualizationReport, String> {
    request.validate()?;
    let core = config.to_core();
    core.validate().map_err(|e| e.to_string())?;
    let input_sha256 = format!(
        "{:x}",
        Sha256::digest(
            serde_json::to_vec(&(&config, &drive_settings, &cad_geometry, &request))
                .map_err(|e| e.to_string())?
        )
    );
    let implementation_sha256=format!("{:x}",Sha256::digest(concat!(include_str!("visualization.rs"),
        include_str!("../../../../../Cargo.lock"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/visualization.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/drive/geometry.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/drive/mod.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/units.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/physics/mod.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/magnetic/magnet_model/mod.rs"),
        include_str!("../../../../../crates/pcbmotorgen-simulation/src/magnetic/magnet_model/arrangements/alternating.rs")).as_bytes()));
    tauri::async_runtime::spawn_blocking(move || {
        let sim = core.to_simulation();
        let field = if request.fields {
            Some(pcbmotorgen_simulation::visualization::pm_field(
                &sim, &request,
            )?)
        } else {
            None
        };
        let heat = if !request.heat {
            Ok(None)
        } else {
            let calculate = || -> Result<CopperLossPreview, String> {
                if let Some(cad) = cad_geometry.as_ref() {
                    let board = super::cad_source::CadBoard::new(cad, &core)?;
                    return pcbmotorgen_simulation::visualization::copper_loss(
                        &board.simulation_input(cad, &core),
                        &board.routing,
                        &drive_settings,
                        &super::cad_source::CadBoard::drive_hints(cad),
                        request.phase_peak_a,
                    );
                }
                core.design_rules().validate_trace_width()?;
                let routing = pcbmotorgen_routing::generate_routing_result(
                    &core.routing_context(),
                    &core.routing_pattern_id(),
                )
                .map_err(|e| format!("Actual routing failed: {e}"))?;
                pcbmotorgen_simulation::visualization::copper_loss(
                    &sim,
                    &routing,
                    &drive_settings,
                    &Default::default(),
                    request.phase_peak_a,
                )
            };
            calculate().map(Some)
        };
        let (heat, heat_unavailable_reason) = match heat {
            Ok(v) => (v, None),
            Err(reason) => (None, Some(reason)),
        };
        Ok(VisualizationReport {
            schema: "simulation-visualization-v1",
            request_id: request.request_id,
            input_sha256,
            implementation_sha256,
            app_version: env!("CARGO_PKG_VERSION"),
            coordinate_convention:
                "SI routing frame: X travel, Y across board, PCB top Z=0; no geometry relocation",
            field,
            heat,
            heat_unavailable_reason,
        })
    })
    .await
    .map_err(|e| format!("Visualization worker failed: {e}"))?
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request() -> VisualizationRequest {
        VisualizationRequest {
            request_id: "actual-view".into(),
            mover_position_m: 0.01,
            bounds_m: [[0., 0.02], [0., 0.008], [-0.001, 0.005]],
            counts: [4, 3, 3],
            phase_peak_a: 1.,
            fields: true,
            heat: true,
        }
    }
    #[test]
    fn actual_generated_inputs_return_native_scoped_fields_and_losses() {
        let config = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        let result = tauri::async_runtime::block_on(sample_simulation_visualization(
            config,
            Default::default(),
            None,
            request(),
        ))
        .unwrap();
        assert_eq!(result.field.as_ref().unwrap().samples.len(), 36);
        assert_eq!(result.input_sha256.len(), 64);
        let heat = result.heat.as_ref().unwrap();
        assert!(heat.total_loss_w > 0.);
        assert!(heat.power_balance_relative_error < 1e-8);
        let json = serde_json::to_value(&result).unwrap();
        assert!(json.get("pm_array_force_n").is_none());
        assert!(json.get("temperature_c").is_none());
    }
    #[test]
    fn overflow_nonfinite_or_invalid_pose_is_rejected_before_sampling() {
        for change in 0..3 {
            let mut r = request();
            if change == 0 {
                r.counts = [usize::MAX, 64, 64];
            } else if change == 1 {
                r.bounds_m[1] = [0., f64::NAN];
            } else {
                r.mover_position_m = f64::INFINITY;
            }
            let config = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
            assert!(
                tauri::async_runtime::block_on(sample_simulation_visualization(
                    config,
                    Default::default(),
                    None,
                    r
                ))
                .is_err()
            );
        }
    }

    #[test]
    #[ignore = "Explicit interactive native-model export for saved-design viewer verification; requires PCB_MOTOR_PROJECT_PATH and PCB_MOTOR_VISUALIZATION_OUTPUT"]
    fn export_saved_design_visualization_for_viewer_verification() {
        let path = std::env::var("PCB_MOTOR_PROJECT_PATH").unwrap();
        let project: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        let state = &project["versions"][1]["state"];
        let saved: crate::ipc::ProjectConfigStateIpc =
            serde_json::from_value(state["config"].clone()).unwrap();
        let config = saved.to_linear_motor_ipc();
        let cad: Option<CadGeometry> =
            serde_json::from_value(state["cad_geometry"].clone()).unwrap();
        let coils =
            tauri::async_runtime::block_on(super::super::physics::generate_coils(config.clone()))
                .unwrap();
        let sim = config.to_core().to_simulation();
        let mut r = VisualizationRequest {
            request_id: "saved-design-native-viewer".into(),
            mover_position_m: 0.01,
            bounds_m: [
                [0., sim.active_area_length_m],
                [0., sim.board_width_m],
                [
                    -sim.pcb_thickness_m - 0.0005,
                    sim.air_gap_m + sim.magnet_dims_m[2] + 0.001,
                ],
            ],
            counts: [12, 5, 4],
            phase_peak_a: sim.max_current_a,
            fields: true,
            heat: true,
        };
        // Explicit bounded interactive sampling for field-line/slice rendering
        // checks. This never starts an offline source or force campaign.
        if std::env::var_os("PCB_MOTOR_VISUALIZATION_EXPANDED_FIELD").is_some() {
            let padding = sim.magnet_pitch_m * 0.6;
            r.bounds_m[0] = [
                (r.mover_position_m - sim.magnet_dims_m[0] / 2.).min(0.) - padding,
                (r.mover_position_m + (sim.magnet_count - 1) as f64 * sim.magnet_pitch_m
                    + sim.magnet_dims_m[0] / 2.).max(sim.active_area_length_m) + padding,
            ];
            r.bounds_m[2] = [-sim.pcb_thickness_m - padding, sim.air_gap_m + sim.magnet_dims_m[2] + padding];
            r.counts = [28, 4, 18];
        }
        if let Some(path) = std::env::var_os("PCB_MOTOR_VISUALIZATION_GRID_REQUEST_PATH") {
            let value: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
            r.bounds_m = serde_json::from_value(value["sampling"]["bounds_m"].clone()).unwrap();
            r.counts = serde_json::from_value(value["sampling"]["counts"].clone()).unwrap();
        }
        let result = tauri::async_runtime::block_on(sample_simulation_visualization(
            config.clone(),
            saved.drive.clone(),
            cad.clone(),
            r.clone(),
        ))
        .unwrap();
        assert!(
            result.heat_unavailable_reason.is_none(),
            "{:?}",
            result.heat_unavailable_reason
        );
        let output = std::env::var("PCB_MOTOR_VISUALIZATION_OUTPUT").unwrap();
        let value = serde_json::json!({"scope":"Actual saved-design/native model sampling and graph-loss viewer integration only; no FEM or temperature qualification",
            "source_project":path,"config":config,"drive":saved.drive,"cad_geometry":cad,"coils":coils,"request":r,"report":result});
        use std::io::Write;
        std::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&output)
            .unwrap()
            .write_all(&serde_json::to_vec_pretty(&value).unwrap())
            .unwrap();
        println!("Actual native viewer verification: {output}");
    }
}
