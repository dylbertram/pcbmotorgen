//! Live finite-DC geometry preparation. No magnetic result or implicit closure.
//!
//! Preserve actual route polylines, layer depths, pads/barrels and terminal
//! choices. The network current is an electrical graph check, not a substitute
//! for the separately qualified finite-volume current solve.
use crate::{SimulationInput, drive::{DriveGeometryHints, DriveSettings, EdgeKind,
    extract_phase_networks_with_terminals, solve_network, rho_cu_at, via_resistance_ohm}};
use pcbmotorgen_routing::RoutingResult;
use serde_json::{Value, json};

pub fn snapshot(sim: &SimulationInput, routing: &RoutingResult, drive: &DriveSettings,
                hints: &DriveGeometryHints) -> Result<Value, String> {
    sim.validate().map_err(|error| error.to_string())?;
    if routing.segments.len().saturating_add(routing.vias.len()) > 10_000 {
        return Err("Finite DC geometry preparation exceeds the declared 10000-edge resource cap; geometry was not truncated".into());
    }
    if !routing.curves.is_empty() || !routing.splines.is_empty() {
        return Err("Finite DC coupling has not qualified curved/spline copper; no chord or filament replacement was made".into());
    }
    if !routing.io_traces.is_empty() || !routing.io_pads.is_empty() {
        return Err("Finite DC coupling has not qualified IO fan-out/pad shapes; declare a supported physical return separately".into());
    }
    if !hints.layer_z_m.is_empty() && hints.layer_z_m.len() != sim.num_layers as usize {
        return Err("Explicit copper depth count differs from the layer count; no depths were filled in".into());
    }
    let rho = rho_cu_at(drive.winding_temp_c);
    if [drive.outer_copper_oz, drive.inner_copper_oz, drive.via_plating_m, rho].iter().any(|value| !value.is_finite() || *value <= 0.)
        || !drive.winding_temp_c.is_finite() {
        return Err("Finite DC requires explicit finite copper weights, plating and resistivity settings".into());
    }
    if drive.via_plating_m > sim.min_via_annular_ring_m {
        return Err("Via plating extends outside its physical annular pad".into());
    }
    let valid_layer = |layer: u32| layer < sim.num_layers && hints.layer_z(sim, layer).is_finite();
    if routing.segments.iter().any(|segment| !valid_layer(segment.layer)
        || ![segment.start.x, segment.start.y, segment.end.x, segment.end.y].iter().all(|value| value.is_finite())
        || segment.start == segment.end)
        || routing.vias.iter().any(|via| !valid_layer(via.from_layer) || !valid_layer(via.to_layer)
            || via.from_layer == via.to_layer || ![via.position.x, via.position.y].iter().all(|value| value.is_finite())) {
        return Err("Invalid or zero-length actual copper geometry; no repair was applied".into());
    }
    let layers: Vec<_> = (0..sim.num_layers).map(|layer| {
        let inner = sim.num_layers > 2 && layer != 0 && layer + 1 != sim.num_layers;
        let weight = if inner { drive.inner_copper_oz } else { drive.outer_copper_oz };
        json!({"layer":layer,"centre_z_m":hints.layer_z(sim,layer),
            "thickness_m":crate::units::oz_to_m(weight),"trace_width_m":sim.min_trace_m})
    }).collect();
    let phase_networks = extract_phase_networks_with_terminals(routing, &hints.terminals);
    if phase_networks.is_empty() { return Err("No physical winding networks were supplied".into()); }
    let mut networks = Vec::new();
    for network in phase_networks {
        if network.node_count > 2048 {
            return Err("Finite DC graph preparation exceeds the declared 2048-node-per-net resource cap".into());
        }
        let resistance: Vec<_> = network.edges.iter().map(|edge| match &edge.kind {
            EdgeKind::Trace {layer, length_m, ..} => {
                let inner = sim.num_layers > 2 && *layer != 0 && *layer + 1 != sim.num_layers;
                let weight = if inner {drive.inner_copper_oz} else {drive.outer_copper_oz};
                rho * length_m / (sim.min_trace_m * crate::units::oz_to_m(weight))
            }
            EdgeKind::Via {layers, ..} => via_resistance_ohm(sim.min_via_drill_m, drive.via_plating_m,
                hints.via_length_m(sim, *layers), rho),
        }).collect();
        let solution = solve_network(&network, &resistance);
        if !solution.connected || !solution.resistance_ohm.is_finite() || solution.resistance_ohm <= 0.
            || solution.current_share.iter().any(|value| !value.is_finite()) {
            return Err(format!("Winding {} is disconnected, shorted or electrically invalid; no finite-current source was emitted", network.net));
        }
        networks.push(json!({"net":network.net,"node_count":network.node_count,
            "terminal":network.terminal,"star":network.star,
            "edges":network.edges.iter().zip(&resistance).map(|(edge,r)| {
                let geometry = match &edge.kind {
                    EdgeKind::Trace {layer,points,..} => json!({"kind":"trace","layer":layer,"points_m":points}),
                    EdgeKind::Via {layers,position_m} => json!({"kind":"via","layers":layers,"position_m":position_m}),
                };
                json!({"a":edge.a,"b":edge.b,"r_ohm":r,"geometry":geometry})
            }).collect::<Vec<_>>(),"rust_current_share":solution.current_share,
            "rust_resistance_ohm":solution.resistance_ohm}));
    }
    networks.sort_by(|a,b| a["net"].as_str().cmp(&b["net"].as_str()));
    Ok(json!({"schema":"finite-dc-winding-geometry-v1","sim":sim,"routing":routing,
        "drive":drive,"geometry_hints":{"layer_z_m":hints.layer_z_m,"terminals":hints.terminals},
        "networks":networks,"finite_copper":{"layers":layers,"via_drill_m":sim.min_via_drill_m,
            "via_annular_ring_m":sim.min_via_annular_ring_m,"via_plating_m":drive.via_plating_m,
            "resistivity_ohm_m":rho,"temperature_c":drive.winding_temp_c},
        "coordinate_convention":"PCB top z=0; generated layers at negative depth; imported depths unchanged",
        "scope":"Actual geometry preparation only. No automatic return, material placement, finite-current or coupled force qualification."}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::{Point, RouteSegment, Via};

    fn routed() -> RoutingResult {
        let mut value = RoutingResult::default();
        value.segments.push(RouteSegment {start:Point::new(0.,0.),end:Point::new(10.,0.),
            layer:0,net:"A".into(),is_active:true});
        value.segments.push(RouteSegment {start:Point::new(10.,0.),end:Point::new(0.,1.),
            layer:1,net:"A".into(),is_active:true});
        value.vias.push(Via {position:Point::new(10.,0.),from_layer:0,to_layer:1,net:"A".into()});
        value
    }

    #[test]
    fn imported_depths_finite_copper_and_return_absence_are_preserved() {
        let sim = SimulationInput {num_layers:2, ..Default::default()};
        let hints = DriveGeometryHints {layer_z_m:vec![-0.00002,-0.00073], ..Default::default()};
        let drive = DriveSettings {outer_copper_oz:2., winding_temp_c:75., ..Default::default()};
        let route = routed();
        let before = serde_json::to_value(&route).unwrap();
        let result = snapshot(&sim,&route,&drive,&hints).unwrap();
        assert_eq!(result["routing"],before);
        assert_eq!(result["finite_copper"]["layers"][1]["centre_z_m"],-0.00073);
        assert_eq!(result["finite_copper"]["layers"][0]["thickness_m"],70e-6);
        assert!(result.get("return_path_m").is_none());
        assert!(result.get("force_n").is_none());
        assert_eq!(hints.layer_z_m,vec![-0.00002,-0.00073]);
    }

    #[test]
    fn generated_depths_are_resolved_without_flattening() {
        let sim = SimulationInput {num_layers:2,pcb_thickness_m:0.0008, ..Default::default()};
        let value = snapshot(&sim,&routed(),&DriveSettings::default(),&DriveGeometryHints::default()).unwrap();
        assert_eq!(value["finite_copper"]["layers"][0]["centre_z_m"],0.);
        assert_eq!(value["finite_copper"]["layers"][1]["centre_z_m"],-0.0008);
    }

    #[test]
    fn partial_depths_bad_copper_empty_and_out_of_range_geometry_are_rejected() {
        let sim = SimulationInput {num_layers:2, ..Default::default()};
        assert!(snapshot(&sim,&routed(),&DriveSettings::default(),
            &DriveGeometryHints {layer_z_m:vec![0.], ..Default::default()}).is_err());
        assert!(snapshot(&sim,&routed(),&DriveSettings {via_plating_m:f64::NAN, ..Default::default()},
            &DriveGeometryHints::default()).is_err());
        assert!(snapshot(&sim,&RoutingResult::default(),&DriveSettings::default(),&DriveGeometryHints::default()).is_err());
        let mut route = routed();route.segments[0].layer=2;
        assert!(snapshot(&sim,&route,&DriveSettings::default(),&DriveGeometryHints::default()).is_err());
    }

    #[test]
    fn curved_geometry_is_explicitly_rejected_not_chord_substituted() {
        let mut route = routed();
        route.curves.push(pcbmotorgen_routing::RouteCurve {start:Point::new(0.,0.),
            mid:Point::new(1.,1.),end:Point::new(2.,0.),layer:0,net:"A".into(),is_active:true});
        let error = snapshot(&SimulationInput::default(),&route,&DriveSettings::default(),
            &DriveGeometryHints::default()).unwrap_err();
        assert!(error.contains("no chord or filament replacement"));
    }
}
