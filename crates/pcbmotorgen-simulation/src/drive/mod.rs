//! Driver suitability analysis: does a given three-phase gate/driver IC have
//! the voltage, current, and switching capability to run the routed coils?
//!
//! Everything is derived from the routed copper ([`RoutingResult`]), not from
//! a parametric guess:
//!
//! 1. [`extract_phase_networks`] rebuilds every phase net's conductor graph
//!    (segments + arcs joined by vias). Braids tie their strands together at
//!    crossing vias, so the phase is a resistor mesh between its terminal
//!    ends and its star ends.
//! 2. Each trace edge is `ρ(T)·l/(w·t)` and each via a plated barrel; nodal
//!    analysis gives the phase resistance and the current in every edge.
//! 3. Phase self inductance and the inter-phase mutual inductance are
//!    integrated numerically (Neumann formula over the routed filaments,
//!    weighted by the solved current split), so
//!    the line-to-line inductance `L_LL = L_A + L_B − 2·M_AB` that an LCR
//!    meter would read is available for the ripple check.
//! 4. [`analyze_drive`] combines those with the driver limits and the thrust
//!    constant from the force sweep into pass/warn/fail checks:
//!    bus voltage, holding and at-speed voltage headroom (SVPWM, star),
//!    PWM current ripple, peak/OCP current, continuous current, trace
//!    ampacity (IPC-2221), and thrust vs friction / target.
//!
//! The inductance is an open-path partial inductance of the routed copper:
//! terminal fan-out and the star point are not part of the routing result.
//! Verify on a prototype with a 100 kHz LCR reading (`L_LL = 2·L_s`).

mod geometry;
mod inductance;

pub use geometry::{
    extract_phase_networks, extract_phase_networks_with_terminals, solve_network, EdgeKind,
    NetworkSolution, PhaseNetwork, TerminalPair, TerminalPoint,
};

use crate::params::SimulationInput;
use crate::units::{oz_to_m, RHO_CU};
use pcbmotorgen_routing::RoutingResult;
use serde::{Deserialize, Serialize};

/// Copper temperature coefficient of resistance [1/K] (annealed Cu, 20 °C).
pub const ALPHA_CU: f64 = 0.00393;
/// Reference temperature of [`RHO_CU`] [°C].
const RHO_REF_C: f64 = 20.0;

/// The limits of one three-phase driver IC. All values come from its
/// datasheet; the UI offers presets but every field is editable.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct DriverSpec {
    /// Display name, e.g. `DRV8311`.
    pub name: String,
    /// Confirmed built-in delta handling by the driver/controller. Unconfirmed
    /// legacy specs require star/wye for evaluation, not a hardware prohibition.
    pub supports_delta: bool,
    /// Minimum motor supply voltage [V].
    pub min_supply_v: f64,
    /// Maximum motor supply voltage [V].
    pub max_supply_v: f64,
    /// Peak output current / overcurrent-protection trip [A].
    pub peak_current_a: f64,
    /// Continuous RMS output current per phase [A].
    pub continuous_rms_a: f64,
    /// Total on-resistance in the current path, high side + low side [Ω].
    pub rds_on_ohm: f64,
    /// Highest supported PWM frequency [Hz].
    pub max_pwm_hz: f64,
}

impl Default for DriverSpec {
    fn default() -> Self {
        // TI DRV8311 (integrated FET, 3-phase).
        Self {
            name: "DRV8311".to_string(),
            supports_delta: false,
            min_supply_v: 3.0,
            max_supply_v: 20.0,
            peak_current_a: 5.0,
            continuous_rms_a: 1.5,
            rds_on_ohm: 0.21,
            max_pwm_hz: 200e3,
        }
    }
}

/// Keep hardware compatibility separate from model availability. The present
/// voltage/current/ripple equations assume star/wye and cannot evaluate delta.
pub fn driver_connection_error(driver: &DriverSpec, delta: bool) -> Option<String> {
    if !delta {
        return None;
    }
    let hint = "Go to Design > Topology & Board > Winding connection and select Star (wye).";
    Some(if driver.supports_delta {
        format!("Delta handling is declared for {}, but delta electrical analysis is not yet available. {hint}", driver.name)
    } else {
        format!("{} has no declared built-in delta handling. Star (wye) configuration is required. {hint}", driver.name)
    })
}

#[cfg(test)]
mod connection_tests {
    use super::*;

    #[test]
    fn unconfirmed_delta_requires_star_wye() {
        let driver = DriverSpec::default();
        assert!(driver_connection_error(&driver, false).is_none());
        let error = driver_connection_error(&driver, true).unwrap();
        assert!(error.contains("Star (wye) configuration is required"));
        assert!(error.contains("Design > Topology & Board > Winding connection"));
    }

    #[test]
    fn declared_delta_support_does_not_enable_star_equations_for_delta() {
        let driver = DriverSpec { supports_delta: true, ..DriverSpec::default() };
        let error = driver_connection_error(&driver, true).unwrap();
        assert!(error.contains("delta electrical analysis is not yet available"));
    }

