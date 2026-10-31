use crate::ipc::{ProjectConfigStateIpc, LinearMotorConfigIpc};
use pcbmotorgen_routing::RoutingOrientation;

#[test]
fn routing_orientation_persists_and_native_preview_edit_export_and_simulation_share_it() {
    let base = ProjectConfigStateIpc::default().to_linear_motor_ipc();
    let base_core = base.to_core();
    let base_routing = pcbmotorgen_routing::generate_routing_result(&base_core.routing_context(),&base_core.routing_pattern_id()).unwrap();
    let base_resistance = pcbmotorgen_simulation::drive::analyze_drive_with(&base_core.to_simulation(),&base_routing,&Default::default(),None,&Default::default()).phase_resistance_ohm;
    for mask in 0..8 {
        let flip = RoutingOrientation { mirror_x: mask&1!=0, mirror_y: mask&2!=0, reverse_layers: mask&4!=0 };
        let saved = ProjectConfigStateIpc { routing_orientation: flip, ..Default::default() };
        let restored: ProjectConfigStateIpc = serde_json::from_value(serde_json::to_value(saved).unwrap()).unwrap();
        let input = restored.to_linear_motor_ipc();
        assert_eq!(input.routing_orientation,flip);
        assert_eq!(LinearMotorConfigIpc::from(&input.to_core()).routing_orientation,flip);
        let cad = tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(input.clone())).unwrap();
        let exported = tauri::async_runtime::block_on(super::dxf::export_coils_dxf(input.clone())).unwrap();
        assert_eq!(exported.dxf_content,pcbmotorgen_export::cad_dxf::cad_geometry_to_3d_dxf(&cad).unwrap());
        let preview = tauri::async_runtime::block_on(super::physics::generate_coils(input.clone())).unwrap();
        let native = input.to_core().generate_coils_for_board();
        let expected = serde_json::to_value(crate::ipc::CoilPathIpc::from_core_with_dimensions(&native,input.num_layers,&Default::default())).unwrap();
        let actual = serde_json::to_value(preview).unwrap();
        assert_eq!(actual["phases"],expected["phases"]);
        let core = input.to_core();
        let routing = pcbmotorgen_routing::generate_routing_result(&core.routing_context(),&core.routing_pattern_id()).unwrap();
        let analysis = pcbmotorgen_simulation::drive::analyze_drive_with(&core.to_simulation(),&routing,&Default::default(),None,&Default::default());
        assert!(analysis.phases.iter().all(|phase| phase.connected));
        assert!(analysis.phase_resistance_ohm.is_finite() && analysis.phase_resistance_ohm>0.);
        // Reflections change floating-point elimination order, not resistance.
        assert!((analysis.phase_resistance_ohm-base_resistance).abs()<1e-8*base_resistance,"orientation {mask}: {} vs {base_resistance}",analysis.phase_resistance_ohm);
        if flip.reverse_layers {
            let base_cad = tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(base.clone())).unwrap();
            let mut expected = base_cad.routing.segments[0].clone();
            flip.point(&mut expected.start,core.active_area_length_m*1000.,core.board_width_m*1000.);
            flip.point(&mut expected.end,core.active_area_length_m*1000.,core.board_width_m*1000.);
            expected.layer=base.num_layers-1-expected.layer;
            assert!(cad.routing.segments.iter().any(|segment| segment.layer==expected.layer && segment.net==expected.net
                && segment.start.distance_to(expected.start)<1e-8 && segment.end.distance_to(expected.end)<1e-8));
        }
    }
    let old: ProjectConfigStateIpc = serde_json::from_str("{}").unwrap();
    assert_eq!(old.routing_orientation,RoutingOrientation::default());
}

#[test]
fn reversed_asymmetric_stack_places_old_copper_at_reflected_physical_depths() {
    let mut original = ProjectConfigStateIpc::default().to_linear_motor_ipc();
    original.pcb_thickness_m=0.0008;
    original.pcb_stackup=Some(pcbmotorgen_simulation::params::PcbStackup {
        copper_m:vec![0.000035,0.000018,0.000070,0.000105],dielectric_m:vec![0.0001,0.0003,0.000172] });
    let mut flipped=original.clone();
    flipped.routing_orientation.reverse_layers=true;
    flipped.pcb_stackup.as_mut().unwrap().copper_m.reverse();
    flipped.pcb_stackup.as_mut().unwrap().dielectric_m.reverse();
    let old=tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(original.clone())).unwrap();
    let new=tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(flipped.clone())).unwrap();
    for layer in 0..4 {
        assert!((new.layer_z_mm[3-layer]-(-0.8-old.layer_z_mm[layer])).abs()<1e-12);
        assert_eq!(flipped.pcb_stackup.as_ref().unwrap().copper_m[3-layer],original.pcb_stackup.as_ref().unwrap().copper_m[layer]);
    }
}
