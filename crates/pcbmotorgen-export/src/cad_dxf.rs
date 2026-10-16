//! Round-trippable 3D DXF exchange for trace centerlines.
//!
//! Copper planes are represented by Z elevations. Vias are vertical LINE
//! entities whose endpoints lie on the connected copper planes. DXF layer
//! names carry the logical net and layer index as helpful metadata, but Z is
//! the physical source of truth when importing.

use std::collections::{BTreeMap, BTreeSet};

use pcbmotorgen_routing::{
    Point, RouteCurve, RouteSegment, RouteSpline, RoutingResult, SensorGeometry, Via,
};
use serde::{Deserialize, Serialize};

use crate::{groups, sections};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CadGeometry {
    pub routing: RoutingResult,
    /// Imported CAD basename, retained by project persistence.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_file_name: Option<String>,
    /// Copper plane heights in mm, indexed bottom-to-top.
    pub layer_z_mm: Vec<f64>,
    pub trace_width_mm: f64,
    /// Original DXF layer names and their assigned coil/net identity.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub source_layer_coils: BTreeMap<String, String>,
    /// Explicit terminal positions in mm, keyed by coil/net identity.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub coil_terminals: BTreeMap<String, CadCoilTerminals>,
    /// Selection convention only; does not add connecting copper.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub terminal_connection: Option<TerminalConnection>,
    /// Coil/net identity → motor phase label (`A`, `B`, `C`, …). Coils that
    /// share a phase join the same KiCad net and drive in parallel. A coil
    /// already named after a phase maps to it without an entry.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub coil_phases: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TerminalConnection {
    Star,
    Delta,
}

impl CadGeometry {
    /// Every coil/net identity carrying copper, sorted.
    pub fn coil_names(&self) -> Vec<String> {
        let mut names: BTreeSet<String> = BTreeSet::new();
        names.extend(self.routing.segments.iter().map(|s| s.net.clone()));
        names.extend(self.routing.curves.iter().map(|c| c.net.clone()));
        names.extend(self.routing.splines.iter().map(|s| s.net.clone()));
        names.into_iter().collect()
    }

    /// The phase a coil drives: its explicit assignment, else its own name
    /// when that is already a phase label.
    pub fn phase_of(&self, coil: &str) -> Option<String> {
        match self.coil_phases.get(coil) {
            Some(phase) if !phase.trim().is_empty() => Some(phase.trim().to_string()),
            _ if pcbmotorgen_routing::PHASE_NAMES.contains(&coil) => Some(coil.to_string()),
            _ => None,
        }
    }

    /// Coils without a phase.
    pub fn unmapped_coils(&self) -> Vec<String> {
        self.coil_names().into_iter().filter(|c| self.phase_of(c).is_none()).collect()
    }

    /// The routing with every coil net renamed to its phase, so coils of one
    /// phase share a net. Fails while any coil has no phase.
    pub fn routing_by_phase(&self) -> Result<RoutingResult, String> {
        let unmapped = self.unmapped_coils();
        if !unmapped.is_empty() {
            return Err(format!(
                "Assign a phase to every imported coil first (unassigned: {})",
                unmapped.join(", ")
            ));
        }
        let phase = |net: &str| self.phase_of(net).unwrap_or_else(|| net.to_string());
        let mut routing = self.routing.clone();
        for s in &mut routing.segments {
            s.net = phase(&s.net);
        }
        for c in &mut routing.curves {
            c.net = phase(&c.net);
        }
        for s in &mut routing.splines {
            s.net = phase(&s.net);
        }
        for v in &mut routing.vias {
            v.net = phase(&v.net);
        }
        Ok(routing)
    }

    /// Picked IN/OUT terminals grouped by phase (mapped coils only).
    pub fn terminals_by_phase(&self) -> BTreeMap<String, Vec<CadCoilTerminals>> {
        let mut out: BTreeMap<String, Vec<CadCoilTerminals>> = BTreeMap::new();
        for (coil, t) in &self.coil_terminals {
            if let Some(phase) = self.phase_of(coil) {
                out.entry(phase).or_default().push(t.clone());
            }
        }
        out
    }

