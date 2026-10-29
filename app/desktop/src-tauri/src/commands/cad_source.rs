//! Imported CAD geometry as the copper source for KiCad export, DRC, and the
//! Simulation tab. Every consumer goes through [`CadBoard`] so they all see
//! the same phase-mapped routing.

use crate::config::LinearMotorConfig;
use pcbmotorgen_export::cad_dxf::CadGeometry;
use pcbmotorgen_routing::{PhaseCoil, RoutingResult};

/// Pattern id recorded on coils built from imported geometry.
pub const CAD_PATTERN_ID: &str = "cad-import";

/// Imported copper prepared for the board writers and the physics.
pub struct CadBoard {
    /// Routing with coil nets renamed to their phases.
    pub routing: RoutingResult,
    pub coils: Vec<PhaseCoil>,
    pub num_layers: u32,
    pub rules: pcbmotorgen_dfm::DesignRules,
    /// Length the writer centres on: x is shifted by half of it. Matches the
    /// configured active area when the copper lies inside it, so imported
    /// and generated copper land in the same place.
    pub placement_length_mm: f64,
    /// Copper extent across the travel axis [mm].
    pub width_mm: f64,
    /// Source Z ratios placed within the configured PCB, top copper at zero.
    pub layer_z_m: Vec<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_current_and_power_balance(board: &CadBoard, cad: &CadGeometry) {
        use pcbmotorgen_simulation::drive::{extract_phase_networks_with_terminals, solve_network};
        for net in extract_phase_networks_with_terminals(&board.routing, &board.drive_hints(cad).terminals) {
            // Unequal values exercise signed branching, not only a symmetric path.
            let resistance: Vec<_> = (0..net.edges.len()).map(|i| 0.5 + 0.1 * (i % 7) as f64).collect();
            let solved = solve_network(&net, &resistance);
            assert!(solved.connected, "{}", net.net);
            let mut balance = vec![0.0; net.node_count];
            for (edge, current) in net.edges.iter().zip(&solved.current_share) {
                balance[edge.a] += current;
                balance[edge.b] -= current;
            }
            for node in 0..net.node_count {
                if !net.terminal.contains(&node) && !net.star.contains(&node) {
                    assert!(balance[node].abs() < 1e-8, "{} KCL at {node}: {}", net.net, balance[node]);
                }
            }
            let injected: f64 = net.terminal.iter().map(|&node| balance[node]).sum();
            let returned: f64 = net.star.iter().map(|&node| -balance[node]).sum();
            assert!((injected - 1.0).abs() < 1e-8);
            assert!((returned - injected).abs() < 1e-8);
            let power: f64 = solved.current_share.iter().zip(resistance).map(|(i,r)| i*i*r).sum();
            assert!((power - solved.resistance_ohm).abs() < 1e-8 * power.max(1.0), "{} power mismatch", net.net);
        }
    }

    fn mapped() -> CadGeometry {
        serde_json::from_value(serde_json::json!({
            "trace_width_mm":0.2, "layer_z_mm":[-1.6,0.0],
            "routing":{"format_version":2,"segments":[
                {"start":{"x":0.0,"y":0.0},"end":{"x":1.0,"y":0.0},"layer":0,"net":"coil","is_active":true},
                {"start":{"x":1.0,"y":0.0},"end":{"x":2.0,"y":0.0},"layer":1,"net":"coil","is_active":false}
            ],"curves":[],"vias":[{"position":{"x":1.0,"y":0.0},"from_layer":0,"to_layer":1,"net":"coil"}]},
            "coil_phases":{"coil":"A"},
            "coil_terminals":{"coil":{
                "input":{"position":{"x":0.0,"y":0.0},"layer":0},
                "output":{"position":{"x":2.0,"y":0.0},"layer":1}
            }}
        })).unwrap()
    }

    #[test]
    fn imported_z_ratios_use_configured_pcb_thickness_without_editing_source() {
        let core = LinearMotorConfig { phases: 1, pcb_thickness_m: 0.0016, ..Default::default() };
        let mut cad = mapped();
        for (raw, expected) in [
            (vec![-4.8, -3.2, -1.6, 0.0], vec![-0.0016, -0.0010666666666666667, -0.0005333333333333334, 0.0]),
            (vec![8.0, 7.0, 4.0], vec![0.0, -0.0004, -0.0016]),
            (vec![2.0], vec![0.0]),
        ] {
            cad.layer_z_mm = raw;
            if cad.layer_z_mm.len() == 1 {
                cad.routing.segments[1].layer = 0;
                cad.routing.vias.clear();
                cad.coil_terminals.get_mut("coil").unwrap().output.layer = 0;
            }
            let original = serde_json::to_value(&cad).unwrap();
            let board = CadBoard::new(&cad, &core).unwrap();
            for (a, b) in board.drive_hints(&cad).layer_z_m.iter().zip(expected) {
                assert!((a - b).abs() < 1e-15);
            }
            assert_eq!(serde_json::to_value(&cad).unwrap(), original);
            let thick = LinearMotorConfig { pcb_thickness_m: 0.0032, ..core.clone() };
            let other = CadBoard::new(&cad, &thick).unwrap();
            for (a, b) in board.layer_z_m.iter().zip(other.layer_z_m) { assert!((2.0 * a - b).abs() < 1e-15); }
        }
    }

