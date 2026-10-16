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

impl CadBoard {
    pub fn new(cad: &CadGeometry, core: &LinearMotorConfig) -> Result<Self, String> {
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
