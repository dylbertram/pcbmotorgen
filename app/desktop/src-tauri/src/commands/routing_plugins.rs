//! Routing-pattern plugin catalog commands: listing, registration, persisted
//! plugin-store management, parameter introspection, and DRC interference
//! checks on the routed coils.

use crate::ipc::*;

// ===========================================================================
// list_routing_patterns — routing-pattern plugin catalog
// ===========================================================================

/// One entry in the routing-pattern catalog.
#[derive(serde::Serialize)]
pub struct RoutingPatternInfo {
    pub id: String,
    pub display_name: String,
    /// Pattern-declared layer-range constraints (null = unconstrained).
    /// Mirrored IPC metadata: the frontend only constrains its inputs with
    /// these — the routing crate re-validates authoritatively at generate
    /// time (`validate_layer_range`).
    pub min_layers: Option<u32>,
    pub max_layers: Option<u32>,
    pub layers_multiple_of: Option<u32>,
}

/// List the loadable routing-pattern plugins for the frontend selector, with
/// their declared layer-range metadata.
#[tauri::command]
pub async fn list_routing_patterns() -> Vec<RoutingPatternInfo> {
    pcbmotorgen_routing::available_pattern_metadata()
        .into_iter()
        .map(|m| RoutingPatternInfo {
            id: m.id,
            display_name: m.display_name,
            min_layers: m.min_layers,
            max_layers: m.max_layers,
            layers_multiple_of: m.layers_multiple_of,
        })
        .collect()
}

/// Load and register a routing-pattern plugin (native `cdylib` or Python
/// runner) into the runtime registry AND into the app's persistent plugin
/// store. The plugin is probed against `config` and rejected on upload with a
/// helpful error if it produces a malformed shape.
#[tauri::command]
pub async fn register_routing_plugin(
    app: tauri::AppHandle,
    kind: String,
    path: String,
    name: Option<String>,
    probe_config: LinearMotorConfigIpc,
) -> Result<String, String> {
    let src = std::path::PathBuf::from(&path);
    if !src.is_file() {
        return Err(format!("file not found: {path}"));
    }
    let probe = probe_config.to_core();
    let kind_owned = kind.clone();
    let name_owned = name.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let id = match kind_owned.as_str() {
            "native" => pcbmotorgen_routing::register_native_plugin(&src, &probe.routing_context()),
            "python" => pcbmotorgen_routing::register_python_runner(
                &src,
                &probe.routing_context(),
                name_owned.as_deref(),
            ),
            other => Err(format!(
                "unknown plugin kind \"{other}\" — use \"native\" (cdylib) or \"python\" (runner)"
            )),
        }?;

        // Persist: copy into app data dir + record metadata in plugins.json.
        crate::plugins::register_and_persist(&app, &id, &kind_owned, &src)?;
        Ok(id)
    })
    .await
    .map_err(|e| format!("register_routing_plugin worker failed: {e}"))?
}

/// Re-register every installed plugin from the app's persistent store (run at
/// startup). Returns any per-plugin load errors, so a broken plugin is skipped
/// without crashing the app.
#[tauri::command]
pub async fn load_installed_plugins(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    let installed = crate::plugins::list_plugins(&app);
    let mut errors = Vec::new();
    for p in installed {
        let stored = p.stored_path(&app)?;
        let probe = get_probe_config();
        let res = match p.kind.as_str() {
            "native" => pcbmotorgen_routing::register_native_plugin(&stored, &probe.routing_context()),
            "python" => {
                pcbmotorgen_routing::register_python_runner(&stored, &probe.routing_context(), Some(&p.id))
            }
            _ => Err(format!("unknown stored plugin kind {}", p.kind)),
        };
        if let Err(e) = res {
            errors.push(format!("{}: {e}", p.id));
        }
    }
    Ok(errors)
}

/// List installed plugins (persistent store) with their metadata.
#[tauri::command]
pub async fn list_installed_plugins(app: tauri::AppHandle) -> Vec<InstalledPluginIpc> {
    crate::plugins::list_plugins(&app)
        .into_iter()
        .map(|p| InstalledPluginIpc {
            id: p.id,
            kind: p.kind,
            display_name: p.display_name,
            author: p.author,
            version: p.version,
            description: p.description,
        })
        .collect()
}

/// Remove an installed plugin from the persistent store and the runtime
/// registry by id.
#[tauri::command]
pub async fn remove_routing_plugin(app: tauri::AppHandle, id: String) -> Result<(), String> {
    crate::plugins::remove_plugin(&app, &id)?;
    pcbmotorgen_routing::unregister_runtime_pattern(&id);
    Ok(())
}

