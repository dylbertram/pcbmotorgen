//! Read-only checks against the revised compact 2/4/6-layer user drawings.
use pcbmotorgen_routing::{RoutingContext, RoutingResult};
use std::collections::BTreeMap;

fn copper(r: &RoutingResult) -> BTreeMap<(String, u32, [i64; 2], u32, [i64; 2]), usize> {
    let mut keys = BTreeMap::new();
    let point = |p: pcbmotorgen_routing::Point| [(p.x * 1e5).round() as i64, (p.y * 1e5).round() as i64];
    let mut edge = |net: &str, la, a, lb, b| {
        let (a, b) = if (la, a) < (lb, b) { ((la, a), (lb, b)) } else { ((lb, b), (la, a)) };
        *keys.entry((net.into(), a.0, a.1, b.0, b.1)).or_default() += 1;
    };
    for s in &r.segments { edge(&s.net, s.layer, point(s.start), s.layer, point(s.end)); }
    for v in &r.vias { edge(&v.net, v.from_layer, point(v.position), v.to_layer, point(v.position)); }
    keys
}

#[test]
fn compact_star_preview_frozen_copper_and_dxf_export_use_the_same_series_stack() {
    for layers in [2, 4, 6, 8, 10] {
        let mut state = crate::ipc::ProjectConfigStateIpc::default();
        state.num_layers = layers;
        state.desired_travel_mm = 63.0;
        state.active_area_width_mm = 8.0;
        state.routing_params.insert("num_strands".into(), 3.0);
        state.trace_width_mm = Some(0.2);
        let ipc = state.to_linear_motor_ipc();
        let core = ipc.to_core();
        let expected = pcbmotorgen_routing::generate_routing_result(&core.routing_context(), "infinity-braid").unwrap();
        let frozen = tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(ipc.clone())).unwrap();
        assert_eq!(copper(&frozen.routing), copper(&expected));
        let preview = tauri::async_runtime::block_on(super::physics::generate_coils(ipc.clone())).unwrap();
        assert_eq!(preview.layer_count, layers);
        assert_eq!(preview.phases.len(), (3 * layers) as usize);
        let exported = tauri::async_runtime::block_on(super::dxf::export_coils_dxf(ipc)).unwrap();
        let imported = pcbmotorgen_export::cad_dxf::import_3d_dxf(&exported.dxf_content,
            pcbmotorgen_export::cad_dxf::CadImportOptions {
                units_to_mm: 1.0, z_tolerance_mm: 1e-5, default_trace_width_mm: 0.2,
                legacy_layer_count: layers, legacy_pcb_thickness_mm: state.pcb_thickness_mm,
                prefer_detected_units: true,
            }).unwrap();
        assert!(imported.warnings.iter().all(|w| w.starts_with("DXF layer name suggested copper index ") && w.ends_with("used Z.")),
            "generated copper must not inherit the reference's unassigned barrels: {:?}", imported.warnings);
        // The importer numbers planes from bottom to top. Compare physical Z,
        // rather than mistaking that index convention for a changed layer.
        let map_layer = |layer: u32| frozen.layer_z_mm.iter().position(|z|
            (*z - imported.geometry.layer_z_mm[layer as usize]).abs() < 1e-5).unwrap() as u32;
        let mut roundtrip = imported.geometry.routing.clone();
        for s in &mut roundtrip.segments { s.layer = map_layer(s.layer); }
        for v in &mut roundtrip.vias {
            v.from_layer = map_layer(v.from_layer);
            v.to_layer = map_layer(v.to_layer);
        }
        assert_eq!(copper(&roundtrip), copper(&expected));
        for routing in [&frozen.routing, &imported.geometry.routing] {
            let networks = pcbmotorgen_simulation::drive::extract_phase_networks(routing);
            assert_eq!(networks.len(), 3);
            for network in networks {
                assert_eq!(network.terminal.len(), 1);
                assert_eq!(network.star.len(), 1);
                assert_eq!(network.layers(), (0..layers).collect::<Vec<_>>());
                assert!(pcbmotorgen_simulation::drive::solve_network(&network, &vec![1.0; network.edges.len()]).connected);
            }
        }
    }
}

