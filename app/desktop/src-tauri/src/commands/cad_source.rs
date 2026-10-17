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
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn mapped_import_drives_board_and_electrical_inputs_without_regeneration() {
        let core = LinearMotorConfig { phases:1, routing_pattern:"missing-plugin".into(), ..Default::default() };
        let cad = mapped();
        let board = CadBoard::new(&cad, &core).unwrap();
        assert_eq!(board.routing.segments.len(), 2);
        assert_eq!(board.routing.segments[0].net, "A");
        assert!(!board.routing.segments[1].is_active);
        assert_eq!(board.rules.min_trace_mm, 0.127);
        assert_eq!(board.rules.trace_width_mm, 0.2);
        let sim = board.simulation_input(&cad, &core);
        assert_eq!(sim.min_trace_m, 0.0002);
        assert_eq!(sim.num_layers, 2);
        let analysis = pcbmotorgen_simulation::drive::analyze_drive_with(
            &sim, &board.routing, &Default::default(), None, &CadBoard::drive_hints(&cad));
        assert!(analysis.phases[0].connected);
        assert!(analysis.phase_resistance_ohm > 0.0);
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

    /// Imported layer heights and picked terminals for the drive analysis.
    pub fn drive_hints(cad: &CadGeometry) -> pcbmotorgen_simulation::drive::DriveGeometryHints {
        use pcbmotorgen_simulation::drive::{TerminalPair, TerminalPoint};
        let point = |t: &pcbmotorgen_export::cad_dxf::CadTerminal| TerminalPoint {
            layer: t.layer,
            position: t.position,
        };
        pcbmotorgen_simulation::drive::DriveGeometryHints {
            layer_z_m: cad.layer_z_mm.iter().map(|z| z * 1e-3).collect(),
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
