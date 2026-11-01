//! Project persistence wire format (kata 0cgm): the versioned `.pmproj`
//! artifact DTOs, envelope build/parse, version migration, and the
//! load-time design validation gate.
//!
//! ## Architecture boundary
//!
//! ALL persistence logic lives here and in [`crate::commands::project`] —
//! serialization, versioning/migration, file I/O, and validation. The
//! Svelte frontend only gathers the user-facing state into
//! [`ProjectStateIpc`] (the same way it builds `LinearMotorConfigIpc` for
//! physics calls) and picks a path via the native dialog plugin.
//!
//! ## What is saved
//!
//! The user's INPUTS (motor parameters + generation settings, in the
//! user-facing units the UI edits — mm etc.), plus the mover position.
//! Deliberately NOT saved:
//! - Runtime catalogs (`routing_patterns`, magnet grades, routing param
//!   defs) — backend-owned, reloaded at startup.
//! - Simulation/preview RESULTS (force sweep, coils, stackup, …) — they
//!   are pure functions of the restored inputs and are recomputed
//!   automatically by the frontend's existing reactive scheduling after a
//!   load. Persisting them would risk staleness against a newer physics
//!   engine and bloat the artifact.
//!
//! ## Format + version policy (house style: routing API.md §15)
//!
//! Format v2 stores every design version in one archive, implemented in
//! [`super::project_versions`]. Each version has a stable ID, a description,
//! creation/edit timestamps, and its own complete [`ProjectStateIpc`].
//! Opening an archive selects the version with the greatest last-edited time.
//! The older single-state v1 envelope is still accepted and becomes version 1
//! in memory. The next save writes v2 without losing its inputs or save time.
//!
//! The legacy v1 artifact looked like this:
//!
//! ```json
//! {
//!   "format_version": 1,
//!   "app_version": "0.5.0",
//!   "saved_at_unix_ms": 1790000000000,
//!   "state": { "config": { "…": 0 }, "mover_position_mm": 60.0 }
//! }
//! ```
//!
//! - **Additive change** (new optional state field): no version bump.
//!   `ProjectConfigStateIpc` carries a hand-written `Default` matching the
//!   frontend store defaults, applied per-field via container-level
//!   `#[serde(default)]`, so an older artifact missing a newer field loads
//!   with the app default for that field. Unknown fields are ignored
//!   (serde default behaviour) — a newer artifact's extra fields don't
//!   break an older build's read path (forward tolerance on read).
//! - **Breaking change** (units/semantics/field removal): bump
//!   `PROJECT_FORMAT_VERSION` and extend `parse_project_archive` migration.
//! - **Version mismatches**: a file with `format_version` greater than
//!   this build is REJECTED with a clear message (its semantics are
//!   unknown — guessing would silently corrupt the user's design).
//! - **Deliberate deviation from the plugin wire contract**: unlike the
//!   routing envelope (where an absent `format_version` means "current"),
//!   a project file's missing `format_version` is REJECTED. A project
//!   file has exactly one producer (this app), so an absent version means
//!   corrupt or foreign content; defaulting it could mis-migrate.
//!
//! All structs use `rename_all = "snake_case"` matching the established
//! IPC convention mirrored in `src/lib/types/`.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

use super::config::LinearMotorConfigIpc;
use super::enums::CommutationModeIpc;
use pcbmotorgen_export::cad_dxf::CadGeometry;
use pcbmotorgen_routing::SensorConfig;

/// Current project-file format version. Bump on breaking changes and add
/// a migration step (see the module docs).
pub const PROJECT_FORMAT_VERSION: u32 = 2;

// ===========================================================================
// State payload (crosses IPC on save AND load)
// ===========================================================================

/// The user's working state: design inputs + mover position.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", default)]
pub struct ProjectStateIpc {
    pub config: ProjectConfigStateIpc,
    /// Mover-centre position the user left the design at (mm, absolute
    /// track coordinates — same frame as `MotionStore.positionMm`).
    pub mover_position_mm: f64,
    /// Imported/user-owned CAD geometry. Missing fields in v1 artifacts mean
    /// the project remains config-generated, preserving backward compatibility.
    #[serde(default)]
    pub cad_geometry: Option<CadGeometry>,
    /// Independent induction-position sensor settings. Missing in older
    /// artifacts, in which case the generator defaults are restored.
    #[serde(default)]
    pub sensor_config: SensorConfig,
    /// Imported sensor centerlines, independent of motor CAD geometry.
    #[serde(default)]
    pub sensor_cad_geometry: Option<CadGeometry>,
}

