//! Authoritative routed-copper adapter. No frontend-supplied motor constants.

use super::*;
use crate::drive::{analyze_drive_with, DriveAnalysis, DriveGeometryHints, DriveSettings};
use crate::magnetic::{CommutationMode, ForceEvaluator};
use crate::params::SimulationInput;
use pcbmotorgen_routing::RoutingResult;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "boundary", rename_all = "snake_case", deny_unknown_fields)]
pub enum MoveSource {
    /// Explicitly selected constant-voltage source directly at the DC link.
    StiffDcLink { accepts_regeneration: bool },
}

/// User requirements and explicit solver assumptions only. R, L, force and
/// source voltage are taken from the active design, never this request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RoutedMoveRequest {
    pub profile: MoveProfile,
    pub control: WindingModel,
    /// Balanced sine basis at absolute first-magnet-center x = 0.
    /// This is a declared controller reference, not a fitted motor constant.
    pub electrical_angle_at_zero_rad: f64,
    /// Legacy design goal, ignored by the imposed-demand simulation.
    #[serde(default)]
    pub phase_peak_limit_a: f64,
    pub source: MoveSource,
    pub additional_driver_loss_w: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub loss_model: Option<DeclaredLossModel>,
    /// Uniform force-map positions over the declared move bounds.
    pub force_positions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutedMoveResult {
    pub demand: MovePowerResult,
    pub drive: DriveAnalysis,
    /// Copper full-overlap interval only, not a mechanical end-stop claim.
    pub full_overlap_bounds_m: [f64; 2],
    pub conductor_samples: usize,
    pub force_map_step_m: f64,
    pub meshing: usize,
}