#[test]
#[ignore = "Requires PCB_MOTOR_COMPACT_REFERENCE_DIR with revised 2/4/6-layer DXFs; never modifies them"]
fn compact_star_matches_supplied_two_layer_copper_and_scales_without_half_cycle_pair_reversal() {
    let root = std::path::PathBuf::from(std::env::var("PCB_MOTOR_COMPACT_REFERENCE_DIR").unwrap());
    let output = std::env::var("PCB_MOTOR_COMPACT_REFERENCE_OUTPUT").ok().map(std::path::PathBuf::from);
    let mut ctx = RoutingContext {
        active_area_length_mm: 92.0, board_width_mm: 8.0, num_layers: 2, phases: 3,
        min_trace_mm: 0.127, trace_width_mm: 0.2, min_space_mm: 0.127,
        via_pad_diameter_mm: Some(0.5), magnet_pitch_mm: Some(6.0), magnet_array_span_mm: Some(29.0),
        params: std::collections::HashMap::from([("num_strands".into(), 3.0), ("connection".into(), 2.0), ("pole_matched".into(), 1.0)]),
        ..Default::default()
    };
    for layers in [2, 4, 6] {
        let path = root.join(format!("star-wye_{layers}-layer.dxf"));
        let bytes = std::fs::read(&path).unwrap();
        let imported = pcbmotorgen_export::cad_dxf::import_3d_dxf(std::str::from_utf8(&bytes).unwrap(),
            pcbmotorgen_export::cad_dxf::CadImportOptions {
                units_to_mm: 1.0, z_tolerance_mm: 1e-5, default_trace_width_mm: 0.2,
                legacy_layer_count: layers, legacy_pcb_thickness_mm: 1.6 * (layers - 1) as f64,
                prefer_detected_units: true,
            }).unwrap();
        assert_eq!(imported.geometry.layer_z_mm.len(), layers as usize);
        assert!(imported.warnings.iter().all(|w| w.starts_with("DXF layer name suggested copper index ")
            || w.contains("must connect matching trace endpoints")), "{:?}", imported.warnings);
        let raw = &imported.geometry.routing;
        ctx.num_layers = layers;
        let generated = pcbmotorgen_routing::generate_routing_result(&ctx, "infinity-braid").unwrap();
        if layers == 2 {
            let (actual, expected) = (copper(raw), copper(&generated));
            let extra: Vec<_> = actual.iter().filter(|(k, v)| expected.get(*k) != Some(v)).collect();
            let missing: Vec<_> = expected.iter().filter(|(k, v)| actual.get(*k) != Some(v)).collect();
            assert!(extra.is_empty() && missing.is_empty(), "all actual copper must match: source-only {extra:?}; generated-only {missing:?}");
            // CAD numbers bottom-to-top; generated physical Z is top-to-bottom.
            // The drawings put the driver at Z=0. The existing layer-reversal
            // option, not a hidden coordinate flip, selects that orientation.
            let mut physical_source = raw.clone();
            for s in &mut physical_source.segments { s.layer = 1 - s.layer; }
            for v in &mut physical_source.vias {
                v.from_layer = 1 - v.from_layer;
                v.to_layer = 1 - v.to_layer;
            }
            let mut physical_ctx = ctx.clone();
            physical_ctx.orientation.reverse_layers = true;
            let physical_generated = pcbmotorgen_routing::generate_routing_result(&physical_ctx, "infinity-braid").unwrap();
            assert_eq!(copper(&physical_source), copper(&physical_generated), "physical XY/Z must match when the driver's outer-layer orientation matches the drawing");
        } else {
            // These drawings put each successive pair one pole pitch farther
            // right. The generator deliberately uses TWO pitches to avoid
            // reversing the pair's force. Do not silently repair the drawings.
            let mut closed_ctx = ctx.clone();
            closed_ctx.params.insert("connection".into(), 0.0);
            let mut closed = pcbmotorgen_routing::generate_routing_result(&closed_ctx, "infinity-braid").unwrap();
            for v in &mut closed.vias {
                v.net = match v.net.as_str() { "B" => "C".into(), "C" => "B".into(), _ => v.net.clone() };
            }
            for pair in 0..layers / 2 {
                let low = 2 * pair;
                for (net, x) in [("A", 4.333333), ("B", 8.333333), ("C", 12.333333)] {
                    let stage = layers / 2 - 1 - pair;
                    let missing: Vec<_> = closed.vias.iter().filter(|v| v.from_layer == low && v.net == net)
                        .filter(|v| !raw.vias.iter().any(|q| q.net == net && q.from_layer.min(q.to_layer) == low
                            && q.position.distance_to(v.position) < 1e-5)).collect();
                    assert_eq!(missing.len(), 1);
                    assert!((missing[0].position.x - (x + 6.0 * stage as f64)).abs() < 1e-5);
                }
            }
            let (raw_keys, generated_keys) = (copper(raw), copper(&generated));
            for layer in 0..layers {
                let body = |keys: &BTreeMap<(String, u32, [i64; 2], u32, [i64; 2]), usize>| keys.iter()
                    .filter(|((_, a, p, b, q), _)| *a == layer && *b == layer && p[1] <= 800000 && q[1] <= 800000)
                    .map(|(k, v)| (k.clone(), *v)).collect::<BTreeMap<_, _>>();
                let (raw_body, generated_body) = (body(&raw_keys), body(&generated_keys));
                let missing: Vec<_> = generated_body.iter().filter(|(k, v)| raw_body.get(*k) != Some(v)).collect();
                let extra: Vec<_> = raw_body.iter().filter(|(k, v)| generated_body.get(*k) != Some(v)).collect();
                assert!(extra.is_empty(), "unexpected source body copper on layer {layer}: {extra:?}");
                if layers == 6 && (layer == 4 || layer == 2) {
                    assert_eq!(missing.len(), 1, "the reference's two shortened B body edges must remain visible");
                    assert_eq!(missing[0].0.0, "B");
                } else {
                    assert!(missing.is_empty(), "source body differs on layer {layer}: {missing:?}");
                }
            }
            assert_eq!(raw.vias.iter().filter(|v| v.net == "0").count(), (3 * (layers / 2 - 1)) as usize,
                "unassigned barrel phases are reference defects, not generated copper");
        }
        if let Some(output) = &output {
            for (name, value) in [
                (format!("imported-{layers}.json"), serde_json::to_value(&imported.geometry).unwrap()),
                (format!("generated-{layers}.json"), serde_json::to_value(&generated).unwrap()),
            ] {
                let file = std::fs::OpenOptions::new().write(true).create_new(true).open(output.join(name)).unwrap();
                serde_json::to_writer_pretty(file, &value).unwrap();
            }
        }
        assert_eq!(std::fs::read(path).unwrap(), bytes);
    }
}
