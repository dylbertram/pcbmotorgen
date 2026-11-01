//! Physics / simulation command handlers: magnet grades, height stack, coil
//! generation, force sweep, friction, driver suitability, B-field grid
//! sampling, and the travel envelope.

use crate::ipc::*;

use pcbmotorgen_simulation::magnetic::{
    CommutationMode as CoreCommutationMode, ForceEvaluator, MagnetArray,
};
use pcbmotorgen_simulation::stackup::{FrictionEstimator, HeightStackCalculator};

#[cfg(test)]
#[path = "physics_goal_independence_tests.rs"]
mod goal_independence_tests;

// ===========================================================================
// get_magnet_grades — REAL (core static table)
// ===========================================================================

/// Return the standard NdFeB magnet grade table with remanence ranges and
/// max operating temperatures (PRODUCT_GOALS.md §3.C).
///
/// This reads the real `pcbmotorgen_simulation::magnet_grades::MAGNET_GRADES` table.
#[tauri::command]
pub async fn get_magnet_grades() -> Result<Vec<MagnetGradeIpc>, String> {
    Ok(magnet_grades())
}

// ===========================================================================
// compute_height_stack — REAL (core HeightStackCalculator)
// ===========================================================================

/// Compute the vertical height stack (PCB → air gap → magnet).
///
/// Uses the real `pcbmotorgen_simulation::stackup::HeightStackCalculator` with its
/// default 1 oz outer copper and 0.3 mm assembly tolerance.
#[tauri::command]
pub async fn compute_height_stack(
    config: LinearMotorConfigIpc,
) -> Result<HeightStackResultIpc, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        let hs = HeightStackCalculator::default().calculate(&core.to_simulation());
        Ok(HeightStackResultIpc {
            pcb_thickness_m: hs.pcb_thickness_m,
            cu_protrusion_m: hs.cu_protrusion_m,
            solder_mask_m: hs.solder_mask_m,
            air_gap_m: hs.air_gap_m,
            magnet_height_m: hs.magnet_height_m,
            tolerance_m: hs.tolerance_m,
            total_height_m: hs.total_height_m(),
            backplane_m: hs.backplane_m,
            housing_gap_m: hs.housing_gap_m,
            housing_m: hs.housing_m,
            backplane_analysis: hs.backplane_analysis,
        })
    })
    .await
    .map_err(|e| format!("height_stack worker failed: {e}"))?
}

static PERIODIC_REFERENCE_JOB: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Prepare the request's actual copper for finite-DC eligibility checking.
/// This returns geometry only, never archived forces or implied qualification.
#[tauri::command]
pub async fn prepare_dc_winding_geometry(
    config: LinearMotorConfigIpc,
    drive_settings: pcbmotorgen_simulation::drive::DriveSettings,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
) -> Result<serde_json::Value, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|error| error.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        let (routing, sim, hints) = if let Some(cad) = cad_geometry.as_ref() {
            let board = super::cad_source::CadBoard::new(cad, &core)?;
            let sim = board.simulation_input(cad, &core);
            let hints = board.drive_hints(cad);
            (board.routing, sim, hints)
        } else {
            let routing = pcbmotorgen_routing::generate_routing_result(
                &core.routing_context(), &core.routing_pattern_id()).map_err(|error| error.to_string())?;
            (routing, core.to_simulation(), Default::default())
        };
        pcbmotorgen_simulation::dc_geometry::snapshot(&sim, &routing, &drive_settings, &hints)
    }).await.map_err(|error| format!("DC geometry worker failed: {error}"))?
}

/// PM-induced housing loss does not depend on electrical-driver compatibility.
/// Validate physical geometry/depths, but do not run a coil-current/driver solve.
#[tauri::command]
pub async fn analyze_housing_motion(
    config: LinearMotorConfigIpc,
    profile: pcbmotorgen_simulation::backplane::HousingMotionProfile,
    speed: f64,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
) -> Result<pcbmotorgen_simulation::backplane::HousingMotionAnalysis, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        let sim = if let Some(cad) = cad_geometry.as_ref() {
            let board = super::cad_source::CadBoard::new(cad, &core)?;
            let sim = board.simulation_input(cad, &core);
            sim.validate_for_simulation().map_err(|e| e.to_string())?;
            let hints = board.drive_hints(cad);
            pcbmotorgen_simulation::drive::validate_copper_placement(&sim, &board.routing, &hints).map_err(|e| e.to_string())?;
            sim
        } else { core.to_simulation() };
        sim.validate_for_simulation().map_err(|e| e.to_string())?;
        let stack = sim.backplane.as_ref().ok_or("Add a supported housing before calculating motion-induced heat")?;
        Ok(stack.housing_motion(&sim, speed, profile))
    }).await.map_err(|e| format!("housing motion worker failed: {e}"))?
}

/// Explicit periodic static reference. Does not replace previews, finite-array
/// force, friction or driver calculations, and never substitutes a mock result.
#[tauri::command]
pub async fn periodic_backplane_reference(
    config: LinearMotorConfigIpc,
) -> Result<pcbmotorgen_simulation::backplane::PeriodicStaticReference, String> {
    let sim = config.to_core().to_simulation();
    sim.validate_for_simulation().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        let _permit = PERIODIC_REFERENCE_JOB.try_lock().map_err(|error| match error {
            std::sync::TryLockError::WouldBlock => "A periodic reference is already running. Wait for it to finish before starting another.".to_string(),
            std::sync::TryLockError::Poisoned(_) => "The periodic reference worker failed. Restart the app before retrying.".to_string(),
        })?;
        sim.backplane
            .as_ref()
            .ok_or_else(|| "Add a magnetic backplane before running the periodic reference".to_string())?
            .periodic_static_reference(&sim)
    })
    .await
    .map_err(|e| format!("periodic reference worker failed: {e}"))?
}

// ===========================================================================
// generate_coils — REAL (core geometry generators)
// ===========================================================================

/// Generate coil path geometry for all phases/layers and return the design
/// dimensions used to generate it.
///
/// The routing pattern owns layer semantics, so this command resolves the
/// selected pattern through the routing registry rather than assigning phases
    /// round-robin in the application.  The returned `routing_dimensions` include
    /// the centre-to-centre pole pitch, ideal phase-band pitch, and calculated
    /// phase-band widths for each active `(layer, net)` bundle.
#[tauri::command]
pub async fn generate_coils(config: LinearMotorConfigIpc) -> Result<CoilPathIpc, String> {
    let core = config.to_core();
    core.validate_for_preview().map_err(|e| e.to_string())?;
    let num_layers = config.num_layers;
    tauri::async_runtime::spawn_blocking(move || {
        let ctx = core.routing_context();
        let pattern_id = core.routing_pattern_id();
        let report = pcbmotorgen_routing::generate_routing_report(&ctx, &pattern_id)
            .map_err(|e| format!("routing pattern failed: {e}"))?;
        let coils = pcbmotorgen_routing::routing_result_to_phase_coils(
            &report.result,
            &pattern_id,
        );
        Ok(CoilPathIpc::from_core_with_dimensions(
            &coils,
            num_layers,
            &report.dimensions,
        ))
    })
    .await
    .map_err(|e| format!("generate_coils worker failed: {e}"))?
}

// ===========================================================================
// evaluate_force_sweep — REAL (core ForceEvaluator / Lorentz force)
// ===========================================================================

