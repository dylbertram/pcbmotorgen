//! Experimental steady-travel eddy loss, partitioned by conducting region.
//!
//! Linear housing/FR4 stacks use odd travel harmonics with bounded source tails.
//! Magnetic shielding retains the explicitly limited effective-DC fundamental.
//! Neither path is a finite housing/entry-exit transient model.
//! Joule loss is integrated from each medium's electric field, not obtained by
//! subtracting losses from drag. The independent surface-work expression is
//! checked against the sum of all region losses.
use super::{reflection_ac, mode_bz, dc_fields, describing_mu, BackplaneStack, HousingMaterial, Medium, SolvedStack, MU_0};
use crate::params::SimulationInput;
use nalgebra::Complex;
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

const REFINEMENT_LIMIT: f64 = 0.05;
const ENERGY_BALANCE_LIMIT: f64 = 1e-8;
const POWER_FLOOR_W: f64 = 1e-12;
const MAX_SAMPLES: usize = 16384;
const MAX_HARMONIC: usize = 511;
const TAIL_LIMIT: f64 = 0.005;

/// An already-established steady travelling field maintained for this time.
/// Starts, stops, acceleration and finite housing edges are not represented.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HousingMotionProfile {
    pub duration_s: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum HousingMotionAnalysis {
    Experimental { estimate: HousingMotionEstimate },
    Unavailable { reason: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HousingMotionEstimate {
    pub method: String,
    pub housing_material: HousingMaterial,
    pub speed_m_s: f64,
    pub duration_s: f64,
    pub equivalent_travel_m: f64,
    /// Positive, power-equivalent housing contribution opposing motion.
    pub housing_drag_n: f64,
    /// Signed power-equivalent mover force, opposite the specified velocity.
    pub signed_housing_drag_n: f64,
    pub housing_joule_power_w: f64,
    pub housing_energy_j: f64,
    pub layer_joule_power_w: Vec<f64>,
    pub total_stack_joule_power_w: f64,
    pub total_stack_drag_n: f64,
    pub power_balance_relative_error: f64,
    pub quadrature_relative_change: f64,
    pub quadrature_samples: usize,
    /// Highest odd travel harmonic, not the number of terms.
    pub max_travel_harmonic: usize,
    /// Conservative omitted-source power bounds, only for the linear path.
    pub travel_tail_bound_w: Option<f64>,
    pub cross_travel_tail_bound_w: Option<f64>,
    pub cutoff_relative_change: f64,
    pub warnings: Vec<String>,
}

/// Normalized integral of |A|² over every layer for unit incident B at the
/// stack surface. Both exponential terms decay from their respective faces.
fn mode_losses(kappa: f64, omega: f64, media: &[Medium]) -> Result<Vec<f64>, String> {
    let one = Complex::new(1.0, 0.0);
    let air = Complex::new(kappa, 0.0);
    let mut eta_below = air;
    let mut g = Complex::new(0.0, 0.0);
    let mut bottom = vec![g; media.len()];
    let mut top = bottom.clone();
    let mut gammas = bottom.clone();
    for i in (0..media.len()).rev() {
        let m = media[i];
        let gamma = Complex::new(kappa * kappa, omega * MU_0 * m.mu * m.sigma).sqrt();
        let eta = gamma / m.mu;
        let rho = (eta - eta_below) / (eta + eta_below);
        bottom[i] = (rho + g) / (one + rho * g);
        top[i] = bottom[i] * (-gamma * (2.0 * m.t)).exp();
        gammas[i] = gamma; g = top[i]; eta_below = eta;
    }
    let rho = (air - eta_below) / (air + eta_below);
    let r = (rho + g) / (one + rho * g);
    let mut at_face = one + r;
    let mut losses = Vec::with_capacity(media.len());
    for (i, m) in media.iter().enumerate() {
        let gamma = gammas[i];
        let down = at_face / (one + top[i]);
        let decay = (-gamma * m.t).exp();
        at_face = down * decay * (one + bottom[i]);
        if m.sigma == 0.0 || m.t == 0.0 { losses.push(0.0); continue; }
        let alpha = gamma.re; let beta_t = gamma.im * m.t;
        let attenuation = (-2.0 * alpha * m.t).exp();
        let forward_integral = -(-2.0 * alpha * m.t).exp_m1() / (2.0 * alpha);
        let sinc = if beta_t.abs() < 1e-6 { 1.0 - beta_t * beta_t / 6.0 } else { beta_t.sin() / beta_t };
        let cross = 2.0 * m.t * attenuation * sinc
            * (bottom[i] * Complex::new(0.0, -beta_t).exp()).re;
        let integral = forward_integral * (1.0 + bottom[i].norm_sqr() * attenuation) + cross;
        let value = m.sigma * (omega / kappa).powi(2) * down.norm_sqr() * integral;
        if !value.is_finite() || value < 0.0 {
            return Err("Housing motion encountered a nonfinite or negative region loss".into());
        }
        losses.push(value);
    }
    Ok(losses)
}

struct LossIntegral { regions: Vec<f64>, mechanical_w: f64 }

fn integrate(sim: &SimulationInput, solved: &SolvedStack, speed: f64, n: usize, harmonic: usize, cutoff: f64) -> Result<LossIntegral, String> {
    let k = harmonic as f64 * PI / sim.pole_pitch_m(); let omega = k * speed.abs();
    let ky_max = cutoff / (sim.air_gap_m + sim.pcb_thickness_m);
    let step = ky_max / n as f64; let depth = sim.magnet_dims_m[1];
    let mut regions = vec![0.0; solved.free.len()]; let mut mechanical = 0.0;
    for i in 0..=n {
        let ky = i as f64 * step; let kappa = k.hypot(ky);
        let spectrum = if i == 0 { depth } else { 2.0 * (ky * depth / 2.0).sin() / ky };
        let weight = if i == 0 || i == n { 1.0 } else if i % 2 == 1 { 4.0 } else { 2.0 };
        let incident = if harmonic == 1 { mode_bz(sim, kappa) } else {
            2.0 / (harmonic as f64 * PI) * sim.magnet_remanence_t
                * (k * sim.magnet_dims_m[0] / 2.0).sin()
                * -(-kappa * sim.magnet_dims_m[2]).exp_m1()
                * (-kappa * (sim.air_gap_m + sim.pcb_thickness_m)).exp()
        };
        let field_weight = weight * (incident * spectrum).powi(2);
        for (j, value) in mode_losses(kappa, omega, &solved.magnet)?.iter().enumerate() {
            regions[solved.owner[j]] += field_weight * value;
        }
        // Independent boundary-work operator, not the region-volume loss.
        mechanical += field_weight * (-2.0 * omega / (kappa * MU_0))
            * reflection_ac(kappa, omega, &solved.magnet).im;
    }
    let scale = sim.magnet_count as f64 * sim.pole_pitch_m() * step / (6.0 * PI);
    for value in &mut regions { *value *= scale; }
    Ok(LossIntegral { regions, mechanical_w: mechanical * scale })
}

// Passive linear diffusion has Re(surface admittance)>=0, hence |R|<=1.
// Bound boundary work by 2*omega*B_inc²/(kappa*mu0), |sin|<=1,
// (1-exp(-kappa*h))<=1, kappa>=k_h, and
// integral_0^infinity |2*sin(ky*D/2)/ky|² dky = pi*D.
// The odd-harmonic remainder is then bounded by a geometric series with
// 1/h² replaced by its first omitted value. No fitted coefficients or
// apparent convergence of a few small/vanishing harmonics is used.
fn travel_tail_bound(sim: &SimulationInput, speed: f64, last: usize) -> f64 {
    let a = 2.0 * PI / sim.pole_pitch_m() * (sim.air_gap_m + sim.pcb_thickness_m);
    let next = (last + 2) as f64;
    sim.magnet_count as f64 * sim.pole_pitch_m() * speed.abs() / MU_0
        * (2.0 * sim.magnet_remanence_t / PI).powi(2) * sim.magnet_dims_m[1]
        * (-a * next).exp() / (next * next * -(-2.0 * a).exp_m1())
}

// Same passive bound for ky>K, using |spectrum|<=D, kappa>=ky and
// integral_K^infinity exp(-2*d*ky)/ky dky <= exp(-2*d*K)/(2*d*K).
fn cross_tail_bound(sim: &SimulationInput, speed: f64, harmonic: usize, cutoff: f64) -> f64 {
    let omega = harmonic as f64 * PI / sim.pole_pitch_m() * speed.abs();
    sim.magnet_count as f64 * sim.pole_pitch_m() * omega / (PI * MU_0)
        * (2.0 * sim.magnet_remanence_t * sim.magnet_dims_m[1] / (harmonic as f64 * PI)).powi(2)
        * (-2.0 * cutoff).exp() / (2.0 * cutoff)
}

impl BackplaneStack {
    pub fn housing_motion(&self, sim: &SimulationInput, speed_m_s: f64, profile: HousingMotionProfile) -> HousingMotionAnalysis {
        match self.motion_estimate(sim, speed_m_s, profile) {
            Ok(estimate) => HousingMotionAnalysis::Experimental { estimate },
            Err(reason) => HousingMotionAnalysis::Unavailable { reason },
        }
    }

    fn motion_estimate(&self, sim: &SimulationInput, speed: f64, profile: HousingMotionProfile) -> Result<HousingMotionEstimate, String> {
        self.validate()?; sim.validate().map_err(|e| e.to_string())?;
        let housing = self.housing.as_ref().ok_or("Housing motion requires a housing")?;
        if !speed.is_finite() || !profile.duration_s.is_finite() || profile.duration_s <= 0.0 {
            return Err("Housing motion requires finite speed and positive finite exposure duration".into());
        }
        if !sim.magnet_dims_m.iter().chain([&sim.magnet_pitch_m, &sim.magnet_remanence_t, &sim.pcb_thickness_m, &sim.air_gap_m]).all(|v| v.is_finite()) {
            return Err("Housing motion requires finite physical geometry and remanence".into());
        }
        let linear = self.layers.iter().all(|layer| {
            layer.mu_r() == 1.0 && layer.material.sigma_s_per_m() == 0.0
        });
        let separation = sim.air_gap_m + sim.pcb_thickness_m;
        if separation <= 0.0 { return Err("Housing motion requires positive source separation".into()); }
        let sample_request = (15.0 / separation * sim.magnet_dims_m[1] / (2.0 * PI) * 16.0).ceil().max(200.0);
        let multiplier = if linear { 4 } else { 2 };
        if !sample_request.is_finite() || sample_request > (MAX_SAMPLES / multiplier) as f64 {
            return Err("Housing motion spectral resolution exceeds its bounded workload; use an offline reference".into());
        }
        let n = (sample_request as usize + 1) / 2 * 2;
        let solved = self.solve(sim);
        let (_, fields) = dc_fields(solved.k, &solved.magnet);
        for (i, medium) in solved.magnet.iter().enumerate() {
            let original = solved.free[solved.owner[i]];
            if let Some(bsat) = original.bsat.filter(|_| original.mu > 1.0) {
                let h1 = fields[i].mean * solved.b0 / (MU_0 * medium.mu);
                let residual = (describing_mu(original.mu, bsat, h1) / medium.mu - 1.0).abs();
                if !residual.is_finite() || residual > 1e-6 {
                    return Err("Housing motion DC saturation approximation did not converge".into());
                }
            }
        }
        let housing_index = solved.free.len() - 1;
        let mut max_harmonic = 1;
        let mut tail = 0.0;
        let mut cross_tail = 0.0;
        let mut cutoff_change = 0.0_f64;
        let (fine, change) = if speed == 0.0 {
            (LossIntegral { regions: vec![0.0; solved.free.len()], mechanical_w: 0.0 }, 0.0)
        } else {
            let mut sum = LossIntegral { regions: vec![0.0; solved.free.len()], mechanical_w: 0.0 };
            let mut coarse_sum = sum.regions.clone();
            let mut cut_sum = sum.regions.clone();
            for harmonic in (1..=if linear { MAX_HARMONIC } else { 1 }).step_by(2) {
                let cut = integrate(sim, &solved, speed, n, harmonic, 15.0)?;
                let coarse = if linear { integrate(sim, &solved, speed, 2 * n, harmonic, 30.0)? } else {
                    LossIntegral { regions: cut.regions.clone(), mechanical_w: cut.mechanical_w }
                };
                let fine = integrate(sim, &solved, speed, multiplier * n, harmonic, if linear { 30.0 } else { 15.0 })?;
                let term_total: f64 = fine.regions.iter().sum();
                let balance = (term_total - fine.mechanical_w).abs() / term_total.abs().max(fine.mechanical_w.abs()).max(POWER_FLOOR_W);
                if !balance.is_finite() || balance > ENERGY_BALANCE_LIMIT || fine.mechanical_w < 0.0 {
                    return Err(format!("Housing motion failed harmonic {harmonic} independent energy check"));
                }
                for j in 0..sum.regions.len() {
                    sum.regions[j] += fine.regions[j];
                    coarse_sum[j] += coarse.regions[j];
                    cut_sum[j] += cut.regions[j];
                }
                sum.mechanical_w += fine.mechanical_w;
                max_harmonic = harmonic;
                if !linear { break; }
                tail = travel_tail_bound(sim, speed, harmonic);
                cross_tail += cross_tail_bound(sim, speed, harmonic, 30.0);
                if tail.is_finite() && tail <= TAIL_LIMIT * sum.regions[housing_index].max(POWER_FLOOR_W) { break; }
            }
            let change = coarse_sum.iter().zip(&sum.regions)
                .map(|(a, b)| (a - b).abs() / b.abs().max(POWER_FLOOR_W)).fold(0.0_f64, f64::max);
            if !change.is_finite() || change > REFINEMENT_LIMIT {
                return Err(format!("Housing motion failed its 5% numerical refinement check ({:.2}%)", change * 100.0));
            }
            if linear {
                cutoff_change = cut_sum.iter().zip(&coarse_sum)
                    .map(|(a, b)| (a - b).abs() / b.abs().max(POWER_FLOOR_W)).fold(0.0_f64, f64::max);
                let limit = TAIL_LIMIT * sum.regions[housing_index].max(POWER_FLOOR_W);
                if !tail.is_finite() || tail > limit || !cross_tail.is_finite() || cross_tail > limit {
                    return Err("Housing motion source-tail bound exceeds its bounded workload/0.5% power target; use an offline reference".into());
                }
                if !cutoff_change.is_finite() || cutoff_change > REFINEMENT_LIMIT {
                    return Err("Housing motion failed its independent cross-travel cutoff check".into());
                }
            }
            (sum, change)
        };
        let total: f64 = fine.regions.iter().sum(); let power = fine.regions[housing_index];
        let balance = (total - fine.mechanical_w).abs() / total.abs().max(fine.mechanical_w.abs()).max(POWER_FLOOR_W);
        if !balance.is_finite() || balance > ENERGY_BALANCE_LIMIT || fine.mechanical_w < 0.0 {
            return Err(format!("Housing motion failed its independent steady-state energy check ({balance:e})"));
        }
        let energy = power * profile.duration_s; let travel = speed.abs() * profile.duration_s;
        if !energy.is_finite() || !travel.is_finite() { return Err("Housing motion exposure overflows finite output range".into()); }
        let drag = if speed == 0.0 { 0.0 } else { power / speed.abs() };
        let total_drag = if speed == 0.0 { 0.0 } else { total / speed.abs() };
        let mut warnings = vec![
            if linear { "Experimental linear planar odd-travel-harmonic model with magnetic feedback; not a finite 3D housing prediction or hardware rating.".into() }
                else { "Experimental effective-DC travelling-fundamental shielding approximation. Higher travel harmonics are NOT included for this stack; their heat contribution is unbounded by the quadrature check.".into() },
            "Assumes an established steady field throughout the exposure; starts, stops, acceleration, finite array ends, slots and housing return boundaries are not resolved.".into(),
            "Housing heat is integrated from the housing electric field. Drag is its steady power-equivalent contribution, not a separately qualified housing-body force.".into(),
            "Magnetic shielding uses an effective DC saturation state, not full moving nonlinear or hysteretic material dynamics.".into(),
            "Moving-PM field only: winding-current field reaction and induced PCB-copper shielding are not included.".into(),
            "Housing conductivity is fixed at its room-temperature material value; conductivity/remanence thermal feedback is not included.".into(),
            "5% is a numerical quadrature target, not a physical error bar. Temperature rise and the 100°C absolute target require a separate thermal model.".into(),
            "Driver drag diagnostics remain fundamental-only; they are not an independent same-model check of harmonic housing results.".into(),
        ];
        if travel > sim.travel_m() {
            warnings.push("Equivalent exposure distance exceeds available stroke; this is a periodic steady-exposure estimate, not a validated finite-stroke trajectory.".into());
        }
        Ok(HousingMotionEstimate {
            method: if linear { "linear_planar_odd_harmonics_region_joule_v2" } else { "planar_travelling_fundamental_region_joule_v1" }.into(), housing_material: housing.material,
            speed_m_s: speed, duration_s: profile.duration_s, equivalent_travel_m: travel,
            housing_drag_n: drag, signed_housing_drag_n: -speed.signum() * drag,
            housing_joule_power_w: power, housing_energy_j: energy,
            layer_joule_power_w: fine.regions[..self.layers.len()].to_vec(), total_stack_joule_power_w: total,
            total_stack_drag_n: total_drag, power_balance_relative_error: balance,
            quadrature_relative_change: change, quadrature_samples: if speed == 0.0 { 0 } else { multiplier * n },
            max_travel_harmonic: max_harmonic, travel_tail_bound_w: linear.then_some(tail),
            cross_travel_tail_bound_w: linear.then_some(cross_tail), cutoff_relative_change: cutoff_change, warnings,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::{BackplaneLayer, HousingSpec, LayerMaterial};
    fn stack(material: HousingMaterial) -> BackplaneStack {
        BackplaneStack { layers: vec![], housing: Some(HousingSpec { material, thickness_m: 0.001, gap_m: 0.0001 }) }
    }
    fn estimate(stack: &BackplaneStack, sim: &SimulationInput, speed: f64) -> HousingMotionEstimate {
        match stack.housing_motion(sim, speed, HousingMotionProfile { duration_s: 0.1 }) {
            HousingMotionAnalysis::Experimental { estimate } => estimate,
            HousingMotionAnalysis::Unavailable { reason } => panic!("{reason}"),
        }
    }
    #[test]
    fn direct_region_loss_balances_independent_reflection_work() {
        let sim = SimulationInput::default();
        for material in [HousingMaterial::Aluminum6061, HousingMaterial::Aluminum5052, HousingMaterial::Stainless304, HousingMaterial::Stainless316] {
            let st = stack(material); let value = estimate(&st, &sim, 20.0);
            assert!(value.housing_joule_power_w > 0.0);
            assert!(value.power_balance_relative_error < ENERGY_BALANCE_LIMIT);
            assert_eq!(value.method, "linear_planar_odd_harmonics_region_joule_v2");
            assert!(value.travel_tail_bound_w.unwrap() <= TAIL_LIMIT * value.housing_joule_power_w);
            assert!((value.housing_energy_j / value.housing_joule_power_w - 0.1).abs() < 1e-12);
        }
    }
    #[test]
    fn housing_heat_is_not_total_conducting_stack_loss() {
        let mut st = stack(HousingMaterial::Aluminum6061);
        st.layers.push(BackplaneLayer::new(LayerMaterial::SiliconSteel, 0.00035));
        let value = estimate(&st, &SimulationInput::default(), 2.0);
        assert!(value.layer_joule_power_w[0] > 0.0);
        assert!(value.housing_joule_power_w > 0.0);
        assert!(value.total_stack_joule_power_w > value.housing_joule_power_w);
    }
    #[test]
    fn zero_and_reverse_motion_preserve_passivity_and_direction() {
        let st = stack(HousingMaterial::Stainless316); let sim = SimulationInput::default();
        let zero = estimate(&st, &sim, 0.0); assert_eq!(zero.housing_joule_power_w, 0.0); assert_eq!(zero.housing_drag_n, 0.0);
        let a = estimate(&st, &sim, 3.0); let b = estimate(&st, &sim, -3.0);
        assert_eq!(a.housing_joule_power_w, b.housing_joule_power_w);
        assert_eq!(a.signed_housing_drag_n, -b.signed_housing_drag_n);
        assert!(a.signed_housing_drag_n < 0.0);
    }
    #[test]
    fn invalid_profiles_and_unsupported_housing_have_no_numbers() {
        let sim = SimulationInput::default();
        for duration_s in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert!(matches!(stack(HousingMaterial::Aluminum6061).housing_motion(&sim, 2.0, HousingMotionProfile { duration_s }), HousingMotionAnalysis::Unavailable { .. }));
        }
        assert!(matches!(stack(HousingMaterial::Steel1018).housing_motion(&sim, 2.0, HousingMotionProfile { duration_s: 1.0 }), HousingMotionAnalysis::Unavailable { .. }));
    }
    #[test]
    fn different_geometry_and_maximum_input_cases_are_calculated() {
        for (magnets, layers, width, speed) in [(2, 2, 0.004, 0.2), (5, 4, 0.008, 3.0), (12, 16, 0.012, 20.0)] {
            let sim = SimulationInput { magnet_count: magnets, num_layers: layers, max_layers: 16,
                magnet_dims_m: [0.005, width, 0.003], magnet_pitch_m: 0.006, ..SimulationInput::default() };
            let value = estimate(&stack(HousingMaterial::Aluminum5052), &sim, speed);
            assert!(value.housing_energy_j > 0.0); assert!(value.quadrature_relative_change < REFINEMENT_LIMIT);
        }
    }
    #[test]
    fn narrow_magnets_include_material_harmonic_heating_without_fitting() {
        let sim = SimulationInput { magnet_dims_m: [0.0015, 0.005, 0.003],
            magnet_pitch_m: 0.006, pcb_thickness_m: 0.0002, air_gap_m: 0.0001,
            ..SimulationInput::default() };
        let mut st = stack(HousingMaterial::Aluminum5052);
        st.housing.as_mut().unwrap().thickness_m = 0.005;
        st.housing.as_mut().unwrap().gap_m = 0.0;
        let value = estimate(&st, &sim, 20.0);
        let fundamental = integrate(&sim, &st.solve(&sim), 20.0, 2048, 1, 30.0).unwrap();
        let ratio = value.housing_joule_power_w / fundamental.regions.last().unwrap();
        assert!(ratio > 1.32 && ratio < 1.33, "{ratio}");
        assert!(value.max_travel_harmonic > 1);
        assert!(value.travel_tail_bound_w.unwrap() / value.housing_joule_power_w <= TAIL_LIMIT);
        let mut weaker = sim.clone(); weaker.magnet_remanence_t *= 0.5;
        let scaled = estimate(&st, &weaker, 20.0);
        assert!((scaled.housing_joule_power_w / value.housing_joule_power_w - 0.25).abs() < 1e-10);
    }
    #[test]
    fn passive_tail_bound_dominates_explicit_omitted_terms() {
        let sim = SimulationInput::default(); let st = stack(HousingMaterial::Stainless304);
        let solved = st.solve(&sim);
        for last in [1, 3, 7] {
            let omitted: f64 = ((last + 2)..=31).step_by(2)
                .map(|h| integrate(&sim, &solved, 3.0, 800, h, 30.0).unwrap().mechanical_w).sum();
            assert!(omitted <= travel_tail_bound(&sim, 3.0, last));
        }
    }
    #[test]
    fn magnetic_shield_keeps_explicit_legacy_method_and_no_tail_claim() {
        let mut st = stack(HousingMaterial::Aluminum6061);
        st.layers.push(BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002));
        let value = estimate(&st, &SimulationInput::default(), 3.0);
        assert_eq!(value.method, "planar_travelling_fundamental_region_joule_v1");
        assert_eq!(value.max_travel_harmonic, 1);
        assert_eq!(value.travel_tail_bound_w, None);
        assert!(value.warnings.iter().any(|w| w.contains("Higher travel harmonics are NOT included")));
    }
    #[test]
    fn bounded_resolution_rejects_extreme_source_geometry_without_numbers() {
        let sim = SimulationInput { air_gap_m: 1e-9, pcb_thickness_m: 1e-9, ..SimulationInput::default() };
        assert!(matches!(stack(HousingMaterial::Aluminum6061).housing_motion(&sim, 20.0,
            HousingMotionProfile { duration_s: 0.1 }), HousingMotionAnalysis::Unavailable { .. }));
    }
}