/// One installed-plugin entry (wire form).
#[derive(serde::Serialize)]
pub struct InstalledPluginIpc {
    pub id: String,
    pub kind: String,
    pub display_name: String,
    pub author: String,
    pub version: String,
    pub description: String,
}

/// A minimal probe config for re-loading stored plugins at startup (safe,
/// deterministic geometry).
fn get_probe_config() -> crate::config::LinearMotorConfig {
    use pcbmotorgen_simulation::units::{mm, mils_to_m};
    crate::config::LinearMotorConfig {
        active_area_length_m: mm(120.0),
        board_width_m: mm(20.0),
        magnet_dims_m: [mm(10.0), mm(10.0), mm(4.0)],
        magnet_count: 6,
        magnet_pitch_m: mm(12.0),
        phases: 3,
        target_force_n: 0.2,
        max_current_a: 1.0,
        min_trace_m: mils_to_m(5.0),
        min_space_m: mils_to_m(5.0),
        min_via_drill_m: mm(0.2),
        min_via_annular_ring_m: mm(0.1),
        air_gap_m: mm(0.5),
        max_layers: 4,
        num_layers: 2,
        routing_pattern: "infinity-braid".to_string(),
        ..crate::config::LinearMotorConfig::default()
    }
}

/// Look up the user-editable parameters a routing pattern exposes.
#[tauri::command]
pub async fn routing_pattern_parameters(
    pattern_id: String,
) -> Vec<ParamDefIpc> {
    pcbmotorgen_routing::pattern_parameters(&pattern_id)
        .into_iter()
        .map(|p| ParamDefIpc {
            key: p.key,
            label: p.label,
            description: p.description,
            param_type: match p.param_type {
                pcbmotorgen_routing::ParamType::Int => "int".to_string(),
                pcbmotorgen_routing::ParamType::Float => "float".to_string(),
            },
            default: p.default,
            min: p.min,
            max: p.max,
            step: p.step,
            multiple_of: p.multiple_of,
        })
        .collect()
}

/// A routing-pattern parameter definition (wire form).
#[derive(serde::Serialize)]
pub struct ParamDefIpc {
    pub key: String,
    pub label: String,
    pub description: String,
    pub param_type: String,
    pub default: f64,
    pub min: Option<f64>,
    pub max: Option<f64>,
    pub step: Option<f64>,
    /// "Valid values are multiples of this" constraint declared by the
    /// pattern (null = unconstrained). The frontend mirrors it onto the
    /// input's step + invalid state; the routing crate remains the
    /// validation authority at generate-time (`validate_routing_params`).
    pub multiple_of: Option<f64>,
}

/// One DRC interference violation (wire form).
#[derive(serde::Serialize)]
pub struct InterferenceViolationIpc {
    pub layer: u32,
    pub net_a: String,
    pub net_b: String,
    pub kind: String,
    pub gap_mm: f64,
    pub message: String,
}

/// Run the core's design-rule (interference) checks on the coils the current
/// pattern produces, using the configured trace width / via sizes. The routing
/// plugin only supplies raw lines; all clearance checks happen downstream in
/// the DFM crate (`pcbmotorgen-dfm`, kata 0rgs).
#[tauri::command]
pub async fn check_coil_interference(
    config: LinearMotorConfigIpc,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
) -> Result<Vec<InterferenceViolationIpc>, String> {
    let core = config.to_core();
    tauri::async_runtime::spawn_blocking(move || {
        let (result, rules) = match cad_geometry.as_ref() {
            // Imported copper is checked as drawn. Before every coil has a
            // phase, coils keep their own nets so DRC still runs.
            Some(cad) => {
                let mut rules = core.design_rules();
                rules.min_trace_mm = cad.trace_width_mm;
                (cad.routing_by_phase().unwrap_or_else(|_| cad.routing.clone()), rules)
            }
            None => {
                let ctx = core.routing_context();
                let result =
                    pcbmotorgen_routing::generate_routing_result(&ctx, &core.routing_pattern_id())
                        .map_err(|e| format!("routing pattern failed: {e}"))?;
                (result, core.design_rules())
            }
        };
        let violations = pcbmotorgen_dfm::check_interference(&rules, &result);
        Ok(violations
            .into_iter()
            .map(|v| InterferenceViolationIpc {
                layer: v.layer,
                net_a: v.net_a,
                net_b: v.net_b,
                kind: v.kind.to_string(),
                gap_mm: v.gap_mm,
                message: v.message,
            })
            .collect())
    })
    .await
    .map_err(|e| format!("check_coil_interference worker failed: {e}"))?
}