/// Evaluate force vs mover position along the travel axis.
///
/// Uses the real `pcbmotorgen_simulation::magnetic::ForceEvaluator` which integrates
/// the Lorentz force `F = I · Σ(dLᵢ × Bᵢ)` across all active conductors at
/// each mover position. The magnet array is the fixed plain alternating
/// Z-polarised array.
///
/// Coils are generated for a single layer (layer 0) — sufficient for the
/// force profile since the force scales linearly with layer count.
///
/// Per PRODUCT_GOALS §4.C: `F_mover = -F_stator` — all forces are mover
/// forces. Ripple % = (F_max − F_min) / |F_mean| × 100.
#[tauri::command]
pub async fn evaluate_force_sweep(
    config: LinearMotorConfigIpc,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
    drive: Option<pcbmotorgen_simulation::drive::DriveSettings>,
) -> Result<ForceSweepResultIpc, String> {
    if cad_geometry.as_ref().is_some_and(|cad| cad.terminal_connection == Some(pcbmotorgen_export::cad_dxf::TerminalConnection::Delta)) {
        return Err("Imported delta force analysis is not available. Select Star (wye) coil terminals.".into());
    }
    let drive = drive.ok_or("Force analysis requires explicit drive settings; use the same copper, temperature and via settings as driver analysis.")?;
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    let n_positions = config.n_positions.max(2) as usize;
    let meshing = config.meshing.max(1) as usize;
    let commutation = match config.commutation {
        CommutationModeIpc::MaxThrust => CoreCommutationMode::MaxThrust,
        CommutationModeIpc::PhaseAOnly => CoreCommutationMode::PhaseAOnly,
    };
    tauri::async_runtime::spawn_blocking(move || {
        let (routing, sim, hints) = match cad_geometry.as_ref() {
            Some(cad) => {
                let board = super::cad_source::CadBoard::new(cad, &core)?;
                let sim = board.simulation_input(cad, &core);
                let hints = board.drive_hints(cad);
                (board.routing, sim, hints)
            }
            None => {
                core.design_rules().validate_trace_width()?;
                let ctx = core.routing_context();
                let routing_result = pcbmotorgen_routing::generate_routing_result(
                    &ctx,
                    &core.routing_pattern_id(),
                )
                .map_err(|e| format!("routing pattern failed: {e}"))?;
                (routing_result, core.to_simulation(), Default::default())
            }
        };

        sim.validate_for_simulation().map_err(|e| e.to_string())?;
        let (mut evaluator, coils) = ForceEvaluator::new(n_positions, meshing, commutation, 0.0)
            .with_routed_currents(&routing, &sim, &drive, &hints)
            .map_err(|e| format!("force current solve failed: {e}"))?;
        let result = evaluator
            .evaluate(&sim, &coils)
            .map_err(|e| format!("force_sweep self-calibration failed: {e}"))?;

        let n_phases = result.n_phases;
        let mean = result.mean_thrust_n();
        let peak = result.peak_thrust_n();
        let min = result.min_thrust_n();
        let ripple = result.ripple_pct();
        let per_phase: Vec<Vec<f64>> = result
            .per_phase_force_x
            .chunks(n_phases)
            .map(|c| c.to_vec())
            .collect();

        Ok(ForceSweepResultIpc {
            positions_m: result.positions_m,
            force_x_n: result.force_x_n,
            force_y_n: result.force_y_n,
            force_z_n: result.force_z_n,
            per_phase_force_x: per_phase,
            commutation: match result.commutation {
                CoreCommutationMode::MaxThrust => CommutationModeIpc::MaxThrust,
                CoreCommutationMode::PhaseAOnly => CommutationModeIpc::PhaseAOnly,
            },
            current_a: result.current_a,
            mean_thrust_n: mean,
            peak_thrust_n: peak,
            min_thrust_n: min,
            ripple_pct: ripple,
            n_positions: n_positions as u32,
        })
    })
    .await
    .map_err(|e| format!("force_sweep worker failed: {e}"))?
}

// ===========================================================================
// compute_friction — REAL (core FrictionEstimator)
// ===========================================================================

/// Break down the total friction into bearing, cable drag, wiper, and
/// cogging components.
///
/// Uses the real `pcbmotorgen_simulation::stackup::FrictionEstimator` with the
/// `estimate_for_config()` method, which splits `config.friction_n`
/// proportionally based on the default bearing type (PTE-lined).
/// Cogging is always 0 for coreless motors (PRODUCT_GOALS §4.A) — the
/// estimator no longer allocates any cogging fraction (kata zt1r); the
/// explicit 0 below keeps the IPC contract independent of estimator internals.
#[tauri::command]
pub async fn compute_friction(config: LinearMotorConfigIpc) -> Result<FrictionBudgetIpc, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        let fb = FrictionEstimator::default().estimate_for_config(&core.to_simulation());
        Ok(FrictionBudgetIpc {
            bearing_friction_n: fb.bearing_friction_n,
            cable_drag_n: fb.cable_drag_n,
            wiper_contact_n: fb.wiper_contact_n,
            cogging_n: 0.0, // coreless → zero cogging (§4.A)
            total_n: fb.bearing_friction_n + fb.cable_drag_n + fb.wiper_contact_n,
            minimum_drive_force_n: (fb.bearing_friction_n + fb.cable_drag_n + fb.wiper_contact_n) * 1.3,
        })
    })
    .await
    .map_err(|e| format!("friction worker failed: {e}"))?
}

// ===========================================================================
// sample_b_field — REAL (MagnetArray::bfield_grid via physics adapter) — WP4
// ===========================================================================

/// Hard cap on `n_x * n_z` to prevent runaway sampling. 24×12 = 288 is
/// the WP5 default; 4096 is the upper bound before the async runtime
/// blocks. Configurable per-call via the JS wrapper.
const SAMPLE_B_FIELD_GRID_CAP: usize = 4096;

/// Sample the B-field on an X–Z grid at the board centre-line and return
/// the field vectors + positions as a flat row-major array.
///
/// The flux-viz backend for the WP5 `FluxDiagram` Svelte component. The
/// core `MagnetArray::bfield_grid` routes through the
/// `pcbmotorgen_simulation::physics` magba adapter and always builds the
/// plain alternating array.
///
/// **Grid cap:** `n_x * n_z` must be ≤ 4096. Returns `Err("grid too large")`
/// otherwise. (24×12 = 288 is the recommended resolution; the cap is a
/// safety net against runaway sliders.)
#[tauri::command]
pub async fn sample_b_field(
    config: LinearMotorConfigIpc,
    n_x: usize,
    n_z: usize,
    x_extent_m: [f64; 2],
    z_extent_m: [f64; 2],
) -> Result<BFieldGridIpc, String> {
    if n_x < 2 || n_z < 2 {
        return Err(format!(
            "grid too small: n_x={n_x} n_z={n_z}, need >= 2 each"
        ));
    }
    if n_x * n_z > SAMPLE_B_FIELD_GRID_CAP {
        return Err(format!(
            "grid too large: {n_x}×{n_z} = {} > {SAMPLE_B_FIELD_GRID_CAP}",
            n_x * n_z
        ));
    }
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || {
        // Build linspaces from extents.
        let x_sample: Vec<f64> = linspace(x_extent_m[0], x_extent_m[1], n_x);
        let z_sample: Vec<f64> = linspace(z_extent_m[0], z_extent_m[1], n_z);
        // Build MagnetArray, sample 2D grid (row-major, Z slow).
        let sim = core.to_simulation();
        let magnet_array = MagnetArray::new(&sim);
        let samples_2d = magnet_array.bfield_grid(&x_sample, &z_sample, 0.0);
        // Convert to IPC, computing magnitude.
        let samples_ipc: Vec<BFieldSampleIpc> = samples_2d
            .iter()
            .map(BFieldSampleIpc::from_core)
            .collect();
        Ok(BFieldGridIpc {
            samples: samples_ipc,
            x_extent_m,
            z_extent_m,
        })
    })
    .await
    .map_err(|e| format!("sample_b_field join error: {e}"))?
}

/// `n` evenly-spaced points in `[lo, hi]`. `n == 1` returns `[lo]`,
/// `n == 0` returns empty. Used by `sample_b_field` to expand the
/// extents into grid coordinates.
fn linspace(lo: f64, hi: f64, n: usize) -> Vec<f64> {
    if n == 0 {
        return Vec::new();
    }
    if n == 1 {
        return vec![lo];
    }
    let dx = (hi - lo) / (n - 1) as f64;
    (0..n).map(|i| lo + i as f64 * dx).collect()
}

// ===========================================================================
// analyze_drive — driver suitability from the routed copper
// ===========================================================================

