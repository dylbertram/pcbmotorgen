//! Print the backplane model's numbers for a list of stacks (FEMM check, t707).
//!
//! Reads JSON on stdin:
//!
//! ```json
//! { "geometry": { "pole_pitch_mm": 6, "magnet_width_mm": 5, "magnet_cross_width_mm": 5,
//!                 "magnet_height_mm": 3, "magnet_count": 5, "remanence_t": 1.34,
//!                 "air_gap_mm": 0.5, "pcb_thickness_mm": 1.6 },
//!   "cases": [ { "name": "mnzn_2mm", "stack": { "layers": [...], "housing": null } } ] }
//! ```
//!
//! and writes one JSON object per case to stdout with the [`BackplaneAnalysis`]
//! for that geometry plus `field_ratio_2d`: Bz at the PCB top under a magnet
//! centre, with / without the stack, from the image-magnet field model on a
//! long, wide array (21 magnets, 1 m cross width) so it is comparable to a 2-D
//! planar FEM slice.
//!
//! Run: `cargo run -q -p pcbmotorgen-simulation --example backplane_dump < cases.json`

use std::io::Read;

use pcbmotorgen_simulation::backplane::BackplaneStack;
use pcbmotorgen_simulation::units::mm;
use pcbmotorgen_simulation::{MagnetArray, SimulationInput};
use serde::Deserialize;

#[derive(Deserialize)]
struct Geometry {
    pole_pitch_mm: f64,
    magnet_width_mm: f64,
    magnet_cross_width_mm: f64,
    magnet_height_mm: f64,
    magnet_count: u32,
    remanence_t: f64,
    air_gap_mm: f64,
    pcb_thickness_mm: f64,
}

#[derive(Deserialize)]
struct Case {
    name: String,
    stack: BackplaneStack,
}

#[derive(Deserialize)]
struct Input {
    geometry: Geometry,
    cases: Vec<Case>,
}

fn sim_for(g: &Geometry) -> SimulationInput {
    SimulationInput {
        magnet_dims_m: [
            mm(g.magnet_width_mm),
            mm(g.magnet_cross_width_mm),
            mm(g.magnet_height_mm),
        ],
        magnet_count: g.magnet_count,
        magnet_pitch_m: mm(g.pole_pitch_mm),
        magnet_remanence_t: g.remanence_t,
        air_gap_m: mm(g.air_gap_mm),
        pcb_thickness_m: mm(g.pcb_thickness_mm),
        board_width_m: mm(g.magnet_cross_width_mm),
        ..SimulationInput::default()
    }
}

/// Bz at the PCB top under the centre magnet of a long, wide array.
fn centre_bz(sim: &SimulationInput, stack: Option<&BackplaneStack>) -> f64 {
    let mut wide = sim.clone();
    wide.magnet_count = 21;
    wide.magnet_dims_m[1] = 1.0;
    wide.board_width_m = 1.0;
    wide.backplane = stack.cloned();
    let mover = -10.0 * wide.magnet_pitch_m;
    MagnetArray::new(&wide).bfield_at_pcb_surface(&[0.0], mover, 0.0)[0][2]
}

fn main() {
    let mut raw = String::new();
    std::io::stdin()
        .read_to_string(&mut raw)
        .expect("read stdin");
    let input: Input = serde_json::from_str(&raw).expect("parse input JSON");
    let sim = sim_for(&input.geometry);
    let b0 = centre_bz(&sim, None);
    for case in &input.cases {
        let analysis = case.stack.analyze(&sim);
        let b1 = centre_bz(&sim, Some(&case.stack));
        let out = serde_json::json!({
            "name": case.name,
            "analysis": analysis,
            "field_ratio_2d": b1 / b0,
            "magnet_area_m2": sim.magnet_count as f64 * sim.magnet_dims_m[0] * sim.magnet_dims_m[1],
        });
        println!("{out}");
    }
}
