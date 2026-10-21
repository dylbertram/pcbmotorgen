//! Offline JSON entrypoint for independent housing-motion comparisons.
use pcbmotorgen_simulation::{backplane::{HousingMotionAnalysis, HousingMotionProfile}, SimulationInput};
use serde::Deserialize;
use pcbmotorgen_routing::RoutingResult;
use pcbmotorgen_simulation::{drive::{DriveSettings, DriveGeometryHints, analyze_drive_with, validate_copper_placement}, magnetic::{ForceEvaluator, CommutationMode}};

#[derive(Deserialize)]
struct Case {
    sim: SimulationInput, speed_m_s: f64, duration_s: f64,
    #[serde(default)] routing: Option<RoutingResult>,
    #[serde(default)] drive: DriveSettings,
    #[serde(default)] geometry_hints: Hints,
}

#[derive(Default, Deserialize)]
struct Hints { #[serde(default)] layer_z_m: Vec<f64> }

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).ok_or("Expected JSON case path")?;
    let case: Case = serde_json::from_str(&std::fs::read_to_string(path)?)?;
    case.sim.validate()?;
    let hints = DriveGeometryHints { layer_z_m: case.geometry_hints.layer_z_m, ..Default::default() };
    if !hints.layer_z_m.is_empty() && hints.layer_z_m.len() != case.sim.num_layers as usize {
        return Err("Explicit conductor depth count differs from num_layers; geometry was not changed".into());
    }
    if let Some(routing) = &case.routing { validate_copper_placement(&case.sim, routing, &hints)?; }
    let stack = case.sim.backplane.as_ref().ok_or("Case requires housing/backplane settings")?;
    let value = stack.housing_motion(&case.sim, case.speed_m_s, HousingMotionProfile { duration_s: case.duration_s });
    let unavailable = matches!(value, HousingMotionAnalysis::Unavailable { .. });
    let mut output = serde_json::to_value(&value)?;
    if !unavailable {
        if let Some(routing) = &case.routing {
            let mut settings = case.drive;
            settings.target_speed_m_s = case.speed_m_s;
            settings.housing_motion = Some(HousingMotionProfile { duration_s: case.duration_s });
            let driver = analyze_drive_with(&case.sim, routing, &settings, None, &hints);
            if driver.phases.is_empty() || driver.phases.iter().any(|p| !p.connected) {
                return Err("Imported winding has unconnected phases; no numerical fallback emitted".into());
            }
            let (mut evaluator, coils) = ForceEvaluator::new(9, 40, CommutationMode::PhaseAOnly, 0.0)
                .with_routed_currents(routing, &case.sim, &settings, &hints)?;
            let force = evaluator.evaluate(&case.sim, &coils)?;
            if !driver.phase_resistance_ohm.is_finite() || driver.phase_resistance_ohm <= 0.0 || force.force_x_n.iter().any(|v| !v.is_finite()) {
                return Err("Routed-copper calculation has invalid resistance/force; no fallback emitted".into());
            }
            output["routing_check"] = serde_json::json!({
                "scope":"Actual routed-copper electrical and fixed-phase force calculation, not controller or hardware validation",
                "segments":routing.segments.len(),"vias":routing.vias.len(),"layer_z_m":hints.layer_z_m,
                "phase_resistance_ohm":driver.phase_resistance_ohm,
                "phases":driver.phases.iter().map(|p| serde_json::json!({"net":p.net,"connected":p.connected,"resistance_hot_ohm":p.resistance_hot_ohm,"via_resistance_ohm":p.via_resistance_ohm})).collect::<Vec<_>>(),
                "force_positions_m":force.positions_m,"force_x_n":force.force_x_n,
                "housing_motion_from_driver":driver.backplane.and_then(|p| p.housing_motion),
            });
        }
    }
    println!("{}", serde_json::to_string_pretty(&output)?);
    if unavailable { std::process::exit(1); }
    Ok(())
}