/// Check whether a three-phase driver can run the routed coils: phase
/// resistance and inductance measured from the routing result (network
/// solve + Neumann integral), then bus-voltage headroom, PWM ripple, peak
/// and continuous current, trace ampacity, and thrust.
///
/// `thrust_constant_n_per_a` is the force sweep's mean thrust per ampere;
/// without it the at-speed voltage and thrust checks report `unknown`.
#[tauri::command]
pub async fn analyze_drive(
    config: LinearMotorConfigIpc,
    drive: pcbmotorgen_simulation::drive::DriveSettings,
    thrust_constant_n_per_a: Option<f64>,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
) -> Result<pcbmotorgen_simulation::drive::DriveAnalysis, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    // Pattern-owned contract from motor-coil-generator-add-inputs:
    // 0 = closed, 1 = delta, 2 = star/wye. Imported copper is independent.
    let delta = match cad_geometry.as_ref() {
        Some(cad) => cad.terminal_connection == Some(pcbmotorgen_export::cad_dxf::TerminalConnection::Delta),
        None => core.routing_pattern_id() == "infinity-braid"
            && core.routing_params.get("connection").is_some_and(|value| value.round() == 1.0),
    };
    if let Some(error) = pcbmotorgen_simulation::drive::driver_connection_error(&drive.driver, delta) {
        return Err(error);
    }
    tauri::async_runtime::spawn_blocking(move || {
        if let Some(cad) = cad_geometry.as_ref() {
            let board = super::cad_source::CadBoard::new(cad, &core)?;
            let sim = board.simulation_input(cad, &core);
            sim.validate_for_simulation().map_err(|e| e.to_string())?;
            let hints = board.drive_hints(cad);
            pcbmotorgen_simulation::drive::validate_copper_placement(&sim, &board.routing, &hints)
                .map_err(|error| error.to_string())?;
            return Ok(pcbmotorgen_simulation::drive::analyze_drive_with(
                &sim,
                &board.routing,
                &drive,
                thrust_constant_n_per_a,
                &hints,
            ));
        }
        core.design_rules().validate_trace_width()?;
        let routing = pcbmotorgen_routing::generate_routing_result(
            &core.routing_context(),
            &core.routing_pattern_id(),
        )
        .map_err(|e| format!("routing pattern failed: {e}"))?;
        Ok(pcbmotorgen_simulation::drive::analyze_drive(
            &core.to_simulation(),
            &routing,
            &drive,
            thrust_constant_n_per_a,
        ))
    })
    .await
    .map_err(|e| format!("analyze_drive worker failed: {e}"))?
}

// ===========================================================================
// travel_envelope
// ===========================================================================

/// Stable-equilibrium travel envelope of the mover array centre, as computed
/// by the simulation crate's equilibrium module (glossary "Travel Envelope",
/// kata 5c7r + k5r5): the charge-based electromagnetic endpoints (stable rest
/// of the first/last magnet under the first/last phase-band charge states —
/// the Clarke-transform equilibrium of the band currents) clamped into the
/// span-aware flush limits
/// `centre ∈ [copper_start + span/2, copper_end − span/2]` over the whole
/// active area. When the charge solve is unavailable (no coils, non-3-phase
/// geometry, no stable rest in the scan window) the flush-clamp envelope is
/// returned unchanged. `rest_phase_m` still reports the stable-rest lattice
/// for the holding-force chart zeros. The UI clamps its position slider to
/// [min_position_m, max_position_m].
#[tauri::command]
pub async fn travel_envelope(config: LinearMotorConfigIpc) -> Result<TravelEnvelopeIpc, String> {
    let core = config.to_core();
    core.validate_for_simulation().map_err(|e| e.to_string())?;
    if core.pcb_stackup.is_some() {
        return Err("The planar equilibrium screen does not support custom PCB stackups. Layer heights were not flattened; routed force and move calculations use the configured stack.".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let sim = core.to_simulation();
        // The copper active area is the whole track: [0, active_area_length].
        // There is no padding offset (kata hrd8 removed the padding feature).
        let copper_region_start_m = 0.0;
        let copper_region_end_m = sim.active_area_length_m;
        // Coils for the charge-state solve (same generation as generate_coils).
        let coils = core.generate_coils_for_board();
        Ok(TravelEnvelopeIpc::from(
            pcbmotorgen_simulation::equilibrium::charge::travel_envelope_charge_based(
                &sim,
                &coils,
                copper_region_start_m,
                copper_region_end_m,
            ),
        ))
    })
    .await
    .map_err(|e| format!("travel_envelope worker failed: {e}"))?
}

// ===========================================================================
// Tests — travel_envelope reflects the charge-based refinement (kata k5r5)
// ===========================================================================

#[cfg(test)]
mod coreless_envelope_tests {
    use super::*;

    #[test]
    fn preview_updates_below_the_manufacturing_width_floor_without_approving_export_or_physics() {
        let mut config = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        let mut previous = None;
        for width in [0.0001, 0.00011] {
            config.trace_width_m = width;
            // Braid centerline spacing can stay at the rule floor when copper
            // gets thinner. A routing flip must still propagate with DRC failing.
            config.routing_orientation.mirror_x = width == 0.00011;
            let core = config.to_core();
            assert!(core.validate_for_simulation().unwrap_err().to_string().contains("minimum trace width"));
            assert!(core.design_rules().validate_trace_width().is_err());
            assert!(tauri::async_runtime::block_on(super::super::routing_plugins::check_coil_interference(config.clone(), None)).is_err());
            assert!(tauri::async_runtime::block_on(super::super::dxf::export_coils_dxf(config.clone())).is_err());
            let preview = tauri::async_runtime::block_on(generate_coils(config.clone())).unwrap();
            let report = pcbmotorgen_routing::generate_routing_report(&core.routing_context(), &core.routing_pattern_id()).unwrap();
            let coils = pcbmotorgen_routing::routing_result_to_phase_coils(&report.result, &core.routing_pattern_id());
            let expected = CoilPathIpc::from_core_with_dimensions(&coils, config.num_layers, &report.dimensions);
            let actual = serde_json::to_value(preview).unwrap();
            assert_eq!(actual, serde_json::to_value(expected).unwrap());
            if let Some(old) = previous { assert!(actual["phases"] != old, "routing flip must update while DRC fails"); }
            previous = Some(actual["phases"].clone());
            assert_eq!(config.trace_width_m, width, "preview must not clamp copper to the DRC floor");
        }
        config.trace_width_m = 0.;
        assert!(tauri::async_runtime::block_on(generate_coils(config.clone())).unwrap_err().contains("positive"));
    }

    #[test]
    fn every_public_motor_calculation_rejects_out_of_envelope_inputs_before_work() {
        let mut config = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        config.magnet_count = 13;
        let drive = pcbmotorgen_simulation::drive::DriveSettings::default();
        let errors = vec![
            tauri::async_runtime::block_on(compute_height_stack(config.clone())).unwrap_err(),
            tauri::async_runtime::block_on(compute_friction(config.clone())).unwrap_err(),
            tauri::async_runtime::block_on(generate_coils(config.clone())).unwrap_err(),
            tauri::async_runtime::block_on(sample_b_field(config.clone(), 2, 2, [0.,0.01], [0.,0.01])).unwrap_err(),
            tauri::async_runtime::block_on(analyze_drive(config.clone(), drive.clone(), None, None)).unwrap_err(),
            tauri::async_runtime::block_on(evaluate_force_sweep(config.clone(), None, Some(drive))).unwrap_err(),
            tauri::async_runtime::block_on(travel_envelope(config.clone())).unwrap_err(),
            tauri::async_runtime::block_on(analyze_housing_motion(config.clone(), pcbmotorgen_simulation::backplane::HousingMotionProfile { duration_s: 0.1 }, 3., None)).unwrap_err(),
        ];
        assert!(errors.iter().all(|e| e.contains("≤ 12")), "{errors:?}");
        assert_eq!(config.magnet_count, 13, "no command may clamp saved geometry");
    }

    #[test]
    fn housing_motion_remains_available_when_the_driver_cannot_handle_delta() {
        use pcbmotorgen_simulation::backplane::{BackplaneStack, HousingSpec, HousingMaterial, HousingMotionProfile, HousingMotionAnalysis};
        let mut state = crate::ipc::ProjectConfigStateIpc::default();
        state.routing_params.insert("connection".into(), 1.0);
        state.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec { material: HousingMaterial::Aluminum6061, thickness_m: 0.001, gap_m: 0.001 }) });
        let config = state.to_linear_motor_ipc();
        let error = tauri::async_runtime::block_on(analyze_drive(config.clone(), state.drive, None, None)).unwrap_err();
        assert!(error.contains("Star") || error.contains("delta"));
        let value = tauri::async_runtime::block_on(analyze_housing_motion(config, HousingMotionProfile { duration_s: 0.1 }, 3., None)).unwrap();
        assert!(matches!(value, HousingMotionAnalysis::Experimental { estimate } if estimate.housing_joule_power_w > 0.));
    }
}

#[cfg(test)]
mod travel_envelope_tests {
    use super::*;

