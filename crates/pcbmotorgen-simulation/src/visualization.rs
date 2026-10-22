//! Bounded visualization data from native models, never FEM qualification.
//! Coordinates are SI, in the routing frame, with PCB top z=0. Field samples
//! are actual XYZ observations of the PMs only. Heat is resistor-graph I²R,
//! averaged at an explicit RMS-equivalent winding-phase current, not temperature.
use crate::{
    drive::{
        extract_phase_networks_with_terminals, rho_cu_at, solve_network, via_resistance_ohm,
        DriveGeometryHints, DriveSettings, EdgeKind,
    },
    physics, MagnetArray, SimulationInput,
};
use pcbmotorgen_routing::RoutingResult;
use serde::{Deserialize, Serialize};

pub const SAMPLE_CAP: usize = 2048;
pub const EDGE_CAP: usize = 10_000;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VisualizationRequest {
    pub request_id: String,
    pub mover_position_m: f64,
    pub bounds_m: [[f64; 2]; 3],
    pub counts: [usize; 3],
    pub phase_peak_a: f64,
    pub fields: bool,
    pub heat: bool,
}

impl VisualizationRequest {
    pub fn validate(&self) -> Result<(), String> {
        if self.request_id.is_empty()
            || self.request_id.len() > 128
            || !self.mover_position_m.is_finite()
            || self.mover_position_m.abs() > 1.
            || !self.phase_peak_a.is_finite()
            || !(0. ..=1000.).contains(&self.phase_peak_a)
        {
            return Err("Invalid bounded visualization identity, pose or phase current".into());
        }
        if !self.fields && !self.heat {
            return Err("Select a field or loss visualization".into());
        }
        let count = self
            .counts
            .iter()
            .try_fold(1usize, |n, &v| n.checked_mul(v));
        if self.counts.iter().any(|&n| !(2..=64).contains(&n))
            || count.is_none_or(|n| n > SAMPLE_CAP)
        {
            return Err(format!(
                "XYZ sampling requires 2..64 points per axis and at most {SAMPLE_CAP} total"
            ));
        }
        if self.bounds_m.iter().any(|v| {
            !v[0].is_finite()
                || !v[1].is_finite()
                || v[0] >= v[1]
                || v[0].abs() > 1.
                || v[1].abs() > 1.
        }) {
            return Err("Visualization bounds must be finite, ordered and within one metre".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct FieldSample {
    pub position_m: [f64; 3],
    pub b_t: [f64; 3],
    pub magnitude_t: f64,
}
#[derive(Clone, Debug, Serialize)]
pub struct MagnetBox {
    pub center_m: [f64; 3],
    pub size_m: [f64; 3],
    pub positive_z: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct FieldPreview {
    pub method: &'static str,
    pub scope: &'static str,
    pub samples: Vec<FieldSample>,
    pub magnets: Vec<MagnetBox>,
}

pub fn pm_field(
    sim: &SimulationInput,
    request: &VisualizationRequest,
) -> Result<FieldPreview, String> {
    request.validate()?;
    sim.validate().map_err(|e| e.to_string())?;
    // The existing screening assembly can include image magnets. This mode
    // deliberately excludes them and labels itself PM-only, not a solved stack.
    let mut bare = sim.clone();
    bare.backplane = None;
    let array = MagnetArray::new(&bare);
    let assembly = array.build_assembly(request.mover_position_m);
    let coordinate = |axis: usize, index: usize| {
        request.bounds_m[axis][0]
            + (request.bounds_m[axis][1] - request.bounds_m[axis][0]) * index as f64
                / (request.counts[axis] - 1) as f64
    };
    let mut observers = Vec::with_capacity(request.counts.iter().product());
    for z in 0..request.counts[2] {
        for y in 0..request.counts[1] {
            for x in 0..request.counts[0] {
                observers.push(nalgebra::Point3::new(
                    coordinate(0, x),
                    coordinate(1, y),
                    coordinate(2, z),
                ));
            }
        }
    }
    let values = physics::compute_b_batch_parallel(&assembly, &observers);
    let samples = observers
        .iter()
        .zip(values)
        .map(|(p, b)| FieldSample {
            position_m: [p.x, p.y, p.z],
            b_t: [b.x, b.y, b.z],
            magnitude_t: b.norm(),
        })
        .collect::<Vec<_>>();
    if samples
        .iter()
        .any(|v| !v.magnitude_t.is_finite() || v.b_t.iter().any(|x| !x.is_finite()))
    {
        return Err(
            "PM field is nonfinite at a requested point; no clipped or substituted field returned"
                .into(),
        );
    }
    let magnets = array
        .magnet_x_centers_m(request.mover_position_m)
        .iter()
        .enumerate()
        .map(|(i, &x)| MagnetBox {
            center_m: [x, bare.board_width_m / 2., array.magnet_z_center_m()],
            size_m: bare.magnet_dims_m,
            positive_z: i % 2 == 0,
        })
        .collect();
    Ok(FieldPreview{method:"analytical-pm-only-xyz",scope:"Permanent magnets only. No winding reaction, backplane/housing response, nonlinear FEM or force qualification.",samples,magnets})
}

#[derive(Clone, Debug, Serialize)]
pub struct EdgeLoss {
    pub net: String,
    pub kind: &'static str,
    pub layers: [u32; 2],
    pub points_m: Vec<[f64; 3]>,
    pub loss_w: f64,
    pub rms_current_a: f64,
    pub resistance_ohm: f64,
}
#[derive(Clone, Debug, Serialize)]
pub struct CopperLossPreview {
    pub method: &'static str,
    pub scope: &'static str,
    pub phase_peak_a: f64,
    pub phase_rms_a: f64,
    pub winding_temperature_c: f64,
    pub total_loss_w: f64,
    pub power_balance_relative_error: f64,
    pub edges: Vec<EdgeLoss>,
}

pub fn copper_loss(
    sim: &SimulationInput,
    routing: &RoutingResult,
    settings: &DriveSettings,
    hints: &DriveGeometryHints,
    phase_peak_a: f64,
) -> Result<CopperLossPreview, String> {
    sim.validate().map_err(|e| e.to_string())?;
    if !phase_peak_a.is_finite() || !(0. ..=1000.).contains(&phase_peak_a) {
        return Err("Invalid winding-phase peak current".into());
    }
    if routing
        .segments
        .len()
        .saturating_add(routing.curves.len())
        .saturating_add(routing.vias.len())
        > EDGE_CAP
        || !routing.splines.is_empty()
        || !routing.io_traces.is_empty()
        || !routing.io_pads.is_empty()
    {
        return Err("Loss preview supports at most10000 straight/arc/via primitives, without splines or IO fan-out".into());
    }
    if !hints.layer_z_m.is_empty() && hints.layer_z_m.len() != sim.num_layers as usize {
        return Err("Actual copper depth count is incomplete".into());
    }
    let valid_layer = |layer: u32| layer < sim.num_layers && hints.layer_z(sim, layer).is_finite();
    if routing.segments.iter().any(|s| {
        !valid_layer(s.layer)
            || ![s.start.x, s.start.y, s.end.x, s.end.y]
                .iter()
                .all(|x| x.is_finite())
            || s.start == s.end
    }) || routing.curves.iter().any(|s| {
        !valid_layer(s.layer)
            || ![s.start.x, s.start.y, s.mid.x, s.mid.y, s.end.x, s.end.y]
                .iter()
                .all(|x| x.is_finite())
    }) || routing.vias.iter().any(|v| {
        !valid_layer(v.from_layer)
            || !valid_layer(v.to_layer)
            || v.from_layer == v.to_layer
            || ![v.position.x, v.position.y].iter().all(|x| x.is_finite())
    }) {
        return Err(
            "Invalid physical trace/via coordinates or copper layers; no loss geometry repaired"
                .into(),
        );
    }
    let rho = rho_cu_at(settings.winding_temp_c);
    if [
        rho,
        sim.min_trace_m,
        settings.outer_copper_oz,
        settings.inner_copper_oz,
        settings.via_plating_m,
    ]
    .iter()
    .any(|x| !x.is_finite() || *x <= 0.)
        || !settings.winding_temp_c.is_finite()
        || settings.via_plating_m > sim.min_via_annular_ring_m
    {
        return Err(
            "Actual copper width, weights, plating and resistivity must be positive and finite"
                .into(),
        );
    }
    let networks = extract_phase_networks_with_terminals(routing, &hints.terminals);
    if networks.is_empty() {
        return Err("No actual connected copper networks for a loss preview".into());
    }
    let rms = phase_peak_a / std::f64::consts::SQRT_2;
    let mut edges = Vec::new();
    let mut expected = 0.;
    for network in networks {
        if network.node_count > 2048 || edges.len() + network.edges.len() > EDGE_CAP {
            return Err("Loss preview exceeds the bounded graph resource cap".into());
        }
        let resistances = network
            .edges
            .iter()
            .map(|e| match &e.kind {
                EdgeKind::Trace {
                    layer, length_m, ..
                } => {
                    let inner = sim.num_layers > 2 && *layer != 0 && *layer + 1 != sim.num_layers;
                    rho * length_m
                        / (sim.min_trace_m
                            * crate::units::oz_to_m(if inner {
                                settings.inner_copper_oz
                            } else {
                                settings.outer_copper_oz
                            }))
                }
                EdgeKind::Via { layers, .. } => via_resistance_ohm(
                    sim.min_via_drill_m,
                    settings.via_plating_m,
                    hints.via_length_m(sim, *layers),
                    rho,
                ),
            })
            .collect::<Vec<_>>();
        let solved = solve_network(&network, &resistances);
        if !solved.connected || solved.resistance_ohm <= 0. || !solved.resistance_ohm.is_finite() {
            return Err(format!(
                "Winding{} is not a connected finite resistor network",
                network.net
            ));
        }
        expected += rms * rms * solved.resistance_ohm;
        for ((edge, share), resistance) in network
            .edges
            .iter()
            .zip(solved.current_share)
            .zip(resistances)
        {
            let (kind, layers, points) = match &edge.kind {
                EdgeKind::Trace { layer, points, .. } => (
                    "trace",
                    [*layer, *layer],
                    points
                        .iter()
                        .map(|p| [p[0], p[1], hints.layer_z(sim, *layer)])
                        .collect(),
                ),
                EdgeKind::Via { layers, position_m } => (
                    "via",
                    *layers,
                    layers
                        .iter()
                        .map(|&l| [position_m[0], position_m[1], hints.layer_z(sim, l)])
                        .collect(),
                ),
            };
            edges.push(EdgeLoss {
                net: network.net.clone(),
                kind,
                layers,
                points_m: points,
                loss_w: rms * rms * share * share * resistance,
                rms_current_a: rms * share,
                resistance_ohm: resistance,
            });
        }
    }
    let total = edges.iter().map(|e| e.loss_w).sum::<f64>();
    let error = (total - expected).abs() / expected.max(1e-12);
    if edges.iter().any(|e| {
        !e.loss_w.is_finite()
            || e.loss_w < 0.
            || e.points_m.iter().flatten().any(|x| !x.is_finite())
    }) || !error.is_finite()
        || error > 1e-8
    {
        return Err(
            "Copper loss failed finite-value or original network power-balance checks".into(),
        );
    }
    Ok(CopperLossPreview{method:"native-resistor-graph-rms-i2r",scope:"RMS-equivalent winding-phase I²R at the specified peak current. Arc resistance uses the native graph's chord rule. No temperature prediction, finite-volume hot spots, AC/PWM/core loss, or housing heating.",
        phase_peak_a,phase_rms_a:rms,winding_temperature_c:settings.winding_temp_c,total_loss_w:total,power_balance_relative_error:error,edges})
}

#[cfg(test)]
mod tests {
    use super::*;
    use pcbmotorgen_routing::{Point, RouteSegment};
    fn request() -> VisualizationRequest {
        VisualizationRequest {
            request_id: "view".into(),
            mover_position_m: 0.,
            bounds_m: [[0., 0.02], [0., 0.01], [-0.001, 0.005]],
            counts: [4, 3, 3],
            phase_peak_a: 1.,
            fields: true,
            heat: true,
        }
    }
    #[test]
    fn xyz_sampling_is_real_bounded_and_pm_only() {
        let sim = SimulationInput::default();
        let r = request();
        let v = pm_field(&sim, &r).unwrap();
        assert_eq!(v.samples.len(), 36);
        assert_eq!(v.samples[4].position_m[1], 0.005);
        assert!(v.samples.iter().all(|v| v.magnitude_t.is_finite()));
        let mut moved = r.clone();
        moved.mover_position_m += 0.0001;
        let b = pm_field(&sim, &moved).unwrap();
        assert!((b.magnets[0].center_m[0] - v.magnets[0].center_m[0] - 0.0001).abs() < 1e-15);
        assert_ne!(b.samples[0].b_t, v.samples[0].b_t);
        let mut overflow = r.clone();
        overflow.counts = [usize::MAX, 64, 64];
        assert!(overflow.validate().is_err());
        let mut invalid = r.clone();
        invalid.bounds_m[0] = [f64::NAN, 1.];
        assert!(invalid.validate().is_err());
        invalid = r;
        invalid.counts = [1, 2, 2];
        assert!(invalid.validate().is_err());
        let mut across = request();
        across.bounds_m[1] = [0.001, 0.009];
        let xyz = pm_field(&sim, &across).unwrap();
        assert_ne!(xyz.samples[0].b_t, xyz.samples[4].b_t);
    }
    #[test]
    fn actual_graph_losses_conserve_power_scale_with_i_squared_and_preserve_depth() {
        let sim = SimulationInput::default();
        let mut route = RoutingResult::default();
        route.segments.push(RouteSegment {
            start: Point::new(0., 0.),
            end: Point::new(10., 1.),
            layer: 0,
            net: "A".into(),
            is_active: true,
        });
        let settings = DriveSettings::default();
        let hints = DriveGeometryHints::default();
        let a = copper_loss(&sim, &route, &settings, &hints, 1.).unwrap();
        let b = copper_loss(&sim, &route, &settings, &hints, 2.).unwrap();
        assert!((b.total_loss_w / a.total_loss_w - 4.).abs() < 1e-12);
        assert!(a.power_balance_relative_error < 1e-8);
        let zero = copper_loss(&sim, &route, &settings, &hints, 0.).unwrap();
        assert_eq!(zero.total_loss_w, 0.);
        assert_eq!(a.edges[0].points_m[1], [0.01, 0.001, 0.]);
        let mut deeper = hints;
        deeper.layer_z_m = (0..sim.num_layers)
            .map(|i| -0.0002 - i as f64 * 0.0002)
            .collect();
        assert_eq!(
            copper_loss(&sim, &route, &settings, &deeper, 1.)
                .unwrap()
                .edges[0]
                .points_m[0][2],
            -0.0002
        );
        assert!(copper_loss(&sim, &route, &settings, &deeper, f64::NAN).is_err());
        route.segments[0].start.x = f64::NAN;
        assert!(copper_loss(&sim, &route, &settings, &deeper, 1.).is_err());
    }
}
