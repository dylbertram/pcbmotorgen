//! Physics / simulation command handlers: magnet grades, height stack, coil
//! generation, force sweep, friction, driver suitability, B-field grid
//! sampling, and the travel envelope.

use crate::ipc::*;

use pcbmotorgen_simulation::magnetic::{
    CommutationMode as CoreCommutationMode, ForceEvaluator, MagnetArray,
};
use pcbmotorgen_simulation::stackup::{FrictionEstimator, HeightStackCalculator};

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
        })
    })
    .await
    .map_err(|e| format!("height_stack worker failed: {e}"))?
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
    let core = config.to_core();
    let n_positions = config.n_positions.max(2) as usize;
    let meshing = config.meshing.max(1) as usize;
    let commutation = match config.commutation {
        CommutationModeIpc::MaxThrust => CoreCommutationMode::MaxThrust,
        CommutationModeIpc::PhaseAOnly => CoreCommutationMode::PhaseAOnly,
    };
    tauri::async_runtime::spawn_blocking(move || {
        let (routing, sim) = match cad_geometry.as_ref() {
            Some(cad) => {
                let board = super::cad_source::CadBoard::new(cad, &core)?;
                let sim = board.simulation_input(cad, &core);
                (board.routing, sim)
            }
            None => {
                core.design_rules().validate_trace_width()?;
                let ctx = core.routing_context();
                let routing_result = pcbmotorgen_routing::generate_routing_result(
                    &ctx,
                    &core.routing_pattern_id(),
                )
                .map_err(|e| format!("routing pattern failed: {e}"))?;
                (routing_result, core.to_simulation())
            }
        };

        let hints = cad_geometry.as_ref().map(super::cad_source::CadBoard::drive_hints).unwrap_or_default();
        let (mut evaluator, coils) = ForceEvaluator::new(n_positions, meshing, commutation, 0.0)
            .with_routed_currents(&routing, &sim, &drive.unwrap_or_default(), &hints)
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
            return Ok(pcbmotorgen_simulation::drive::analyze_drive_with(
                &board.simulation_input(cad, &core),
                &board.routing,
                &drive,
                thrust_constant_n_per_a,
                &super::cad_source::CadBoard::drive_hints(cad),
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
mod analyze_drive_tests {
    use super::*;

    #[test]
    #[ignore = "Exports real winding geometry for independent Magpylib validation"]
    fn export_magpylib_validation_fixture() {
        let mut ipc = crate::ipc::ProjectConfigStateIpc::default().to_linear_motor_ipc();
        ipc.routing_params.insert("connection".into(), 2.0);
        let core = ipc.to_core();
        let routing = pcbmotorgen_routing::generate_routing_result(&core.routing_context(), &core.routing_pattern_id()).unwrap();
        let sim = core.to_simulation();
        let points = vec![0.0, 0.001, 0.003, 0.006, 0.012, 0.036, 0.06];
        let array = pcbmotorgen_simulation::magnetic::magnet_model::MagnetArray::new(&sim);
        let b = array.bfield_at_pcb_surface(&points, 0.0, 0.0);
        let (mut evaluator, coils) = ForceEvaluator::new(9, 10, CoreCommutationMode::PhaseAOnly, 0.0)
            .with_routed_currents(&routing, &sim, &pcbmotorgen_simulation::drive::DriveSettings::default(), &Default::default()).unwrap();
        let force = evaluator.evaluate(&sim, &coils).unwrap();
        let samples: Vec<_> = evaluator.routed_conductor_samples().unwrap()[0].iter()
            .map(|s| serde_json::json!({"point": s.midpoint_3d, "dl": s.dl_3d})).collect();
        let out = serde_json::json!({"routing": routing, "sim": sim, "field_x_m": points, "rust_b_t": b,
            "phase_a_samples": samples, "force_positions_m": force.positions_m, "rust_force_x_n": force.force_x_n});
        std::fs::write("magpylib-fixture.json", serde_json::to_vec(&out).unwrap()).unwrap();
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
        for mesh in [10, 20, 40] {
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
                assert!(a.ripple_pp_a > state.drive.ripple_limit_fraction * ipc.max_current_a);
                assert!(a.thrust_n.unwrap() < ipc.target_force_n);
            }
            if let Some(old) = previous.as_ref() {
                let max_diff = old.iter().zip(&sweep.force_x_n).map(|(a,b)| (a-b).abs()).fold(0.0, f64::max);
                assert!(max_diff / sweep.mean_thrust_n.abs() < 0.002, "mesh {mesh} has not converged: {max_diff}");
            }
            previous = Some(sweep.force_x_n);
        }
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
                let pass = a.checks.iter().all(|c| c.status == pcbmotorgen_simulation::drive::CheckStatus::Pass);
                if strands == 9.0 {
                    assert_eq!(pass, voltage == 12.0, "nine-strand 5 V / 12 V feasibility regression: {:?}", a.checks);
                }
                eprintln!("DRV8311 strands={strands} V={voltage} ALL_PASS={pass} R={} L_uH={} thrust={:?} holding={} speed={:?} available={} ripple={} ripple_limit={}", a.phase_resistance_ohm, a.synchronous_inductance_h*1e6, a.thrust_n, a.holding_voltage_v, a.speed_voltage_v, a.available_voltage_v, a.ripple_pp_a, 0.35*1.1);
                eprintln!("checks={:?}", a.checks.iter().map(|c| (&c.id, c.status, c.value, c.limit)).collect::<Vec<_>>());
            }
        }
    }

    #[test]
    fn drv8311_star_reference_passes_all_checks() {
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
                        let a = tauri::async_runtime::block_on(analyze_drive(ipc.clone(), settings, Some(kf), None)).unwrap();
                        let electrical_pass = a.checks.iter().filter(|c| c.id != "thrust").all(|c| c.status == pcbmotorgen_simulation::drive::CheckStatus::Pass);
                        assert!(a.checks.iter().all(|c| c.status == pcbmotorgen_simulation::drive::CheckStatus::Pass), "reference driver checks: {:?}", a.checks);
                        eprintln!("trial width={width_mm} V={voltage} I={current} checks={:?}", a.checks.iter().map(|c| (&c.id, c.status, c.value, c.limit)).collect::<Vec<_>>());
                        if electrical_pass {
                            eprintln!("ELECTRICAL PASS DRV8311 width={width_mm} copper={copper}oz V={voltage} I={current} thrust={:?} N checks={:?}", a.thrust_n, a.checks.iter().map(|c| (&c.id, c.status)).collect::<Vec<_>>());
                        }
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
    /// braid: three connected phases with five strands each.
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
    fn unmapped_coils_are_reported() {
        let (ipc, cad) = exported_default();
        let err = tauri::async_runtime::block_on(evaluate_force_sweep(ipc, Some(cad), None))
            .expect_err("unmapped");
        assert!(err.contains("coil A"), "{err}");
    }

    #[test]
    fn mapped_import_matches_the_generated_copper() {
        let (mut ipc, mut cad) = exported_default();
        ipc.n_positions = 9;
        ipc.meshing = 5;
        for p in ["A", "B", "C"] {
            cad.coil_phases.insert(format!("coil {p}"), p.to_string());
        }
        let gen = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), None, None)).unwrap();
        let imp = tauri::async_runtime::block_on(evaluate_force_sweep(ipc.clone(), Some(cad.clone()), None)).unwrap();
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