    #[test]
    fn mapped_import_drives_board_and_electrical_inputs_without_regeneration() {
        let core = LinearMotorConfig { phases:1, routing_pattern:"missing-plugin".into(), ..Default::default() };
        let cad = mapped();
        let board = CadBoard::new(&cad, &core).unwrap();
        assert_current_and_power_balance(&board, &cad);
        assert_eq!(board.routing.segments.len(), 2);
        assert_eq!(board.routing.segments[0].net, "A");
        assert!(!board.routing.segments[1].is_active);
        assert_eq!(board.rules.min_trace_mm, 0.127);
        assert_eq!(board.rules.trace_width_mm, 0.2);
        let sim = board.simulation_input(&cad, &core);
        assert_eq!(sim.min_trace_m, 0.0002);
        assert_eq!(sim.num_layers, 2);
        let analysis = pcbmotorgen_simulation::drive::analyze_drive_with(
            &sim, &board.routing, &Default::default(), None, &board.drive_hints(&cad));
        assert!(analysis.phases[0].connected);
        assert!(analysis.phase_resistance_ohm > 0.0);
    }

    #[test]
    fn through_hole_barrel_with_only_inner_landings_drives_the_imported_coil() {
        let core = LinearMotorConfig { phases:1, num_layers:4, ..Default::default() };
        let mut cad = mapped();
        cad.layer_z_mm = vec![-0.8, -0.5, -0.3, 0.0];
        cad.routing.segments[0].layer = 1;
        cad.routing.segments[1].layer = 2;
        cad.routing.vias[0].to_layer = 3;
        let terminals = cad.coil_terminals.get_mut("coil").unwrap();
        terminals.input.layer = 1;
        terminals.output.layer = 2;
        let board = CadBoard::new(&cad, &core).unwrap();
        assert_current_and_power_balance(&board, &cad);
        let sim = board.simulation_input(&cad, &core);
        let analysis = pcbmotorgen_simulation::drive::analyze_drive_with(
            &sim, &board.routing, &Default::default(), None, &board.drive_hints(&cad));
        assert!(analysis.phases[0].connected);
        assert_eq!(analysis.phases[0].layers, vec![1, 2]);
        assert!(analysis.phase_resistance_ohm.is_finite() && analysis.phase_resistance_ohm > 0.0);
    }

    /// Run against an untracked user project without making it a test fixture:
    /// PCB_MOTOR_PROJECT_PATH=/absolute/path.pmmotor cargo test -p pcbmotorgen
    /// imported_user_project_connectivity -- --ignored --nocapture
    #[test]
    #[ignore = "Requires PCB_MOTOR_PROJECT_PATH pointing to a user project"]
    fn imported_user_project_connectivity() {
        let path = std::env::var("PCB_MOTOR_PROJECT_PATH").expect("set PCB_MOTOR_PROJECT_PATH");
        let project: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        let mut checked = 0;
        for version in project["versions"].as_array().unwrap() {
            let state = &version["state"];
            if state["cad_geometry"].is_null() { continue; }
            let config: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(state["config"].clone()).unwrap();
            let cad: CadGeometry = serde_json::from_value(state["cad_geometry"].clone()).unwrap();
            let core = config.to_linear_motor_ipc().to_core();
            let board = CadBoard::new(&cad, &core).unwrap();
            assert_current_and_power_balance(&board, &cad);
            let sim = board.simulation_input(&cad, &core);
            let analysis = pcbmotorgen_simulation::drive::analyze_drive_with(
                &sim, &board.routing, &config.drive, None, &board.drive_hints(&cad));
            assert_eq!(analysis.phases.len(), core.phases as usize);
            assert!(analysis.phases.iter().all(|phase| phase.connected));
            assert!(analysis.phase_resistance_ohm.is_finite() && analysis.phase_resistance_ohm > 0.0);
            let sweep = tauri::async_runtime::block_on(crate::commands::physics::evaluate_force_sweep(
                config.to_linear_motor_ipc(), Some(cad.clone()), Some(config.drive.clone()))).unwrap();
            assert!(!sweep.force_x_n.is_empty() && sweep.force_x_n.iter().all(|force| force.is_finite()));
            eprintln!("Imported version {}: {} segments, {} vias, {} connected phases, mean thrust {} N", version["id"], cad.routing.segments.len(), cad.routing.vias.len(), analysis.phases.len(), sweep.mean_thrust_n);
            checked += 1;
        }
        assert!(checked > 0, "project has no imported geometry");
    }

