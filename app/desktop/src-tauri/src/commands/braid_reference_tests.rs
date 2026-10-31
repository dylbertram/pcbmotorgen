use pcbmotorgen_routing::RoutingResult;
use std::collections::BTreeMap;

// These are explicit, test-only repairs of known reference-file defects.
// Neither the importer nor the user's files are changed or silently repaired.
fn intended_reference(raw: &RoutingResult, layers: u32) -> RoutingResult {
    use pcbmotorgen_routing::{Point, RouteSegment, Via};
    let mut r = raw.clone();
    let mut relabeled = 0;
    for v in &mut r.vias {
        if v.net != "0" { continue; }
        let nets: std::collections::BTreeSet<_> = r.segments.iter().filter(|s|
            s.start.distance_to(v.position) < 1e-5 || s.end.distance_to(v.position) < 1e-5)
            .map(|s| s.net.clone()).collect();
        assert_eq!(nets.len(), 1, "reference series barrel must have one unambiguous phase");
        v.net = nets.into_iter().next().unwrap();
        relabeled += 1;
    }
    assert_eq!(relabeled, 3 * (layers / 2 - 1));
    // C's first two outgoing leads start 0.054348 mm above their winding.
    for stage in 0..(layers / 2 - 1).min(2) {
        let layer = layers - 2 - 2 * stage;
        let start = Point::new(8.0 + 1.0 / 3.0 + 6.0 * stage as f64, 8.0);
        let end = r.segments.iter().filter(|s| s.layer == layer && s.net == "C")
            .flat_map(|s| [s.start, s.end]).find(|p|
                (p.x - start.x).abs() < 1e-5 && (p.y - 8.054348077171092).abs() < 1e-5).unwrap();
        r.segments.push(RouteSegment { start, end, layer, net: "C".into(), is_active: false });
    }
    // The 6/8-layer files have one extra first-period cut on pair 0/1.
    // In the 8-layer file that pair is on layers 2/3, not layers 0/1.
    if layers >= 6 {
        let layer = layers - 6;
        for (i, net) in ["A", "B", "C"].into_iter().enumerate() {
            let position = Point::new(4.0 + 1.0 / 3.0 + 2.0 * i as f64, 8.0);
            assert!(!r.vias.iter().any(|v| v.from_layer.min(v.to_layer) == layer
                && v.position.distance_to(position) < 1e-5));
            r.vias.push(Via { position, from_layer: layer, to_layer: layer + 1, net: net.into() });
        }
    }
    r
}

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
        // A lead ending at 7.999999999999996 clips to a sub-roundoff point,
        // not another piece of active copper.
        if a == b { continue; }
        if a > b { std::mem::swap(&mut a, &mut b); }
        *result.entry((s.net.clone(), [a[0], a[1], b[0], b[1]])).or_default() += 1;
    }
    result
}

