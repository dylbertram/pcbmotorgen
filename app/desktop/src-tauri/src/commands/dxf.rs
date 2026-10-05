//! DXF export command (pure `pcbmotorgen-export` R12 ASCII export).

use crate::ipc::*;
use pcbmotorgen_export::cad_dxf::{
    cad_geometry_to_3d_dxf, import_3d_dxf, phase_coils_to_cad_geometry, CadGeometry,
    CadImportOptions,
};

// ===========================================================================
// export_coils_dxf — REAL (pcbmotorgen-export pure DXF R12 ASCII export)
// ===========================================================================

/// DXF export result returned to the frontend.
///
/// The frontend writes `dxf_content` to a file selected by the user via
/// `dialog.save()`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct DxfExportResult {
    /// Full DXF R12 ASCII content, ready to write to a `.dxf` file.
    pub dxf_content: String,
    /// Human-readable summary for UI feedback.
    pub summary: DxfExportSummary,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct DxfExportSummary {
    pub total_lines: u32,
    pub total_arcs: u32,
    pub total_circles: u32,
    pub layer_count: u32,
}

/// Generate coil geometry from the config and return it as a DXF R12 ASCII
/// string suitable for mechanical CAD / CAM import.
///
/// The command builds the same `PhaseCoil` set as `write_coils_to_board`,
/// converts it to DXF via `pcbmotorgen_export::phase_coils_to_dxf`, and returns
/// the complete file content. The frontend is responsible for saving to disk.
#[tauri::command]
pub async fn export_coils_dxf(config: LinearMotorConfigIpc) -> Result<DxfExportResult, String> {
    let core = config.to_core();
    tauri::async_runtime::spawn_blocking(move || {
        let coils = core.generate_coils_for_board();
        let num_layers = core.num_layers;
        let rules = core.design_rules();
        let active = core.active_area_length_m * 1e3;

        let geometry = phase_coils_to_cad_geometry(
            &coils,
            num_layers,
            core.pcb_thickness_m * 1e3,
            rules.min_trace_mm,
        )?;
        let mut geometry = geometry;
        // Generated geometry is centred for CAD, matching the legacy exporter.
        let x_offset = active / 2.0;
        for segment in &mut geometry.routing.segments {
            segment.start.x -= x_offset;
            segment.end.x -= x_offset;
        }
        for curve in &mut geometry.routing.curves {
            curve.start.x -= x_offset;
            curve.mid.x -= x_offset;
            curve.end.x -= x_offset;
        }
        for via in &mut geometry.routing.vias {
            via.position.x -= x_offset;
        }
        let dxf_content = cad_geometry_to_3d_dxf(&geometry)?;

        let total_lines = dxf_content.matches("0\nLINE\n").count() as u32;
        let total_arcs = dxf_content.matches("0\nARC\n").count() as u32;
        let total_circles = dxf_content.matches("0\nCIRCLE\n").count() as u32;

        // Count unique layer names from the DXF LAYER definitions in the
        // TABLES section (each `LAYER\n  2\n<name>` pair).
        let layer_count = dxf_content.match_indices("LAYER\n  2\n").count() as u32;

        Ok(DxfExportResult {
            dxf_content,
            summary: DxfExportSummary {
                total_lines,
                total_arcs,
                total_circles,
                layer_count,
            },
        })
    })
    .await
    .map_err(|e| format!("export_coils_dxf worker failed: {e}"))?
}

/// Import planar copper traces and vertical inter-layer via centerlines from DXF.
#[tauri::command]
pub async fn import_cad_dxf(
    path: String,
    units_to_mm: f64,
    z_tolerance_mm: f64,
    default_trace_width_mm: f64,
    legacy_layer_count: u32,
    legacy_pcb_thickness_mm: f64,
) -> Result<pcbmotorgen_export::cad_dxf::CadImportResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let text = std::fs::read_to_string(&path)
            .map_err(|e| format!("could not read CAD file \"{path}\": {e}"))?;
        import_3d_dxf(
            &text,
            CadImportOptions {
                units_to_mm,
                z_tolerance_mm,
                default_trace_width_mm,
                legacy_layer_count,
                legacy_pcb_thickness_mm,
            },
        )
        .map_err(|e| format!("DXF import failed: {e}"))
    })
    .await
    .map_err(|e| format!("import_cad_dxf worker failed: {e}"))?
}

/// Export the active saved geometry as round-trippable 3D DXF.
#[tauri::command]
pub async fn export_cad_geometry_dxf(geometry: CadGeometry) -> Result<DxfExportResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let dxf_content = cad_geometry_to_3d_dxf(&geometry)?;
        let total_lines = dxf_content.matches("0\nLINE\n").count() as u32;
        let total_arcs = dxf_content.matches("0\nARC\n").count() as u32;
        let total_circles = dxf_content.matches("0\nCIRCLE\n").count() as u32;
        let layer_count = dxf_content.match_indices("LAYER\n  2\n").count() as u32;
        Ok(DxfExportResult {
            dxf_content,
            summary: DxfExportSummary {
                total_lines,
                total_arcs,
                total_circles,
                layer_count,
            },
        })
    })
    .await
    .map_err(|e| format!("export_cad_geometry_dxf worker failed: {e}"))?
}