    /// Verify the command returns EXACTLY the crate's charge-based envelope
    /// for the given design inputs — not the geometric flush clamp alone.
    /// Swept over several geometries; prints base vs refined so a drift is
    /// visible in the test log.
    #[test]
    fn command_matches_the_charge_based_envelope() {
        for (n, p_e_mm, travel_mm) in [
            (12_u32, 12.0, 75.0), // app defaults = the reference fixture
            (10, 24.0, 123.0),
            (6, 12.0, 111.0),
            (12, 18.0, 75.0),
        ] {
            let mut state = crate::ipc::ProjectConfigStateIpc::default();
            state.magnet_count = n;
            state.electrical_pitch_mm = p_e_mm;
            state.desired_travel_mm = travel_mm;
            let ipc = state.to_linear_motor_ipc();

            let env = tauri::async_runtime::block_on(travel_envelope(ipc.clone()))
                .expect("command should succeed");

            let core = ipc.to_core();
            let sim = core.to_simulation();
            let coils = core.generate_coils_for_board();
            let len_m = sim.active_area_length_m;
            let refined = pcbmotorgen_simulation::equilibrium::charge::travel_envelope_charge_based(
                &sim, &coils, 0.0, len_m,
            );
            let base = pcbmotorgen_simulation::equilibrium::travel_envelope_over_slots(
                2.0 * sim.magnet_pitch_m,
                sim.magnet_count,
                0.0,
                len_m,
            );
            eprintln!(
                "N={n} P_e={p_e_mm} L={:.1}mm coils={} | base [{:.3}, {:.3}] mm | refined [{:.3}, {:.3}] mm | command [{:.3}, {:.3}] mm",
                len_m * 1e3,
                coils.len(),
                base.min_position_m * 1e3,
                base.max_position_m * 1e3,
                refined.min_position_m * 1e3,
                refined.max_position_m * 1e3,
                env.min_position_m * 1e3,
                env.max_position_m * 1e3,
            );
            assert!(
                env.min_position_m == refined.min_position_m
                    && env.max_position_m == refined.max_position_m
                    && env.rest_phase_m == refined.rest_phase_m
                    && env.electrical_period_m == refined.electrical_period_m,
                "N={n} P_e={p_e_mm}: command != refined"
            );
        }
    }

    /// App-default design (N=12, P_e=12 mm, travel 75 mm ⇒ copper [0, 147] mm)
    /// with the app's REAL routing pattern (infinity-braid, not the crate's
    /// serpentine fixture): the charge refinement ENGAGES — the min endpoint
    /// stays flush-clamped at 36 mm (the raw first-magnet rest overhangs the
    /// copper start) while the max endpoint is pulled INWARD off the 111 mm
    /// flush limit (measured ≈ 107.97 mm) by the last magnet's
    /// electromagnetic rest under the edge-anchored charge state — the max
    /// charges are the min charges mirrored (A↔C, B unchanged), anchored on
    /// the phase that owns the braid's last active leg (C). This is the
    /// live number the position slider and previews must show (the 111 mm
    /// placeholder pin is the flagged mock, never the live physics).
    #[test]
    fn command_refines_the_max_endpoint_on_app_defaults() {
        let ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        let env = tauri::async_runtime::block_on(travel_envelope(ipc)).expect("command");
        eprintln!(
            "app defaults: command [{:.3}, {:.3}] mm, rest {:.3} mm, P_e {:.3} mm",
            env.min_position_m * 1e3,
            env.max_position_m * 1e3,
            env.rest_phase_m * 1e3,
            env.electrical_period_m * 1e3,
        );
        // Min: flush clamp binds (raw rest overhangs the copper start).
        assert!(
            (env.min_position_m - 0.036).abs() < 1e-9,
            "min {}",
            env.min_position_m
        );
        // Max: refined strictly inside the flush limit [36, 111] mm.
        assert!(
            env.max_position_m > env.min_position_m && env.max_position_m < 0.111,
            "max {} not refined inward of the flush limit",
            env.max_position_m
        );
        // Lattice unchanged by the refinement (holding-force chart zeros).
        assert!((env.rest_phase_m - 0.010).abs() < 1e-12, "rest {}", env.rest_phase_m);
        assert!(
            (env.electrical_period_m - 0.012).abs() < 1e-12,
            "period {}",
            env.electrical_period_m
        );
    }
}

#[cfg(test)]
mod periodic_reference_tests {
    use super::*;
    use pcbmotorgen_simulation::backplane::{BackplaneLayer, BackplaneStack, LayerMaterial};

    #[test]
    fn missing_or_unsupported_backplane_is_an_error_not_a_preview_fallback() {
        let mut config = crate::ipc::ProjectConfigStateIpc::default();
        let error = tauri::async_runtime::block_on(periodic_backplane_reference(config.to_linear_motor_ipc())).unwrap_err();
        assert!(error.contains("Add a magnetic backplane"), "{error}");
        config.backplane = Some(BackplaneStack {
            layers: vec![BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002); 2],
            housing: None,
        });
        let error = tauri::async_runtime::block_on(periodic_backplane_reference(config.to_linear_motor_ipc())).unwrap_err();
        assert!(error.contains("one magnetic layer"), "{error}");
    }
}

#[cfg(test)]
mod analyze_drive_tests {
    use super::*;

    #[test]
    fn force_sweep_rejects_implicit_copper_defaults() {
        let ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        let error = tauri::async_runtime::block_on(evaluate_force_sweep(ipc, None, None)).unwrap_err();
        assert!(error.contains("explicit drive settings"), "{error}");
    }

