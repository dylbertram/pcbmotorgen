//! Headless live-geometry serializer for request-contract verification.
use pcbmotorgen_simulation::{SimulationInput, drive::{DriveSettings, DriveGeometryHints, TerminalPair}};
use pcbmotorgen_routing::RoutingResult;
use serde::Deserialize;

#[derive(Default, Deserialize)]
struct Hints {
    #[serde(default)] layer_z_m: Vec<f64>,
    #[serde(default)] terminals: std::collections::BTreeMap<String, Vec<TerminalPair>>,
}

#[derive(Deserialize)]
struct Request { sim: SimulationInput, routing: RoutingResult, drive: DriveSettings,
    #[serde(default)] geometry_hints: Hints }

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).ok_or("Expected explicit geometry JSON path")?;
    let request: Request = serde_json::from_str(&std::fs::read_to_string(path)?)?;
    let hints = DriveGeometryHints {layer_z_m:request.geometry_hints.layer_z_m, terminals:request.geometry_hints.terminals};
    let value = pcbmotorgen_simulation::dc_geometry::snapshot(&request.sim, &request.routing, &request.drive, &hints)?;
    println!("{}", serde_json::to_string(&value)?);
    Ok(())
}