    #[test]
    fn legacy_driver_specs_default_to_unconfirmed_delta_support() {
        let driver: DriverSpec = serde_json::from_str(r#"{"name":"Legacy"}"#).unwrap();
        assert!(!driver.supports_delta);
    }
}

/// Operating point and board assumptions for the driver analysis. Bus
/// voltage and target phase current come from [`SimulationInput`]
/// (`supply_voltage_v`, `max_current_a`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct DriveSettings {
    pub driver: DriverSpec,
    /// Configured PWM switching frequency [Hz].
    pub pwm_hz: f64,
    /// Fastest move the mover must make at full current [m/s].
    pub target_speed_m_s: f64,
    /// Finished copper weight of the outer layers [oz].
    pub outer_copper_oz: f64,
    /// Finished copper weight of the inner layers [oz].
    pub inner_copper_oz: f64,
    /// Via barrel plating thickness [m].
    pub via_plating_m: f64,
    /// Winding temperature used for the resistance [°C].
    pub winding_temp_c: f64,
    /// Allowed trace temperature rise for the ampacity limit [°C].
    pub allowed_rise_c: f64,
    /// Acceptable peak-to-peak ripple as a fraction of the phase current.
    pub ripple_limit_fraction: f64,
    /// Fraction of the bus a current loop may use (control headroom).
    pub voltage_headroom: f64,
    /// External series inductance added at the driver terminals, per phase [H].
    ///
    /// Coreless coils have very low phase inductance, so a physical inductor
    /// is often fitted near the driver to tame PWM ripple. It adds directly to
    /// the per-phase (synchronous) inductance used for the ripple, time
    /// constant, and ω·L voltage terms; zero means none.
    pub series_inductance_h: f64,
}

impl Default for DriveSettings {
    fn default() -> Self {
        Self {
            driver: DriverSpec::default(),
            pwm_hz: 100e3,
            target_speed_m_s: 0.5,
            outer_copper_oz: 1.0,
            inner_copper_oz: 1.0,
            via_plating_m: 25e-6,
            winding_temp_c: 75.0,
            allowed_rise_c: 20.0,
            ripple_limit_fraction: 0.3,
            voltage_headroom: 0.85,
            series_inductance_h: 0.0,
        }
    }
}

/// Measured routed copper and electrical parameters of one phase.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseElectrical {
    pub net: String,
    /// Parallel paths entering at the phase terminal.
    pub strands: u32,
    /// Copper layers the phase uses.
    pub layers: Vec<u32>,
    /// Trace length per parallel path (total ÷ strands) [m].
    pub strand_length_m: f64,
    /// Total trace length of the phase, all strands [m].
    pub total_length_m: f64,
    /// Trace length that produces thrust (active legs), all strands [m].
    pub active_length_m: f64,
    /// Vias in one strand (mean).
    pub vias_per_strand: f64,
    /// Total vias in the phase.
    pub vias_total: u32,
    /// Phase DC resistance at 20 °C [Ω].
    pub resistance_20c_ohm: f64,
    /// Phase DC resistance at the winding temperature [Ω].
    pub resistance_hot_ohm: f64,
    /// Share of the hot resistance contributed by vias [Ω].
    pub via_resistance_ohm: f64,
    /// Open-path partial self inductance [H].
    pub self_inductance_h: f64,
    /// Largest share of the phase current in any one trace (1/strands for
    /// an even split).
    pub max_trace_share: f64,
    /// False when no conducting path joins the terminal and star ends.
    pub connected: bool,
}

/// Pass / warn / fail state of one driver check.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CheckStatus {
    Pass,
    Warn,
    Fail,
    /// Not evaluated (missing input such as the thrust constant).
    Unknown,
}

/// One driver suitability check: `value` against `limit`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriveCheck {
    pub id: String,
    pub label: String,
    pub status: CheckStatus,
    pub value: f64,
    pub limit: f64,
    pub unit: String,
    pub detail: String,
}

/// Required line-to-line voltage at one mover speed.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct SpeedVoltagePoint {
    pub speed_m_s: f64,
    pub required_v: f64,
}