#[test]
#[ignore = "Reads supplied 2/4/6/8-layer DXFs and saved projects without modifying them"]
fn supplied_even_layer_copper_matches_generated_active_stack() {
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
    for layers in [2, 4, 6, 8] {
        let name = format!("star-wye_{layers}-layer.dxf");
        let bytes = std::fs::read(root.join(&name)).unwrap();
        let imported = pcbmotorgen_export::cad_dxf::import_3d_dxf(
            std::str::from_utf8(&bytes).unwrap(),
            pcbmotorgen_export::cad_dxf::CadImportOptions {
                units_to_mm: 1.0, z_tolerance_mm: 1e-6, default_trace_width_mm: 0.127,
                legacy_layer_count: layers, legacy_pcb_thickness_mm: 1.6, prefer_detected_units: false,
            },
        ).unwrap();
        assert!(imported.warnings.iter().all(|w| w.starts_with("DXF layer name suggested copper index")
            || w.contains("must connect matching trace endpoints")), "{name}: {:?}", imported.warnings);
        assert_eq!(imported.geometry.layer_z_mm.len(), layers as usize);
        let raw = &imported.geometry.routing;
        if layers > 2 {
            assert!(pcbmotorgen_simulation::drive::extract_phase_networks(raw).iter().all(|n|
                !pcbmotorgen_simulation::drive::solve_network(n, &vec![1.0; n.edges.len()]).connected),
                "the raw reference's known defects must not be represented as validated copper");
        }
        let corrected = intended_reference(raw, layers);
        let dxf = &corrected;
        state.num_layers = layers;
        let ipc = state.to_linear_motor_ipc();
        let core = ipc.to_core();
        let routing = pcbmotorgen_routing::generate_routing_result(&core.routing_context(), "infinity-braid").unwrap();
        if layers > 2 {
            let warnings = tauri::async_runtime::block_on(super::routing_plugins::check_coil_interference(ipc.clone(), None)).unwrap();
            assert!(warnings.iter().any(|w| w.kind == "series_via_clearance" && (w.gap_mm - 0.0944444444).abs() < 1e-8));
            assert!(warnings.iter().any(|w| w.kind == "series_via_pad_clearance" && (w.gap_mm - 0.0555555556).abs() < 1e-8));
        }
        let preview = tauri::async_runtime::block_on(super::physics::generate_coils(ipc)).unwrap();
        assert_eq!(preview.layer_count, layers);
        assert_eq!(preview.phases.len(), (layers * 3) as usize);
        for layer in 0..layers {
            assert_eq!(preview.phases.iter().filter(|p| p.layer_idx == layer).count(), 3);
            assert_eq!(active_xy(&routing, layer), active_xy(&reference, layer % 2), "active copper on layer {layer} must match the saved reference");
            let generated_xy = active_xy(&routing, layer);
            let reference_xy = active_xy(dxf, layer);
            let extra: Vec<_> = generated_xy.iter().filter(|(k, v)| reference_xy.get(*k) != Some(v)).collect();
            let missing: Vec<_> = reference_xy.iter().filter(|(k, v)| generated_xy.get(*k) != Some(v)).collect();
            assert!(extra.is_empty() && missing.is_empty(), "{name} layer {layer}: generated-only {extra:?}; reference-only {missing:?}");
        }
        let spans = |r: &RoutingResult| {
            let mut counts = BTreeMap::new();
            for v in &r.vias { *counts.entry((v.from_layer.min(v.to_layer), v.from_layer.max(v.to_layer))).or_insert(0usize) += 1; }
            counts
        };
        assert_eq!(spans(&routing), spans(dxf), "via barrel spans must match {name}");
        let body_vias = |r: &RoutingResult| {
            let mut keys: Vec<_> = r.vias.iter().filter(|v| v.position.y <= 8.0 + 1e-6).map(|v| (
                v.net.clone(), v.from_layer.min(v.to_layer), v.from_layer.max(v.to_layer),
                (v.position.x * 1e5).round() as i64, (v.position.y * 1e5).round() as i64,
            )).collect();
            keys.sort(); keys
        };
        assert_eq!(body_vias(&routing), body_vias(dxf), "exact winding openings and restored vias must match {name}");
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
                for boundary in (1..layers - 1).step_by(2) {
                    let joins: Vec<_> = n.edges.iter().zip(&solution.current_share).filter(|(e, _)|
                        matches!(e.kind, pcbmotorgen_simulation::drive::EdgeKind::Via { layers: [a, b], .. } if a == boundary && b == boundary + 1)).collect();
                    assert_eq!(joins.len(), 1);
                    assert!((joins[0].1.abs() - 1.0).abs() < 1e-8);
                }
            }
            for via in r.vias.iter().filter(|v| v.from_layer.abs_diff(v.to_layer) == layers - 1 && layers > 2) {
                let mut cut = r.clone();
                cut.vias.retain(|v| v.position != via.position || v.net != via.net);
                for n in pcbmotorgen_simulation::drive::extract_phase_networks(&cut) {
                    if n.net == via.net {
                        assert!(!pcbmotorgen_simulation::drive::solve_network(&n, &vec![1.0; n.edges.len()]).connected);
                    }
                }
            }
        }
        dxf_sources.push((name, bytes));
        generated.push((layers, routing));
        if let Ok(output) = std::env::var("PCB_MOTOR_BRAID_OUTPUT") {
            let output = std::path::PathBuf::from(output);
            std::fs::create_dir_all(&output).unwrap();
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
                .open(output.join(format!("reference-{layers}-layer.json"))).unwrap();
            serde_json::to_writer(&mut file, raw).unwrap();
            let mut preview_file = std::fs::OpenOptions::new().write(true).create_new(true)
                .open(output.join(format!("generated-{layers}-preview.json"))).unwrap();
            serde_json::to_writer(&mut preview_file, &preview).unwrap();
            // Also exercise the application's usual five-strand setting through
            // the real command, not a hand-written frontend braid fixture.
            let mut five_strand_ipc = state.to_linear_motor_ipc();
            five_strand_ipc.routing_params.insert("num_strands".into(), 5.0);
            let five_strand_preview = tauri::async_runtime::block_on(super::physics::generate_coils(five_strand_ipc)).unwrap();
            let mut five_file = std::fs::OpenOptions::new().write(true).create_new(true)
                .open(output.join(format!("generated-{layers}-five-strand-preview.json"))).unwrap();
            serde_json::to_writer(&mut five_file, &five_strand_preview).unwrap();
        }
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
        for layers in [2, 4, 6, 8] {
            let mut project = two.clone();
            project["versions"] = serde_json::json!([two["versions"][0].clone()]);
            project["versions"][0]["state"]["config"]["num_layers"] = layers.into();
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
                .open(output.join(format!("generated-{layers}-layer.pmmotor"))).unwrap();
            serde_json::to_writer(&mut file, &project).unwrap();
        }
    }
}