    #[test]
    #[ignore = "Exports real winding geometry for independent Magpylib validation"]
    fn export_magpylib_validation_fixture() {
        let driver_reference = std::env::var("PCB_MOTOR_ORACLE_CASE").ok().as_deref() == Some("drv8311");
        assert!(!driver_reference || std::env::var_os("PCB_MOTOR_PROJECT_PATH").is_none(), "DRV8311 fixture is a separate explicit generated case");
        let (state, cad) = if let Ok(path) = std::env::var("PCB_MOTOR_PROJECT_PATH") {
            let project: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
            let index: usize = std::env::var("PCB_MOTOR_VERSION_INDEX").unwrap_or_else(|_| "0".into()).parse().unwrap();
            let saved = &project["versions"][index]["state"];
            (serde_json::from_value::<crate::ipc::ProjectConfigStateIpc>(saved["config"].clone()).unwrap(),
             serde_json::from_value::<Option<pcbmotorgen_export::cad_dxf::CadGeometry>>(saved["cad_geometry"].clone()).unwrap())
        } else {
            let mut state = crate::ipc::ProjectConfigStateIpc::default();
            state.drive.outer_copper_oz = 3.0;
            state.drive.inner_copper_oz = 1.0;
            (state, None)
        };
        let mut state = state;
        if driver_reference { state.drive.inner_copper_oz = 3.0; }
        let mut ipc = state.to_linear_motor_ipc();
        if std::env::var_os("PCB_MOTOR_PROJECT_PATH").is_none() {
            ipc.routing_params.insert("connection".into(), 2.0);
        }
        if driver_reference { ipc.min_trace_m = 0.0005; ipc.trace_width_m = 0.0005; }
        let core = ipc.to_core();
        let (routing, sim, hints) = if let Some(cad) = cad.as_ref() {
            let board = crate::commands::cad_source::CadBoard::new(cad, &core).unwrap();
            let sim = board.simulation_input(cad, &core);
            let hints = board.drive_hints(cad);
            (board.routing, sim, hints)
        } else {
            (pcbmotorgen_routing::generate_routing_result(&core.routing_context(), &core.routing_pattern_id()).unwrap(),
             core.to_simulation(), Default::default())
        };
        assert!(sim.backplane.is_none(), "Magpylib is a free-space oracle; use the FEMM harness for soft magnetic backplanes");
        let points = vec![0.0, 0.001, 0.003, 0.006, 0.012, 0.036, 0.06];
        let array = pcbmotorgen_simulation::magnetic::magnet_model::MagnetArray::new(&sim);
        let b = array.bfield_at_pcb_surface(&points, 0.0, 0.0);
        let meshing: usize = std::env::var("PCB_MOTOR_FORCE_MESH").unwrap_or_else(|_| "10".into()).parse().unwrap();
        assert!((1..=512).contains(&meshing));
        let (mut evaluator, coils) = ForceEvaluator::new(if driver_reference { 25 } else { 9 }, meshing,
            if driver_reference { CoreCommutationMode::MaxThrust } else { CoreCommutationMode::PhaseAOnly }, 0.0)
            .with_routed_currents(&routing, &sim, &state.drive, &hints).unwrap();
        let force = evaluator.evaluate(&sim, &coils).unwrap();
        let samples: Vec<_> = evaluator.routed_conductor_samples().unwrap()[0].iter()
            .map(|s| serde_json::json!({"point": s.midpoint_3d, "dl": s.dl_3d})).collect();
        let phase_samples: Vec<Vec<_>> = evaluator.routed_conductor_samples().unwrap().iter().map(|samples| samples.iter()
            .map(|s| serde_json::json!({"point":s.midpoint_3d,"dl":s.dl_3d})).collect()).collect();
        let excitation: Vec<_> = force.positions_m.iter().map(|&x| evaluator.excitation_currents_at(&sim, &coils, x).unwrap()).collect();
        let driver_analysis = if driver_reference {
            let kf = force.mean_thrust_n().abs() / force.current_a;
            let mut driver_ipc = ipc.clone(); driver_ipc.supply_voltage_v = 5.0; driver_ipc.max_current_a = 1.1;
            let mut settings = state.drive.clone(); settings.pwm_hz = 200e3;
            settings.ripple_limit_fraction = 0.35; settings.voltage_headroom = 0.95;
            let analysis = tauri::async_runtime::block_on(analyze_drive(driver_ipc, settings, Some(kf), None)).unwrap();
            Some(serde_json::json!({"kf_n_per_a":kf,"thrust_n":analysis.thrust_n,"speed_voltage_v":analysis.speed_voltage_v,
                "validation_basis":"Independent winding/field/force comparison, not design-goal compliance"}))
        } else { None };
        use pcbmotorgen_simulation::drive::{extract_phase_networks_with_terminals, solve_network, EdgeKind};
        let rho = pcbmotorgen_simulation::drive::rho_cu_at(state.drive.winding_temp_c);
        let networks: Vec<_> = extract_phase_networks_with_terminals(&routing, &hints.terminals).iter().map(|net| {
            let resistances: Vec<_> = net.edges.iter().map(|edge| match &edge.kind {
                EdgeKind::Via { layers, .. } => pcbmotorgen_simulation::drive::via_resistance_ohm(sim.min_via_drill_m, state.drive.via_plating_m, hints.via_length_m(&sim, *layers), rho),
                EdgeKind::Trace { layer, length_m, .. } => {
                    let inner = sim.num_layers > 2 && *layer != 0 && *layer + 1 != sim.num_layers;
                    let oz = if inner { state.drive.inner_copper_oz } else { state.drive.outer_copper_oz };
                    rho * length_m / (sim.min_trace_m * pcbmotorgen_simulation::units::oz_to_m(oz))
                }
            }).collect();
            let solution = solve_network(net, &resistances);
            assert!(solution.connected);
            serde_json::json!({"net": net.net, "node_count": net.node_count, "terminal": net.terminal, "star": net.star,
                "edges": net.edges.iter().zip(resistances).map(|(e,r)| {
                    let geometry = match &e.kind {
                        EdgeKind::Trace { layer, points, .. } => serde_json::json!({"kind":"trace","layer":layer,"points_m":points}),
                        EdgeKind::Via { layers, position_m } => serde_json::json!({"kind":"via","layers":layers,"position_m":position_m}),
                    };
                    serde_json::json!({"a":e.a,"b":e.b,"r_ohm":r,"geometry":geometry})
                }).collect::<Vec<_>>(),
                "rust_current_share":solution.current_share, "rust_resistance_ohm":solution.resistance_ohm})
        }).collect();
        let out = serde_json::json!({"routing": routing, "sim": sim, "drive": state.drive, "geometry_hints": {"layer_z_m": hints.layer_z_m}, "field_x_m": points, "rust_b_t": b,
            "networks": networks, "force_subdivisions": evaluator.meshing,
            "phase_samples":phase_samples,"excitation_currents_a":excitation,"driver_reference":driver_analysis,
            "phase_a_samples": samples, "force_positions_m": force.positions_m, "rust_force_x_n": force.force_x_n});
        let bytes = serde_json::to_vec(&out).unwrap();
        if let Ok(path) = std::env::var("PCB_MOTOR_ORACLE_OUTPUT") {
            let mut file = std::fs::OpenOptions::new().create_new(true).write(true).open(path).unwrap();
            std::io::Write::write_all(&mut file, &bytes).unwrap();
        } else {
            std::fs::write("magpylib-fixture.json", bytes).unwrap();
        }
    }

