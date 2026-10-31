use crate::ipc::*;
use pcbmotorgen_export::cad_dxf::CadGeometry;
use pcbmotorgen_simulation::params::PcbStackup;
use pcbmotorgen_simulation::drive::{DriveSettings, DriveGeometryHints};

fn stack() -> PcbStackup {
    PcbStackup { copper_m: vec![35e-6, 18e-6, 70e-6, 35e-6], dielectric_m: vec![0.1e-3, 0.4e-3, 0.142e-3] }
}

fn config() -> LinearMotorConfigIpc {
    let mut input = ProjectConfigStateIpc::default().to_linear_motor_ipc();
    input.phases = 1;
    input.pcb_thickness_m = 0.0008;
    input.pcb_stackup = Some(stack());
    input
}

fn geometry() -> CadGeometry {
    let segments: Vec<_> = (0..4).map(|layer| serde_json::json!({"start":{"x":layer*10,"y":0},
        "end":{"x":(layer+1)*10,"y":0},"layer":layer,"net":"A","is_active":true})).collect();
    let vias: Vec<_> = (0..3).map(|layer| serde_json::json!({"position":{"x":(layer+1)*10,"y":0},
        "from_layer":layer,"to_layer":layer+1,"net":"A"})).collect();
    serde_json::from_value(serde_json::json!({"trace_width_mm":0.2,"layer_z_mm":[0,-1,-2,-3],
        "routing":{"format_version":2,"segments":segments,"curves":[],"vias":vias},
        "coil_phases":{"A":"A"},"coil_terminals":{"A":{"input":{"position":{"x":0,"y":0},"layer":0},
        "output":{"position":{"x":40,"y":0},"layer":3}}}})).unwrap()
}

#[test]
fn custom_stackup_roundtrips_saved_units_and_preserves_legacy_absence() {
    let legacy = ProjectConfigStateIpc::default();
    assert!(serde_json::to_value(&legacy).unwrap().get("pcb_stackup_mm").is_none());
    assert!(serde_json::to_value(legacy.to_linear_motor_ipc()).unwrap().get("pcb_stackup").is_none());
    let mut saved = legacy;
    saved.pcb_thickness_mm = 0.8;
    saved.pcb_stackup_mm = Some(crate::ipc::project::PcbStackupMm {
        copper_mm: vec![0.035,0.018,0.070,0.035], dielectric_mm: vec![0.1,0.4,0.142] });
    let restored: ProjectConfigStateIpc = serde_json::from_value(serde_json::to_value(&saved).unwrap()).unwrap();
    let ipc = restored.to_linear_motor_ipc();
    ipc.to_core().validate_for_simulation().unwrap();
    let sim = ipc.to_core().to_simulation();
    for (i, expected) in [-0.0175e-3,-0.144e-3,-0.588e-3,-0.7825e-3].iter().enumerate() {
        assert!((DriveGeometryHints::default().layer_z(&sim,i as u32)-expected).abs()<1e-15);
    }
}