impl Default for ProjectStateIpc {
    fn default() -> Self {
        Self {
            config: ProjectConfigStateIpc::default(),
            mover_position_mm: 60.0,
            cad_geometry: None,
            sensor_config: SensorConfig::default(),
            sensor_cad_geometry: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum CarriageMassSource {
    Magnets,
    Assembly,
}

/// Every user-facing design input, in UI units (mm and SI engineering
/// units) — mirrors the fields of the frontend `ConfigStore` one-for-one.
///
/// Container-level `#[serde(default)]` + the hand-written `Default` (which
/// mirrors the frontend store defaults) implement the additive-versioning
/// policy: a field added in a later version loads from an older artifact
/// with the app default value instead of a zero.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", default)]
pub struct ProjectConfigStateIpc {
    // --- Topology ---
    pub topology: String,

    // --- Active area (mm) ---
    pub desired_travel_mm: f64,
    pub active_area_width_mm: f64,

    // --- Multi-strand ---
    pub strands_per_phase: u32,

    // --- Magnet array (mm) ---
    pub magnet_count: u32,
    pub magnet_width_mm: f64,
    pub magnet_cross_width_mm: f64,
    pub magnet_height_mm: f64,
    pub magnet_grade: String,
    pub magnet_remanence_t: f64,
    pub air_gap_mm: f64,

    // --- Phase-band constraint (mm) ---
    pub electrical_pitch_mm: f64,

    // --- Coil / routing (generation settings) ---
    pub routing_pattern: String,
    // Do not apply the new-project termination to old files with no params.
    #[serde(default)]
    pub routing_params: HashMap<String, f64>,
    #[serde(default)]
    pub routing_orientation: pcbmotorgen_routing::RoutingOrientation,
    pub phases: u32,
    pub num_layers: u32,

    // --- Drive / electrical ---
    pub max_current_a: f64,
    pub supply_voltage_v: f64,

    // --- Force targets / mechanical ---
    pub target_force_n: f64,
    pub peak_force_n: f64,
    pub friction_n: f64,
    pub carriage_mass_kg: f64,
    /// None preserves legacy saved masses; new UI designs explicitly select magnets or assembly.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub carriage_mass_source: Option<CarriageMassSource>,
    pub max_accel_m_s2: f64,
    pub capacitor_bank_uf: f64,

    // --- Solver ---
    pub commutation: CommutationModeIpc,
    pub n_positions: u32,
    pub meshing: u32,

    // --- PCB manufacturing defaults (mm) ---
    pub min_trace_mm: f64,
    /// Nominal (actual) trace width [mm]. `None` in files saved before it
    /// existed; callers fall back to `min_trace_mm` so older projects keep
    /// their copper width.
    #[serde(default)]
    pub trace_width_mm: Option<f64>,
    pub min_space_mm: f64,
    pub min_via_drill_mm: f64,
    pub min_via_annular_ring_mm: f64,
    pub pcb_thickness_mm: f64,
    /// Explicit layer thicknesses in saved UI units.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pcb_stackup_mm: Option<PcbStackupMm>,
    pub max_layers: u32,
    pub drive_frequency_hz: f64,
    pub max_temperature_rise_c: f64,

    // --- Driver suitability (Simulation tab) ---
    /// Driver IC limits and operating assumptions; absent in older files.
    pub drive: pcbmotorgen_simulation::drive::DriveSettings,

    /// Explicit optional operating requirements. Legacy files have no move,
    /// never an invented duration, mass breakdown, controller or loss law.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub power_move: Option<pcbmotorgen_simulation::drive::move_power::routed::RoutedMoveRequest>,

    // --- Backplane and housing stackup (t707) ---
    /// Layers below the PCB and the optional housing; absent in older files,
    /// which load with no backplane.
    #[serde(default)]
    pub backplane: Option<pcbmotorgen_simulation::backplane::BackplaneStack>,
}

/// Deserialization defaults preserve legacy inputs. New frontend designs use
/// automatic magnet mass; legacy artifacts without a mass basis keep their
/// saved carriage mass, with 15 g retained only as the missing-field fallback.
/// Other values mirror the frontend initial design.
impl Default for ProjectConfigStateIpc {
    fn default() -> Self {
        Self {
            topology: "linear".to_string(),
            desired_travel_mm: 75.0,
            active_area_width_mm: 20.0,
            strands_per_phase: 2,
            magnet_count: 12,
            magnet_width_mm: 4.5,
            magnet_cross_width_mm: 10.0,
            magnet_height_mm: 3.0,
            magnet_grade: "N44".to_string(),
            magnet_remanence_t: 1.34,
            air_gap_mm: 0.5,
            electrical_pitch_mm: 12.0,
            routing_pattern: "infinity-braid".to_string(),
            // New driver-ready projects use terminated star windings. Bare
            // routing contexts can still explicitly request closed rings.
            routing_params: HashMap::from([("connection".into(), 2.0), ("pole_matched".into(), 1.0)]),
            routing_orientation: Default::default(),
            phases: 3,
            num_layers: 4,
            max_current_a: 1.0,
            supply_voltage_v: 5.0,
            target_force_n: 0.5,
            peak_force_n: 1.0,
            friction_n: 0.05,
            carriage_mass_kg: 0.015,
            carriage_mass_source: None,
            max_accel_m_s2: 2.0,
            capacitor_bank_uf: 1000.0,
            commutation: CommutationModeIpc::MaxThrust,
            n_positions: 50,
            meshing: 20,
            min_trace_mm: 0.127,
            trace_width_mm: None,
            min_space_mm: 0.127,
            min_via_drill_mm: 0.2,
            min_via_annular_ring_mm: 0.1,
            pcb_thickness_mm: 1.6,
            pcb_stackup_mm: None,
            max_layers: pcbmotorgen_simulation::params::MAX_PCB_LAYERS,
            drive_frequency_hz: 500.0,
            max_temperature_rise_c: 20.0,
            drive: pcbmotorgen_simulation::drive::DriveSettings::default(),
            power_move: None,
            backplane: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PcbStackupMm {
    pub copper_mm: Vec<f64>,
    pub dielectric_mm: Vec<f64>,
}

impl ProjectConfigStateIpc {
    /// Convert the user-unit design inputs into the SI `LinearMotorConfigIpc`
    /// used by every physics command — the Rust mirror of the frontend
    /// store's `toIpc()`. Used ONLY for load-time validation of the
    /// restored design; the runtime source of truth remains the frontend
    /// store's own conversion.
    ///
    /// Derived quantities are recomputed exactly as the store derives them:
    /// - pole pitch tau_p = electrical_pitch / 2
    /// - active-area length = desired travel + physical mover span
    /// - magnet gap = max(0, tau_p - width), spacing ratio pinned to 1.0
    pub fn to_linear_motor_ipc(&self) -> LinearMotorConfigIpc {
        let pole_pitch_mm = self.electrical_pitch_mm / 2.0;
        let mover_span_mm = self.magnet_count.saturating_sub(1) as f64 * pole_pitch_mm + self.magnet_width_mm;
        let active_len_mm = self.desired_travel_mm + mover_span_mm;
        let gap_mm = (pole_pitch_mm - self.magnet_width_mm).max(0.0);
        let m = |mm: f64| mm / 1000.0;

        LinearMotorConfigIpc {
            active_area_length_m: m(active_len_mm),
            board_width_m: m(self.active_area_width_mm),
            pcb_thickness_m: m(self.pcb_thickness_mm),
            pcb_stackup: self.pcb_stackup_mm.as_ref().map(|s| pcbmotorgen_simulation::params::PcbStackup {
                copper_m: s.copper_mm.iter().map(|t| m(*t)).collect(),
                dielectric_m: s.dielectric_mm.iter().map(|t| m(*t)).collect(),
            }),
            strands_per_phase: self.strands_per_phase,
            magnet_count: self.magnet_count,
            magnet_width_m: m(self.magnet_width_mm),
            magnet_cross_width_m: m(self.magnet_cross_width_mm),
            magnet_height_m: m(self.magnet_height_mm),
            magnet_gap_m: m(gap_mm),
            magnet_pitch_m: m(pole_pitch_mm),
            magnet_remanence_t: self.magnet_remanence_t,
            magnet_grade: self.magnet_grade.clone(),
            air_gap_m: m(self.air_gap_mm),
            routing_pattern: self.routing_pattern.clone(),
            routing_params: self.routing_params.clone(),
            routing_orientation: self.routing_orientation,
            phases: self.phases,
            spacing_ratio: 1.0,
            max_current_a: self.max_current_a,
            supply_voltage_v: self.supply_voltage_v,
            num_layers: self.num_layers,
            min_trace_m: m(self.min_trace_mm),
            trace_width_m: m(self.trace_width_mm.unwrap_or(self.min_trace_mm)),
            min_space_m: m(self.min_space_mm),
            min_via_drill_m: m(self.min_via_drill_mm),
            min_via_annular_ring_m: m(self.min_via_annular_ring_mm),
            max_layers: self.max_layers,
            drive_frequency_hz: self.drive_frequency_hz,
            backplane: self.backplane.clone(),
            max_temperature_rise_c: self.max_temperature_rise_c,
            target_force_n: self.target_force_n,
            peak_force_n: self.peak_force_n,
            friction_n: self.friction_n,
            carriage_mass_kg: self.carriage_mass_kg,
            max_accel_m_s2: self.max_accel_m_s2,
            capacitor_bank_uf: self.capacitor_bank_uf,
            commutation: self.commutation,
            n_positions: self.n_positions,
            meshing: self.meshing,
            name: None,
        }
    }
}

// ===========================================================================
// Command results
// ===========================================================================

/// Result of `save_project` — everything the UI needs to confirm the save.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SaveProjectResultIpc {
    pub path: String,
    pub format_version: u32,
    pub saved_at_unix_ms: i64,
    pub active_version_id: u32,
    pub versions: Vec<super::project_versions::ProjectVersionInfoIpc>,
}

/// Design-level validation findings for a loaded artifact. These do NOT
/// block the load (work-in-progress designs are legitimately loadable);
/// the UI surfaces them alongside the live cross-field validation.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ProjectValidationIpc {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

/// Result of `load_project`: the restored state + the artifact provenance
/// + the load-time design validation.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct LoadProjectResultIpc {
    pub project: ProjectStateIpc,
    /// Format version stamped on the file.
    pub source_format_version: u32,
    /// Version after migration (always `PROJECT_FORMAT_VERSION` on success).
    pub format_version: u32,
    pub validation: ProjectValidationIpc,
    pub active_version_id: u32,
    pub versions: Vec<super::project_versions::ProjectVersionInfoIpc>,
}

// ===========================================================================
// Envelope parse + migration + validation (pure — unit-tested here)
// ===========================================================================

/// Parse a `.pmproj` artifact: JSON → version check → migrate → typed
/// state. Returns the state and the file's source format version.
///
/// Every failure mode produces a specific, human-readable error: corrupt
/// JSON, foreign content (missing version), newer format, or malformed
/// state — the caller surfaces the message verbatim and the frontend
/// leaves the in-progress work untouched.
#[cfg(test)]
pub fn parse_project_file(json: &str) -> Result<(ProjectStateIpc, u32), String> {
    let (archive, source) = super::project_versions::parse_project_archive(json)?;
    Ok((archive.latest().project.clone(), source))
}

/// Load-time design validation of the restored state, reusing the core
/// `LinearMotorConfig::validate()` pipeline (the same gate the physics
/// commands use). The findings are informational — the load itself
/// succeeds so the user can fix the design in the UI.
pub fn design_validation(state: &ProjectStateIpc) -> ProjectValidationIpc {
    let core = state.config.to_linear_motor_ipc().to_core();
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    if let Err(e) = core.validate() {
        errors.push(e.to_string());
    }
    // Travel sanity mirror of `validate_config` (the loaded design may be
    // work-in-progress; surface the same message the UI would compute).
    let travel = core.travel_m();
    if travel <= 0.0 {
        errors.push(format!(
            "Travel is zero or negative ({:.1} mm) — active area must exceed \
             the magnet array span",
            travel * 1e3
        ));
    } else if travel < 5e-3 {
        warnings.push(format!(
            "Travel is very small ({:.1} mm) — consider a longer active area",
            travel * 1e3
        ));
    }
    if let Err(e) = pcbmotorgen_routing::generate_sensor(&state.sensor_config) {
        errors.push(format!("Induction sensor: {e}"));
    }
    ProjectValidationIpc { errors, warnings }
}

/// Atomic-ish artifact write: serialize to a sibling temp file first, then
/// rename over the destination. A mid-write failure therefore leaves the
/// previous artifact intact (worst case: an orphaned `.tmp` file). On
/// platforms where rename-over-existing fails (Windows), fall back to
/// remove-then-rename.
pub fn write_project_atomic(path: &Path, json: &str) -> Result<(), String> {
    let file_name = path
        .file_name()
        .ok_or_else(|| format!("invalid project path: {}", path.display()))?;
    let tmp = path.with_file_name(format!("{}.tmp", file_name.to_string_lossy()));
    std::fs::write(&tmp, json)
        .map_err(|e| format!("failed to write project (temp file {}): {e}", tmp.display()))?;
    if std::fs::rename(&tmp, path).is_err() {
        // Windows-style fallback: the destination may already exist.
        if path.exists() {
            std::fs::remove_file(path)
                .map_err(|e| format!("failed to replace existing project file: {e}"))?;
        }
        std::fs::rename(&tmp, path)
            .map_err(|e| format!("failed to finalize project file {}: {e}", path.display()))?;
    }
    Ok(())
}

// ===========================================================================
// Tests — the persistence module contract (kata 0cgm acceptance)
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn carriage_mass_basis_round_trips_without_reinterpreting_legacy_mass() {
        let legacy: super::ProjectConfigStateIpc = serde_json::from_value(serde_json::json!({
            "carriage_mass_kg": 0.015
        })).unwrap();
        assert_eq!(legacy.carriage_mass_kg, 0.015);
        assert_eq!(legacy.carriage_mass_source, None);
        for source in [super::CarriageMassSource::Magnets, super::CarriageMassSource::Assembly] {
            let config = super::ProjectConfigStateIpc {
                carriage_mass_source: Some(source.clone()), ..legacy.clone()
            };
            let restored: super::ProjectConfigStateIpc = serde_json::from_str(
                &serde_json::to_string(&config).unwrap()).unwrap();
            assert_eq!(restored.carriage_mass_source, Some(source));
            assert_eq!(restored.to_linear_motor_ipc().carriage_mass_kg, 0.015);
        }
    }

    /// A fully-populated state (every field non-default where meaningful).
    fn sample_state() -> ProjectStateIpc {
        let mut config = ProjectConfigStateIpc::default();
        config.desired_travel_mm = 60.0;
        config.active_area_width_mm = 25.0;
        config.magnet_count = 16;
        config.magnet_width_mm = 5.0;
        config.magnet_grade = "N52".to_string();
        config.magnet_remanence_t = 1.43;
        config.routing_pattern = "quad-stack".to_string();
        config.routing_params.insert("num_strands".into(), 3.0);
        config.num_layers = 6;
        config.commutation = CommutationModeIpc::PhaseAOnly;
        ProjectStateIpc {
            config,
            mover_position_mm: 42.5,
            cad_geometry: Some(CadGeometry {
                routing: pcbmotorgen_routing::RoutingResult {
                    segments: vec![pcbmotorgen_routing::RouteSegment {
                        start: pcbmotorgen_routing::Point::new(1.0, 2.0),
                        end: pcbmotorgen_routing::Point::new(3.0, 2.0),
                        layer: 0,
                        net: "A".into(),
                        is_active: true,
                    }],
                    ..Default::default()
                },
                layer_z_mm: vec![-0.8, 0.8],
                trace_width_mm: 0.2,
                source_file_name: Some("motor-coils.dxf".into()),
                applied_orientation: Some(pcbmotorgen_routing::RoutingOrientation { mirror_x: true, mirror_y: false, reverse_layers: true }),
                source_layer_coils: std::collections::BTreeMap::from([(
                    "Bottom winding".into(),
                    "A".into(),
                )]),
                terminal_connection: None,
                coil_terminals: std::collections::BTreeMap::from([(
                    "A".into(),
                    pcbmotorgen_export::cad_dxf::CadCoilTerminals {
                        input: pcbmotorgen_export::cad_dxf::CadTerminal {
                            position: pcbmotorgen_routing::Point::new(1.0, 2.0),
                            layer: 0,
                        },
                        output: pcbmotorgen_export::cad_dxf::CadTerminal {
                            position: pcbmotorgen_routing::Point::new(3.0, 2.0),
                            layer: 0,
                        },
                    },
                )]),
                coil_phases: std::collections::BTreeMap::new(),
            }),
            sensor_config: SensorConfig::default(),
            sensor_cad_geometry: None,
        }
    }

    /// Serialize through the real save path (envelope → pretty JSON).
    fn serialize(state: &ProjectStateIpc) -> String {
        serde_json::to_string_pretty(&super::super::project_versions::ProjectArchive::new(
            state.clone(),
            1_790_000_000_000,
        ))
        .expect("envelope serialize")
    }

    #[test]
    fn round_trip_save_load_preserves_state() {
        let state = sample_state();
        let json = serialize(&state);
        let (loaded, version) = parse_project_file(&json).expect("parse");
        assert_eq!(version, PROJECT_FORMAT_VERSION);
        assert_eq!(loaded.mover_position_mm, 42.5);
        let c = loaded.config;
        assert_eq!(c.desired_travel_mm, 60.0);
        assert_eq!(c.active_area_width_mm, 25.0);
        assert_eq!(c.magnet_count, 16);
        assert_eq!(c.magnet_width_mm, 5.0);
        assert_eq!(c.magnet_grade, "N52");
        assert_eq!(c.magnet_remanence_t, 1.43);
        assert_eq!(c.routing_pattern, "quad-stack");
        assert_eq!(c.routing_params.get("num_strands"), Some(&3.0));
        assert_eq!(c.num_layers, 6);
        assert_eq!(c.commutation, CommutationModeIpc::PhaseAOnly);
        // Untouched defaults survive the round trip too.
        assert_eq!(c.electrical_pitch_mm, 12.0);
        assert_eq!(c.capacitor_bank_uf, 1000.0);
        let geometry = loaded.cad_geometry.expect("saved CAD geometry");
        assert_eq!(geometry.layer_z_mm, vec![-0.8, 0.8]);
        assert_eq!(geometry.trace_width_mm, 0.2);
        assert_eq!(geometry.source_file_name.as_deref(), Some("motor-coils.dxf"));
        assert_eq!(geometry.routing.segments[0].net, "A");
        assert_eq!(loaded.sensor_config, SensorConfig::default());
    }

    #[test]
    fn sensor_cad_round_trip_is_independent_of_motor_cad() {
        let mut state = sample_state();
        state.sensor_cad_geometry = state.cad_geometry.clone();
        state.sensor_cad_geometry.as_mut().unwrap().routing.segments[0].net = "CL1".into();
        let (loaded, _) = parse_project_file(&serialize(&state)).expect("parse");
        assert_eq!(loaded.cad_geometry.unwrap().routing.segments[0].net, "A");
        assert_eq!(
            loaded.sensor_cad_geometry.unwrap().routing.segments[0].net,
            "CL1"
        );
        let mut legacy: serde_json::Value = serde_json::from_str(&serialize(&state)).unwrap();
        legacy["versions"][0]["project"]
            .as_object_mut()
            .unwrap()
            .remove("sensor_cad_geometry");
        assert!(parse_project_file(&legacy.to_string())
            .unwrap()
            .0
            .sensor_cad_geometry
            .is_none());
    }

    #[test]
    fn older_project_without_sensor_settings_gets_sensor_defaults() {
        let mut value: serde_json::Value =
            serde_json::from_str(&serialize(&sample_state())).expect("json");
        value["versions"][0]["project"]
            .as_object_mut()
            .unwrap()
            .remove("sensor_config");
        let (loaded, _) = parse_project_file(&value.to_string()).expect("old project loads");
        assert_eq!(loaded.sensor_config, SensorConfig::default());
    }

    #[test]
    fn corrupt_json_rejected() {
        let err = parse_project_file("{ this is not json").expect_err("must reject");
        assert!(err.contains("corrupt project file"), "got: {err}");
    }

    #[test]
    fn non_object_content_rejected() {
        let err = parse_project_file("[1, 2, 3]").expect_err("must reject");
        assert!(err.contains("expected a JSON object"), "got: {err}");
    }

    #[test]
    fn missing_format_version_rejected() {
        // A project file has exactly one producer: a missing version means
        // corrupt/foreign content — never silently defaulted.
        let json = r#"{ "state": { "config": {}, "mover_position_mm": 1.0 } }"#;
        let err = parse_project_file(json).expect_err("must reject");
        assert!(err.contains("missing format_version"), "got: {err}");
    }

    #[test]
    fn future_format_version_rejected() {
        let mut value: serde_json::Value =
            serde_json::from_str(&serialize(&sample_state())).expect("json");
        value["format_version"] = serde_json::json!(PROJECT_FORMAT_VERSION + 1);
        let json = serde_json::to_string(&value).expect("reserialize");
        let err = parse_project_file(&json).expect_err("must reject");
        assert!(err.contains("newer version of pcbmotorgen"), "got: {err}");
    }

    #[test]
    fn forward_compatible_load_missing_fields_take_defaults() {
        let json = r#"{
            "format_version": 2,
            "app_version": "0.5.0",
            "saved_at_unix_ms": 123,
            "next_version_id": 2,
            "versions": [{
                "id": 1,
                "description": "",
                "created_at_unix_ms": 123,
                "last_edited_at_unix_ms": 123,
                "project": {
                    "config": {
                        "desired_travel_mm": 30.0,
                        "brand_new_future_field": { "x": 1 }
                    },
                    "mover_position_mm": 10.0
                }
            }]
        }"#;
        let (state, version) = parse_project_file(json).expect("parse");
        assert_eq!(version, 2);
        assert_eq!(state.config.desired_travel_mm, 30.0);
        assert_eq!(state.mover_position_mm, 10.0);
        // Everything absent falls back to the app defaults, not zeroes.
        assert_eq!(state.config.magnet_count, 12);
        assert_eq!(state.config.routing_pattern, "infinity-braid");
        assert_eq!(state.config.capacitor_bank_uf, 1000.0);
        assert!(state.config.routing_params.is_empty());
        assert!(state.cad_geometry.is_none());
    }

    #[test]
    fn new_project_star_default_does_not_reinterpret_legacy_or_explicit_connections() {
        assert_eq!(ProjectConfigStateIpc::default().routing_params["connection"], 2.0);
        for value in [serde_json::json!({}), serde_json::json!({"routing_params": {}})] {
            let loaded: ProjectConfigStateIpc = serde_json::from_value(value).unwrap();
            assert!(loaded.routing_params.is_empty());
        }
        for connection in [0.0, 1.0, 2.0] {
            let loaded: ProjectConfigStateIpc = serde_json::from_value(serde_json::json!({
                "routing_params": {"connection": connection}
            })).unwrap();
            assert_eq!(loaded.routing_params["connection"], connection);
        }
    }

    #[test]
    fn legacy_project_without_nominal_width_uses_the_minimum() {
        // Files written before the nominal trace width existed must keep
        // their copper width: the converter seeds it from min_trace_mm.
        let json = r#"{
            "format_version": 2,
            "app_version": "0.5.0",
            "saved_at_unix_ms": 123,
            "next_version_id": 2,
            "versions": [{
                "id": 1,
                "description": "",
                "created_at_unix_ms": 123,
                "last_edited_at_unix_ms": 123,
                "project": {
                    "config": { "desired_travel_mm": 30.0, "min_trace_mm": 0.25 },
                    "mover_position_mm": 10.0
                }
            }]
        }"#;
        let (state, _) = parse_project_file(json).expect("parse");
        assert_eq!(state.config.trace_width_mm, None);
        assert!((state.config.to_linear_motor_ipc().trace_width_m - 0.25e-3).abs() < 1e-12);
    }

    #[test]
    fn missing_state_rejected() {
        let json = r#"{ "format_version": 2, "app_version": "0.5.0" }"#;
        let err = parse_project_file(json).expect_err("must reject");
        assert!(err.contains("malformed project file"), "got: {err}");
    }

    #[test]
    fn design_validation_reports_invalid_restored_design() {
        // travel 0 → the core pipeline must flag an error, but the state
        // itself still loads (work-in-progress is loadable).
        let mut state = sample_state();
        state.config.desired_travel_mm = 0.0;
        let v = design_validation(&state);
        assert!(!v.errors.is_empty(), "travel-0 design must error");
    }

    #[test]
    fn design_validation_clean_for_valid_design() {
        let mut state = sample_state();
        state.config.magnet_count = 12;
        let v = design_validation(&state);
        assert!(v.errors.is_empty(), "errors: {:?}", v.errors);
        assert!(v.warnings.is_empty(), "warnings: {:?}", v.warnings);
    }

    #[test]
    fn legacy_design_outside_coreless_envelope_still_loads_but_reports_error() {
        let state = sample_state();
        assert_eq!(state.config.magnet_count, 16);
        let v = design_validation(&state);
        assert!(v.errors.iter().any(|error| error.contains("≤ 12")));
        assert_eq!(state.config.magnet_count, 16, "validation must not clamp restored geometry");
    }

    #[test]
    fn design_validation_reports_invalid_sensor_configuration() {
        let mut state = sample_state();
        state.sensor_config.turns = 8;
        state.sensor_config.lambda_mm = 30.0;
        state.sensor_config.amplitude_mm = 8.0;
        let validation = design_validation(&state);
        assert!(validation
            .errors
            .iter()
            .any(|error| error.starts_with("Induction sensor:")));
    }

    #[test]
    fn to_linear_motor_ipc_matches_store_derivation() {
        let state = sample_state();
        let ipc = state.config.to_linear_motor_ipc();
        // pole pitch = electrical/2 = 6mm; physical span = 15*6+5 = 95mm;
        // active length = 60 + 95 = 155mm.
        assert!((ipc.active_area_length_m - 0.155).abs() < 1e-12);
        assert!((ipc.magnet_pitch_m - 0.006).abs() < 1e-12);
        // gap = max(0, 6 - 5) = 1mm
        assert!((ipc.magnet_gap_m - 0.001).abs() < 1e-12);
        assert_eq!(ipc.num_layers, 6);
        assert_eq!(ipc.routing_pattern, "quad-stack");
    }

    #[test]
    fn atomic_write_round_trip_and_overwrite() {
        let dir = std::env::temp_dir().join(format!("pcbmotorgen-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("tmpdir");
        let path = dir.join("project.pmproj");

        let json1 = serialize(&sample_state());
        write_project_atomic(&path, &json1).expect("first write");
        let read1 = std::fs::read_to_string(&path).expect("read back");
        assert_eq!(read1, json1);

        // Overwrite with different content — no leftovers, no corruption.
        let mut state2 = sample_state();
        state2.mover_position_mm = 77.0;
        let json2 = serialize(&state2);
        write_project_atomic(&path, &json2).expect("overwrite");
        let read2 = std::fs::read_to_string(&path).expect("read back");
        assert_eq!(read2, json2);
        assert!(
            parse_project_file(&read2)
                .expect("parse")
                .0
                .mover_position_mm
                == 77.0
        );

        // No orphaned temp files.
        let leftovers: Vec<_> = std::fs::read_dir(&dir)
            .expect("readdir")
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().ends_with(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "orphaned tmp files: {leftovers:?}");

        std::fs::remove_dir_all(&dir).expect("cleanup");
    }

    #[test]
    fn legacy_projects_do_not_acquire_operating_requirements() {
        let config: ProjectConfigStateIpc = serde_json::from_value(serde_json::json!({})).unwrap();
        assert!(config.power_move.is_none());
        assert!(serde_json::to_value(config).unwrap().get("power_move").is_none());
        let (state, _) = parse_project_file(&serialize(&sample_state())).unwrap();
        assert!(state.config.power_move.is_none());
    }

    #[test]
    fn explicit_move_and_unknown_driver_losses_survive_saved_archive_roundtrip() {
        let mut state = sample_state();
        let input = serde_json::json!({
            "profile": { "start_m":0.0025, "end_m":0.0655,
                "initial_velocity_m_s":0.0, "final_velocity_m_s":0.0,
                "duration_s":1.0, "travel_min_m":0.0025, "travel_max_m":0.0655,
                "max_speed_m_s":0.5, "max_acceleration_m_s2":2.0, "max_deceleration_m_s2":1.0,
                "moving_mass_kg":0.015, "mass_includes":"Explicit test scenario, cap included",
                "coulomb_friction_n":0.05, "damping_n_s_per_m":0.0, "external_load_n":0.0,
                "time_step_s":0.001 },
            "control":"balanced_star_sinusoidal", "electrical_angle_at_zero_rad":0.0,
            "phase_peak_limit_a":1.0, "source":{"boundary":"stiff_dc_link", "accepts_regeneration":false},
            "additional_driver_loss_w":null, "force_positions":65
        });
        state.config.power_move = Some(serde_json::from_value(input.clone()).unwrap());
        let (restored, _) = parse_project_file(&serialize(&state)).unwrap();
        assert_eq!(serde_json::to_value(restored.config.power_move.unwrap()).unwrap(), input);
    }
}
