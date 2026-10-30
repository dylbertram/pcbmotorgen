use pcbmotorgen_routing::RoutingResult;
use std::collections::BTreeMap;

// Compare actual copper clipped to the active board width. The supplied CAD
// has extended/filleted leads and marks them active; those external leads are
// not a golden template for trace flags or for the generator's lead spacing.
fn active_xy(routing: &RoutingResult, layer: u32) -> BTreeMap<(String, [i64; 4]), usize> {
    let mut result = BTreeMap::new();
    for s in routing.segments.iter().filter(|s| s.layer == layer && s.is_active) {
        let dy = s.end.y - s.start.y;
        let (t0, t1) = if dy.abs() < 1e-12 {
            if s.start.y < 0.0 || s.start.y > 8.0 { continue; }
            (0.0, 1.0)
        } else {
            let a = -s.start.y / dy;
            let b = (8.0 - s.start.y) / dy;
            (a.min(b).max(0.0), a.max(b).min(1.0))
        };
        if t1 <= t0 { continue; }
        let point = |t: f64| [
            ((s.start.x + t * (s.end.x - s.start.x)) * 1e5).round() as i64,
            ((s.start.y + t * dy) * 1e5).round() as i64,
        ];
        let (mut a, mut b) = (point(t0), point(t1));
        if a > b { std::mem::swap(&mut a, &mut b); }
        *result.entry((s.net.clone(), [a[0], a[1], b[0], b[1]])).or_default() += 1;
    }
    result
}