#[test]
fn custom_stackup_drives_imported_heights_current_resistance_and_dc_copper() {
    let input = config(); let core = input.to_core(); let cad = geometry();
    let before = serde_json::to_value(&cad).unwrap();
    let board = super::cad_source::CadBoard::new(&cad,&core).unwrap();
    let sim = board.simulation_input(&cad,&core); let hints = board.drive_hints(&cad);
    let drive = DriveSettings::default();
    let result = pcbmotorgen_simulation::drive::analyze_drive_with(&sim,&board.routing,&drive,None,&hints);
    let rho = 1.724e-8 * (1. + 0.00393 * (drive.winding_temp_c - 20.));
    let s = stack();
    let traces: f64 = s.copper_m.iter().map(|t| rho * 0.010 / (0.0002 * t)).sum();
    let length = s.layer_z_m(0)-s.layer_z_m(3);
    let vias = pcbmotorgen_simulation::drive::via_resistance_ohm(sim.min_via_drill_m,drive.via_plating_m,length,rho);
    assert!(result.phases[0].connected);
    assert!((result.phases[0].resistance_hot_ohm-traces-vias).abs()<1e-7);
    assert_eq!(result.layer_copper_m, Some(s.copper_m.clone()));
    let heat = pcbmotorgen_simulation::visualization::copper_loss(&sim,&board.routing,&drive,&hints,2.).unwrap();
    assert!((heat.total_loss_w-2.*result.phases[0].resistance_hot_ohm).abs()<1e-10);
    for edge in &heat.edges {
        for (point, layer) in edge.points_m.iter().zip(if edge.kind=="trace" {vec![edge.layers[0];edge.points_m.len()]} else {edge.layers.to_vec()}) {
            assert!((point[2]-s.layer_z_m(layer)).abs()<1e-15);
        }
        if edge.kind=="trace" {
            let expected_r = rho*0.010/(0.0002*s.copper_m[edge.layers[0] as usize]);
            assert!((edge.resistance_ohm-expected_r).abs()<1e-10);
        }
    }
    let dc = tauri::async_runtime::block_on(super::physics::prepare_dc_winding_geometry(input,drive,Some(cad.clone()))).unwrap();
    let value = serde_json::to_value(dc).unwrap();
    // Snapshot exports actual layer dimensions for downstream finite-copper solvers.
    for (i, layer) in value["finite_copper"]["layers"].as_array().unwrap().iter().enumerate() {
        assert!((layer["centre_z_m"].as_f64().unwrap()-s.layer_z_m(i as u32)).abs()<1e-15);
        assert_eq!(layer["thickness_m"].as_f64().unwrap(),s.copper_m[i]);
    }
    let (evaluator,_) = pcbmotorgen_simulation::magnetic::ForceEvaluator::new(2,2,
        pcbmotorgen_simulation::magnetic::CommutationMode::MaxThrust,0.)
        .with_routed_currents(&board.routing,&sim,&DriveSettings::default(),&hints).unwrap();
    let samples = &evaluator.routed_conductor_samples().unwrap()[0];
    for layer in 0..4 { assert!(samples.iter().any(|p| (p.midpoint_3d[2]-s.layer_z_m(layer)).abs()<1e-15)); }
    assert_eq!(serde_json::to_value(cad).unwrap(),before);
    for layer in 0..4 { assert!((hints.layer_z(&sim,layer)-s.layer_z_m(layer)).abs()<1e-15); }
}

#[test]
fn malformed_custom_stackups_are_rejected_without_uniform_fallback() {
    for mode in 0..3 {
        let mut input = config();
        if mode==0 { input.pcb_stackup.as_mut().unwrap().copper_m.pop(); }
        if mode==1 { input.pcb_stackup.as_mut().unwrap().dielectric_m[0]=0.; }
        if mode==2 { input.pcb_thickness_m=0.0016; }
        assert!(input.to_core().validate_for_simulation().is_err());
        assert!(tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(input)).is_err());
    }
}

#[test]
fn generated_editable_and_dxf_use_the_same_custom_centers() {
    let mut input = config(); input.phases=3;
    let cad = tauri::async_runtime::block_on(super::dxf::editable_coil_geometry(input.clone())).unwrap();
    for layer in 0..4 { assert!((cad.layer_z_mm[layer]-stack().layer_z_m(layer as u32)*1000.).abs()<1e-12); }
    let dxf = tauri::async_runtime::block_on(super::dxf::export_coils_dxf(input)).unwrap();
    assert_eq!(dxf.dxf_content,pcbmotorgen_export::cad_dxf::cad_geometry_to_3d_dxf(&cad).unwrap());
}

#[test]
fn custom_stackup_assembly_height_includes_copper_once_and_planar_screen_refuses_flattening() {
    let input = config();
    let sim = input.to_core().to_simulation();
    let height = pcbmotorgen_simulation::stackup::HeightStackCalculator::default().calculate(&sim);
    assert_eq!(height.cu_protrusion_m,0.);
    assert!((height.pcb_thickness_m-stack().thickness_m()).abs()<1e-15);
    let error = tauri::async_runtime::block_on(super::physics::travel_envelope(input)).unwrap_err();
    assert!(error.contains("does not support custom PCB stackups"));
}