    #[test]
    fn closed_infinity_six_magnets_simulates() {
        let mut state: crate::ipc::ProjectConfigStateIpc = serde_json::from_str(include_str!("fixtures/closed_infinity_pattern.config.json")).unwrap();
        let five_ipc = state.to_linear_motor_ipc();
        let five = tauri::async_runtime::block_on(evaluate_force_sweep(five_ipc, None, Some(state.drive.clone()))).unwrap();
        state.magnet_count = 6;
        let ipc = state.to_linear_motor_ipc();
        let sweep = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(state.drive.clone()))).expect("six-magnet user configuration must simulate");
        assert!(sweep.force_x_n.iter().all(|f| f.is_finite()));
        eprintln!("six magnets mean={} min={} max={}", sweep.mean_thrust_n, sweep.min_thrust_n, sweep.peak_thrust_n);
        assert!(sweep.min_thrust_n > 0.0);
        assert!(sweep.mean_thrust_n > five.mean_thrust_n, "adding a magnet must not collapse thrust for this fixture");
        let analysis = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), state.drive, Some(sweep.mean_thrust_n / sweep.current_a), None)).expect("six-magnet driver analysis");
        assert!(!serde_json::to_string(&analysis).unwrap().contains(":null"));
        tauri::async_runtime::block_on(compute_friction(ipc.clone())).expect("six-magnet friction");
        tauri::async_runtime::block_on(compute_height_stack(ipc.clone())).expect("six-magnet height stack");
        tauri::async_runtime::block_on(generate_coils(ipc.clone())).expect("six-magnet coil preview");
        tauri::async_runtime::block_on(travel_envelope(ipc)).expect("six-magnet travel envelope");
    }

    #[test]
    #[ignore = "User project force convergence and driver diagnostics"]
    fn closed_infinity_user_project_diagnostics() {
        let state: crate::ipc::ProjectConfigStateIpc = serde_json::from_str(include_str!("fixtures/closed_infinity_pattern.config.json")).unwrap();
        let mut ipc = state.to_linear_motor_ipc();
        assert!((ipc.active_area_length_m - 0.092).abs() < 1e-12);
        let mut previous: Option<Vec<f64>> = None;
        for mesh in [10, 20, 40, 80] {
            ipc.meshing = mesh;
            let sweep = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(state.drive.clone()))).unwrap();
            let kf = sweep.mean_thrust_n / sweep.current_a;
            eprintln!("USER mesh={mesh} x=[{},{}] mean={} min={} max={} ripple_pct={} first={} last={}", sweep.positions_m[0], sweep.positions_m.last().unwrap(), sweep.mean_thrust_n, sweep.min_thrust_n, sweep.peak_thrust_n, sweep.ripple_pct, sweep.force_x_n[0], sweep.force_x_n.last().unwrap());
            if mesh == 20 {
                let a = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), state.drive.clone(), Some(kf), None)).unwrap();
                eprintln!("USER driver={}", serde_json::to_string(&a).unwrap());
                eprintln!("USER force_x={:?}", sweep.force_x_n);
                eprintln!("USER phase means={:?}", (0..3).map(|p| sweep.per_phase_force_x.iter().map(|row| row[p]).sum::<f64>() / sweep.per_phase_force_x.len() as f64).collect::<Vec<_>>());
                assert!(a.ripple_pp_a < 12.0 / (2.0 * a.phase_resistance_ohm));
                assert!((a.thrust_n.unwrap() - kf * ipc.max_current_a).abs() < 1e-12);
                let mut goals = ipc.clone();
                goals.target_force_n = 100.0;
                goals.peak_force_n = 0.001;
                let changed = tauri::async_runtime::block_on(analyze_drive(goals, state.drive.clone(), Some(kf), None)).unwrap();
                super::goal_independence_tests::assert_electrical_equal(&a, &changed);
            }
            if let Some(old) = previous.as_ref() {
                let max_diff = old.iter().zip(&sweep.force_x_n).map(|(a,b)| (a-b).abs()).fold(0.0, f64::max);
                assert!(max_diff / sweep.mean_thrust_n.abs() < 0.002, "mesh {mesh} has not converged: {max_diff}");
            }
            previous = Some(sweep.force_x_n);
        }
    }

    /// The user's "version 2" of the closed-infinity design: 0.8 mm PCB, one
    /// 0.2 mm flexible ferrite sheet and a 1 mm aluminium 6061 housing 0.1 mm
    /// below it (tickets 04n2, q9nw).
    fn closed_infinity_version_two() -> crate::ipc::ProjectConfigStateIpc {
        use pcbmotorgen_simulation::backplane::*;
        let mut state: crate::ipc::ProjectConfigStateIpc = serde_json::from_str(include_str!("fixtures/closed_infinity_pattern.config.json")).unwrap();
        state.pcb_thickness_mm = 0.8;
        state.trace_width_mm = Some(0.2);
        state.backplane = Some(BackplaneStack {
            layers: vec![BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.2e-3)],
            housing: Some(HousingSpec { material: HousingMaterial::Aluminum6061, thickness_m: 1.0e-3, gap_m: 0.1e-3 }),
        });
        state
    }

    #[test]
    #[ignore = "Version 2 backplane diagnostics (saturation, eddy currents)"]
    fn closed_infinity_version_two_diagnostics() {
        let state = closed_infinity_version_two();
        let ipc = state.to_linear_motor_ipc();
        let sweep = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(state.drive.clone()))).unwrap();
        let kf = sweep.mean_thrust_n / sweep.current_a;
        let a = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), state.drive.clone(), Some(kf), None)).unwrap();
        let h = tauri::async_runtime::block_on(compute_height_stack(ipc)).unwrap();
        eprintln!("V2 mean={} min={} max={}", sweep.mean_thrust_n, sweep.min_thrust_n, sweep.peak_thrust_n);
        eprintln!("V2 driver={}", serde_json::to_string(&a).unwrap());
        eprintln!("V2 backplane={}", serde_json::to_string(&h.backplane_analysis).unwrap());
        // The sheet saturates: no multi-tesla peak, and almost no image left.
        let bp = h.backplane_analysis.unwrap();
        assert!(bp.layer_states[0].saturated() && bp.layer_peak_b_t[0] < 1.0);
        assert!(bp.image_strength < 0.1);
        // At 20 m/s the aluminium housing drags harder than the motor pushes.
        let eddy = a.backplane.as_ref().unwrap();
        assert!(eddy.drag_n > a.thrust_n.unwrap() && eddy.drag_limited_speed_m_s.unwrap() < 20.0);
        assert!(eddy.pwm_inductance_h < a.effective_inductance_h);
    }

    #[test]
    #[ignore = "Exploratory 5 V versus 12 V geometry comparison"]
    fn drv8311_compare_five_and_twelve_volts() {
        for strands in [7.0, 9.0] {
            let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
            ipc.routing_params.insert("connection".into(), 2.0);
            ipc.routing_params.insert("num_strands".into(), strands);
            ipc.min_trace_m = 0.0005;
            ipc.trace_width_m = 0.0005;
            ipc.n_positions = 25;
            ipc.meshing = 20;
            let mut settings = pcbmotorgen_simulation::drive::DriveSettings::default();
            settings.outer_copper_oz = 3.0;
            settings.inner_copper_oz = 3.0;
            settings.pwm_hz = 200e3;
            settings.ripple_limit_fraction = 0.35;
            settings.voltage_headroom = 0.95;
            let sweep = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(settings.clone()))).unwrap();
            let kf = sweep.mean_thrust_n.abs() / sweep.current_a;
            ipc.max_current_a = 1.1;
            for voltage in [5.0, 12.0] {
                ipc.supply_voltage_v = voltage;
                let a = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), settings.clone(), Some(kf), None)).unwrap();
                assert!((a.thrust_n.unwrap() - kf * ipc.max_current_a).abs() < 1e-12);
                let expected_ripple = voltage / (2.0 * a.phase_resistance_ohm)
                    * (a.phase_resistance_ohm / (4.0 * settings.pwm_hz * a.effective_inductance_h)).tanh();
                assert!((a.ripple_pp_a - expected_ripple).abs() < 1e-10);
                eprintln!("DRV8311 strands={strands} V={voltage} numerical R={} L_uH={} thrust={:?} holding={} speed={:?} ripple={}", a.phase_resistance_ohm, a.synchronous_inductance_h*1e6, a.thrust_n, a.holding_voltage_v, a.speed_voltage_v, a.ripple_pp_a);
                eprintln!("checks={:?}", a.checks.iter().map(|c| (&c.id, c.status, c.value, c.limit)).collect::<Vec<_>>());
            }
        }
    }

    #[test]
    fn drv8311_star_reference_matches_independent_numerics_regardless_of_goals() {
        for width_mm in [0.5] {
            let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
            ipc.routing_params.insert("connection".into(), 2.0);
            ipc.min_trace_m = width_mm * 1e-3;
            ipc.trace_width_m = width_mm * 1e-3;
            ipc.n_positions = 25;
            ipc.meshing = 20;
            let mut force_settings = pcbmotorgen_simulation::drive::DriveSettings::default();
            force_settings.outer_copper_oz = 3.0;
            force_settings.inner_copper_oz = 3.0;
            let sweep = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(force_settings))).unwrap();
            let kf = sweep.mean_thrust_n.abs() / sweep.current_a;
            eprintln!("width={width_mm} computed Kf={kf} N/A");
            // Four-layer compact braid with staggered openings, physical spans
            // and signed via force. Moving an opening changes mesh currents.
            // This legacy excitation reference does not qualify a star controller.
            // Magpylib + independent R/current/dL reconstruction verifies this
            // fixture with its exported excitation; controller PWM is unqualified.
            assert!((kf - 0.2621774340).abs() < 1e-8, "DRV8311 Kf changed: {kf}");
            for copper in [3.0] {
                for voltage in [5.0] {
                    for current in [1.1] {
                        ipc.supply_voltage_v = voltage;
                        ipc.max_current_a = current;
                        let mut settings = pcbmotorgen_simulation::drive::DriveSettings::default();
                        settings.outer_copper_oz = copper;
                        settings.inner_copper_oz = copper;
                        settings.pwm_hz = 200e3;
                        settings.ripple_limit_fraction = 0.35;
                        settings.voltage_headroom = 0.95;
                        let a = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), settings.clone(), Some(kf), None)).unwrap();
                        assert!((a.thrust_n.unwrap() - 0.2883951774).abs() < 1e-8);
                        assert!((a.speed_voltage_v.unwrap() - 7.4230824523).abs() < 1e-8);
                        let mut goals = ipc.clone();
                        goals.target_force_n = 100.0;
                        goals.peak_force_n = 0.001;
                        settings.ripple_limit_fraction = 0.0001;
                        settings.voltage_headroom = 0.01;
                        settings.allowed_rise_c = 0.1;
                        let changed = tauri::async_runtime::block_on(analyze_drive(goals, settings, Some(kf), None)).unwrap();
                        super::goal_independence_tests::assert_electrical_equal(&a, &changed);
                    }
                }
            }
        }
    }

    #[test]
    fn generated_star_driver_analysis_tracks_voltage_and_current() {
        let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        ipc.routing_params.insert("connection".into(), 2.0);
        let drive = pcbmotorgen_simulation::drive::DriveSettings::default();
        let run = |ipc| tauri::async_runtime::block_on(analyze_drive(ipc, drive.clone(), Some(0.4), None)).unwrap();
        let baseline = run(ipc.clone());
        eprintln!("STAR baseline R={} ohm L={} H", baseline.phase_resistance_ohm, baseline.synchronous_inductance_h);
        for check in &baseline.checks {
            eprintln!("{}: {:?} value={} limit={} {}", check.id, check.status, check.value, check.limit, check.unit);
        }
        assert_eq!(baseline.phases.len(), 3);
        assert!(baseline.phases.iter().all(|phase| phase.connected));
        assert!(baseline.phase_resistance_ohm.is_finite() && baseline.phase_resistance_ohm > 0.0);
        assert!(baseline.phase_inductance_h.is_finite() && baseline.phase_inductance_h > 0.0);
        ipc.supply_voltage_v *= 2.0;
        let higher_voltage = run(ipc.clone());
        assert!((higher_voltage.available_voltage_v / baseline.available_voltage_v - 2.0).abs() < 1e-9);
        assert!((higher_voltage.ripple_pp_a / baseline.ripple_pp_a - 2.0).abs() < 1e-9);
        ipc.max_current_a *= 2.0;
        let higher_current = run(ipc);
        assert!((higher_current.copper_loss_w / higher_voltage.copper_loss_w - 4.0).abs() < 1e-9);
    }

    #[test]
    fn command_rejects_delta_before_running_star_analysis() {
        let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        ipc.routing_params.insert("connection".into(), 1.0);
        let mut drive = pcbmotorgen_simulation::drive::DriveSettings::default();
        let error = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), drive.clone(), None, None))
            .unwrap_err();
        assert!(error.contains("Star (wye) configuration is required"));
        drive.driver.supports_delta = true;
        let error = tauri::async_runtime::block_on(analyze_drive(ipc, drive, None, None))
            .unwrap_err();
        assert!(error.contains("delta electrical analysis is not yet available"));
    }

    /// The command runs on the app's default design and reports the routed
    /// four-layer star braid: three connected phases with one routed line each.
    #[test]
    fn command_reports_the_default_braid() {
        let ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        let a = tauri::async_runtime::block_on(analyze_drive(
            ipc,
            pcbmotorgen_simulation::drive::DriveSettings::default(),
            Some(0.4),
            None,
        ))
        .expect("command");
        assert_eq!(a.phases.len(), 3);
        assert!(a.phases.iter().all(|p| p.connected && p.strands >= 1));
        assert!(a.phase_resistance_ohm > 0.0);
        assert!(a.line_inductance_h > 0.0);
        assert_eq!(a.checks.len(), 9);
    }
}