#[test]
#[ignore = "Reads supplied star_2-layer and star_4-layer projects without modifying them"]
fn supplied_four_layer_copper_matches_generated_active_stack() {
    let root = std::path::PathBuf::from(std::env::var("PCB_MOTOR_SUPPLIED_DESIGN_DIR").unwrap());
    let two_bytes = std::fs::read(root.join("star_2-layer.pmmotor")).unwrap();
    let four_bytes = std::fs::read(root.join("star_4-layer.pmmotor")).unwrap();
    let two: serde_json::Value = serde_json::from_slice(&two_bytes).unwrap();
    let four: serde_json::Value = serde_json::from_slice(&four_bytes).unwrap();
    let mut state: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(two["versions"][0]["state"]["config"].clone()).unwrap();
    let reference: RoutingResult = serde_json::from_value(four["versions"][0]["state"]["cad_geometry"]["routing"].clone()).unwrap();
    // CAD is the reference: its config is stale (delta / five strands), while
    // the actual saved copper is a three-strand star series stack.
    assert_eq!(state.routing_params["num_strands"], 3.0);
    assert_eq!(state.routing_params["connection"], 2.0);
    let mut generated = Vec::new();
    let mut dxf_sources = Vec::new();
    for layers in [2, 4] {
        let name = format!("star-wye_{layers}-layer.dxf");
        let bytes = std::fs::read(root.join(&name)).unwrap();
        let imported = pcbmotorgen_export::cad_dxf::import_3d_dxf(
            std::str::from_utf8(&bytes).unwrap(),
            pcbmotorgen_export::cad_dxf::CadImportOptions {
                units_to_mm: 1.0, z_tolerance_mm: 1e-6, default_trace_width_mm: 0.127,
                legacy_layer_count: layers, legacy_pcb_thickness_mm: 1.6, prefer_detected_units: false,
            },
        ).unwrap();
        assert!(imported.warnings.is_empty(), "{name}: {:?}", imported.warnings);
        assert_eq!(imported.geometry.layer_z_mm.len(), layers as usize);
        let dxf = &imported.geometry.routing;
        state.num_layers = layers;
        let ipc = state.to_linear_motor_ipc();
        let core = ipc.to_core();
        let routing = pcbmotorgen_routing::generate_routing_result(&core.routing_context(), "infinity-braid").unwrap();
        let preview = tauri::async_runtime::block_on(super::physics::generate_coils(ipc)).unwrap();
        assert_eq!(preview.layer_count, layers);
        assert_eq!(preview.phases.len(), (layers * 3) as usize);
        for layer in 0..layers {
            assert_eq!(preview.phases.iter().filter(|p| p.layer_idx == layer).count(), 3);
            assert_eq!(active_xy(&routing, layer), active_xy(&reference, layer), "active copper on layer {layer} must match the saved reference");
            assert_eq!(active_xy(&routing, layer), active_xy(dxf, layer), "active copper on layer {layer} must match {name}");
        }
        let spans = |r: &RoutingResult| {
            let mut counts = BTreeMap::new();
            for v in &r.vias { *counts.entry((v.from_layer, v.to_layer)).or_insert(0usize) += 1; }
            counts
        };
        assert_eq!(spans(&routing), spans(dxf), "via barrel spans must match {name}");
        for r in [&routing, dxf] {
            let networks = pcbmotorgen_simulation::drive::extract_phase_networks(r);
            assert_eq!(networks.len(), 3);
            for n in &networks {
                let solution = pcbmotorgen_simulation::drive::solve_network(n, &vec![1.0; n.edges.len()]);
                assert!(solution.connected, "{name}: {}", n.net);
                assert_eq!(n.terminal.len(), 1);
                assert_eq!(n.star.len(), 1);
                let terminal_layers = |node| n.edges.iter().filter_map(|e| {
                    match e.kind {
                        pcbmotorgen_simulation::drive::EdgeKind::Trace { layer, .. }
                            if e.a == node || e.b == node => Some(layer),
                        _ => None,
                    }
                }).collect::<Vec<_>>();
                assert_eq!(terminal_layers(n.terminal[0]), vec![layers - 1], "line terminal is on the last layer");
                assert!(terminal_layers(n.star[0]).iter().all(|l| *l == 0), "neutral is on layer zero");
                if layers == 4 {
                    let joins: Vec<_> = n.edges.iter().zip(&solution.current_share).filter(|(e, _)|
                        matches!(e.kind, pcbmotorgen_simulation::drive::EdgeKind::Via { layers: [1, 2], .. })).collect();
                    assert_eq!(joins.len(), 1);
                    assert!((joins[0].1.abs() - 1.0).abs() < 1e-8);
                }
            }
            if layers == 4 {
                let mut cut = r.clone();
                cut.vias.retain(|v| (v.from_layer, v.to_layer) != (0, 3));
                for n in pcbmotorgen_simulation::drive::extract_phase_networks(&cut) {
                    assert!(!pcbmotorgen_simulation::drive::solve_network(&n, &vec![1.0; n.edges.len()]).connected);
                }
            }
        }
        dxf_sources.push((name, bytes));
        generated.push((layers, routing));
    }
    assert_eq!(std::fs::read(root.join("star_2-layer.pmmotor")).unwrap(), two_bytes);
    assert_eq!(std::fs::read(root.join("star_4-layer.pmmotor")).unwrap(), four_bytes);
    for (name, bytes) in dxf_sources { assert_eq!(std::fs::read(root.join(name)).unwrap(), bytes); }
    if let Ok(output) = std::env::var("PCB_MOTOR_BRAID_OUTPUT") {
        let output = std::path::PathBuf::from(output);
        std::fs::create_dir_all(&output).unwrap();
        for (layers, routing) in generated {
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
                .open(output.join(format!("generated-{layers}-layer.json"))).unwrap();
            serde_json::to_writer(&mut file, &routing).unwrap();
        }
        let mut project = two.clone();
        project["versions"] = serde_json::json!([two["versions"][0].clone()]);
        project["versions"][0]["state"]["config"]["num_layers"] = 4.into();
        let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
            .open(output.join("generated-four-layer.pmmotor")).unwrap();
        serde_json::to_writer(&mut file, &project).unwrap();
    }
}