/// Bounded per-design calculation. A conductive/magnetic stack needs a
/// different dynamic loss/inductance model; it is rejected, not omitted.
pub fn evaluate_routed_move(
    sim: &SimulationInput,
    routing: &RoutingResult,
    settings: &DriveSettings,
    hints: &DriveGeometryHints,
    request: &RoutedMoveRequest,
    meshing: usize,
    cancelled: &impl Fn() -> bool,
) -> Result<RoutedMoveResult, String> {
    if cancelled() {
        return Err("Move power calculation cancelled".into());
    }
    sim.validate_for_move().map_err(|e| e.to_string())?;
    if sim.phases != 3 || request.control != WindingModel::BalancedStarSinusoidal {
        return Err(
            "Move calculation requires an explicit three-phase balanced-star sinusoidal controller"
                .into(),
        );
    }
    if sim
        .backplane
        .as_ref()
        .is_some_and(|s| !s.layers.is_empty() || s.housing.is_some())
    {
        return Err("Move power with a backplane or housing is not supported: dynamic inductance/eddy and drag losses are not integrated. Geometry was not changed.".into());
    }
    if !(2..=513).contains(&request.force_positions) || !(1..=128).contains(&meshing) {
        return Err(
            "Move budget requires 2..513 force-map positions and 1..128 conductor subdivisions"
                .into(),
        );
    }
    if ![
        settings.outer_copper_oz,
        settings.inner_copper_oz,
        settings.via_plating_m,
        settings.pwm_hz,
    ]
    .into_iter()
    .all(positive)
        || !settings.winding_temp_c.is_finite()
        || !positive(crate::drive::rho_cu_at(settings.winding_temp_c))
        || !nonnegative(settings.series_inductance_h)
        || !nonnegative(settings.driver.rds_on_ohm)
        || ![
            settings.driver.min_supply_v,
            settings.driver.max_supply_v,
            settings.driver.max_pwm_hz,
        ]
        .into_iter()
        .all(positive)
        || settings.driver.min_supply_v > settings.driver.max_supply_v
        || !nonnegative(settings.driver.peak_current_a)
        || !nonnegative(settings.driver.continuous_rms_a)
        || !request.electrical_angle_at_zero_rad.is_finite()
        || request
            .additional_driver_loss_w
            .is_some_and(|w| !nonnegative(w))
    {
        return Err("Invalid copper, temperature, driver or move electrical settings".into());
    }
    if sim.supply_voltage_v < settings.driver.min_supply_v
        || sim.supply_voltage_v > settings.driver.max_supply_v
        || settings.pwm_hz > settings.driver.max_pwm_hz
    {
        return Err(
            "Supply voltage or PWM frequency exceeds the declared driver operating range".into(),
        );
    }
    // Bound field and Neumann integration before constructing an expensive model.
    if routing.segments.len() + routing.curves.len() + routing.vias.len() > 10_000
        || !routing.splines.is_empty()
    {
        return Err("Move calculation exceeds the 2000-filament budget or uses unsupported spline copper; no substitute geometry was calculated".into());
    }
    let networks = crate::drive::extract_phase_networks_with_terminals(routing, &hints.terminals);
    if networks.len() != 3 || networks.iter().any(|n| n.node_count > 1500) {
        return Err(
            "Move calculation requires three phase networks of at most 1500 nodes each".into(),
        );
    }
    let filaments: usize = networks
        .iter()
        .flat_map(|n| &n.edges)
        .map(|e| match &e.kind {
            crate::drive::EdgeKind::Trace { points, .. } => points.len().saturating_sub(1),
            _ => 0,
        })
        .sum();
    if filaments > 2000 {
        return Err("Move calculation exceeds the 2000-filament budget; no substitute geometry was calculated".into());
    }
    let (evaluator, coils) = ForceEvaluator::new(2, meshing, CommutationMode::MaxThrust, 0.0)
        .with_routed_currents(routing, sim, settings, hints)
        .map_err(|e| e.to_string())?;
    if coils.len() != 3 {
        return Err("Move power requires exactly three solved phase networks".into());
    }
    if request.loss_model.as_ref().is_some_and(|l| {
        coils
            .iter()
            .zip(&l.phase_names)
            .any(|(coil, name)| &coil.phase_name != name)
    }) {
        return Err("Loss-model phase order does not match the actual winding networks".into());
    }
    let samples = evaluator
        .routed_conductor_samples()
        .unwrap()
        .iter()
        .map(Vec::len)
        .sum::<usize>();
    if samples > 40_000 || samples.saturating_mul(request.force_positions) > 8_000_000 {
        return Err(
            "Move force-map calculation exceeds its 8-million conductor-point budget".into(),
        );
    }
    let (physical_min, physical_max) = evaluator
        .sweep_center_limits_m(sim)
        .map_err(|e| e.to_string())?;
    let p = &request.profile;
    if !p.travel_min_m.is_finite()
        || !p.travel_max_m.is_finite()
        || p.travel_min_m >= p.travel_max_m
    {
        return Err(
            "Declare finite increasing move bounds in absolute first-magnet-center coordinates"
                .into(),
        );
    }
    let mut electrical = MoveElectricalModel {
        winding: request.control,
        phase_resistance_hot_ohm: 0.0,
        effective_phase_inductance_h: 0.0,
        electrical_period_m: 2.0 * sim.magnet_pitch_m,
        electrical_angle_at_zero_rad: request.electrical_angle_at_zero_rad,
        // Used only to validate user inputs before running any field solve.
        force_map: vec![
            ForceConstantPoint {
                position_m: p.travel_min_m,
                kf_n_per_a: 1.0,
            },
            ForceConstantPoint {
                position_m: p.travel_max_m,
                kf_n_per_a: 1.0,
            },
        ],
        phase_peak_limit_a: request.phase_peak_limit_a,
        source_voltage_v: sim.supply_voltage_v,
        voltage_headroom: settings.voltage_headroom,
        driver_path_resistance_ohm: settings.driver.rds_on_ohm,
        additional_driver_loss_w: request.additional_driver_loss_w,
        source_accepts_regeneration: match request.source {
            MoveSource::StiffDcLink {
                accepts_regeneration,
            } => accepts_regeneration,
        },
        phase_model: None,
        loss_model: request.loss_model.clone(),
        loss_operating_point: Some(LossOperatingPoint {
            driver_name: settings.driver.name.clone(),
            pwm_hz: settings.pwm_hz,
            winding_temp_c: settings.winding_temp_c,
            copper_thickness_m: Some(crate::drive::maximum_copper_thickness_m(sim, settings)),
        }),
    };
    validate(p, &electrical)?;
    let step = (p.travel_max_m - p.travel_min_m) / (request.force_positions - 1) as f64;
    let mut phase_map = Vec::with_capacity(request.force_positions);
    let mut scalar_map = Vec::with_capacity(request.force_positions);
    for i in 0..request.force_positions {
        if cancelled() {
            return Err("Move power calculation cancelled".into());
        }
        let x = p.travel_min_m + i as f64 * step;
        let force: [f64; 3] = evaluator
            .unit_phase_force_constants_at(sim, x)
            .map_err(|e| e.to_string())?
            .try_into()
            .map_err(|_| "Wrong phase count")?;
        let theta = TAU * x / electrical.electrical_period_m + request.electrical_angle_at_zero_rad;
        let kf = dot(
            force,
            std::array::from_fn(|j| (theta - TAU * j as f64 / 3.0).sin()),
        );
        // Force sign is never absolutized, fitted or polarity-calibrated here.
        if !positive(kf) {
            return Err(format!("Declared balanced-star reference reverses or loses thrust coupling at x={x:.9} m. Choose a supported controller reference; static sweep Kf was not substituted."));
        }
        scalar_map.push(ForceConstantPoint {
            position_m: x,
            kf_n_per_a: kf,
        });
        phase_map.push(PhaseForcePoint {
            position_m: x,
            force_n_per_a: force,
        });
    }
    if cancelled() {
        return Err("Move power calculation cancelled".into());
    }
    let drive = analyze_drive_with(sim, routing, settings, None, hints);
    if cancelled() {
        return Err("Move power calculation cancelled".into());
    }
    if drive.phases.len() != 3
        || drive.phases.iter().any(|p| !p.connected)
        || drive.phase_inductance_matrix_h.len() != 3
    {
        return Err("Move electrical network does not contain three connected phases".into());
    }
    let names: [String; 3] = std::array::from_fn(|i| drive.phases[i].net.clone());
    if coils
        .iter()
        .zip(&names)
        .any(|(coil, name)| &coil.phase_name != name)
    {
        return Err("Force/electrical phase order mismatch; no result was published".into());
    }
    let matrix = std::array::from_fn(|i| {
        std::array::from_fn(|j| {
            drive.phase_inductance_matrix_h[i][j]
                + if i == j {
                    settings.series_inductance_h
                } else {
                    0.0
                }
        })
    });
    electrical.phase_resistance_hot_ohm = drive.phase_resistance_ohm;
    electrical.effective_phase_inductance_h = drive.effective_inductance_h;
    electrical.force_map = scalar_map;
    electrical.phase_model = Some(PhaseDomainModel {
        phase_names: names,
        resistance_hot_ohm: std::array::from_fn(|i| drive.phases[i].resistance_hot_ohm),
        inductance_h: matrix,
        force_map: phase_map,
    });
    let mut demand = evaluate_move_with_cancel(p, &electrical, cancelled)?;
    demand.notes.extend(drive.notes.iter().cloned());
    demand.notes.push("Move control explicitly uses balanced-star sine currents with the declared electrical zero. The static preview current setpoint and design goals do not bound current allocation or suppress demand. No OCP response, peak-duration or thermal safety prediction.".into());
    if p.travel_min_m < physical_min || p.travel_max_m > physical_max {
        demand.notes.push(format!("Declared bounds include partial magnetic-array overlap with copper. The actual field/force is evaluated there without extending copper. Full-overlap interval is [{physical_min:.9}, {physical_max:.9}] m, not a verified mechanical limit."));
    }
    Ok(RoutedMoveResult {
        demand,
        drive,
        full_overlap_bounds_m: [physical_min, physical_max],
        conductor_samples: samples,
        force_map_step_m: step,
        meshing,
    })
}