    /// `[min, max]` copper extent along x and y in mm (`None` when empty).
    pub fn extent_mm(&self) -> Option<([f64; 2], [f64; 2])> {
        let mut pts: Vec<Point> = Vec::new();
        for s in &self.routing.segments {
            pts.extend([s.start, s.end]);
        }
        for c in &self.routing.curves {
            pts.extend([c.start, c.mid, c.end]);
        }
        for s in &self.routing.splines {
            pts.extend(s.control_points.iter().copied());
        }
        if pts.is_empty() {
            return None;
        }
        let fold = |f: fn(&Point) -> f64| {
            pts.iter().map(f).fold([f64::INFINITY, f64::NEG_INFINITY], |a, v| [a[0].min(v), a[1].max(v)])
        };
        Some((fold(|p| p.x), fold(|p| p.y)))
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CadTerminal {
    pub position: Point,
    pub layer: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CadCoilTerminals {
    pub input: CadTerminal,
    pub output: CadTerminal,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CadImportOptions {
    /// Multiply drawing coordinates by this value to convert them to mm.
    /// Also the fallback when `prefer_detected_units` is set but the file has
    /// no recognisable `$INSUNITS`.
    pub units_to_mm: f64,
    pub z_tolerance_mm: f64,
    pub default_trace_width_mm: f64,
    pub legacy_layer_count: u32,
    pub legacy_pcb_thickness_mm: f64,
    /// Use the DXF `$INSUNITS` header unit when present and recognised,
    /// overriding `units_to_mm` (the user can still override by disabling it).
    pub prefer_detected_units: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CadImportResult {
    pub geometry: CadGeometry,
    pub warnings: Vec<String>,
    /// Millimetres per drawing unit actually applied to the import.
    #[serde(default = "one_mm")]
    pub units_to_mm: f64,
    /// Millimetres per unit read from the DXF `$INSUNITS` header. `None` when
    /// the file declares no units or an unrecognised code.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_units_mm: Option<f64>,
}

fn one_mm() -> f64 {
    1.0
}

/// Millimetres per drawing unit for a DXF `$INSUNITS` code (kata chgg).
///
/// Covers the units a mechanical-CAD export plausibly uses. Unitless (0) and
/// codes outside this set return `None`, so the caller keeps the user's
/// explicit choice rather than guessing. Values follow the DXF reference.
pub fn dxf_insunits_to_mm(code: i32) -> Option<f64> {
    Some(match code {
        1 => 25.4,      // inches
        2 => 304.8,     // feet
        4 => 1.0,       // millimetres
        5 => 10.0,      // centimetres
        6 => 1000.0,    // metres
        8 => 2.54e-5,   // microinches
        9 => 0.0254,    // mils
        13 => 1e-3,     // micrometres
        _ => return None,
    })
}

/// Read the `$INSUNITS` header value from the parsed pair stream.
fn detect_source_units_mm(pairs: &[(i32, String)]) -> Option<f64> {
    pairs
        .windows(2)
        .find(|window| window[0].0 == 9 && window[0].1.trim() == "$INSUNITS")
        .and_then(|window| window[1].1.trim().parse::<i32>().ok())
        .and_then(dxf_insunits_to_mm)
}

#[derive(Debug, Clone)]
struct Entity {
    kind: String,
    fields: Vec<(i32, String)>,
}

#[derive(Debug, Clone)]
struct PendingSegment {
    start: Point,
    end: Point,
    z: f64,
    net: String,
    layer_hint: Option<u32>,
}

#[derive(Debug, Clone)]
struct PendingCurve {
    start: Point,
    mid: Point,
    end: Point,
    z: f64,
    net: String,
    layer_hint: Option<u32>,
}

#[derive(Debug, Clone)]
struct PendingVia {
    x: f64,
    y: f64,
    z0: f64,
    z1: f64,
    net: String,
}

struct PendingSpline {
    spline: RouteSpline,
    z: f64,
    layer_hint: Option<u32>,
}

/// Preserve sensor curves in the CAD model. Sensor layers are top-to-bottom;
/// CAD layers are bottom-to-top. The sensor uses a fixed 1.6 mm stack.
pub fn sensor_geometry_to_cad_geometry(sensor: &SensorGeometry) -> CadGeometry {
    let mut routing = RoutingResult::default();
    for net in &sensor.nets {
        routing
            .segments
            .extend(net.segments.iter().cloned().map(|mut s| {
                s.layer = 1 - s.layer;
                s
            }));
        routing
            .curves
            .extend(net.curves.iter().cloned().map(|mut c| {
                c.layer = 1 - c.layer;
                c
            }));
        routing
            .splines
            .extend(net.splines.iter().cloned().map(|mut s| {
                s.layer = 1 - s.layer;
                s
            }));
        routing.vias.extend(net.vias.iter().cloned().map(|mut v| {
            v.from_layer = 0;
            v.to_layer = 1;
            v
        }));
    }
    CadGeometry {
        routing,
        layer_z_mm: vec![-1.6, 0.0],
        trace_width_mm: sensor.nets[0].trace_width_mm,
        source_layer_coils: BTreeMap::new(),
        source_file_name: None,
        coil_terminals: BTreeMap::new(),
        terminal_connection: None,
        coil_phases: BTreeMap::new(),
    }
}

/// Export 3D DXF with planar trace centerlines and vertical via centerlines.
pub fn cad_geometry_to_3d_dxf(geometry: &CadGeometry) -> Result<String, String> {
    validate_geometry(geometry)?;
    let modern = !geometry.routing.splines.is_empty();
    let mut layer_names = BTreeSet::new();
    for segment in &geometry.routing.segments {
        layer_names.insert(format!(
            "L{}_{}",
            segment.layer,
            safe_layer_part(&segment.net)
        ));
    }
    for curve in &geometry.routing.curves {
        layer_names.insert(format!("L{}_{}", curve.layer, safe_layer_part(&curve.net)));
    }
    for spline in &geometry.routing.splines {
        layer_names.insert(format!(
            "L{}_{}",
            spline.layer,
            safe_layer_part(&spline.net)
        ));
    }
    for via in &geometry.routing.vias {
        layer_names.insert(format!(
            "Via_L{}_L{}_{}",
            via.from_layer,
            via.to_layer,
            safe_layer_part(&via.net)
        ));
    }
    let layer_names: Vec<String> = layer_names.into_iter().collect();
    let mut out = Vec::new();
    groups::dxf_group(
        &mut out,
        999,
        &format!("pcbmotorgen:trace_width_mm={:.9}", geometry.trace_width_mm),
    );
    if geometry.routing.splines.is_empty() {
        sections::write_header(&mut out);
    } else {
        // SPLINE requires DXF R13 or newer, not the legacy R12 contract.
        groups::dxf_group(&mut out, 0, "SECTION");
        groups::dxf_group(&mut out, 2, "HEADER");
        groups::dxf_group(&mut out, 9, "$ACADVER");
        groups::dxf_group(&mut out, 1, "AC1015");
        groups::dxf_group(&mut out, 9, "$INSUNITS");
        groups::dxf_group(&mut out, 70, "4");
        groups::dxf_group(&mut out, 0, "ENDSEC");
    }
    sections::write_tables_version(&mut out, &layer_names, modern);
    groups::dxf_group(&mut out, 0, "SECTION");
    groups::dxf_group(&mut out, 2, "ENTITIES");

    for segment in &geometry.routing.segments {
        let z = geometry.layer_z_mm[segment.layer as usize];
        let layer = format!("L{}_{}", segment.layer, safe_layer_part(&segment.net));
        write_3d_line(
            &mut out,
            &layer,
            (segment.start.x, segment.start.y, z),
            (segment.end.x, segment.end.y, z),
            modern,
        );
    }
    for curve in &geometry.routing.curves {
        let z = geometry.layer_z_mm[curve.layer as usize];
        let layer = format!("L{}_{}", curve.layer, safe_layer_part(&curve.net));
        write_3d_arc(
            &mut out,
            &layer,
            (curve.start.x, curve.start.y),
            (curve.mid.x, curve.mid.y),
            (curve.end.x, curve.end.y),
            z,
            modern,
        );
    }
    for spline in &geometry.routing.splines {
        let layer = format!("L{}_{}", spline.layer, safe_layer_part(&spline.net));
        write_3d_spline(
            &mut out,
            &layer,
            spline,
            geometry.layer_z_mm[spline.layer as usize],
        );
    }
    for via in &geometry.routing.vias {
        let layer = format!(
            "Via_L{}_L{}_{}",
            via.from_layer,
            via.to_layer,
            safe_layer_part(&via.net)
        );
        write_3d_line(
            &mut out,
            &layer,
            (
                via.position.x,
                via.position.y,
                geometry.layer_z_mm[via.from_layer as usize],
            ),
            (
                via.position.x,
                via.position.y,
                geometry.layer_z_mm[via.to_layer as usize],
            ),
            modern,
        );
    }
    groups::dxf_group(&mut out, 0, "ENDSEC");
    groups::dxf_group(&mut out, 0, "EOF");
    let mut text = out.join("\n");
    text.push('\n');
    Ok(text)
}

/// Build the exchange model from the app's generated coil presentation model.
pub fn phase_coils_to_cad_geometry(
    coils: &[pcbmotorgen_routing::PhaseCoil],
    num_layers: u32,
    pcb_thickness_mm: f64,
    trace_width_mm: f64,
) -> Result<CadGeometry, String> {
    if num_layers == 0 {
        return Err("Generated CAD geometry needs at least one copper layer".into());
    }
    if !pcb_thickness_mm.is_finite() || pcb_thickness_mm < 0.0 {
        return Err("PCB thickness must be non-negative and finite".into());
    }
    let layer_z_mm = if num_layers == 1 {
        vec![0.0]
    } else {
        (0..num_layers)
            // Generated layer 0 is top copper, as in the force and preview
            // models. Preserve that physical position when exporting CAD.
            .map(|i| -pcb_thickness_mm * i as f64 / (num_layers - 1) as f64)
            .collect()
    };
    let mut routing = RoutingResult::default();
    for coil in coils {
        for segment in &coil.segments {
            routing.segments.push(RouteSegment {
                start: Point::new(segment.start.0, segment.start.1),
                end: Point::new(segment.end.0, segment.end.1),
                layer: coil.layer_idx,
                net: coil.phase_name.clone(),
                is_active: segment.is_active,
            });
        }
        for curve in &coil.corner_arcs {
            routing.curves.push(RouteCurve {
                start: Point::new(curve.start.0, curve.start.1),
                mid: Point::new(curve.mid.0, curve.mid.1),
                end: Point::new(curve.end.0, curve.end.1),
                layer: coil.layer_idx,
                net: coil.phase_name.clone(),
                is_active: curve.is_active,
            });
        }
        let (from_layer, to_layer) = if let Some(pair) = coil.layer_pair {
            pair
        } else if coil.layer_idx + 1 < num_layers {
            (coil.layer_idx, coil.layer_idx + 1)
        } else if coil.layer_idx > 0 {
            (coil.layer_idx - 1, coil.layer_idx)
        } else {
            return Err("Cannot assign an inter-layer via on a single-layer board".into());
        };
        for &(x, y) in &coil.center_via_positions {
            routing.vias.push(Via {
                position: Point::new(x, y),
                from_layer,
                to_layer,
                net: coil.phase_name.clone(),
            });
        }
    }
    let geometry = CadGeometry {
        routing,
        layer_z_mm,
        trace_width_mm,
        source_layer_coils: BTreeMap::new(),
        source_file_name: None,
        coil_terminals: BTreeMap::new(),
        terminal_connection: None,
        coil_phases: BTreeMap::new(),
    };
    validate_geometry(&geometry)?;
    Ok(geometry)
}

/// Import DXF lines, classic/lightweight polylines, and planar curves as centerlines.
///
/// Old app DXFs with 2D traces remain importable through their `L<idx>_<net>`
/// layer names. 2D via circles are deliberately reported because they do not
/// identify which copper planes the via connects.
pub fn import_3d_dxf(text: &str, options: CadImportOptions) -> Result<CadImportResult, String> {
    import_3d_dxf_with_coils(text, options, &BTreeMap::new())
}

/// Assign source DXF layers, including via layers, to coil identities.
/// Copper planes still come from Z, or named layer indices for legacy 2D files.
pub fn import_3d_dxf_with_coils(
    text: &str,
    options: CadImportOptions,
    assignments: &BTreeMap<String, String>,
) -> Result<CadImportResult, String> {
    if assignments.values().any(|coil| coil.trim().is_empty()) {
        return Err("Every source layer assignment needs a non-empty coil name".into());
    }
    if !options.units_to_mm.is_finite() || options.units_to_mm <= 0.0 {
        return Err("DXF unit conversion must be a positive finite value".into());
    }
    if !options.z_tolerance_mm.is_finite() || options.z_tolerance_mm < 0.0 {
        return Err("Z tolerance must be a non-negative finite value".into());
    }
    if !options.default_trace_width_mm.is_finite() || options.default_trace_width_mm <= 0.0 {
        return Err("Default trace width must be a positive finite value".into());
    }
    if !options.legacy_pcb_thickness_mm.is_finite() || options.legacy_pcb_thickness_mm < 0.0 {
        return Err("Legacy PCB thickness must be non-negative and finite".into());
    }
    let pairs = parse_pairs(text)?;
    // (kata chgg) Honour the drawing's declared units when asked, keeping the
    // caller's value as the fallback for unitless or unknown files.
    let source_units_mm = detect_source_units_mm(&pairs);
    let mut options = options;
    if options.prefer_detected_units {
        if let Some(scale) = source_units_mm {
            options.units_to_mm = scale;
        }
    }
    let embedded_width = pairs
        .iter()
        .find_map(|(code, value)| {
            if *code == 999 {
                value
                    .strip_prefix("pcbmotorgen:trace_width_mm=")?
                    .parse::<f64>()
                    .ok()
            } else {
                None
            }
        })
        .filter(|width| width.is_finite() && *width > 0.0)
        .map(|width| width * options.units_to_mm);
    let entities = entities_section(&pairs)?;
    let source_layer_coils = entities
        .iter()
        .filter(|e| {
            matches!(
                e.kind.as_str(),
                "LINE" | "ARC" | "SPLINE" | "POLYLINE" | "LWPOLYLINE"
            )
        })
        .map(|e| {
            let name = field(e, 8).unwrap_or("0");
            let coil = assignments
                .get(name)
                .map(|s| s.trim().to_string())
                .unwrap_or_else(|| decode_trace_layer(name).0);
            (name.to_string(), coil)
        })
        .collect::<BTreeMap<_, _>>();
    let mut warnings = Vec::new();
    let mut segments = Vec::new();
    let mut curves = Vec::new();
    let mut splines = Vec::new();
    let mut vias = Vec::new();
    let mut legacy_circles = 0usize;

    let mut entities = entities.into_iter().peekable();
    while let Some(entity) = entities.next() {
        let name = field(&entity, 8).unwrap_or("0");
        let (default_net, layer_hint) = decode_trace_layer(name);
        let net = source_layer_coils.get(name).cloned().unwrap_or(default_net);
        match entity.kind.as_str() {
            "POLYLINE" => {
                // Classic polylines store their points in following VERTEX
                // entities, terminated by SEQEND. Consume the sequence even
                // when unsupported so its records do not become extra warnings.
                let mut vertices = Vec::new();
                while entities.peek().is_some_and(|e| e.kind == "VERTEX") {
                    vertices.push(entities.next().unwrap());
                }
                if !entities.peek().is_some_and(|e| e.kind == "SEQEND") {
                    warnings.push(format!(
                        "Skipped malformed DXF POLYLINE on layer '{name}': missing SEQEND."
                    ));
                    continue;
                }
                entities.next();
                let flags = optional_number(&entity, 70).unwrap_or(0.0) as i32;
                if flags & (2 | 4 | 16 | 32 | 64) != 0 {
                    warnings.push(format!(
                        "Skipped unsupported fitted or mesh DXF POLYLINE on layer '{name}'."
                    ));
                    continue;
                }
                if [(210, 0.0), (220, 0.0), (230, 1.0)]
                    .iter()
                    .any(|&(code, default)| {
                        (optional_number(&entity, code).unwrap_or(default) - default).abs() > 1e-12
                    })
                {
                    warnings.push(format!(
                        "Skipped DXF POLYLINE with unsupported extrusion on layer '{name}'."
                    ));
                    continue;
                }
                if vertices.len() < 2 {
                    warnings.push(format!(
                        "Skipped malformed DXF POLYLINE on layer '{name}': fewer than two vertices."
                    ));
                    continue;
                }
                if vertices.iter().any(|v| {
                    optional_number(v, 70).unwrap_or(0.0) as i32 & (1 | 2 | 8 | 16 | 64 | 128) != 0
                        || optional_number(v, 42).unwrap_or(0.0).abs() > 1e-12
                }) {
                    warnings.push(format!(
                        "Skipped unsupported fitted, mesh, or bulged DXF POLYLINE vertices on layer '{name}'."
                    ));
                    continue;
                }
                let elevation = optional_number(&entity, 30).unwrap_or(0.0);
                let points = vertices
                    .iter()
                    .map(|v| {
                        Ok((
                            number(v, 10)? * options.units_to_mm,
                            number(v, 20)? * options.units_to_mm,
                            if flags & 8 != 0 {
                                optional_number(v, 30).unwrap_or(0.0)
                            } else {
                                elevation
                            } * options.units_to_mm,
                        ))
                    })
                    .collect::<Result<Vec<_>, String>>()?;
                let edge_count = points.len() - 1 + usize::from(flags & 1 != 0);
                for i in 0..edge_count {
                    let a = points[i];
                    let b = points[(i + 1) % points.len()];
                    let dz = b.2 - a.2;
                    if (b.0 - a.0).hypot(b.1 - a.1) <= options.z_tolerance_mm
                        && dz.abs() > options.z_tolerance_mm
                    {
                        vias.push(PendingVia {
                            x: (a.0 + b.0) / 2.0,
                            y: (a.1 + b.1) / 2.0,
                            z0: a.2,
                            z1: b.2,
                            net: net.clone(),
                        });
                    } else if dz.abs() <= options.z_tolerance_mm {
                        segments.push(PendingSegment {
                            start: Point::new(a.0, a.1),
                            end: Point::new(b.0, b.1),
                            z: (a.2 + b.2) / 2.0,
                            net: net.clone(),
                            layer_hint,
                        });
                    } else {
                        warnings.push(format!(
                            "Skipped non-planar DXF POLYLINE segment on layer '{name}'."
                        ));
                    }
                }
            }
            "SPLINE" => {
                let values = |code: i32| -> Result<Vec<f64>, String> {
                    entity
                        .fields
                        .iter()
                        .filter(|(c, _)| *c == code)
                        .map(|(_, v)| {
                            v.parse::<f64>()
                                .map_err(|_| "DXF SPLINE has invalid numeric data".to_string())
                        })
                        .collect()
                };
                let xs = values(10)?;
                let ys = values(20)?;
                let zs = values(30)?;
                if xs.len() != ys.len() || (!zs.is_empty() && zs.len() != xs.len()) {
                    return Err("DXF SPLINE has mismatched control point coordinates".into());
                }
                let z = zs.first().copied().unwrap_or(0.0) * options.units_to_mm;
                if zs.iter().any(|v| {
                    !v.is_finite() || (v * options.units_to_mm - z).abs() > options.z_tolerance_mm
                }) {
                    return Err(format!(
                        "Non-planar DXF SPLINE on layer '{name}' is not supported"
                    ));
                }
                let spline = RouteSpline {
                    degree: number(&entity, 71)? as usize,
                    knots: values(40)?,
                    weights: values(41)?,
                    control_points: xs
                        .iter()
                        .zip(ys)
                        .map(|(x, y)| Point::new(x * options.units_to_mm, y * options.units_to_mm))
                        .collect(),
                    layer: 0,
                    net,
                    is_active: true,
                };
                spline.validate()?;
                splines.push(PendingSpline {
                    spline,
                    z,
                    layer_hint,
                });
            }
            "LINE" => {
                let point = |x_code, y_code, z_code| -> Result<(f64, f64, f64), String> {
                    Ok((
                        number(&entity, x_code)? * options.units_to_mm,
                        number(&entity, y_code)? * options.units_to_mm,
                        optional_number(&entity, z_code).unwrap_or(0.0) * options.units_to_mm,
                    ))
                };
                let a = point(10, 20, 30)?;
                let b = point(11, 21, 31)?;
                let dx = b.0 - a.0;
                let dy = b.1 - a.1;
                let dz = b.2 - a.2;
                if dx.hypot(dy) <= options.z_tolerance_mm && dz.abs() > options.z_tolerance_mm {
                    vias.push(PendingVia {
                        x: (a.0 + b.0) / 2.0,
                        y: (a.1 + b.1) / 2.0,
                        z0: a.2,
                        z1: b.2,
                        net,
                    });
                } else if dz.abs() <= options.z_tolerance_mm {
                    segments.push(PendingSegment {
                        start: Point::new(a.0, a.1),
                        end: Point::new(b.0, b.1),
                        z: (a.2 + b.2) / 2.0,
                        net,
                        layer_hint,
                    });
                } else {
                    warnings.push(format!("Skipped non-planar DXF LINE on layer '{name}'."));
                }
            }
            "LWPOLYLINE" => {
                let xs: Vec<f64> = entity
                    .fields
                    .iter()
                    .filter(|(code, _)| *code == 10)
                    .map(|(_, value)| {
                        value
                            .parse::<f64>()
                            .map(|v| v * options.units_to_mm)
                            .map_err(|_| "DXF LWPOLYLINE has an invalid X coordinate".to_string())
                    })
                    .collect::<Result<_, _>>()?;
                let ys: Vec<f64> = entity
                    .fields
                    .iter()
                    .filter(|(code, _)| *code == 20)
                    .map(|(_, value)| {
                        value
                            .parse::<f64>()
                            .map(|v| v * options.units_to_mm)
                            .map_err(|_| "DXF LWPOLYLINE has an invalid Y coordinate".to_string())
                    })
                    .collect::<Result<_, _>>()?;
                if xs.len() != ys.len() || xs.len() < 2 {
                    warnings.push(format!(
                        "Skipped malformed DXF LWPOLYLINE on layer '{name}'."
                    ));
                    continue;
                }
                if entity.fields.iter().any(|(code, value)| {
                    *code == 42 && value.parse::<f64>().unwrap_or(0.0).abs() > 1e-12
                }) {
                    warnings.push(format!("LWPOLYLINE bulge/arc segments on layer '{name}' were imported as straight centerline chords."));
                }
                let z = optional_number(&entity, 38)
                    .or_else(|| optional_number(&entity, 30))
                    .unwrap_or(0.0)
                    * options.units_to_mm;
                let closed = optional_number(&entity, 70).unwrap_or(0.0) as i32 & 1 != 0;
                let edge_count = xs.len() - 1 + usize::from(closed);
                for i in 0..edge_count {
                    let j = (i + 1) % xs.len();
                    segments.push(PendingSegment {
                        start: Point::new(xs[i], ys[i]),
                        end: Point::new(xs[j], ys[j]),
                        z,
                        net: net.clone(),
                        layer_hint,
                    });
                }
            }
            "ARC" => {
                let cx = number(&entity, 10)? * options.units_to_mm;
                let cy = number(&entity, 20)? * options.units_to_mm;
                let z = optional_number(&entity, 30).unwrap_or(0.0) * options.units_to_mm;
                let radius = number(&entity, 40)? * options.units_to_mm;
                let start = number(&entity, 50)?.to_radians();
                let end = number(&entity, 51)?.to_radians();
                if radius <= 0.0 {
                    warnings.push(format!("Skipped degenerate DXF ARC on layer '{name}'."));
                    continue;
                }
                let sweep = (end - start).rem_euclid(std::f64::consts::TAU);
                let mid = start + sweep / 2.0;
                curves.push(PendingCurve {
                    start: Point::new(cx + radius * start.cos(), cy + radius * start.sin()),
                    mid: Point::new(cx + radius * mid.cos(), cy + radius * mid.sin()),
                    end: Point::new(cx + radius * end.cos(), cy + radius * end.sin()),
                    z,
                    net,
                    layer_hint,
                });
            }
            "CIRCLE" => {
                legacy_circles += 1;
            }
            other => warnings.push(format!(
                "Skipped unsupported DXF {other} entity on layer '{name}'."
            )),
        }
    }
    if legacy_circles > 0 {
        warnings.push(format!(
            "Skipped {legacy_circles} 2D circle(s); circles do not encode via layer spans."
        ));
    }
    if segments.is_empty() && curves.is_empty() && splines.is_empty() && vias.is_empty() {
        return Err("DXF contained no supported trace or via centerlines".into());
    }

    let heights: Vec<f64> = segments
        .iter()
        .map(|s| s.z)
        .chain(curves.iter().map(|c| c.z))
        .chain(splines.iter().map(|s| s.z))
        .chain(vias.iter().flat_map(|v| [v.z0, v.z1]))
        .collect();
    let has_explicit_z = heights.iter().any(|z| z.abs() > 1e-9);
    let legacy_2d = !has_explicit_z
        && vias.is_empty()
        && (segments.iter().any(|s| s.layer_hint.is_some())
            || curves.iter().any(|c| c.layer_hint.is_some())
            || splines.iter().any(|s| s.layer_hint.is_some()));
    let legacy_layers = options
        .legacy_layer_count
        .max(
            segments
                .iter()
                .filter_map(|s| s.layer_hint)
                .chain(curves.iter().filter_map(|c| c.layer_hint))
                .chain(splines.iter().filter_map(|s| s.layer_hint))
                .max()
                .map_or(1, |n| n + 1),
        )
        .max(1);
    let mut layer_z_mm = if legacy_2d {
        if legacy_layers == 1 {
            vec![0.0]
        } else {
            (0..legacy_layers)
                .map(|i| {
                    options.legacy_pcb_thickness_mm * (i as f64 / (legacy_layers - 1) as f64 - 1.0)
                })
                .collect()
        }
    } else {
        cluster_heights(&heights, options.z_tolerance_mm)
    };
    if legacy_2d {
        warnings.push("Imported legacy 2D DXF: layer names were used; Z heights were synthesized from the current PCB thickness.".into());
    }
    let layer_for = |z: f64| nearest_height(&layer_z_mm, z);
    let mut routing = RoutingResult::default();
    for segment in segments {
        let layer = if legacy_2d {
            segment.layer_hint.unwrap_or(0)
        } else {
            layer_for(segment.z)
        };
        let layer = reconcile_layer_hint(layer, segment.layer_hint, &mut warnings);
        routing.segments.push(RouteSegment {
            start: segment.start,
            end: segment.end,
            layer,
            net: segment.net,
            is_active: true,
        });
    }
    for curve in curves {
        let layer = if legacy_2d {
            curve.layer_hint.unwrap_or(0)
        } else {
            layer_for(curve.z)
        };
        let layer = reconcile_layer_hint(layer, curve.layer_hint, &mut warnings);
        routing.curves.push(RouteCurve {
            start: curve.start,
            mid: curve.mid,
            end: curve.end,
            layer,
            net: curve.net,
            is_active: true,
        });
    }
    for mut pending in splines {
        let layer = if legacy_2d {
            pending.layer_hint.unwrap_or(0)
        } else {
            layer_for(pending.z)
        };
        pending.spline.layer = reconcile_layer_hint(layer, pending.layer_hint, &mut warnings);
        routing.splines.push(pending.spline);
    }
    for via in vias {
        let from_layer = layer_for(via.z0);
        let to_layer = layer_for(via.z1);
        if from_layer == to_layer {
            warnings.push("Skipped vertical line whose endpoints fall on the same Z layer.".into());
            continue;
        }
        routing.vias.push(Via {
            position: Point::new(via.x, via.y),
            from_layer,
            to_layer,
            net: via.net,
        });
    }
    for via in &routing.vias {
        for endpoint in [via.from_layer, via.to_layer] {
            let connected = routing.segments.iter().any(|segment| {
                segment.layer == endpoint
                    && segment.net == via.net
                    && (segment.start.distance_to(via.position) <= options.z_tolerance_mm
                        || segment.end.distance_to(via.position) <= options.z_tolerance_mm)
            }) || routing.curves.iter().any(|curve| {
                curve.layer == endpoint
                    && curve.net == via.net
                    && (curve.start.distance_to(via.position) <= options.z_tolerance_mm
                        || curve.end.distance_to(via.position) <= options.z_tolerance_mm)
            }) || routing.splines.iter().any(|spline| {
                spline.layer == endpoint
                    && spline.net == via.net
                    && [
                        spline.knots[spline.degree],
                        spline.knots[spline.control_points.len()],
                    ]
                    .iter()
                    .any(|&t| {
                        spline.point_at(t).distance_to(via.position) <= options.z_tolerance_mm
                    })
            });
            if !connected {
                warnings.push(format!(
                    "Via at ({:.3}, {:.3}) mm has no matching trace endpoint on layer {endpoint}.",
                    via.position.x, via.position.y
                ));
            }
        }
    }
    if !warnings.is_empty() {
        warnings.sort();
        warnings.dedup();
    }
    // Normalize the physical top copper plane to the DXF/app Z origin. Keep
    // layer indices bottom-to-top, matching the KiCad mapping.
    if let Some(top_z) = layer_z_mm.last().copied() {
        for z in &mut layer_z_mm {
            *z -= top_z;
        }
    }
    let geometry = CadGeometry {
        routing,
        layer_z_mm,
        trace_width_mm: embedded_width.unwrap_or(options.default_trace_width_mm),
        source_layer_coils,
        source_file_name: None,
        coil_terminals: BTreeMap::new(),
        terminal_connection: None,
        coil_phases: BTreeMap::new(),
    };
    validate_geometry(&geometry)?;
    Ok(CadImportResult { geometry, warnings, units_to_mm: options.units_to_mm, source_units_mm })
}

fn validate_geometry(geometry: &CadGeometry) -> Result<(), String> {
    if geometry.layer_z_mm.is_empty() {
        return Err("CAD geometry needs at least one layer height".into());
    }
    if !geometry.trace_width_mm.is_finite() || geometry.trace_width_mm <= 0.0 {
        return Err("Trace width must be positive and finite".into());
    }
    if geometry.layer_z_mm.iter().any(|z| !z.is_finite()) {
        return Err("Layer heights must be finite".into());
    }
    for layer in geometry
        .routing
        .segments
        .iter()
        .map(|s| s.layer)
        .chain(geometry.routing.curves.iter().map(|c| c.layer))
        .chain(geometry.routing.splines.iter().map(|s| s.layer))
        .chain(
            geometry
                .routing
                .vias
                .iter()
                .flat_map(|v| [v.from_layer, v.to_layer]),
        )
    {
        if layer as usize >= geometry.layer_z_mm.len() {
            return Err(format!("Geometry refers to missing layer {layer}"));
        }
    }
    let finite_point = |p: Point| p.x.is_finite() && p.y.is_finite();
    for spline in &geometry.routing.splines {
        spline.validate()?;
    }
    if geometry
        .routing
        .segments
        .iter()
        .any(|s| !finite_point(s.start) || !finite_point(s.end))
        || geometry
            .routing
            .curves
            .iter()
            .any(|c| !finite_point(c.start) || !finite_point(c.mid) || !finite_point(c.end))
        || geometry
            .routing
            .vias
            .iter()
            .any(|v| !finite_point(v.position))
    {
        return Err("CAD geometry coordinates must be finite".into());
    }
    for (coil, phase) in &geometry.coil_phases {
        let phase = phase.trim();
        if !phase.is_empty() && !pcbmotorgen_routing::PHASE_NAMES.contains(&phase) {
            return Err(format!("Coil '{coil}' has unknown phase '{phase}'"));
        }
    }
    for (coil, terminals) in &geometry.coil_terminals {
        for (label, terminal) in [("IN", &terminals.input), ("OUT", &terminals.output)] {
            if !finite_point(terminal.position)
                || terminal.layer as usize >= geometry.layer_z_mm.len()
            {
                return Err(format!(
                    "Coil '{coil}' {label} terminal has invalid coordinates or copper layer"
                ));
            }
            let matches = |point: Point| point.distance_to(terminal.position) <= 1e-9;
            let endpoint = geometry.routing.segments.iter().any(|s| {
                s.net == *coil && s.layer == terminal.layer && (matches(s.start) || matches(s.end))
            }) || geometry.routing.curves.iter().any(|s| {
                s.net == *coil && s.layer == terminal.layer && (matches(s.start) || matches(s.end))
            }) || geometry.routing.splines.iter().any(|s| {
                s.net == *coil
                    && s.layer == terminal.layer
                    && (matches(s.point_at(s.knots[s.degree]))
                        || matches(s.point_at(s.knots[s.control_points.len()])))
            });
            if !endpoint {
                return Err(format!(
                    "Coil '{coil}' {label} terminal must be a trace endpoint on its copper layer"
                ));
            }
        }
        if terminals.input.layer == terminals.output.layer
            && terminals
                .input
                .position
                .distance_to(terminals.output.position)
                <= 1e-9
        {
            return Err(format!(
                "Coil '{coil}' IN and OUT must be different endpoints"
            ));
        }
    }
    Ok(())
}

fn safe_layer_part(value: &str) -> String {
    let cleaned: String = value
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect();
    if cleaned.is_empty() {
        "Imported".into()
    } else {
        cleaned
    }
}

fn write_3d_spline(out: &mut Vec<String>, layer: &str, spline: &RouteSpline, z: f64) {
    groups::dxf_group(out, 0, "SPLINE");
    groups::dxf_group(out, 100, "AcDbEntity");
    groups::dxf_group(out, 8, layer);
    groups::dxf_group(out, 100, "AcDbSpline");
    groups::dxf_group(out, 70, if spline.weights.is_empty() { "8" } else { "12" });
    groups::dxf_group(out, 71, &spline.degree.to_string());
    groups::dxf_group(out, 72, &spline.knots.len().to_string());
    groups::dxf_group(out, 73, &spline.control_points.len().to_string());
    groups::dxf_group(out, 74, "0");
    for knot in &spline.knots {
        groups::dxf_group(out, 40, &knot.to_string());
    }
    for weight in &spline.weights {
        groups::dxf_group(out, 41, &weight.to_string());
    }
    for p in &spline.control_points {
        groups::dxf_group(out, 10, &format!("{:.12}", p.x));
        groups::dxf_group(out, 20, &format!("{:.12}", p.y));
        groups::dxf_group(out, 30, &format!("{z:.12}"));
    }
}

fn write_3d_line(
    out: &mut Vec<String>,
    layer: &str,
    a: (f64, f64, f64),
    b: (f64, f64, f64),
    modern: bool,
) {
    groups::dxf_group(out, 0, "LINE");
    if modern {
        groups::dxf_group(out, 100, "AcDbEntity");
    }
    groups::dxf_group(out, 8, layer);
    if modern {
        groups::dxf_group(out, 100, "AcDbLine");
    }
    groups::dxf_group_f64(out, 10, a.0);
    groups::dxf_group_f64(out, 20, a.1);
    groups::dxf_group_f64(out, 30, a.2);
    groups::dxf_group_f64(out, 11, b.0);
    groups::dxf_group_f64(out, 21, b.1);
    groups::dxf_group_f64(out, 31, b.2);
}

fn write_3d_arc(
    out: &mut Vec<String>,
    layer: &str,
    a: (f64, f64),
    m: (f64, f64),
    b: (f64, f64),
    z: f64,
    modern: bool,
) {
    let (ax, ay) = a;
    let (mx, my) = m;
    let (bx, by) = b;
    let d = 2.0 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my));
    if d.abs() < 1e-12 {
        write_3d_line(out, layer, (ax, ay, z), (bx, by, z), modern);
        return;
    }
    let aa = ax * ax + ay * ay;
    let mm = mx * mx + my * my;
    let bb = bx * bx + by * by;
    let cx = (aa * (my - by) + mm * (by - ay) + bb * (ay - my)) / d;
    let cy = (aa * (bx - mx) + mm * (ax - bx) + bb * (mx - ax)) / d;
    let angle = |p: (f64, f64)| (p.1 - cy).atan2(p.0 - cx).to_degrees().rem_euclid(360.0);
    let mut start = angle(a);
    let mut end = angle(b);
    let mid = angle(m);
    let ccw = (end - start).rem_euclid(360.0);
    if (mid - start).rem_euclid(360.0) > ccw {
        std::mem::swap(&mut start, &mut end);
    }
    groups::dxf_group(out, 0, "ARC");
    if modern {
        groups::dxf_group(out, 100, "AcDbEntity");
    }
    groups::dxf_group(out, 8, layer);
    if modern {
        groups::dxf_group(out, 100, "AcDbCircle");
    }
    groups::dxf_group_f64(out, 10, cx);
    groups::dxf_group_f64(out, 20, cy);
    groups::dxf_group_f64(out, 30, z);
    groups::dxf_group_f64(out, 40, (ax - cx).hypot(ay - cy));
    if modern {
        groups::dxf_group(out, 100, "AcDbArc");
    }
    groups::dxf_group_f64(out, 50, start);
    groups::dxf_group_f64(out, 51, end);
}

fn parse_pairs(text: &str) -> Result<Vec<(i32, String)>, String> {
    let lines: Vec<&str> = text.lines().collect();
    if lines.len() % 2 != 0 {
        return Err("Malformed DXF: group code without a value".into());
    }
    lines
        .chunks_exact(2)
        .map(|pair| {
            let code = pair[0]
                .trim()
                .parse::<i32>()
                .map_err(|_| format!("Malformed DXF group code '{}'", pair[0].trim()))?;
            Ok((code, pair[1].trim().to_string()))
        })
        .collect()
}

fn entities_section(pairs: &[(i32, String)]) -> Result<Vec<Entity>, String> {
    let mut inside = false;
    let mut found = false;
    let mut entities = Vec::new();
    let mut current: Option<Entity> = None;
    let mut i = 0;
    while i < pairs.len() {
        let (code, value) = &pairs[i];
        if *code == 0
            && value == "SECTION"
            && pairs
                .get(i + 1)
                .is_some_and(|p| p.0 == 2 && p.1 == "ENTITIES")
        {
            inside = true;
            found = true;
            i += 2;
            continue;
        }
        if inside && *code == 0 && value == "ENDSEC" {
            if let Some(e) = current.take() {
                entities.push(e);
            }
            break;
        }
        if inside && *code == 0 {
            if let Some(e) = current.take() {
                entities.push(e);
            }
            current = Some(Entity {
                kind: value.clone(),
                fields: Vec::new(),
            });
        } else if inside {
            if let Some(e) = &mut current {
                e.fields.push((*code, value.clone()));
            }
        }
        i += 1;
    }
    if !found {
        return Err("DXF has no ENTITIES section".into());
    }
    Ok(entities)
}

fn field(entity: &Entity, code: i32) -> Option<&str> {
    entity
        .fields
        .iter()
        .find(|(c, _)| *c == code)
        .map(|(_, v)| v.as_str())
}
fn number(entity: &Entity, code: i32) -> Result<f64, String> {
    let value = field(entity, code)
        .ok_or_else(|| format!("DXF {} is missing coordinate group {code}", entity.kind))?
        .parse::<f64>()
        .map_err(|_| format!("DXF {} has an invalid number in group {code}", entity.kind))?;
    if !value.is_finite() {
        return Err(format!(
            "DXF {} has a non-finite number in group {code}",
            entity.kind
        ));
    }
    Ok(value)
}
fn optional_number(entity: &Entity, code: i32) -> Option<f64> {
    field(entity, code)
        .and_then(|v| v.parse::<f64>().ok())
        .filter(|v| v.is_finite())
}

fn decode_trace_layer(layer: &str) -> (String, Option<u32>) {
    if let Some(rest) = layer.strip_prefix('L') {
        if let Some((idx, net)) = rest.split_once('_') {
            if let Ok(idx) = idx.parse::<u32>() {
                return (net.to_string(), Some(idx));
            }
        }
    }
    if let Some(rest) = layer.strip_prefix("Via_L") {
        if let Some((_, net)) = rest.split_once('_') {
            if let Some((_, net)) = net.split_once('_') {
                return (net.to_string(), None);
            }
        }
    }
    (
        if layer == "0" {
            "Imported".into()
        } else {
            layer.into()
        },
        None,
    )
}

fn cluster_heights(values: &[f64], tolerance: f64) -> Vec<f64> {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let mut groups: Vec<Vec<f64>> = Vec::new();
    for z in sorted {
        if let Some(group) = groups.last_mut() {
            let center = median(group);
            if (z - center).abs() <= tolerance {
                group.push(z);
                continue;
            }
        }
        groups.push(vec![z]);
    }
    groups.into_iter().map(|g| median(&g)).collect()
}
fn median(sorted: &[f64]) -> f64 {
    let middle = sorted.len() / 2;
    if sorted.len() % 2 == 0 {
        sorted[middle - 1] + (sorted[middle] - sorted[middle - 1]) / 2.0
    } else {
        sorted[middle]
    }
}
fn nearest_height(heights: &[f64], z: f64) -> u32 {
    heights
        .iter()
        .enumerate()
        .min_by(|(_, a), (_, b)| (z - **a).abs().total_cmp(&(z - **b).abs()))
        .map(|(i, _)| i as u32)
        .unwrap_or(0)
}
fn reconcile_layer_hint(z_layer: u32, hint: Option<u32>, warnings: &mut Vec<String>) -> u32 {
    if let Some(hint) = hint {
        if hint != z_layer {
            warnings.push(format!("DXF layer name suggested copper index {hint}, but Z maps to index {z_layer}; used Z."));
        }
    }
    z_layer
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sensor_dxf_preserves_editable_splines_arcs_and_layer_transitions() {
        let sensor =
            pcbmotorgen_routing::generate_sensor(&pcbmotorgen_routing::SensorConfig::default())
                .unwrap();
        let geometry = sensor_geometry_to_cad_geometry(&sensor);
        let text = cad_geometry_to_3d_dxf(&geometry).unwrap();
        assert!(text.contains("$ACADVER\n1\nAC1015"));
        assert!(text.contains("100\nAcDbSpline"));
        assert!(text.contains("100\nAcDbArc"));
        assert_eq!(text.matches("0\nSPLINE\n").count(), 28);
        assert_eq!(text.matches("0\nARC\n").count(), 2);
        assert_eq!(text.matches("0\nLINE\n").count(), 110);
        let imported = import_3d_dxf(
            &text,
            CadImportOptions {
                units_to_mm: 1.0,
                z_tolerance_mm: 0.01,
                default_trace_width_mm: 0.15,
                legacy_layer_count: 2,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        assert!(imported.warnings.is_empty(), "{:?}", imported.warnings);
        assert_eq!(imported.geometry.layer_z_mm, vec![-1.6, 0.0]);
        assert_eq!(imported.geometry.routing.splines.len(), 28);
        assert_eq!(imported.geometry.routing.curves.len(), 2);
        assert_eq!(imported.geometry.routing.vias.len(), 27);
        for (a, b) in geometry
            .routing
            .splines
            .iter()
            .zip(&imported.geometry.routing.splines)
        {
            assert_eq!(a.knots, b.knots);
            assert_eq!(a.layer, b.layer);
            assert_eq!(a.net, b.net);
            assert_eq!(a.control_points.len(), b.control_points.len());
            for i in 0..=100 {
                assert!(
                    a.point_at(i as f64 / 100.0)
                        .distance_to(b.point_at(i as f64 / 100.0))
                        < 1e-9
                );
            }
        }
        let again = cad_geometry_to_3d_dxf(&imported.geometry).unwrap();
        assert_eq!(again.matches("0\nSPLINE\n").count(), 28);
        assert_eq!(again.matches("0\nLINE\n").count(), 110);
    }

    #[test]
    fn spline_only_dxf_round_trips_rational_control_points_with_unit_conversion() {
        let spline = RouteSpline {
            degree: 2,
            knots: vec![0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
            control_points: vec![
                Point::new(1.0, 0.0),
                Point::new(1.0, 1.0),
                Point::new(0.0, 1.0),
            ],
            weights: vec![1.0, 0.5_f64.sqrt(), 1.0],
            layer: 0,
            net: "RX".into(),
            is_active: true,
        };
        let geometry = CadGeometry {
            routing: RoutingResult {
                splines: vec![spline.clone()],
                ..RoutingResult::default()
            },
            layer_z_mm: vec![-1.0],
            trace_width_mm: 0.15,
            source_layer_coils: BTreeMap::new(),
            source_file_name: None,
            coil_terminals: BTreeMap::new(),
            terminal_connection: None,
            coil_phases: BTreeMap::new(),
        };
        let text = cad_geometry_to_3d_dxf(&geometry).unwrap();
        let imported = import_3d_dxf(
            &text,
            CadImportOptions {
                units_to_mm: 25.4,
                z_tolerance_mm: 0.01,
                default_trace_width_mm: 0.15,
                legacy_layer_count: 1,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        let curve = &imported.geometry.routing.splines[0];
        assert!(imported.geometry.routing.segments.is_empty());
        assert_eq!(curve.knots, spline.knots);
        assert_eq!(curve.weights, spline.weights);
        assert!((curve.point_at(0.5).x - 25.4 * 0.5_f64.sqrt()).abs() < 1e-9);
    }

    #[test]
    fn insunits_detection_scales_and_preserves_an_explicit_override() {
        let dxf = "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n1\n0\nENDSEC\n\
0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nL0_A\n10\n0\n20\n0\n30\n0\n11\n1\n21\n0\n31\n0\n0\nENDSEC\n0\nEOF\n";
        let options = |units_to_mm, prefer_detected_units| CadImportOptions {
            units_to_mm,
            z_tolerance_mm: 0.01,
            default_trace_width_mm: 0.15,
            legacy_layer_count: 2,
            legacy_pcb_thickness_mm: 1.6,
            prefer_detected_units,
        };
        // Auto uses the declared inches; the numbers are preserved in mm.
        let auto = import_3d_dxf(dxf, options(1.0, true)).unwrap();
        assert_eq!(auto.source_units_mm, Some(25.4));
        assert_eq!(auto.units_to_mm, 25.4);
        assert!((auto.geometry.routing.segments[0].end.x - 25.4).abs() < 1e-9);
        // An explicit choice overrides the header value.
        let forced = import_3d_dxf(dxf, options(1.0, false)).unwrap();
        assert_eq!(forced.units_to_mm, 1.0);
        assert!((forced.geometry.routing.segments[0].end.x - 1.0).abs() < 1e-9);
        // Unitless and unknown codes are reported as no detection.
        for code in ["0", "999"] {
            let unitless = dxf.replace("\n70\n1\n", &format!("\n70\n{code}\n"));
            let imported = import_3d_dxf(&unitless, options(2.0, true)).unwrap();
            assert_eq!(imported.source_units_mm, None);
            assert_eq!(imported.units_to_mm, 2.0);
        }
        assert_eq!(dxf_insunits_to_mm(4), Some(1.0));
        assert_eq!(dxf_insunits_to_mm(9), Some(0.0254));
        assert_eq!(dxf_insunits_to_mm(0), None);
    }

    fn sample() -> CadGeometry {
        let mut routing = RoutingResult::default();
        routing.segments.push(RouteSegment {
            start: Point::new(1.0, 2.0),
            end: Point::new(8.0, 2.0),
            layer: 0,
            net: "A".into(),
            is_active: true,
        });
        routing.segments.push(RouteSegment {
            start: Point::new(8.0, 2.0),
            end: Point::new(8.0, 4.0),
            layer: 1,
            net: "A".into(),
            is_active: true,
        });
        routing.curves.push(RouteCurve {
            start: Point::new(0.0, 0.0),
            mid: Point::new(1.0, 1.0),
            end: Point::new(2.0, 0.0),
            layer: 1,
            net: "A".into(),
            is_active: false,
        });
        routing.vias.push(Via {
            position: Point::new(8.0, 2.0),
            from_layer: 0,
            to_layer: 1,
            net: "A".into(),
        });
        CadGeometry {
            routing,
            layer_z_mm: vec![-1.6, 0.0],
            trace_width_mm: 0.2,
            source_layer_coils: BTreeMap::new(),
            source_file_name: None,
            coil_terminals: BTreeMap::new(),
            terminal_connection: None,
            coil_phases: BTreeMap::new(),
        }
    }

    #[test]
    fn three_dimensional_dxf_round_trips_trace_layers_and_vias() {
        let source = sample();
        let dxf = cad_geometry_to_3d_dxf(&source).unwrap();
        assert!(dxf.contains("0\nLINE\n"));
        assert!(dxf.contains("31\n0"));
        let imported = import_3d_dxf(
            &dxf,
            CadImportOptions {
                units_to_mm: 1.0,
                z_tolerance_mm: 0.001,
                default_trace_width_mm: 0.2,
                legacy_layer_count: 2,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        assert_eq!(imported.geometry.layer_z_mm, source.layer_z_mm);
        assert_eq!(imported.geometry.trace_width_mm, source.trace_width_mm);
        assert_eq!(imported.geometry.routing.segments.len(), 2);
        assert_eq!(imported.geometry.routing.curves.len(), 1);
        assert!((imported.geometry.routing.curves[0].mid.y - 1.0).abs() < 1e-9);
        assert_eq!(imported.geometry.routing.vias.len(), 1);
        assert_eq!(imported.geometry.routing.vias[0].from_layer, 0);
        assert_eq!(imported.geometry.routing.vias[0].to_layer, 1);
        assert_eq!(imported.geometry.routing.vias[0].net, "A");
        assert_eq!(
            imported.geometry.routing.segments[0].start,
            source.routing.segments[0].start
        );
        assert!(
            imported.warnings.is_empty(),
            "unexpected import warnings: {:?}",
            imported.warnings
        );
    }

    #[test]
    fn source_filename_is_preserved_in_json_and_optional_for_legacy_geometry() {
        let mut geometry = sample();
        geometry.source_file_name = Some("motor-coils.dxf".into());
        let json = serde_json::to_string(&geometry).unwrap();
        let loaded: CadGeometry = serde_json::from_str(&json).unwrap();
        assert_eq!(loaded.source_file_name.as_deref(), Some("motor-coils.dxf"));

        let mut legacy = serde_json::to_value(&geometry).unwrap();
        legacy.as_object_mut().unwrap().remove("source_file_name");
        let loaded: CadGeometry = serde_json::from_value(legacy).unwrap();
        assert_eq!(loaded.source_file_name, None);
        assert!(!serde_json::to_value(sample())
            .unwrap()
            .as_object()
            .unwrap()
            .contains_key("source_file_name"));
    }

    #[test]
    fn explicit_terminals_round_trip_in_projects_and_validate_coil_and_layer() {
        let mut geometry = sample();
        geometry.terminal_connection = Some(TerminalConnection::Delta);
        geometry.coil_terminals.insert(
            "A".into(),
            CadCoilTerminals {
                input: CadTerminal {
                    position: Point::new(1.0, 2.0),
                    layer: 0,
                },
                output: CadTerminal {
                    position: Point::new(8.0, 4.0),
                    layer: 1,
                },
            },
        );
        validate_geometry(&geometry).unwrap();
        let json = serde_json::to_string(&geometry).unwrap();
        assert_eq!(
            serde_json::from_str::<CadGeometry>(&json).unwrap(),
            geometry
        );
        let mut legacy: serde_json::Value = serde_json::from_str(&json).unwrap();
        legacy.as_object_mut().unwrap().remove("coil_terminals");
        legacy.as_object_mut().unwrap().remove("terminal_connection");
        assert_eq!(
            serde_json::from_value::<CadGeometry>(legacy.clone())
                .unwrap()
                .terminal_connection,
            None
        );
        assert!(serde_json::from_value::<CadGeometry>(legacy)
            .unwrap()
            .coil_terminals
            .is_empty());
        let mut bad = geometry.clone();
        bad.coil_terminals.get_mut("A").unwrap().input.layer = 1;
        assert!(validate_geometry(&bad)
            .unwrap_err()
            .contains("trace endpoint"));
        let mut bad = geometry.clone();
        let pair = bad.coil_terminals.get_mut("A").unwrap();
        pair.output = pair.input.clone();
        assert!(validate_geometry(&bad)
            .unwrap_err()
            .contains("different endpoints"));
        let mut bad = geometry.clone();
        bad.coil_terminals.get_mut("A").unwrap().input.position.x = f64::NAN;
        assert!(validate_geometry(&bad).is_err());
        let mut bad = geometry.clone();
        let pair = bad.coil_terminals.remove("A").unwrap();
        bad.coil_terminals.insert("B".into(), pair);
        assert!(validate_geometry(&bad)
            .unwrap_err()
            .contains("trace endpoint"));
    }

    #[test]
    fn clusters_small_z_deviations_and_reports_legacy_circles() {
        let dxf = "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nL0_A\n10\n0\n20\n0\n30\n0.001\n11\n1\n21\n0\n31\n0.002\n0\nCIRCLE\n8\nVia\n10\n1\n20\n0\n40\n0.2\n0\nENDSEC\n0\nEOF\n";
        let imported = import_3d_dxf(
            dxf,
            CadImportOptions {
                units_to_mm: 1.0,
                z_tolerance_mm: 0.01,
                default_trace_width_mm: 0.15,
                legacy_layer_count: 4,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        assert_eq!(imported.geometry.layer_z_mm.len(), 1);
        assert!(imported.warnings.iter().any(|w| w.contains("2D circle")));
    }

    #[test]
    fn imports_legacy_named_layers_and_synthesizes_z_from_board_thickness() {
        let dxf = "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nL0_A\n10\n0\n20\n0\n11\n1\n21\n0\n0\nLINE\n8\nL3_B\n10\n0\n20\n1\n11\n1\n21\n1\n0\nENDSEC\n0\nEOF\n";
        let imported = import_3d_dxf(
            dxf,
            CadImportOptions {
                units_to_mm: 1.0,
                z_tolerance_mm: 0.01,
                default_trace_width_mm: 0.15,
                legacy_layer_count: 4,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        assert_eq!(imported.geometry.layer_z_mm.len(), 4);
        assert!((imported.geometry.layer_z_mm[0] + 1.6).abs() < 1e-12);
        assert_eq!(imported.geometry.layer_z_mm[3], 0.0);
        assert_eq!(imported.geometry.routing.segments[0].layer, 0);
        assert_eq!(imported.geometry.routing.segments[1].layer, 3);
        assert!(imported
            .warnings
            .iter()
            .any(|w| w.contains("legacy 2D DXF")));
    }

    #[test]
    fn imports_lightweight_polyline_as_connected_segments() {
        let dxf = "0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n8\nL0_A\n90\n3\n70\n0\n38\n0.5\n10\n0\n20\n0\n10\n1\n20\n0\n10\n1\n20\n1\n0\nLINE\n8\nL1_B\n10\n0\n20\n2\n30\n1\n11\n1\n21\n2\n31\n1\n0\nENDSEC\n0\nEOF\n";
        let imported = import_3d_dxf(
            dxf,
            CadImportOptions {
                units_to_mm: 1.0,
                z_tolerance_mm: 0.001,
                default_trace_width_mm: 0.15,
                legacy_layer_count: 2,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap();
        assert_eq!(imported.geometry.routing.segments.len(), 3);
        assert_eq!(imported.geometry.layer_z_mm, vec![-0.5, 0.0]);
        assert_eq!(
            imported.geometry.routing.segments[0].end,
            imported.geometry.routing.segments[1].start
        );
    }

    fn import_polyline_fixture(entities: &str) -> CadImportResult {
        import_3d_dxf(
            &format!("0\nSECTION\n2\nENTITIES\n{entities}0\nENDSEC\n0\nEOF\n"),
            CadImportOptions {
                units_to_mm: 2.0,
                z_tolerance_mm: 0.001,
                default_trace_width_mm: 0.4,
                legacy_layer_count: 2,
                legacy_pcb_thickness_mm: 1.6,
                prefer_detected_units: false,
            },
        )
        .unwrap()
    }

    #[test]
    fn imports_rhino_two_point_classic_polyline_leads() {
        // Minimal AcDb2dPolyline records matching the missing Rhino input leads.
        let mut entities = String::new();
        for (net, x) in [("A", "4.333333"), ("B", "6.333333")] {
            entities.push_str(&format!(
                "0\nPOLYLINE\n100\nAcDbEntity\n8\nL1_{net}\n100\nAcDb2dPolyline\n66\n1\n10\n0\n20\n0\n30\n0\n0\nVERTEX\n8\nL1_{net}\n100\nAcDbVertex\n100\nAcDb2dVertex\n10\n{x}\n20\n8\n30\n0\n0\nVERTEX\n8\nL1_{net}\n10\n{x}\n20\n8.444444\n30\n0\n0\nSEQEND\n8\nL1_{net}\n"
            ));
        }
        let imported = import_polyline_fixture(&entities);
        assert_eq!(imported.geometry.routing.segments.len(), 2);
        for (segment, net, x) in [
            (&imported.geometry.routing.segments[0], "A", 4.333333),
            (&imported.geometry.routing.segments[1], "B", 6.333333),
        ] {
            assert_eq!(segment.net, net);
            assert_eq!(segment.layer, 1);
            assert_eq!(segment.start, Point::new(x * 2.0, 16.0));
            assert_eq!(segment.end, Point::new(x * 2.0, 16.888888));
        }
        assert!(!imported.warnings.iter().any(|w| w.contains("unsupported")));
    }

    #[test]
    fn assigns_nonstandard_trace_and_via_layers_to_separate_coils() {
        let mut records = Vec::new();
        for (coil, x) in [("A", 0.0), ("B", 2.0)] {
            write_3d_line(
                &mut records,
                &format!("bottom-{coil}"),
                (x, 0.0, -1.6),
                (x, 1.0, -1.6),
                true,
            );
            write_3d_line(
                &mut records,
                &format!("top-{coil}"),
                (x, 1.0, 0.0),
                (x, 2.0, 0.0),
                true,
            );
            write_3d_line(
                &mut records,
                &format!("holes-{coil}"),
                (x, 1.0, -1.6),
                (x, 1.0, 0.0),
                true,
            );
        }
        let text = format!(
            "0\nSECTION\n2\nENTITIES\n{}\n0\nENDSEC\n0\nEOF\n",
            records.join("\n")
        );
        let assignments = BTreeMap::from([
            ("bottom-A".into(), "A".into()),
            ("top-A".into(), "A".into()),
            ("holes-A".into(), "A".into()),
            ("bottom-B".into(), "B".into()),
            ("top-B".into(), "B".into()),
            ("holes-B".into(), "B".into()),
        ]);
        let options = CadImportOptions {
            units_to_mm: 1.0,
            z_tolerance_mm: 0.01,
            default_trace_width_mm: 0.4,
            legacy_layer_count: 2,
            legacy_pcb_thickness_mm: 1.6,
            prefer_detected_units: false,
        };
        let imported = import_3d_dxf_with_coils(&text, options, &assignments).unwrap();
        assert!(imported.warnings.is_empty());
        assert_eq!(imported.geometry.routing.segments.len(), 4);
        assert_eq!(imported.geometry.routing.vias.len(), 2);
        assert_eq!(imported.geometry.source_layer_coils, assignments);
        assert_eq!(
            imported
                .geometry
                .routing
                .segments
                .iter()
                .map(|s| s.net.as_str())
                .collect::<Vec<_>>(),
            vec!["A", "A", "B", "B"]
        );
        assert_eq!(imported.geometry.routing.vias[1].net, "B");
        assert_eq!(imported.geometry.routing.vias[1].to_layer, 1);
        let saved = serde_json::to_string(&imported.geometry).unwrap();
        assert_eq!(
            serde_json::from_str::<CadGeometry>(&saved).unwrap(),
            imported.geometry
        );
        let mut legacy: serde_json::Value = serde_json::from_str(&saved).unwrap();
        legacy.as_object_mut().unwrap().remove("source_layer_coils");
        assert!(serde_json::from_value::<CadGeometry>(legacy)
            .unwrap()
            .source_layer_coils
            .is_empty());
        assert!(import_3d_dxf_with_coils(
            &text,
            options,
            &BTreeMap::from([("top-A".into(), " ".into())])
        )
        .is_err());
        let unassigned = import_3d_dxf(&text, options).unwrap();
        assert_eq!(unassigned.geometry.routing.segments[0].net, "bottom-A");
        assert_eq!(unassigned.geometry.routing.vias[0].net, "holes-A");
    }

    #[test]
    fn standard_layer_names_preserve_coils_across_copper_planes_and_export() {
        let imported = import_polyline_fixture("0\nLINE\n8\nL0_A\n10\n0\n20\n0\n30\n-1\n11\n1\n21\n0\n31\n-1\n0\nLINE\n8\nL1_A\n10\n1\n20\n0\n30\n0\n11\n2\n21\n0\n31\n0\n0\nLINE\n8\nVia_L0_L1_A\n10\n1\n20\n0\n30\n-1\n11\n1\n21\n0\n31\n0\n0\nLINE\n8\nL0_B\n10\n0\n20\n2\n30\n-1\n11\n1\n21\n2\n31\n-1\n");
        assert!(imported.warnings.is_empty());
        assert_eq!(imported.geometry.source_layer_coils["Via_L0_L1_A"], "A");
        assert_eq!(imported.geometry.source_layer_coils["L0_B"], "B");
        assert_eq!(imported.geometry.routing.segments[2].net, "B");
        let exported = cad_geometry_to_3d_dxf(&imported.geometry).unwrap();
        assert!(exported.contains("L0_B"));
        assert!(exported.contains("Via_L0_L1_A"));
    }

    #[test]
    fn imports_closed_classic_polyline_with_header_elevation() {
        let imported = import_polyline_fixture("0\nPOLYLINE\n8\nL0_A\n70\n1\n30\n0.5\n0\nVERTEX\n10\n0\n20\n0\n30\n0\n0\nVERTEX\n10\n1\n20\n0\n0\nVERTEX\n10\n1\n20\n1\n0\nSEQEND\n0\nLINE\n8\nL1_B\n10\n0\n20\n2\n30\n1\n11\n1\n21\n2\n31\n1\n");
        assert_eq!(imported.geometry.routing.segments.len(), 4);
        assert_eq!(imported.geometry.layer_z_mm, vec![-1.0, 0.0]);
        assert_eq!(
            imported.geometry.routing.segments[2].end,
            imported.geometry.routing.segments[0].start
        );
        assert!(imported.warnings.is_empty());
    }

    #[test]
    fn imports_3d_polyline_traces_and_vertical_via() {
        let imported = import_polyline_fixture("0\nPOLYLINE\n8\nL0_A\n70\n8\n0\nVERTEX\n70\n32\n10\n0\n20\n0\n30\n0\n0\nVERTEX\n70\n32\n10\n1\n20\n0\n30\n0\n0\nVERTEX\n70\n32\n10\n1\n20\n0\n30\n1\n0\nVERTEX\n70\n32\n10\n2\n20\n0\n30\n1\n0\nSEQEND\n");
        assert_eq!(imported.geometry.routing.segments.len(), 2);
        assert_eq!(imported.geometry.routing.vias.len(), 1);
        assert_eq!(imported.geometry.layer_z_mm, vec![-2.0, 0.0]);
        assert_eq!(imported.geometry.routing.segments[1].layer, 1);
        assert_eq!(
            imported.geometry.routing.vias[0].position,
            Point::new(2.0, 0.0)
        );
        assert!(
            imported.warnings.iter().all(|w| w.contains("layer name")),
            "{:?}",
            imported.warnings
        );
    }

    #[test]
    fn unsupported_classic_polylines_warn_once_and_preserve_following_line() {
        for extra in ["70\n16\n", "70\n64\n", "70\n2\n", "210\n1\n230\n0\n"] {
            let imported = import_polyline_fixture(&format!("0\nPOLYLINE\n8\nL1_A\n{extra}0\nVERTEX\n10\n0\n20\n0\n0\nVERTEX\n10\n1\n20\n0\n0\nSEQEND\n0\nLINE\n8\nL1_A\n10\n0\n20\n0\n30\n1\n11\n1\n21\n0\n31\n1\n"));
            assert_eq!(imported.geometry.routing.segments.len(), 1);
            assert_eq!(
                imported
                    .warnings
                    .iter()
                    .filter(|w| w.contains("POLYLINE"))
                    .count(),
                1
            );
            assert!(!imported
                .warnings
                .iter()
                .any(|w| w.contains("VERTEX") || w.contains("SEQEND entity")));
        }
    }

    #[test]
    fn reports_sloped_3d_polyline_edges_without_flattening_them() {
        let imported = import_polyline_fixture("0\nPOLYLINE\n8\nA\n70\n8\n0\nVERTEX\n10\n0\n20\n0\n30\n0\n0\nVERTEX\n10\n1\n20\n0\n30\n1\n0\nVERTEX\n10\n2\n20\n0\n30\n1\n0\nSEQEND\n");
        assert_eq!(imported.geometry.routing.segments.len(), 1);
        assert!(imported.geometry.routing.vias.is_empty());
        assert_eq!(
            imported.geometry.routing.segments[0].start,
            Point::new(2.0, 0.0)
        );
        assert_eq!(
            imported.warnings,
            vec!["Skipped non-planar DXF POLYLINE segment on layer 'A'."]
        );
    }

    #[test]
    fn malformed_and_bulged_polylines_do_not_swallow_following_geometry() {
        for vertices in [
            "0\nVERTEX\n10\n0\n20\n0\n0\nVERTEX\n10\n1\n20\n0\n", // No SEQEND.
            "0\nVERTEX\n10\n0\n20\n0\n0\nSEQEND\n",               // Too few points.
            "0\nVERTEX\n10\n0\n20\n0\n42\n1\n0\nVERTEX\n10\n1\n20\n0\n0\nSEQEND\n",
        ] {
            let imported = import_polyline_fixture(&format!("0\nPOLYLINE\n8\nL1_A\n{vertices}0\nLINE\n8\nL1_A\n10\n0\n20\n0\n30\n1\n11\n1\n21\n0\n31\n1\n"));
            assert_eq!(imported.geometry.routing.segments.len(), 1);
            assert_eq!(
                imported
                    .warnings
                    .iter()
                    .filter(|w| w.contains("POLYLINE"))
                    .count(),
                1
            );
        }
    }

    #[test]
    fn generated_stack_places_top_copper_at_origin_and_vias_on_adjacent_planes() {
        let coil = pcbmotorgen_routing::PhaseCoil {
            layer_idx: 0,
            phase_name: "A".into(),
            segments: vec![pcbmotorgen_routing::CoilSegment {
                start: (0.0, 1.0),
                end: (10.0, 1.0),
                is_active: true,
            }],
            center_via_positions: vec![(2.0, 3.0)],
            ..Default::default()
        };
        let geometry = phase_coils_to_cad_geometry(&[coil], 4, 1.6, 0.2).unwrap();
        assert_eq!(geometry.layer_z_mm[0], 0.0);
        assert!((geometry.layer_z_mm[1] + 1.6 / 3.0).abs() < 1e-12);
        assert!((geometry.layer_z_mm[3] + 1.6).abs() < 1e-12);
        let via = &geometry.routing.vias[0];
        assert_eq!((via.from_layer, via.to_layer), (0, 1));
        assert_eq!(geometry.routing.segments[0].start.x, 0.0);
        assert!(
            ((geometry.layer_z_mm[via.to_layer as usize]
                - geometry.layer_z_mm[via.from_layer as usize])
                .abs()
                - 1.6 / 3.0)
                .abs()
                < 1e-12
        );
    }
}