    #[test]
    fn incomplete_mapping_and_disconnected_islands_are_rejected() {
        let core = LinearMotorConfig { phases:1, ..Default::default() };
        let mut cad = mapped();
        let terminals = std::mem::take(&mut cad.coil_terminals);
        assert!(CadBoard::new(&cad, &core).err().unwrap().contains("Select driver"));
        cad.coil_terminals = terminals;
        let mut island = cad.routing.segments[0].clone();
        island.start.x += 100.0;
        island.end.x += 100.0;
        cad.routing.segments.push(island);
        assert!(CadBoard::new(&cad, &core).err().unwrap().contains("disconnected copper"));
    }
}

impl CadBoard {
    pub fn validate(cad: &CadGeometry, core: &LinearMotorConfig) -> Result<(), String> {
        cad.validate_motor_mapping(core.phases, core.design_rules().min_trace_mm)?;
        if !core.pcb_thickness_m.is_finite() || core.pcb_thickness_m <= 0.0 {
            return Err("Configured PCB thickness must be finite and positive".into());
        }
        if cad.layer_z_mm.len() > 1 {
            let low = cad.layer_z_mm.iter().copied().fold(f64::INFINITY, f64::min);
            let high = cad.layer_z_mm.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            if !((high - low).is_finite() && high > low) {
                return Err("Imported copper needs distinct finite layer heights for proportional PCB placement".into());
            }
        }
        // Validate each coil before phase mapping can join separate coils to
        // virtual buses. This is a topology check, not a resistance estimate.
        for network in pcbmotorgen_simulation::drive::extract_phase_networks(&cad.routing) {
            let mut neighbors = vec![Vec::new(); network.node_count];
            for edge in &network.edges {
                neighbors[edge.a].push(edge.b);
                neighbors[edge.b].push(edge.a);
            }
            let mut visited = vec![false; network.node_count];
            let mut pending = vec![0];
            while let Some(node) = pending.pop() {
                if visited[node] { continue; }
                visited[node] = true;
                pending.extend(neighbors[node].iter().copied());
            }
            if visited.iter().any(|seen| !seen) {
                return Err(format!("Coil '{}' contains disconnected copper; review trace endpoints and via connections", network.net));
            }
        }
        Ok(())
    }

    pub fn new(cad: &CadGeometry, core: &LinearMotorConfig) -> Result<Self, String> {
        Self::validate(cad, core)?;
        let routing = cad.routing_by_phase()?;
        let coils = pcbmotorgen_routing::routing_result_to_phase_coils(&routing, CAD_PATTERN_ID);
        if coils.is_empty() {
            return Err("The imported geometry has no copper".into());
        }
        let (x, y) = cad.extent_mm().ok_or("The imported geometry has no copper")?;
        let configured = core.active_area_length_m * 1e3;
        let placement_length_mm = if x[0] >= -1e-6 && x[1] <= configured + 1e-6 {
            configured
        } else {
            x[0] + x[1]
        };
        let mut rules = core.design_rules();
        // The imported DXF width is the actual copper width; the config's
        // minimum trace width stays the DRC floor.
        rules.trace_width_mm = cad.trace_width_mm;
        Ok(Self {
            routing,
            coils,
            num_layers: cad.layer_z_mm.len() as u32,
            rules,
            placement_length_mm,
            width_mm: y[1] - y[0],
            layer_z_m: {
                let low = cad.layer_z_mm.iter().copied().fold(f64::INFINITY, f64::min);
                let high = cad.layer_z_mm.iter().copied().fold(f64::NEG_INFINITY, f64::max);
                cad.layer_z_mm.iter().map(|z| if high == low { 0.0 } else {
                    ((z - high) / (high - low)) * core.pcb_thickness_m
                }).collect()
            },
        })
    }

    /// Simulation inputs for this copper: the config's magnets and drive with
    /// the imported layer count and trace width.
    pub fn simulation_input(
        &self,
        cad: &CadGeometry,
        core: &LinearMotorConfig,
    ) -> pcbmotorgen_simulation::SimulationInput {
        let mut sim = core.to_simulation();
        sim.num_layers = self.num_layers;
        sim.min_trace_m = cad.trace_width_mm * 1e-3;
        sim.phase_bands = Vec::new();
        sim
    }

    /// Configured physical layer heights and original picked terminals.
    pub fn drive_hints(&self, cad: &CadGeometry) -> pcbmotorgen_simulation::drive::DriveGeometryHints {
        use pcbmotorgen_simulation::drive::{TerminalPair, TerminalPoint};
        let point = |t: &pcbmotorgen_export::cad_dxf::CadTerminal| TerminalPoint {
            layer: t.layer,
            position: t.position,
        };
        pcbmotorgen_simulation::drive::DriveGeometryHints {
            layer_z_m: self.layer_z_m.clone(),
            terminals: cad
                .terminals_by_phase()
                .into_iter()
                .map(|(phase, pairs)| {
                    (
                        phase,
                        pairs
                            .iter()
                            .map(|p| TerminalPair { input: point(&p.input), output: point(&p.output) })
                            .collect(),
                    )
                })
                .collect(),
        }
    }
}