#[cfg(test)]
mod cad_source_tests {
    use super::*;

    /// The default design exported as CAD geometry, with its coils renamed
    /// so they need a phase mapping.
    fn exported_default() -> (LinearMotorConfigIpc, pcbmotorgen_export::cad_dxf::CadGeometry) {
        let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        ipc.routing_params.insert("connection".into(), 2.0);
        let core = ipc.to_core();
        let mut cad = pcbmotorgen_export::cad_dxf::phase_coils_to_cad_geometry(
            &core.generate_coils_for_board(),
            core.num_layers,
            core.pcb_thickness_m * 1e3,
            core.min_trace_m * 1e3,
        )
        .expect("export");
        let rename = |net: &mut String| *net = format!("coil {net}");
        cad.routing.segments.iter_mut().for_each(|s| rename(&mut s.net));
        cad.routing.curves.iter_mut().for_each(|c| rename(&mut c.net));
        cad.routing.vias.iter_mut().for_each(|v| rename(&mut v.net));
        // This fixture explicitly reviews the generated star terminals. A
        // fresh DXF import must still prompt the user instead of inferring
        // electrical buses behind their back.
        use pcbmotorgen_simulation::drive::{extract_phase_networks, EdgeKind};
        use pcbmotorgen_export::cad_dxf::{CadTerminal, CadCoilTerminals};
        for network in extract_phase_networks(&cad.routing) {
            assert_eq!(network.terminal.len(), 1);
            assert_eq!(network.star.len(), 1);
            let endpoint = |node| network.edges.iter().find_map(|edge| {
                if let EdgeKind::Trace { layer, points, .. } = &edge.kind {
                    let point = if edge.a == node { points.first() } else if edge.b == node { points.last() } else { None }?;
                    Some(CadTerminal { layer: *layer, position: pcbmotorgen_routing::Point::new(point[0]*1000.0, point[1]*1000.0) })
                } else { None }
            }).unwrap();
            cad.coil_terminals.insert(network.net.clone(), CadCoilTerminals {
                input: endpoint(network.terminal[0]), output: endpoint(network.star[0]),
            });
        }
        (ipc, cad)
    }

