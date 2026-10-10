use std::collections::BTreeMap;

use crate::coil::{CoilArc, CoilSegment, PhaseCoil};
use crate::model::RoutingResult;

/// Adapt a validated [`RoutingResult`] into the [`PhaseCoil`] presentation used
/// by the preview and the force model.
///
/// Elements are grouped by `(layer_idx, phase_name)`. Because a `PhaseCoil`
/// carries a single `layer_idx`, each (layer, net) pair becomes its own coil.
/// Vias are collected (by net+layer pair only as positions — the writer's
/// through-via model does not carry from/to direction, which is acceptable for
/// preview; the dedicated writer path can read the full directions from the
/// `RoutingResult` when needed).
pub fn routing_result_to_phase_coils(result: &RoutingResult, pattern_id: &str) -> Vec<PhaseCoil> {
    // key: (layer, net) -> coil index
    let mut coils: Vec<PhaseCoil> = Vec::new();
    let mut index: BTreeMap<(u32, String), usize> = BTreeMap::new();

    // The legacy force model consumes straight conductors. Keep the routing
    // model untouched and tessellate spline copies only at this boundary.
    let sampled: Vec<_> = result
        .splines
        .iter()
        .flat_map(|s| {
            let length: f64 = s
                .control_points
                .windows(2)
                .map(|p| p[0].distance_to(p[1]))
                .sum();
            s.tessellate((length / 10_000.0).max(0.25))
                .expect("routing splines must be validated before adapting to coils")
        })
        .collect();
    for s in result.segments.iter().chain(&sampled) {
        let key = (s.layer, s.net.clone());
        let idx = *index.entry(key.clone()).or_insert_with(|| {
            coils.push(PhaseCoil {
                layer_idx: s.layer,
                phase_name: s.net.clone(),
                pattern_id: pattern_id.to_string(),
                ..PhaseCoil::default()
            });
            coils.len() - 1
        });
        coils[idx].segments.push(CoilSegment {
            start: (s.start.x, s.start.y),
            end: (s.end.x, s.end.y),
            is_active: s.is_active,
        });
    }

    for c in &result.curves {
        let key = (c.layer, c.net.clone());
        let idx = *index.entry(key.clone()).or_insert_with(|| {
            coils.push(PhaseCoil {
                layer_idx: c.layer,
                phase_name: c.net.clone(),
                pattern_id: pattern_id.to_string(),
                ..PhaseCoil::default()
            });
            coils.len() - 1
        });
        coils[idx].corner_arcs.push(CoilArc {
            start: (c.start.x, c.start.y),
            mid: (c.mid.x, c.mid.y),
            end: (c.end.x, c.end.y),
            is_active: c.is_active,
        });
    }

    for v in &result.vias {
        let key = (v.from_layer, v.net.clone());
        if let Some(&idx) = index.get(&key) {
            coils[idx]
                .center_via_positions
                .push((v.position.x, v.position.y));
        } else {
            // Via on a layer with no conductor — attach to a coil on that
            // layer+net if one exists later, else drop (preview only).
            let _ = v;
        }
    }

    // Assign a distinct enumerated phase_idx per distinct net for stability.
    let mut phase_map: BTreeMap<String, u32> = BTreeMap::new();
    for coil in &mut coils {
        let next = phase_map.len() as u32;
        let pid = *phase_map.entry(coil.phase_name.clone()).or_insert(next);
        coil.phase_idx = pid;
    }

    coils.sort_by_key(|c| (c.layer_idx, c.phase_idx));
    coils
}