/// Full driver suitability result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriveAnalysis {
    pub driver_name: String,
    pub phases: Vec<PhaseElectrical>,
    // --- Geometry inputs echoed for the UI ---
    pub trace_width_m: f64,
    pub outer_copper_m: f64,
    pub inner_copper_m: f64,
    pub via_resistance_each_ohm: f64,
    // --- Electrical summary (worst / mean phase) ---
    /// Worst (highest) hot phase resistance [Ω].
    pub phase_resistance_ohm: f64,
    /// Mean phase self inductance [H].
    pub phase_inductance_h: f64,
    /// Mean mutual inductance between phases [H] (sign follows the strand
    /// orientation, terminal at the low-x end).
    pub mutual_inductance_h: f64,
    /// Line-to-line inductance an LCR meter reads between two terminals [H].
    pub line_inductance_h: f64,
    /// Effective per-phase (synchronous) inductance `L_LL / 2` [H].
    pub synchronous_inductance_h: f64,
    /// External series inductance per phase defined at the driver terminals [H].
    pub series_inductance_h: f64,
    /// Per-phase inductance the checks use: copper `synchronous_inductance_h`
    /// plus `series_inductance_h` [H].
    pub effective_inductance_h: f64,
    /// Line-to-line resistance a 4-wire measurement reads (`2·R_phase`) [Ω].
    pub line_resistance_ohm: f64,
    /// Electrical time constant `L_s / R` [s].
    pub time_constant_s: f64,
    // --- Operating point ---
    pub bus_voltage_v: f64,
    pub phase_current_a: f64,
    pub pwm_hz: f64,
    pub target_speed_m_s: f64,
    /// Thrust constant (N per A peak phase current), from the force sweep.
    pub thrust_constant_n_per_a: Option<f64>,
    /// Phase back-EMF constant, peak volts per m/s.
    pub back_emf_constant_v_s_per_m: Option<f64>,
    /// Line-to-line voltage needed to hold the phase current at standstill [V].
    pub holding_voltage_v: f64,
    /// Line-to-line voltage needed at the target speed [V].
    pub speed_voltage_v: Option<f64>,
    /// Usable line-to-line voltage: `headroom · V_bus` [V].
    pub available_voltage_v: f64,
    /// Highest phase current the bus can force at standstill [A].
    pub voltage_limited_current_a: f64,
    /// Highest speed at the target current within the usable voltage [m/s].
    pub max_speed_m_s: Option<f64>,
    /// Peak-to-peak ripple of the assumed 50%-duty two-phase RL loop [A].
    pub ripple_pp_a: f64,
    /// PWM frequency needed to meet the ripple limit [Hz].
    pub min_pwm_hz: f64,
    /// Series inductance to add per phase to meet the ripple limit at the
    /// configured PWM frequency (0 when already met) [H].
    pub added_inductance_h: f64,
    /// Phase current plus half the ripple [A].
    pub peak_current_a: f64,
    /// Highest DC phase current before the most loaded trace or via exceeds
    /// its IPC-2221 limit at the allowed temperature rise [A].
    pub trace_ampacity_a: f64,
    /// Copper loss at the operating current (`1.5·I²·R`) [W].
    pub copper_loss_w: f64,
    /// Thrust at the target current using the supplied force constant [N].
    /// The desktop supplies the mean sweep constant, not a holding-position value.
    pub thrust_n: Option<f64>,
    /// Highest continuous phase current: min of driver, ampacity, voltage [A].
    pub max_continuous_current_a: f64,
    /// What limits `max_continuous_current_a`.
    pub limiting_factor: String,
    /// Thrust at `max_continuous_current_a` [N].
    pub max_continuous_thrust_n: Option<f64>,
    pub checks: Vec<DriveCheck>,
    /// Required voltage vs speed, for the operating-envelope plot.
    pub speed_curve: Vec<SpeedVoltagePoint>,
    /// Assumptions the user should know about.
    pub notes: Vec<String>,
    /// Backplane and housing at the operating point; absent without one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub backplane: Option<DriveBackplane>,
}

/// Backplane and housing effects at the drive's operating point (tickets
/// 04n2, q9nw). See [`crate::backplane`] for the model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriveBackplane {
    /// Low-frequency inductance factor, with the magnets' bias on saturated
    /// layers.
    pub inductance_factor: f64,
    /// Inductance factor `Re F` at the PWM frequency, eddy currents included.
    pub pwm_inductance_factor: f64,
    /// Per-phase inductance at the PWM frequency plus series inductance [H].
    /// The ripple check uses it.
    pub pwm_inductance_h: f64,
    /// Series resistance per phase that eddy currents add at the PWM
    /// frequency [Ω].
    pub pwm_resistance_ohm: f64,
    /// Eddy loss in the backplane and housing from the PWM ripple [W].
    pub ripple_eddy_loss_w: f64,
    /// Eddy drag on the mover at the target speed [N], opposing motion.
    pub drag_n: f64,
    /// Normal attraction at the target speed [N].
    pub normal_force_n: f64,
    /// Drag power at the target speed, `drag·v` [W].
    pub drag_power_w: f64,
    /// Mean sweep thrust minus drag at the target speed [N].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub net_thrust_n: Option<f64>,
    /// Lowest speed at which the drag reaches the full-current thrust [m/s].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub drag_limited_speed_m_s: Option<f64>,
    /// Drag and normal force at the `speed_curve` speeds.
    pub drag_curve: Vec<DragPoint>,
}

/// Eddy drag and normal force at one mover speed.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct DragPoint {
    pub speed_m_s: f64,
    pub drag_n: f64,
    pub normal_n: f64,
}

/// Copper resistivity at `temp_c` [Ω·m].
pub fn rho_cu_at(temp_c: f64) -> f64 {
    RHO_CU * (1.0 + ALPHA_CU * (temp_c - RHO_REF_C))
}

/// Resistance of one plated through via barrel [Ω].
pub fn via_resistance_ohm(drill_m: f64, plating_m: f64, length_m: f64, rho: f64) -> f64 {
    let area = std::f64::consts::PI * plating_m * (drill_m + plating_m);
    if area <= 0.0 {
        return 0.0;
    }
    rho * length_m / area
}

/// IPC-2221 trace current capacity [A] for one trace.
/// `I = k·ΔT^0.44·A^0.725`, A in mil², k = 0.048 outer / 0.024 inner.
pub fn ipc2221_ampacity_a(width_m: f64, thickness_m: f64, rise_c: f64, internal: bool) -> f64 {
    let mil = 25.4e-6;
    let area_mil2 = (width_m / mil) * (thickness_m / mil);
    let k = if internal { 0.024 } else { 0.048 };
    k * rise_c.max(0.0).powf(0.44) * area_mil2.max(0.0).powf(0.725)
}

fn is_inner(layer: u32, num_layers: u32) -> bool {
    num_layers > 2 && layer != 0 && layer + 1 != num_layers
}