    #[test]
    fn imported_copper_with_conducting_housing_is_goal_independent() {
        use pcbmotorgen_simulation::backplane::{BackplaneStack, HousingSpec, HousingMaterial};
        let (mut ipc, mut cad) = exported_default();
        ipc.n_positions = 9;
        ipc.meshing = 3;
        ipc.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec {
            material: HousingMaterial::Aluminum6061, thickness_m: 0.001, gap_m: 0.001,
        }) });
        for p in ["A", "B", "C"] { cad.coil_phases.insert(format!("coil {p}"), p.into()); }
        let original = serde_json::to_value(&cad).unwrap();
        let baseline = pcbmotorgen_simulation::drive::DriveSettings::default();
        let mut strict = baseline.clone();
        strict.voltage_headroom = 0.0001;
        strict.ripple_limit_fraction = 0.0001;
        strict.allowed_rise_c = 0.1;
        let run = |c: LinearMotorConfigIpc, settings: pcbmotorgen_simulation::drive::DriveSettings| {
            let force = tauri::async_runtime::block_on(evaluate_force_sweep(
                c.clone(), Some(cad.clone()), Some(settings.clone()))).unwrap();
            let kf = force.mean_thrust_n / force.current_a;
            let electrical = tauri::async_runtime::block_on(analyze_drive(
                c, settings, Some(kf), Some(cad.clone()))).unwrap();
            (force, electrical)
        };
        let a = run(ipc.clone(), baseline.clone());
        let mut goals = ipc.clone();
        goals.target_force_n = 100.0;
        goals.peak_force_n = 0.001;
        goals.max_accel_m_s2 = 0.0;
        goals.max_temperature_rise_c = 0.0;
        let b = run(goals, strict);
        assert_eq!(serde_json::to_value(&a.0).unwrap(), serde_json::to_value(&b.0).unwrap());
        super::goal_independence_tests::assert_electrical_equal(&a.1, &b.1);
        let bp_a = serde_json::to_value(a.1.backplane.as_ref().unwrap()).unwrap();
        let bp_b = serde_json::to_value(b.1.backplane.as_ref().unwrap()).unwrap();
        for (key, value) in bp_a.as_object().unwrap() {
            if key != "drag_curve" {
                super::goal_independence_tests::assert_numerically_equal(value, &bp_b[key], &format!("backplane {key}"));
            }
        }
        // Positive control: actual excitation changes force and copper heating.
        ipc.max_current_a *= 2.0;
        let physical = run(ipc, baseline);
        assert!((physical.0.mean_thrust_n / a.0.mean_thrust_n - 2.0).abs() < 1e-10);
        assert!((physical.1.copper_loss_w / a.1.copper_loss_w - 4.0).abs() < 1e-10);
        assert_eq!(serde_json::to_value(&cad).unwrap(), original);
    }

    #[test]
    fn unmapped_coils_are_reported() {
        let (ipc, cad) = exported_default();
        let err = tauri::async_runtime::block_on(evaluate_force_sweep(ipc, Some(cad), Some(Default::default())))
            .expect_err("unmapped");
        assert!(err.contains("coil A"), "{err}");
    }

    #[test]
    fn dc_geometry_command_preserves_actual_imported_depths_and_has_no_force_result() {
        let (ipc, mut cad) = exported_default();
        for phase in ["A", "B", "C"] { cad.coil_phases.insert(format!("coil {phase}"), phase.into()); }
        let original = serde_json::to_value(&cad).unwrap();
        let result = tauri::async_runtime::block_on(prepare_dc_winding_geometry(
            ipc.clone(), Default::default(), Some(cad.clone()))).expect("actual imported geometry");
        let hints = crate::commands::cad_source::CadBoard::new(&cad, &ipc.to_core()).unwrap().drive_hints(&cad);
        assert_eq!(result["geometry_hints"]["layer_z_m"], serde_json::json!(hints.layer_z_m));
        assert_eq!(serde_json::to_value(&cad).unwrap(), original);
        assert_eq!(result["schema"], "finite-dc-winding-geometry-v1");
        assert!(result.get("force_n").is_none());
        assert!(result.get("return_path_m").is_none());
    }

    #[test]
    fn dc_geometry_command_rejects_unmapped_imports_without_generated_fallback() {
        let (ipc, cad) = exported_default();
        let error = tauri::async_runtime::block_on(prepare_dc_winding_geometry(
            ipc, Default::default(), Some(cad))).unwrap_err();
        assert!(error.contains("coil A"), "{error}");
    }

    #[test]
    fn imported_z_scaling_is_shared_by_force_driver_heat_housing_and_dc_geometry() {
        use pcbmotorgen_simulation::backplane::{BackplaneLayer, BackplaneStack, LayerMaterial};
        let (mut ipc, mut cad) = exported_default();
        for p in ["A", "B", "C"] { cad.coil_phases.insert(format!("coil {p}"), p.to_string()); }
        let count = cad.layer_z_mm.len();
        cad.layer_z_mm = (0..count).map(|layer| -2.0 * (count - 1 - layer) as f64).collect();
        ipc.backplane = Some(BackplaneStack { layers: vec![BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002)], housing: None });
        ipc.n_positions = 3;
        ipc.meshing = 2;
        let before = serde_json::to_value(&cad).unwrap();
        let mut placed = cad.clone();
        placed.layer_z_mm = crate::commands::cad_source::CadBoard::new(&cad, &ipc.to_core()).unwrap()
            .layer_z_m.iter().map(|z| z * 1000.0).collect();
        let force = |g| tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), Some(g), Some(Default::default()))).unwrap();
        let driver = |g| tauri::async_runtime::block_on(analyze_drive(ipc.clone(), Default::default(), Some(0.4), Some(g))).unwrap();
        let a = force(cad.clone());
        let b = force(placed.clone());
        for (a, b) in a.force_x_n.iter().zip(&b.force_x_n) { assert!((a - b).abs() < 1e-12); }
        let da = driver(cad.clone());
        let db = driver(placed.clone());
        assert!((da.phase_resistance_ohm - db.phase_resistance_ohm).abs() < 1e-12);
        assert!((da.effective_inductance_h - db.effective_inductance_h).abs() < 1e-15);
        let heat = |g, config| {
            let request = pcbmotorgen_simulation::visualization::VisualizationRequest {
                request_id: "z-audit".into(), mover_position_m: 0.01,
                bounds_m: [[0., 0.02], [0., 0.008], [-0.004, 0.005]], counts: [2, 2, 2],
                phase_peak_a: 1.0, fields: false, heat: true,
                field_source: Default::default(), phase_angle_deg: 0.,
            };
            serde_json::to_value(tauri::async_runtime::block_on(
                crate::commands::visualization::sample_simulation_visualization(config, Default::default(), Some(g), request)
            ).unwrap()).unwrap()
        };
        let ha = heat(cad.clone(), ipc.clone());
        let hb = heat(placed.clone(), ipc.clone());
        assert!(ha["heat_unavailable_reason"].is_null(), "{ha}");
        assert_eq!(ha["heat"], hb["heat"]);
        tauri::async_runtime::block_on(analyze_housing_motion(ipc.clone(), pcbmotorgen_simulation::backplane::HousingMotionProfile { duration_s: 0.1 }, 3., Some(cad.clone()))).unwrap();
        let snapshot = tauri::async_runtime::block_on(prepare_dc_winding_geometry(ipc.clone(), Default::default(), Some(cad.clone()))).unwrap();
        let z = snapshot["geometry_hints"]["layer_z_m"].as_array().unwrap();
        let low = z.iter().map(|v| v.as_f64().unwrap()).fold(f64::INFINITY, f64::min);
        let high = z.iter().map(|v| v.as_f64().unwrap()).fold(f64::NEG_INFINITY, f64::max);
        assert!((low + ipc.pcb_thickness_m).abs() < 1e-15);
        assert_eq!(high, 0.0);
        for edge in ha["heat"]["edges"].as_array().unwrap() {
            for (point, layer) in edge["points_m"].as_array().unwrap().iter().zip(edge["layers"].as_array().unwrap().iter().cycle()) {
                let expected = z[layer.as_u64().unwrap() as usize].as_f64().unwrap();
                assert!((point[2].as_f64().unwrap() - expected).abs() < 1e-15);
            }
        }
        let mut thicker = ipc.clone();
        thicker.pcb_thickness_m *= 2.0;
        // Check an actual native response after changing only software thickness.
        // Omit the backplane here: its placement is a separate model input.
        thicker.backplane = None;
        let thick_heat = heat(cad.clone(), thicker.clone());
        assert!(thick_heat["heat_unavailable_reason"].is_null());
        let deep = tauri::async_runtime::block_on(prepare_dc_winding_geometry(thicker.clone(), Default::default(), Some(cad.clone()))).unwrap();
        for (a, b) in z.iter().zip(deep["geometry_hints"]["layer_z_m"].as_array().unwrap()) {
            assert!((2.0 * a.as_f64().unwrap() - b.as_f64().unwrap()).abs() < 1e-15);
        }
        for edge in thick_heat["heat"]["edges"].as_array().unwrap() {
            for point in edge["points_m"].as_array().unwrap() {
                let z = point[2].as_f64().unwrap();
                assert!(z >= -thicker.pcb_thickness_m - 1e-15 && z <= 1e-15);
            }
        }
        assert_eq!(serde_json::to_value(&cad).unwrap(), before);
    }

    #[test]
    fn independent_housing_command_uses_imported_geometry_without_driver_or_connection_substitution() {
        use pcbmotorgen_simulation::backplane::{BackplaneStack, HousingSpec, HousingMaterial, HousingMotionProfile, HousingMotionAnalysis};
        let (mut ipc, mut cad) = exported_default();
        for p in ["A", "B", "C"] { cad.coil_phases.insert(format!("coil {p}"), p.to_string()); }
        ipc.backplane = Some(BackplaneStack { layers: vec![], housing: Some(HousingSpec { material: HousingMaterial::Stainless316, thickness_m: 0.001, gap_m: 0.001 }) });
        let depths = cad.layer_z_mm.clone();
        let profile = HousingMotionProfile { duration_s: 0.1 };
        let generated = tauri::async_runtime::block_on(analyze_housing_motion(ipc.clone(), profile, 3., None)).unwrap();
        cad.terminal_connection = Some(pcbmotorgen_export::cad_dxf::TerminalConnection::Delta);
        let imported = tauri::async_runtime::block_on(analyze_housing_motion(ipc, profile, 3., Some(cad.clone()))).unwrap();
        match (generated, imported) {
            (HousingMotionAnalysis::Experimental { estimate: a }, HousingMotionAnalysis::Experimental { estimate: b }) => {
                assert!(a.housing_joule_power_w > 0.);
                assert!((a.housing_joule_power_w / b.housing_joule_power_w - 1.).abs() < 1e-12);
                assert_eq!(a.method, "linear_planar_odd_harmonics_region_joule_v2");
                assert_eq!(a.method, b.method);
                assert!(a.travel_tail_bound_w.unwrap() <= 0.005 * a.housing_joule_power_w);
                assert!((b.housing_energy_j - b.housing_joule_power_w * 0.1).abs() < 1e-12);
                assert!((b.housing_drag_n * 3.0 - b.housing_joule_power_w).abs() < 1e-12);
            }
            values => panic!("{values:?}"),
        }
        assert_eq!(cad.layer_z_mm, depths);
    }

    #[test]
    fn mapped_import_matches_the_generated_copper() {
        let (mut ipc, mut cad) = exported_default();
        ipc.n_positions = 9;
        ipc.meshing = 5;
        for p in ["A", "B", "C"] {
            cad.coil_phases.insert(format!("coil {p}"), p.to_string());
        }
        let gen = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, Some(Default::default()))).unwrap();
        let imp = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), Some(cad.clone()), Some(Default::default()))).unwrap();
        assert!(
            (gen.mean_thrust_n - imp.mean_thrust_n).abs() <= 1e-6 * gen.mean_thrust_n.abs().max(1.0),
            "generated {} vs imported {}",
            gen.mean_thrust_n,
            imp.mean_thrust_n
        );
        let settings = pcbmotorgen_simulation::drive::DriveSettings::default();
        let a_gen = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), settings.clone(), Some(0.4), None)).unwrap();
        let a_imp = tauri::async_runtime::block_on(analyze_drive(ipc, settings, Some(0.4), Some(cad))).unwrap();
        assert_eq!(a_imp.phases.len(), 3);
        let rel = (a_gen.phase_resistance_ohm - a_imp.phase_resistance_ohm).abs() / a_gen.phase_resistance_ohm;
        assert!(rel < 0.02, "R generated {} vs imported {}", a_gen.phase_resistance_ohm, a_imp.phase_resistance_ohm);
    }
}
