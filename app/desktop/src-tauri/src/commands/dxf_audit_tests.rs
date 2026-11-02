//! Opt-in import receipt for the user's actual DXF, never regenerated copper.
use pcbmotorgen_export::cad_dxf::{import_3d_dxf, CadCoilTerminals, CadImportOptions, CadTerminal, TerminalConnection};
use std::collections::{BTreeMap, BTreeSet};

#[test]
#[ignore = "Requires PCB_MOTOR_DXF_PATH and PCB_MOTOR_DXF_PROJECT_OUTPUT; exports actual imported geometry"]
fn export_actual_dxf_audit_project() {
    let source = std::env::var("PCB_MOTOR_DXF_PATH").unwrap();
    let output = std::env::var("PCB_MOTOR_DXF_PROJECT_OUTPUT").unwrap();
    // Width is an explicit audit assumption: LINE centerlines do not specify it.
    let width: f64 = std::env::var("PCB_MOTOR_DXF_TRACE_WIDTH_MM").unwrap().parse().unwrap();
    let imported = import_3d_dxf(&std::fs::read_to_string(&source).unwrap(), CadImportOptions {
        units_to_mm: 1.0, z_tolerance_mm: 1e-5, default_trace_width_mm: width,
        legacy_layer_count: 2, legacy_pcb_thickness_mm: 1.6, prefer_detected_units: true,
    }).unwrap();
    assert!(imported.warnings.iter().all(|w| w.starts_with("DXF layer name suggested copper index ") && w.ends_with("used Z.")),
        "Only physical-Z/name-index notices are allowed, never skipped copper: {:?}", imported.warnings);
    eprintln!("Import notices: {:?}", imported.warnings);
    let mut cad = imported.geometry;
    assert_eq!(cad.layer_z_mm, [-1.6, 0.0]);
    assert_eq!(cad.trace_width_mm, width, "Do not override embedded physical copper width");
    assert_eq!(cad.coil_names(), ["A", "B", "C"]);
    // Find the physical common neutral, independently of left/right terminal
    // inference. All three nets have an endpoint at the same bottom-plane node.
    let key = |layer: u32, p: pcbmotorgen_routing::Point| (layer, (p.x * 1000.0).round() as i64, (p.y * 1000.0).round() as i64);
    let mut nodes: BTreeMap<_, BTreeSet<String>> = BTreeMap::new();
    for s in &cad.routing.segments {
        for p in [s.start, s.end] { nodes.entry(key(s.layer, p)).or_default().insert(s.net.clone()); }
    }
    let shared: Vec<_> = nodes.iter().filter(|(_, nets)| nets.len() == 3).map(|(node, _)| *node).collect();
    assert_eq!(shared.len(), 1, "Expected one physical star neutral, got {shared:?}");
    let neutral = shared[0];
    for net in ["A", "B", "C"] {
        let endpoints: Vec<_> = cad.routing.segments.iter().filter(|s| s.net == net)
            .flat_map(|s| [CadTerminal { layer: s.layer, position: s.start }, CadTerminal { layer: s.layer, position: s.end }]).collect();
        let input = endpoints.iter().min_by(|a,b| a.position.x.total_cmp(&b.position.x)).unwrap().clone();
        assert!(input.position.x.abs() < 1e-5 && input.layer == 1, "Driver must be the actual left-hand top-plane lead");
        let output = endpoints.iter().find(|p| key(p.layer, p.position) == neutral).unwrap().clone();
        cad.coil_terminals.insert(net.into(), CadCoilTerminals { input, output });
    }
    cad.terminal_connection = Some(TerminalConnection::Star);
    cad.source_file_name = Some(std::path::Path::new(&source).file_name().unwrap().to_string_lossy().into());
    let reference: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(
        std::env::var("PCB_MOTOR_DXF_CONFIG_REFERENCE").unwrap()).unwrap()).unwrap();
    let mut state: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(reference["versions"][0]["state"]["config"].clone()).unwrap();
    state.num_layers = 2;
    state.pcb_thickness_mm = 1.6;
    state.pcb_stackup_mm = None;
    state.trace_width_mm = Some(width);
    state.min_trace_mm = width.min(0.127);
    state.active_area_width_mm = 8.0;
    state.desired_travel_mm = 89.333333 - 29.0;
    state.routing_orientation = Default::default();
    state.routing_params.insert("pole_matched".into(), 1.0); // Identical balanced terminal command for both imports.
    let core = state.to_linear_motor_ipc().to_core();
    let board = super::super::cad_source::CadBoard::new(&cad, &core).unwrap();
    assert_eq!(board.layer_z_m, [-0.0016, 0.0]);
    let inferred = pcbmotorgen_simulation::drive::extract_phase_networks(&board.routing);
    let explicit = pcbmotorgen_simulation::drive::extract_phase_networks_with_terminals(&board.routing, &board.drive_hints(&cad).terminals);
    for (a,b) in inferred.iter().zip(&explicit) {
        assert_eq!(a.terminal, b.terminal, "Driver inference differs for {}", a.net);
        assert_eq!(a.star, b.star, "Neutral inference differs for {}", a.net);
    }
    eprintln!("{}: {} traces, {} vias, physical Z {:?}, picked terminals {:?}", source, cad.routing.segments.len(), cad.routing.vias.len(), cad.layer_z_mm, cad.coil_terminals);
    let project = serde_json::json!({"versions":[{"id":1,"state":{"config":state,"cad_geometry":cad}}]});
    let mut file = std::fs::OpenOptions::new().create_new(true).write(true).open(output).unwrap();
    std::io::Write::write_all(&mut file, &serde_json::to_vec_pretty(&project).unwrap()).unwrap();
}