fn copper_m(layer: u32, num_layers: u32, settings: &DriveSettings) -> f64 {
    if is_inner(layer, num_layers) {
        oz_to_m(settings.inner_copper_oz)
    } else {
        oz_to_m(settings.outer_copper_oz)
    }
}

/// Run the driver suitability analysis.
///
/// `thrust_constant_n_per_a` is the force-sweep mean thrust divided by its
/// phase current; without it the speed and thrust checks are `Unknown`.
pub fn analyze_drive(
    sim: &SimulationInput,
    routing: &RoutingResult,
    settings: &DriveSettings,
    thrust_constant_n_per_a: Option<f64>,
) -> DriveAnalysis {
    analyze_drive_with(sim, routing, settings, thrust_constant_n_per_a, &DriveGeometryHints::default())
}

/// Extra geometry known for imported copper.
#[derive(Debug, Clone, Default)]
pub struct DriveGeometryHints {
    /// Copper plane heights per layer index [m]; evenly spaced through
    /// `pcb_thickness_m` when empty.
    pub layer_z_m: Vec<f64>,
    /// Picked IN/OUT terminals per phase net.
    pub terminals: std::collections::BTreeMap<String, Vec<TerminalPair>>,
}

/// [`analyze_drive`] with imported-geometry hints.
pub fn analyze_drive_with(
    sim: &SimulationInput,
    routing: &RoutingResult,
    settings: &DriveSettings,
    thrust_constant_n_per_a: Option<f64>,
    hints: &DriveGeometryHints,
) -> DriveAnalysis {
    let num_layers = sim.num_layers.max(1);
    let width = sim.min_trace_m;
    let rho_hot = rho_cu_at(settings.winding_temp_c);
    let rho_20 = rho_cu_at(RHO_REF_C);
    let via_len = sim.pcb_thickness_m;
    let r_via_hot = via_resistance_ohm(sim.min_via_drill_m, settings.via_plating_m, via_len, rho_hot);
    let layer_pitch = if num_layers > 1 {
        sim.pcb_thickness_m / (num_layers - 1) as f64
    } else {
        0.0
    };

    let networks = extract_phase_networks_with_terminals(routing, &hints.terminals);
    let layer_z = |l: u32| hints.layer_z_m.get(l as usize).copied().unwrap_or(l as f64 * layer_pitch);
    let mut notes = Vec::new();
    let via_amp = ipc2221_ampacity_a(
        std::f64::consts::PI * sim.min_via_drill_m,
        settings.via_plating_m,
        settings.allowed_rise_c,
        false,
    );

    // --- Resistance per phase (nodal solve) -----------------------------
    let edge_resistances = |net: &PhaseNetwork, via_r: f64| -> Vec<f64> {
        net.edges
            .iter()
            .map(|e| match &e.kind {
                EdgeKind::Trace { layer, length_m, .. } => {
                    rho_hot * length_m / (width * copper_m(*layer, num_layers, settings))
                }
                EdgeKind::Via => via_r,
            })
            .collect()
    };
    let solutions: Vec<NetworkSolution> = networks
        .iter()
        .map(|net| solve_network(net, &edge_resistances(net, r_via_hot)))
        .collect();
    let mut phase_ampacity = Vec::new();
    let mut phases: Vec<PhaseElectrical> = networks
        .iter()
        .zip(solutions.iter())
        .map(|(net, sol)| {
            // At unit phase current, each edge's I²R is its contribution
            // to equivalent resistance. Avoid an ill-conditioned second
            // solve with ideal-short vias, whose failure could attribute
            // the entire phase resistance to the vias.
            let via_resistance: f64 = net.edges.iter().zip(&sol.current_share)
                .filter(|(edge, _)| matches!(edge.kind, EdgeKind::Via))
                .map(|(_, share)| share * share * r_via_hot).sum();
            let strands = net.strands().max(1);
            let total_len = net.trace_length_m();
            let vias = net.via_count();
            // Ampacity: the edge with the largest current share relative to
            // its own limit binds first.
            let mut amp = f64::INFINITY;
            let mut max_share: f64 = 0.0;
            for (e, share) in net.edges.iter().zip(sol.current_share.iter()) {
                let share = share.abs();
                if share < 1e-9 {
                    continue;
                }
                let limit = match &e.kind {
                    EdgeKind::Trace { layer, .. } => {
                        max_share = max_share.max(share);
                        ipc2221_ampacity_a(
                            width,
                            copper_m(*layer, num_layers, settings),
                            settings.allowed_rise_c,
                            is_inner(*layer, num_layers),
                        )
                    }
                    EdgeKind::Via => via_amp,
                };
                amp = amp.min(limit / share);
            }
            phase_ampacity.push(if sol.connected && amp.is_finite() { amp } else { 0.0 });
            PhaseElectrical {
                net: net.net.clone(),
                strands,
                layers: net.layers(),
                strand_length_m: total_len / strands as f64,
                total_length_m: total_len,
                active_length_m: net.active_length_m,
                vias_per_strand: vias as f64 / strands as f64,
                vias_total: vias,
                resistance_20c_ohm: sol.resistance_ohm * rho_20 / rho_hot,
                resistance_hot_ohm: sol.resistance_ohm,
                via_resistance_ohm: via_resistance,
                self_inductance_h: 0.0,
                max_trace_share: max_share,
                connected: sol.connected,
            }
        })
        .collect();

    if phases.iter().any(|p| !p.connected) {
        notes.push(
            "A phase has no conducting path between its terminal and star ends; its values are zero."
                .to_string(),
        );
    }

    // --- Inductance -----------------------------------------------------
    let thickness_for_gmd = oz_to_m(settings.outer_copper_oz.max(settings.inner_copper_oz));
    let filaments: Vec<Vec<inductance::Filament>> = networks
        .iter()
        .zip(solutions.iter())
        .map(|(net, sol)| inductance::phase_filaments(net, &sol.current_share, layer_z))
        .collect();
    let self_l: Vec<f64> = filaments
        .iter()
        .map(|f| inductance::phase_self_inductance(f, width, thickness_for_gmd))
        .collect();
    for (ph, l) in phases.iter_mut().zip(self_l.iter()) {
        ph.self_inductance_h = *l;
    }
    let mut mutuals = Vec::new();
    for i in 0..filaments.len() {
        for j in (i + 1)..filaments.len() {
            mutuals.push(inductance::phase_mutual_inductance(
                &filaments[i],
                &filaments[j],
                width,
                thickness_for_gmd,
            ));
        }
    }
    let mean = |v: &[f64]| if v.is_empty() { 0.0 } else { v.iter().sum::<f64>() / v.len() as f64 };
    let l_self = mean(&self_l);
    let m_mut = mean(&mutuals);
    // Line-to-line: L_A + L_B − 2·M_AB. Guard against a non-physical result.
    let mut l_ll = 2.0 * l_self - 2.0 * m_mut;
    if !(l_ll > 0.0) {
        l_ll = 2.0 * l_self;
    }
    // A backplane or housing adds image currents that raise the copper
    // inductance (t707). Saturation under the magnets and eddy currents make
    // the factor depend on frequency (04n2, q9nw). With no backplane the
    // factor is 1 and nothing changes.
    let l_copper = l_ll / 2.0;
    let mut l_s = l_copper;
    let solved = sim.backplane.as_ref().map(|stack| stack.solve(sim));
    if let Some(stack) = &sim.backplane {
        let analysis = stack.analyze(sim);
        l_s *= analysis.inductance_factor;
        let limit_hz = crate::backplane::SILICON_STEEL_PWM_LIMIT_HZ;
        if stack.has_silicon_steel() && settings.pwm_hz > limit_hz {
            notes.push(format!(
                "Silicon steel backplane at {:.0} kHz PWM: expect severe eddy-current heating. Use ferrite or SMC above {:.0} kHz.",
                settings.pwm_hz / 1e3,
                limit_hz / 1e3
            ));
        }
        notes.extend(analysis.warnings);
    }
    // External inductors fitted at the driver terminals add in series with
    // each phase, so one per-phase value raises the effective synchronous
    // inductance that the ripple, time-constant, and ω·L terms see.
    let l_total = l_s + settings.series_inductance_h.max(0.0);
    // Per-phase inductance and the series resistance eddy currents add, at
    // frequency `f`: `L0·Re F` and `−2π·f·L0·Im F`.
    let coil_at = |f: f64| -> (f64, f64) {
        match &solved {
            Some(s) => {
                let c = s.coil_factor(f);
                (
                    l_copper * c.re + settings.series_inductance_h.max(0.0),
                    -2.0 * std::f64::consts::PI * f * l_copper * c.im,
                )
            }
            None => (l_total, 0.0),
        }
    };
    // The ripple sees the inductance at the switching frequency.
    let (l_ripple, r_pwm) = coil_at(settings.pwm_hz);

    let r_phase = phases.iter().map(|p| p.resistance_hot_ohm).fold(0.0, f64::max);
    let i = sim.max_current_a.max(0.0);
    let v_bus = sim.supply_voltage_v;
    let d = &settings.driver;
    let available = settings.voltage_headroom * v_bus;

    // --- Voltage --------------------------------------------------------
    let sqrt3 = 3f64.sqrt();
    let holding_v = sqrt3 * i * r_phase + i * d.rds_on_ohm;
    let voltage_limited_current = if sqrt3 * r_phase + d.rds_on_ohm > 0.0 {
        available / (sqrt3 * r_phase + d.rds_on_ohm)
    } else {
        f64::INFINITY
    };
    let electrical_period = 2.0 * sim.magnet_pitch_m;
    let kf = thrust_constant_n_per_a.filter(|k| k.is_finite() && *k > 0.0);
    // FOC (id = 0): F = 3/2·Ke·I  ⇒  Ke (phase peak, V·s/m) = 2/3·Kf.
    let ke = kf.map(|k| 2.0 / 3.0 * k);
    let required_v = |speed: f64| -> f64 {
        let e = ke.unwrap_or(0.0) * speed;
        let omega = if electrical_period > 0.0 {
            2.0 * std::f64::consts::PI * speed / electrical_period
        } else {
            0.0
        };
        // L and R at the electrical frequency of this speed.
        let (l_e, r_eddy) = coil_at(omega / (2.0 * std::f64::consts::PI));
        let v_ph = ((i * (r_phase + r_eddy) + e).powi(2) + (omega * l_e * i).powi(2)).sqrt();
        sqrt3 * v_ph + i * d.rds_on_ohm
    };
    let speed_v = ke.map(|_| required_v(settings.target_speed_m_s));
    let max_speed = ke.map(|_| {
        if required_v(0.0) > available {
            return 0.0;
        }
        let mut hi = 1.0;
        while required_v(hi) < available && hi < 1e3 {
            hi *= 2.0;
        }
        let mut lo = 0.0;
        for _ in 0..60 {
            let mid = 0.5 * (lo + hi);
            if required_v(mid) <= available {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        lo
    });

    // --- Ripple ---------------------------------------------------------
    // Steady-state RL response to +/- Vbus/2 across Rloop=2R, Lloop=2Ls.
    // The inductive V/(8fLs) approximation is valid only when R/(4fLs)<<1.
    // Ls is the inductance at the PWM frequency (`l_ripple`); R stays the DC
    // resistance.
    let ripple = if settings.pwm_hz > 0.0 && l_ripple > 0.0 {
        if r_phase > 1e-12 {
            v_bus / (2.0 * r_phase) * (r_phase / (4.0 * settings.pwm_hz * l_ripple)).tanh()
        } else {
            v_bus / (8.0 * settings.pwm_hz * l_ripple)
        }
    } else {
        f64::INFINITY
    };
    let ripple_limit = settings.ripple_limit_fraction * i;
    let required_fl = if ripple_limit <= 0.0 || v_bus <= 0.0 {
        f64::INFINITY
    } else if r_phase <= 1e-12 {
        v_bus / (8.0 * ripple_limit)
    } else if 2.0 * r_phase * ripple_limit >= v_bus {
        0.0
    } else {
        r_phase / (4.0 * (2.0 * r_phase * ripple_limit / v_bus).atanh())
    };
    let min_pwm = if l_ripple > 0.0 {
        required_fl / l_ripple
    } else {
        f64::INFINITY
    };
    let peak_current = i + ripple / 2.0;
    let added_inductance = if settings.pwm_hz > 0.0 && ripple_limit > 0.0 {
        (required_fl / settings.pwm_hz - l_ripple).max(0.0)
    } else {
        0.0
    };

    // --- Backplane at the operating point --------------------------------
    let thrust = kf.map(|k| k * i);
    let backplane = solved.as_ref().map(|s| {
        // The ripple estimate's 50%-duty ±Vbus/2 square wave across the
        // two-phase loop: odd harmonic n has amplitude 4/(nπ)·Vbus/2.
        let ripple_eddy_loss_w = (1..=49)
            .step_by(2)
            .map(|n| {
                let f = n as f64 * settings.pwm_hz;
                let (l, r_eddy) = coil_at(f);
                let z = 2.0 * (r_phase + r_eddy).hypot(2.0 * std::f64::consts::PI * f * l);
                let amplitude = 4.0 / (n as f64 * std::f64::consts::PI) * v_bus / 2.0 / z;
                if z > 0.0 {
                    amplitude * amplitude * r_eddy
                } else {
                    0.0
                }
            })
            .sum();
        let at_target = s.magnet_forces(sim, settings.target_speed_m_s);
        DriveBackplane {
            inductance_factor: s.coil_factor(0.0).re,
            pwm_inductance_factor: s.coil_factor(settings.pwm_hz).re,
            pwm_inductance_h: l_ripple,
            pwm_resistance_ohm: r_pwm,
            ripple_eddy_loss_w,
            drag_n: at_target.drag_n,
            normal_force_n: at_target.normal_n,
            drag_power_w: at_target.drag_n * settings.target_speed_m_s.abs(),
            net_thrust_n: thrust.map(|f| f - at_target.drag_n),
            drag_limited_speed_m_s: None,
            drag_curve: Vec::new(),
        }
    });

    // --- Ampacity -------------------------------------------------------
    let ampacity = phase_ampacity.iter().copied().fold(f64::INFINITY, f64::min);
    let ampacity = if ampacity.is_finite() { ampacity } else { 0.0 };

    let copper_loss = 1.5 * i * i * r_phase;

    // --- Limits ---------------------------------------------------------
    let candidates = [
        (d.continuous_rms_a, format!("{} continuous rating", d.name)),
        (ampacity, "trace ampacity".to_string()),
        (voltage_limited_current, "bus voltage".to_string()),
    ];
    let (max_cont, limiting) = candidates
        .iter()
        .filter(|(v, _)| v.is_finite())
        .fold((f64::INFINITY, String::new()), |acc, (v, n)| {
            if *v < acc.0 { (*v, n.clone()) } else { acc }
        });
    let max_cont = if max_cont.is_finite() { max_cont } else { 0.0 };

    // --- Checks ---------------------------------------------------------
    let mut checks = Vec::new();
    let status = |ok: bool, warn: bool| {
        if ok {
            CheckStatus::Pass
        } else if warn {
            CheckStatus::Warn
        } else {
            CheckStatus::Fail
        }
    };
    checks.push(DriveCheck {
        id: "supply".into(),
        label: "Bus voltage within driver rating".into(),
        status: status(v_bus >= d.min_supply_v && v_bus <= d.max_supply_v, false),
        value: v_bus,
        limit: if v_bus < d.min_supply_v { d.min_supply_v } else { d.max_supply_v },
        unit: "V".into(),
        detail: format!("{} runs from {:.1} V to {:.1} V.", d.name, d.min_supply_v, d.max_supply_v),
    });
    checks.push(DriveCheck {
        id: "holding_voltage".into(),
        label: "Voltage to hold the phase current".into(),
        status: status(holding_v <= available, holding_v <= v_bus),
        value: holding_v,
        limit: available,
        unit: "V".into(),
        detail: format!(
            "√3·I·R + I·R_DS(on) = √3·{i:.2} A·{r_phase:.2} Ω + {i:.2} A·{:.2} Ω. Limit is {:.0} % of the bus.",
            d.rds_on_ohm,
            settings.voltage_headroom * 100.0
        ),
    });
    checks.push(match speed_v {
        Some(v) => DriveCheck {
            id: "speed_voltage".into(),
            label: format!("Voltage at {:.2} m/s", settings.target_speed_m_s),
            status: status(v <= available, v <= v_bus),
            value: v,
            limit: available,
            unit: "V".into(),
            detail: format!(
                "Adds back-EMF {:.3} V·s/m and ωL drop at full current. Top speed at this current is {:.2} m/s.",
                ke.unwrap_or(0.0),
                max_speed.unwrap_or(0.0)
            ),
        },
        None => DriveCheck {
            id: "speed_voltage".into(),
            label: format!("Voltage at {:.2} m/s", settings.target_speed_m_s),
            status: CheckStatus::Unknown,
            value: 0.0,
            limit: available,
            unit: "V".into(),
            detail: "Needs the thrust sweep for the back-EMF constant.".into(),
        },
    });
    checks.push(DriveCheck {
        id: "pwm_range".into(),
        label: "PWM frequency within driver range".into(),
        status: status(settings.pwm_hz <= d.max_pwm_hz, false),
        value: settings.pwm_hz,
        limit: d.max_pwm_hz,
        unit: "Hz".into(),
        detail: format!("{} switches up to {:.0} kHz.", d.name, d.max_pwm_hz / 1e3),
    });
    checks.push(DriveCheck {
        id: "ripple".into(),
        label: "PWM current ripple estimate (50% duty)".into(),
        status: status(ripple <= ripple_limit, ripple <= i),
        value: ripple,
        limit: ripple_limit,
        unit: "A".into(),
        detail: if added_inductance > 0.0 {
            format!(
                "50%-duty RL estimate, not a switched-waveform simulation: V_bus/(2R)·tanh(R/(4·f_sw·L_s)), L_s = {:.2} µH. Meeting {:.0} % of the phase current needs f_sw ≥ {:.0} kHz, or {:.1} µH added in series per phase at {:.0} kHz.",
                l_ripple * 1e6,
                settings.ripple_limit_fraction * 100.0,
                min_pwm / 1e3,
                added_inductance * 1e6,
                settings.pwm_hz / 1e3
            )
        } else {
            format!(
                "50%-duty RL estimate, not a switched-waveform simulation: V_bus/(2R)·tanh(R/(4·f_sw·L_s)), L_s = {:.2} µH. The limit holds down to f_sw = {:.0} kHz.",
                l_ripple * 1e6,
                min_pwm / 1e3
            )
        },
    });
    checks.push(DriveCheck {
        id: "peak_current".into(),
        label: "Peak current below overcurrent trip".into(),
        status: status(peak_current <= 0.8 * d.peak_current_a, peak_current <= d.peak_current_a),
        value: peak_current,
        limit: d.peak_current_a,
        unit: "A".into(),
        detail: "Phase current plus half the ripple. Warns above 80 % of the trip.".into(),
    });
    checks.push(DriveCheck {
        id: "continuous_current".into(),
        label: "Holding current within driver continuous rating".into(),
        status: status(i <= d.continuous_rms_a, i <= d.peak_current_a),
        value: i,
        limit: d.continuous_rms_a,
        unit: "A".into(),
        detail: "Holding parks one phase at its peak, so the DC current equals the peak phase current.".into(),
    });
    checks.push(DriveCheck {
        id: "ampacity".into(),
        label: format!("Trace ampacity at +{:.0} °C", settings.allowed_rise_c),
        status: status(i <= ampacity, i <= 1.25 * ampacity),
        value: i,
        limit: ampacity,
        unit: "A".into(),
        detail: "IPC-2221 on the most loaded trace or via of the solved current split. Conservative for inner layers.".into(),
    });
    match kf {
        Some(k) => {
            let f = k * i;
            checks.push(DriveCheck {
                id: "thrust".into(),
                label: "Mean sweep thrust vs continuous target".into(),
                status: status(f >= sim.target_force_n, f > sim.friction_n),
                value: f,
                limit: sim.target_force_n,
                unit: "N".into(),
                detail: format!(
                    "Mean sweep K_f = {k:.3} N/A, not a position-specific holding-force result. Friction is {:.3} N; at the {limiting} limit ({max_cont:.2} A) mean thrust reaches {:.3} N.",
                    sim.friction_n,
                    k * max_cont
                ),
            });
        }
        None => checks.push(DriveCheck {
            id: "thrust".into(),
            label: "Mean sweep thrust vs continuous target".into(),
            status: CheckStatus::Unknown,
            value: 0.0,
            limit: sim.target_force_n,
            unit: "N".into(),
            detail: "Needs the thrust sweep.".into(),
        }),
    }

    // --- Speed curve ----------------------------------------------------
    let top = max_speed
        .unwrap_or(0.0)
        .max(settings.target_speed_m_s)
        .max(0.1)
        * 1.4;
    let speed_curve: Vec<SpeedVoltagePoint> = (0..=40)
        .map(|k| {
            let s = top * k as f64 / 40.0;
            SpeedVoltagePoint { speed_m_s: s, required_v: required_v(s) }
        })
        .collect();

    // --- Eddy drag ------------------------------------------------------
    let mut backplane = backplane;
    if let (Some(bp), Some(s)) = (backplane.as_mut(), solved.as_ref()) {
        let drag = |v: f64| s.magnet_forces(sim, v);
        bp.drag_curve = speed_curve
            .iter()
            .map(|p| {
                let f = drag(p.speed_m_s);
                DragPoint {
                    speed_m_s: p.speed_m_s,
                    drag_n: f.drag_n,
                    normal_n: f.normal_n,
                }
            })
            .collect();
        // First crossing of drag over thrust on the curve, refined by bisection.
        bp.drag_limited_speed_m_s = thrust.and_then(|f| {
            let hit = bp.drag_curve.iter().position(|p| p.drag_n >= f)?;
            let (mut lo, mut hi) = (
                bp.drag_curve[hit.saturating_sub(1)].speed_m_s,
                bp.drag_curve[hit].speed_m_s,
            );
            for _ in 0..40 {
                let mid = 0.5 * (lo + hi);
                if drag(mid).drag_n >= f {
                    hi = mid;
                } else {
                    lo = mid;
                }
            }
            Some(hi)
        });
        if s.conducts() {
            let v = settings.target_speed_m_s;
            let limit = match bp.drag_limited_speed_m_s {
                Some(v_lim) => format!("Drag reaches the full-current thrust at {v_lim:.2} m/s."),
                None => format!("Drag stays below the full-current thrust up to {top:.1} m/s."),
            };
            checks.push(DriveCheck {
                id: "eddy_drag".into(),
                label: format!("Eddy drag at {v:.2} m/s vs thrust"),
                status: match thrust {
                    Some(f) => status(bp.drag_n <= 0.1 * f, bp.drag_n < f),
                    None => CheckStatus::Unknown,
                },
                value: bp.drag_n,
                limit: thrust.map_or(0.0, |f| 0.1 * f),
                unit: "N".into(),
                detail: format!(
                    "Eddy currents in the backplane and housing drag the mover with {:.3} N ({:.2} W) at {v:.2} m/s. {limit} Passes below 10 % of the thrust.",
                    bp.drag_n, bp.drag_power_w
                ),
            });
            notes.push(format!(
                "Eddy currents at {:.0} kHz PWM: inductance factor {:.2}× at low frequency, {:.2}× at the PWM frequency, {:.3} Ω added per phase, {:.3} W lost in the backplane and housing from the ripple.",
                settings.pwm_hz / 1e3,
                bp.inductance_factor,
                bp.pwm_inductance_factor,
                bp.pwm_resistance_ohm,
                bp.ripple_eddy_loss_w
            ));
        }
    }

    notes.push(format!(
        "Resistance uses ρ_Cu at {:.0} °C ({:.2e} Ω·m), trace width {:.3} mm, via drill {:.2} mm with {:.0} µm plating.",
        settings.winding_temp_c,
        rho_hot,
        width * 1e3,
        sim.min_via_drill_m * 1e3,
        settings.via_plating_m * 1e6
    ));
    notes.push(
        "Inductance is integrated over the routed copper only; terminal fan-out and the star point add a little. Confirm with an LCR meter at 100 kHz (L_LL = 2·L_s)."
            .to_string(),
    );
    if settings.series_inductance_h > 0.0 {
        notes.push(format!(
            "Includes {:.1} µH external series inductance per phase at the driver terminals in the ripple, time-constant, and voltage terms.",
            settings.series_inductance_h * 1e6
        ));
    }

    DriveAnalysis {
        driver_name: d.name.clone(),
        phases,
        trace_width_m: width,
        outer_copper_m: oz_to_m(settings.outer_copper_oz),
        inner_copper_m: oz_to_m(settings.inner_copper_oz),
        via_resistance_each_ohm: r_via_hot,
        phase_resistance_ohm: r_phase,
        phase_inductance_h: l_self,
        mutual_inductance_h: m_mut,
        line_inductance_h: l_ll,
        synchronous_inductance_h: l_s,
        series_inductance_h: settings.series_inductance_h.max(0.0),
        effective_inductance_h: l_total,
        line_resistance_ohm: 2.0 * r_phase,
        time_constant_s: if r_phase > 0.0 { l_total / r_phase } else { 0.0 },
        bus_voltage_v: v_bus,
        phase_current_a: i,
        pwm_hz: settings.pwm_hz,
        target_speed_m_s: settings.target_speed_m_s,
        thrust_constant_n_per_a: kf,
        back_emf_constant_v_s_per_m: ke,
        holding_voltage_v: holding_v,
        speed_voltage_v: speed_v,
        available_voltage_v: available,
        voltage_limited_current_a: voltage_limited_current,
        max_speed_m_s: max_speed,
        ripple_pp_a: ripple,
        min_pwm_hz: min_pwm,
        added_inductance_h: added_inductance,
        peak_current_a: peak_current,
        trace_ampacity_a: ampacity,
        copper_loss_w: copper_loss,
        thrust_n: kf.map(|k| k * i),
        max_continuous_current_a: max_cont,
        limiting_factor: limiting,
        max_continuous_thrust_n: kf.map(|k| k * max_cont),
        checks,
        speed_curve,
        notes,
        backplane,
    }
}

#[cfg(test)]
mod tests;
