//! Print the backplane model's numbers for a list of stacks (FEMM check, t707).
//!
//! Reads JSON on stdin:
//!
//! ```json
//! { "geometry": { "pole_pitch_mm": 6, "magnet_width_mm": 5, "magnet_cross_width_mm": 5,
//!                 "magnet_height_mm": 3, "magnet_count": 5, "remanence_t": 1.34,
//!                 "air_gap_mm": 0.5, "pcb_thickness_mm": 1.6, "copper_layers": 2,
//!                 "active_area_length_mm": 92, "freqs_hz": [1e5], "speeds_m_s": [20] },
//!   "cases": [ { "name": "mnzn_2mm", "stack": { "layers": [...], "housing": null } } ] }
//! ```
//!
//! `copper_layers` is optional and defaults to 2. It sets `num_layers`, the
//! copper sheet count of the layered inductance factor. `active_area_length_mm`
//! defaults to the magnet span, so the whole winding sits under the magnets.
//! `freqs_hz` and `speeds_m_s` are optional. `linear: true` raises every
//! layer's Bsat to the override limit, for comparison with linear FEM runs.
//!
//! and writes one JSON object per case to stdout with the [`BackplaneAnalysis`]
//! for that geometry plus `field_ratio_2d`: Bz at the PCB top under a magnet
//! centre, with / without the stack, from the image-magnet field model on a
//! long, wide array (21 magnets, 1 m cross width) so it is comparable to a 2-D
//! planar FEM slice. `coil` holds the complex inductance factor `[re, im]` at
//! each frequency, away from and under the magnets. `motion` holds, at each
//! speed, the fundamental reflection `[re, im]` the moving magnet field sees
//! and the normal force and drag of the magnets [N].
//!
//! Run: `cargo run -q -p pcbmotorgen-simulation --example backplane_dump < cases.json`

use std::io::Read;

use pcbmotorgen_simulation::backplane::{BackplaneStack, MAX_BSAT_T};
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
    #[serde(default = "default_copper_layers")]
    copper_layers: u32,
    #[serde(default)]
    active_area_length_mm: Option<f64>,
    #[serde(default)]
    freqs_hz: Vec<f64>,
    #[serde(default)]
    speeds_m_s: Vec<f64>,
    #[serde(default)]
    linear: bool,
}

fn default_copper_layers() -> u32 {
    2
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
    let span = g.magnet_count as f64 * g.pole_pitch_mm;
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
        active_area_length_m: mm(g.active_area_length_mm.unwrap_or(span)),
        board_width_m: mm(g.magnet_cross_width_mm),
        num_layers: g.copper_layers,
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
    let g = &input.geometry;
    let sim = sim_for(g);
    let b0 = centre_bz(&sim, None);
    for case in &input.cases {
        let mut stack = case.stack.clone();
        if g.linear {
            for l in &mut stack.layers {
                l.bsat_t = Some(MAX_BSAT_T);
            }
        }
        let analysis = stack.analyze(&sim);
        let solved = stack.solve(&sim);
        let b1 = centre_bz(&sim, Some(&stack));
        let coil: Vec<_> = g
            .freqs_hz
            .iter()
            .map(|&f| {
                let [away, under] = solved.coil_factor_parts(f);
                serde_json::json!({ "freq_hz": f, "away": [away.re, away.im], "under": [under.re, under.im] })
            })
            .collect();
        let motion: Vec<_> = g
            .speeds_m_s
            .iter()
            .map(|&v| {
                let r = solved.magnet_reflection(v);
                let f = solved.magnet_forces(&sim, v);
                serde_json::json!({ "speed_m_s": v, "reflection": [r.re, r.im],
                                    "normal_n": f.normal_n, "drag_n": f.drag_n })
            })
            .collect();
        let out = serde_json::json!({
            "name": case.name,
            "analysis": analysis,
            "field_ratio_2d": b1 / b0,
            "magnet_area_m2": sim.magnet_count as f64 * sim.magnet_dims_m[0] * sim.magnet_dims_m[1],
            "coil": coil,
            "motion": motion,
        });
        println!("{out}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copper_layers_default_to_two() {
        let g: Geometry = serde_json::from_str(
            r#"{ "pole_pitch_mm": 6, "magnet_width_mm": 5, "magnet_cross_width_mm": 5,
                 "magnet_height_mm": 3, "magnet_count": 5, "remanence_t": 1.34,
                 "air_gap_mm": 0.5, "pcb_thickness_mm": 1.6 }"#,
        )
        .unwrap();
        assert_eq!(g.copper_layers, 2);
        assert_eq!(sim_for(&g).num_layers, 2);
        assert_eq!(sim_for(&g).active_area_length_m, mm(30.0));
    }
}
