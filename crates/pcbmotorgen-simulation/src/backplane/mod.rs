//! Backplane and housing stackup below the PCB (ticket t707).
//!
//! The stack sits under the PCB and is ordered from the PCB downward:
//! `layers[0]` touches the PCB. A housing can sit below the stack with an
//! air gap between them.
//!
//! # Approximations
//!
//! These are the documented limits of the model. They are also shown in the UI.
//!
//! - Boundaries are planar and infinite. Edge and corner effects are ignored.
//! - Permeability is linear. Saturation is reported as a warning and is not
//!   fed back into the field.
//! - Only the fundamental, `k = π/τ`, is modelled. The whole stack, housing
//!   included, becomes one reflection coefficient `R` at the PCB bottom, and
//!   the magnet field model mirrors the array across that plane with
//!   strength `R`.
//! - `R` comes from the layered-media recursion over every layer, the
//!   housing gap and the housing, bottom up:
//!   `R_top = (r + R_b·e^(−2kT)) / (1 + r·R_b·e^(−2kT))`, with `r` the
//!   interface coefficient seen from above and `R_b` the reflection below the
//!   layer of thickness `T`. One slab in air gives
//!   `R = r(1 − e^(−2kT)) / (1 − r²e^(−2kT))`, `r = (μ−1)/(μ+1)`. FR4 and a
//!   non-magnetic housing have μ = 1, so they only add distance.
//! - The coil is `N` copper sheets (`N = num_layers ≥ 2`) spread evenly
//!   through the PCB of thickness `T`, at `d_i = i·T/(N−1)` above the PCB
//!   bottom: `d = 0` is the bottom face, `d = T` the top face. Each sheet
//!   sees its own image `2·d_i` away, so the inductance factor is
//!   `1 + R·(1/N)·Σ e^(−2k·d_i)`. For `N = 2` this is `1 + R·(1 + e^(−2kT))/2`.
//! - Every sheet carries the same current, as in a series-connected coil.
//!   Sheets are evenly spaced; real 4- and 6-layer stackups have uneven core
//!   and prepreg thicknesses, so inner-layer depths are approximate.
//! - Attraction is the mean Maxwell stress on the stack top. For an infinitely
//!   deep array it is `R·B0²/μ0` over the footprint `N·τ·D`, where `B0` is the
//!   2-D fundamental of the bare array at the stack top. Magnets of finite depth
//!   `D` are summed over their cross-travel spectrum, see [`attraction_n`].
//!   Array ends in the travel direction are ignored.
//! - Eddy-current loss and eddy drag in conductive housings are not modelled.
//!   Silicon steel above 20 kHz is flagged as a warning instead.
//! - Saturation: the normal field `(1+R)·B0` at the stack top turns into a
//!   high-μ plate of thickness `T` and peaks at its top face at
//!   `(1+R)·B0·coth(kT)`. Every magnetic layer and the housing is assumed to
//!   carry all of the flux on its own, so deeper layers are overestimated.
//!
//! Material values are typical handbook numbers, not supplier data. Check
//! them against the datasheet of the part you buy.

use std::f64::consts::PI;

use serde::{Deserialize, Serialize};

use crate::params::SimulationInput;

/// Vacuum permeability [H/m].
const MU_0: f64 = 4.0e-7 * PI;
/// Switching frequency above which silicon steel is flagged [Hz].
pub const SILICON_STEEL_PWM_LIMIT_HZ: f64 = 20e3;
/// Largest accepted thickness for one layer or the housing [m].
pub const MAX_THICKNESS_M: f64 = 0.02;

/// Material for a backplane layer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LayerMaterial {
    /// Glass-epoxy spacer. Non-magnetic, so it only adds height.
    Fr4,
    /// Electrical steel lamination.
    SiliconSteel,
    /// Sintered manganese-zinc ferrite plate.
    MnZnFerrite,
    /// Sintered nickel-zinc ferrite plate.
    NiZnFerrite,
    /// Polymer-bound flexible ferrite sheet.
    FlexFerrite,
}

impl LayerMaterial {
    /// Relative permeability (typical starting value).
    pub fn mu_r(self) -> f64 {
        match self {
            LayerMaterial::Fr4 => 1.0,
            LayerMaterial::SiliconSteel => 4000.0,
            LayerMaterial::MnZnFerrite => 2500.0,
            LayerMaterial::NiZnFerrite => 500.0,
            LayerMaterial::FlexFerrite => 60.0,
        }
    }

    /// Saturation flux density [T], or `None` for non-magnetic material.
    pub fn bsat_t(self) -> Option<f64> {
        match self {
            LayerMaterial::Fr4 => None,
            LayerMaterial::SiliconSteel => Some(1.8),
            LayerMaterial::MnZnFerrite => Some(0.45),
            LayerMaterial::NiZnFerrite => Some(0.35),
            LayerMaterial::FlexFerrite => Some(0.25),
        }
    }

    /// Thickness used when a layer is first added [m].
    pub fn default_thickness_m(self) -> f64 {
        match self {
            LayerMaterial::Fr4 => 1.6e-3,
            LayerMaterial::SiliconSteel => 0.35e-3,
            LayerMaterial::MnZnFerrite => 2.0e-3,
            LayerMaterial::NiZnFerrite => 2.0e-3,
            LayerMaterial::FlexFerrite => 0.3e-3,
        }
    }

    /// Display name.
    pub fn label(self) -> &'static str {
        match self {
            LayerMaterial::Fr4 => "FR4",
            LayerMaterial::SiliconSteel => "Silicon steel",
            LayerMaterial::MnZnFerrite => "Sintered MnZn ferrite",
            LayerMaterial::NiZnFerrite => "Sintered NiZn ferrite",
            LayerMaterial::FlexFerrite => "Flexible ferrite sheet",
        }
    }
}

/// Material for the housing below the backplane.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HousingMaterial {
    /// Aluminum 6061-T6. Non-magnetic.
    Aluminum6061,
    /// Aluminum 5052-H32. Non-magnetic.
    Aluminum5052,
    /// Mild steel AISI 1018.
    Steel1018,
    /// Austenitic stainless 304. Non-magnetic when annealed.
    Stainless304,
    /// Austenitic stainless 316. Non-magnetic when annealed.
    Stainless316,
    /// Ferritic stainless 430. Magnetic.
    Stainless430,
}

impl HousingMaterial {
    /// Relative permeability (typical starting value).
    pub fn mu_r(self) -> f64 {
        match self {
            HousingMaterial::Aluminum6061 | HousingMaterial::Aluminum5052 => 1.0,
            HousingMaterial::Steel1018 => 800.0,
            HousingMaterial::Stainless304 | HousingMaterial::Stainless316 => 1.02,
            HousingMaterial::Stainless430 => 500.0,
        }
    }

    /// Saturation flux density [T], or `None` for non-magnetic material.
    pub fn bsat_t(self) -> Option<f64> {
        match self {
            HousingMaterial::Steel1018 => Some(1.6),
            HousingMaterial::Stainless430 => Some(1.2),
            _ => None,
        }
    }

    /// Display name.
    pub fn label(self) -> &'static str {
        match self {
            HousingMaterial::Aluminum6061 => "Aluminum 6061-T6",
            HousingMaterial::Aluminum5052 => "Aluminum 5052-H32",
            HousingMaterial::Steel1018 => "Mild steel 1018",
            HousingMaterial::Stainless304 => "Stainless 304",
            HousingMaterial::Stainless316 => "Stainless 316",
            HousingMaterial::Stainless430 => "Stainless 430",
        }
    }
}

/// One layer of the backplane stack.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BackplaneLayer {
    pub material: LayerMaterial,
    /// Layer thickness [m].
    pub thickness_m: f64,
}

/// Housing below the backplane, separated from it by an air gap.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct HousingSpec {
    pub material: HousingMaterial,
    /// Housing wall thickness [m].
    pub thickness_m: f64,
    /// Air gap between the bottom of the backplane and the housing [m].
    pub gap_m: f64,
}

/// Backplane stack plus optional housing.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BackplaneStack {
    /// Layers ordered from the PCB downward.
    pub layers: Vec<BackplaneLayer>,
    pub housing: Option<HousingSpec>,
}

/// Derived backplane quantities for one [`SimulationInput`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BackplaneAnalysis {
    /// Total thickness of the backplane layers [m].
    pub stack_thickness_m: f64,
    /// Composite reflection `R` of the stack and housing at the PCB bottom,
    /// at the fundamental. Zero when nothing below the PCB is magnetic.
    pub image_strength: f64,
    /// Fundamental normal field of the bare magnet array at the stack top,
    /// 2-D (infinitely deep magnets) [T].
    pub b0_t: f64,
    /// Copper sheet count `N` used for `inductance_factor` (`num_layers`,
    /// at least 2).
    pub copper_layers: u32,
    /// Height of each copper sheet above the PCB bottom [m], bottom first.
    pub copper_depths_m: Vec<f64>,
    /// Multiplier on per-phase inductance from the image currents.
    pub inductance_factor: f64,
    /// Estimated normal attraction between the magnets and the backplane +
    /// housing [N]. Positive pulls the mover toward the stack.
    pub attraction_n: f64,
    /// Estimated peak flux density in each backplane layer [T] (zero for
    /// non-magnetic layers), in the same order as `layers`.
    pub layer_peak_b_t: Vec<f64>,
    /// Estimated peak flux density in the housing wall [T] (zero if none).
    pub housing_peak_b_t: f64,
    /// Human-readable warnings (saturation, material limits).
    pub warnings: Vec<String>,
}

impl BackplaneStack {
    /// Total thickness of all backplane layers [m].
    pub fn stack_thickness_m(&self) -> f64 {
        self.layers.iter().map(|l| l.thickness_m).sum()
    }

    /// Thickness of the housing wall, or zero when there is none [m].
    pub fn housing_thickness_m(&self) -> f64 {
        self.housing.as_ref().map_or(0.0, |h| h.thickness_m)
    }

    /// Air gap below the backplane, or zero when there is no housing [m].
    pub fn housing_gap_m(&self) -> f64 {
        self.housing.as_ref().map_or(0.0, |h| h.gap_m)
    }

    /// Check thicknesses and gaps. Returns the first problem found.
    pub fn validate(&self) -> Result<(), String> {
        for (i, layer) in self.layers.iter().enumerate() {
            check_thickness(&format!("backplane layer {}", i + 1), layer.thickness_m)?;
        }
        if let Some(h) = &self.housing {
            check_thickness("housing", h.thickness_m)?;
            if !h.gap_m.is_finite() || h.gap_m < 0.0 || h.gap_m > MAX_THICKNESS_M {
                return Err(format!(
                    "housing gap must be between 0 and {} mm",
                    MAX_THICKNESS_M * 1e3
                ));
            }
        }
        Ok(())
    }

    /// Media below the PCB bottom, top down, as `(μr, thickness)`.
    fn media(&self) -> Vec<(f64, f64)> {
        let mut media: Vec<(f64, f64)> = self
            .layers
            .iter()
            .map(|l| (l.material.mu_r(), l.thickness_m))
            .collect();
        if let Some(h) = &self.housing {
            media.extend([(1.0, h.gap_m), (h.material.mu_r(), h.thickness_m)]);
        }
        media
    }

    /// Composite reflection `R` at the PCB bottom for the fundamental of `sim`.
    pub fn image_strength(&self, sim: &SimulationInput) -> f64 {
        reflection(PI / sim.pole_pitch_m(), &self.media())
    }

    /// Derive the composite reflection, inductance factor, attraction and
    /// saturation estimates for `sim`.
    pub fn analyze(&self, sim: &SimulationInput) -> BackplaneAnalysis {
        let tau = sim.pole_pitch_m();
        let k = PI / tau;
        let t_pcb = sim.pcb_thickness_m;
        let media = self.media();
        let image_strength = reflection(k, &media);
        let b0 = mode_bz(sim, k);

        // Equal-current copper sheets spread over the PCB, each with its own
        // image. Validation rejects num_layers < 2; clamp so analyze never
        // divides by zero on unvalidated input.
        let copper_layers = sim.num_layers.max(2);
        let copper_depths_m = copper_depths(t_pcb, copper_layers);
        let inductance_factor = inductance_factor(image_strength, k, &copper_depths_m);

        // Peak flux density at the top face of a high-μ plate of thickness t
        // that carries all the flux entering the stack top on its own.
        let b_surface = (1.0 + image_strength) * b0;
        let mut warnings = Vec::new();
        let mut peak = |what: String, bsat: Option<f64>, t: f64, advice: &str| -> f64 {
            let Some(bsat) = bsat else { return 0.0 };
            let b = b_surface / (k * t).tanh();
            if b > bsat {
                warnings.push(format!(
                    "{what}: estimated peak {b:.2} T exceeds Bsat {bsat:.2} T. {advice}"
                ));
            }
            b
        };
        let layer_peak_b_t: Vec<f64> = self
            .layers
            .iter()
            .enumerate()
            .map(|(i, l)| {
                peak(
                    format!("Backplane layer {} ({})", i + 1, l.material.label()),
                    l.material.bsat_t(),
                    l.thickness_m,
                    "The linear model is not valid here; add thickness or change material.",
                )
            })
            .collect();
        let housing_peak_b_t = self.housing.as_ref().map_or(0.0, |h| {
            peak(
                format!("Housing ({})", h.material.label()),
                h.material.bsat_t(),
                h.thickness_m,
                "Increase wall thickness or use a non-magnetic grade.",
            )
        });

        BackplaneAnalysis {
            stack_thickness_m: self.stack_thickness_m(),
            image_strength,
            b0_t: b0,
            copper_layers,
            copper_depths_m,
            inductance_factor,
            attraction_n: attraction_n(sim, &media),
            layer_peak_b_t,
            housing_peak_b_t,
            warnings,
        }
    }

    /// True when any layer is silicon steel. Used with the switching frequency
    /// to raise the eddy-current warning.
    pub fn has_silicon_steel(&self) -> bool {
        self.layers
            .iter()
            .any(|l| l.material == LayerMaterial::SiliconSteel)
    }
}

/// Reflection coefficient at the top of `media` (top down, `(μr, thickness)`)
/// for a field `e^(−k·z)` arriving from air above, with air below the last
/// medium. Built bottom up with `R = (ρ + R'·e^(−2kT)) / (1 + ρ·R'·e^(−2kT))`.
fn reflection(k: f64, media: &[(f64, f64)]) -> f64 {
    // `g`: reflection seen from inside the medium below, at its top face.
    let mut mu_below = 1.0;
    let mut g = 0.0;
    for &(mu, t) in media.iter().rev() {
        let rho = (mu_below - mu) / (mu_below + mu);
        g = (rho + g) / (1.0 + rho * g) * (-2.0 * k * t).exp();
        mu_below = mu;
    }
    let rho = (mu_below - 1.0) / (mu_below + 1.0);
    (rho + g) / (1.0 + rho * g)
}

/// Normal-field amplitude at the stack top of one spatial mode `kappa` of
/// the bare alternating array: `(2/π)·Br·sin(πw/2τ)·(1 − e^(−κh))·e^(−κd)`,
/// `d = air_gap + t_pcb`. At `κ = k = π/τ` this is the 2-D fundamental `B0`.
fn mode_bz(sim: &SimulationInput, kappa: f64) -> f64 {
    let [w, _, h] = sim.magnet_dims_m;
    let d = sim.air_gap_m + sim.pcb_thickness_m;
    2.0 / PI
        * sim.magnet_remanence_t
        * (PI * w / (2.0 * sim.pole_pitch_m())).sin()
        * (1.0 - (-kappa * h).exp())
        * (-kappa * d).exp()
}

/// Normal attraction between the magnets and the stack [N].
///
/// Each spatial mode `(k, k_y)` of the array field presses on the stack with
/// the mean Maxwell stress `R(κ)·B(κ)²/μ0`, `κ = √(k² + k_y²)`. A row of `N`
/// magnets of depth `D` spans `N·τ` along travel and has the cross-travel
/// spectrum `2·sin(k_y·D/2)/k_y`, so
/// `F = N·τ/(π·μ0) · ∫₀^∞ R(κ)·B(κ)²·(2·sin(k_y·D/2)/k_y)² dk_y`.
/// For `D → ∞` this is `R·B0²/μ0·N·τ·D`.
fn attraction_n(sim: &SimulationInput, media: &[(f64, f64)]) -> f64 {
    let tau = sim.pole_pitch_m();
    let k = PI / tau;
    let depth = sim.magnet_dims_m[1];
    let d = sim.air_gap_m + sim.pcb_thickness_m;
    // The field falls off as e^(−k_y·d): stop at e^(−15). Resolve both that
    // decay and the depth spectrum, whose lobes are 2π/D wide.
    let ky_max = 15.0 / d;
    let n = ((ky_max * depth / (2.0 * PI) * 16.0).ceil() as usize).max(200) / 2 * 2;
    let step = ky_max / n as f64;
    let integrand = |ky: f64| {
        let kappa = k.hypot(ky);
        let b = mode_bz(sim, kappa);
        let spectrum = if ky == 0.0 {
            depth
        } else {
            2.0 * (ky * depth / 2.0).sin() / ky
        };
        reflection(kappa, media) * b * b * spectrum * spectrum
    };
    // Composite Simpson.
    let sum: f64 = (0..=n)
        .map(|i| {
            let weight = if i == 0 || i == n {
                1.0
            } else if i % 2 == 1 {
                4.0
            } else {
                2.0
            };
            weight * integrand(i as f64 * step)
        })
        .sum();
    sim.magnet_count as f64 * tau / (PI * MU_0) * sum * step / 3.0
}

/// Heights of `n ≥ 2` evenly spaced copper sheets above the PCB bottom [m]:
/// `d_i = i·T/(n−1)`, from the bottom face to the top face.
fn copper_depths(t_pcb: f64, n: u32) -> Vec<f64> {
    (0..n).map(|i| t_pcb * i as f64 / (n - 1) as f64).collect()
}

/// `1 + R·(1/N)·Σ e^(−2k·d_i)`: each equal-current sheet at `d_i` above the
/// reflecting plane couples to its image `2·d_i` away.
fn inductance_factor(r: f64, k: f64, depths: &[f64]) -> f64 {
    let mean: f64 = depths.iter().map(|d| (-2.0 * k * d).exp()).sum::<f64>() / depths.len() as f64;
    1.0 + r * mean
}

fn check_thickness(what: &str, t: f64) -> Result<(), String> {
    if !t.is_finite() || t <= 0.0 || t > MAX_THICKNESS_M {
        return Err(format!(
            "{what} thickness must be greater than 0 and at most {} mm",
            MAX_THICKNESS_M * 1e3
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::units::mm;

    fn sim() -> SimulationInput {
        SimulationInput::default()
    }

    fn layer(material: LayerMaterial, t_mm: f64) -> BackplaneLayer {
        BackplaneLayer {
            material,
            thickness_m: mm(t_mm),
        }
    }

    fn housing(material: HousingMaterial, t_mm: f64, gap_mm: f64) -> Option<HousingSpec> {
        Some(HousingSpec {
            material,
            thickness_m: mm(t_mm),
            gap_m: mm(gap_mm),
        })
    }

    fn stack(layers: Vec<BackplaneLayer>, housing: Option<HousingSpec>) -> BackplaneStack {
        BackplaneStack { layers, housing }
    }

    fn mnzn(t_mm: f64) -> BackplaneStack {
        stack(vec![layer(LayerMaterial::MnZnFerrite, t_mm)], None)
    }

    /// The closed-infinity benchmark used in scripts/femm/RESULTS.md.
    fn benchmark() -> SimulationInput {
        SimulationInput {
            magnet_dims_m: [mm(5.0), mm(5.0), mm(3.0)],
            magnet_count: 5,
            magnet_pitch_m: mm(6.0),
            magnet_remanence_t: 1.34,
            air_gap_m: mm(0.5),
            pcb_thickness_m: mm(1.6),
            num_layers: 2,
            ..sim()
        }
    }

    fn k() -> f64 {
        PI / sim().pole_pitch_m()
    }

    #[test]
    fn default_backplane_is_empty_and_has_no_effect() {
        let stack = BackplaneStack::default();
        let a = stack.analyze(&sim());
        assert_eq!(a.image_strength, 0.0);
        assert_eq!(a.inductance_factor, 1.0);
        assert_eq!(a.attraction_n, 0.0);
        assert_eq!(stack.stack_thickness_m(), 0.0);
    }

    #[test]
    fn non_magnetic_material_only_adds_height() {
        let fr4 = stack(vec![layer(LayerMaterial::Fr4, 1.6)], None).analyze(&sim());
        let al = stack(vec![], housing(HousingMaterial::Aluminum6061, 3.0, 1.0)).analyze(&sim());
        for a in [&fr4, &al] {
            assert_eq!(a.image_strength, 0.0);
            assert_eq!(a.inductance_factor, 1.0);
            assert_eq!(a.attraction_n, 0.0);
            assert_eq!(a.housing_peak_b_t, 0.0);
            assert!(a.warnings.is_empty());
        }
        assert!((fr4.stack_thickness_m - mm(1.6)).abs() < 1e-12);
    }

    #[test]
    fn thick_slab_reflects_r() {
        let mu = LayerMaterial::FlexFerrite.mu_r();
        let r = (mu - 1.0) / (mu + 1.0);
        assert!((reflection(k(), &[(mu, 1.0)]) - r).abs() < 1e-12);
    }

    #[test]
    fn slab_closed_form_matches_recursion() {
        for (mu, t) in [
            (60.0, mm(0.3)),
            (2500.0, mm(2.0)),
            (4000.0, mm(0.35)),
            (1.5, mm(5.0)),
        ] {
            let r: f64 = (mu - 1.0) / (mu + 1.0);
            let e = (-2.0 * k() * t).exp();
            let closed = r * (1.0 - e) / (1.0 - r * r * e);
            assert!((reflection(k(), &[(mu, t)]) - closed).abs() < 1e-12);
        }
    }

    #[test]
    fn reflection_grows_with_permeability_and_thickness() {
        let s = sim();
        let nizn = stack(vec![layer(LayerMaterial::NiZnFerrite, 3.0)], None).analyze(&s);
        let thin = mnzn(0.5).analyze(&s);
        let thick = mnzn(3.0).analyze(&s);
        assert!(thick.image_strength > nizn.image_strength);
        assert!(thick.image_strength > thin.image_strength);
        assert!(thick.image_strength < 1.0);
        assert!(thick.inductance_factor > nizn.inductance_factor);
    }

    #[test]
    fn spacer_scales_reflection_by_its_round_trip() {
        let s = sim();
        let bare = mnzn(2.0);
        let spaced = stack(
            vec![
                layer(LayerMaterial::Fr4, 1.0),
                layer(LayerMaterial::MnZnFerrite, 2.0),
            ],
            None,
        );
        let decay = (-2.0 * k() * mm(1.0)).exp();
        assert!((spaced.image_strength(&s) - bare.image_strength(&s) * decay).abs() < 1e-12);
        assert!(spaced.analyze(&s).inductance_factor < bare.analyze(&s).inductance_factor);
    }

    #[test]
    fn split_magnetic_layers_reflect_like_one_plate() {
        // FEMM gives 1.596× for 1 mm MnZn / 0.5 mm FR4 / 1 mm MnZn and for
        // 2 mm MnZn alone. Collapsing the stack into one series-μ slab gave
        // R = 0.64 here.
        let split = stack(
            vec![
                layer(LayerMaterial::MnZnFerrite, 1.0),
                layer(LayerMaterial::Fr4, 0.5),
                layer(LayerMaterial::MnZnFerrite, 1.0),
            ],
            None,
        );
        let r = split.image_strength(&benchmark());
        assert!(
            r > 0.998 && r < mnzn(2.0).image_strength(&benchmark()),
            "{r}"
        );
    }

    fn layered(num_layers: u32) -> BackplaneAnalysis {
        let mut s = sim();
        s.num_layers = num_layers;
        mnzn(2.0).analyze(&s)
    }

    #[test]
    fn two_layers_match_closed_form() {
        let a = layered(2);
        let t = sim().pcb_thickness_m;
        let expected = 1.0 + a.image_strength * (1.0 + (-2.0 * k() * t).exp()) / 2.0;
        assert_eq!(a.copper_layers, 2);
        assert_eq!(a.copper_depths_m, vec![0.0, t]);
        assert!((a.inductance_factor - expected).abs() < 1e-12);
    }

    #[test]
    fn four_layers_match_closed_form() {
        let a = layered(4);
        let t = sim().pcb_thickness_m;
        let sum: f64 = [0.0, t / 3.0, 2.0 * t / 3.0, t]
            .iter()
            .map(|d| (-2.0 * k() * d).exp())
            .sum();
        assert!((a.inductance_factor - (1.0 + a.image_strength * sum / 4.0)).abs() < 1e-12);
    }

    #[test]
    fn many_layers_tend_to_continuous_average() {
        let a = layered(201);
        let x = 2.0 * k() * sim().pcb_thickness_m;
        let limit = (1.0 - (-x).exp()) / x;
        let mean = (a.inductance_factor - 1.0) / a.image_strength;
        assert!((mean / limit - 1.0).abs() < 0.01, "{mean} vs {limit}");
    }

    #[test]
    fn fewer_than_two_layers_clamp_to_two() {
        assert_eq!(layered(0), layered(2));
        assert_eq!(layered(1), layered(2));
    }

    #[test]
    fn deep_array_attraction_is_mean_maxwell_stress() {
        let mut s = sim();
        s.magnet_dims_m[1] = 1.0;
        let a = mnzn(2.0).analyze(&s);
        let footprint = s.magnet_count as f64 * s.pole_pitch_m() * s.magnet_dims_m[1];
        let two_d = a.image_strength * a.b0_t * a.b0_t / MU_0 * footprint;
        assert!(
            (a.attraction_n / two_d - 1.0).abs() < 0.005,
            "{} vs {two_d}",
            a.attraction_n
        );
    }

    #[test]
    fn attraction_of_benchmark_magnets_matches_3d_images() {
        // Benchmark: 5 magnets, 5 × 5 × 3 mm, τ = 6 mm, 0.5 mm gap, 1.6 mm
        // PCB, 2 mm MnZn. Magpylib, force between the magnets and their
        // R-scaled images in 3-D: 3.889 N. This model: 3.67 N, short by the
        // two array ends it ignores. The 2-D R·B0²/μ0·N·τ·D: 5.63 N.
        let s = benchmark();
        let f = mnzn(2.0).analyze(&s).attraction_n;
        assert!((f / 3.889 - 1.0).abs() < 0.07, "{f}");
        let mut more = s.clone();
        more.magnet_count *= 2;
        assert!((mnzn(2.0).analyze(&more).attraction_n / f - 2.0).abs() < 1e-9);
    }

    #[test]
    fn saturation_peak_follows_plate_thickness() {
        // FEMM, peak |B| at the stack top of the benchmark: 0.556 T for 2 mm
        // MnZn, 0.439 T for 5 mm and 2.40 T for 0.35 mm Si steel.
        let s = benchmark();
        let k = PI / s.pole_pitch_m();
        for (material, t_mm, femm) in [
            (LayerMaterial::MnZnFerrite, 2.0, 0.556),
            (LayerMaterial::MnZnFerrite, 5.0, 0.439),
            (LayerMaterial::SiliconSteel, 0.35, 2.40),
        ] {
            let a = stack(vec![layer(material, t_mm)], None).analyze(&s);
            let expected = (1.0 + a.image_strength) * a.b0_t / (k * mm(t_mm)).tanh();
            assert!((a.layer_peak_b_t[0] - expected).abs() < 1e-12);
            assert!((a.layer_peak_b_t[0] / femm - 1.0).abs() < 0.02, "{t_mm} mm");
        }
        let thin_si = stack(vec![layer(LayerMaterial::SiliconSteel, 0.35)], None).analyze(&s);
        assert!(thin_si.layer_peak_b_t[0] > LayerMaterial::SiliconSteel.bsat_t().unwrap());
        assert!(thin_si.warnings.iter().any(|w| w.contains("Silicon steel")));
        let fr4 = stack(
            vec![
                layer(LayerMaterial::Fr4, 1.0),
                layer(LayerMaterial::MnZnFerrite, 2.0),
            ],
            None,
        )
        .analyze(&s);
        assert_eq!(fr4.layer_peak_b_t[0], 0.0);
    }

    #[test]
    fn non_magnetic_housing_changes_nothing_behind_a_plate() {
        let s = sim();
        let with_al = stack(
            vec![layer(LayerMaterial::MnZnFerrite, 2.0)],
            housing(HousingMaterial::Aluminum6061, 3.0, 1.0),
        )
        .analyze(&s);
        let bare = mnzn(2.0).analyze(&s);
        assert_eq!(with_al.image_strength, bare.image_strength);
        assert_eq!(with_al.inductance_factor, bare.inductance_factor);
        assert_eq!(with_al.attraction_n, bare.attraction_n);
        assert_eq!(with_al.housing_peak_b_t, 0.0);
    }

    #[test]
    fn magnetic_housing_adds_unless_screened() {
        let s = sim();
        let steel = housing(HousingMaterial::Steel1018, 3.0, 0.5);
        let alone = stack(vec![], steel.clone()).analyze(&s);
        assert!(alone.inductance_factor > 1.0);
        assert!(alone.attraction_n > 0.0);
        assert!(alone.housing_peak_b_t > 0.0);
        // Behind 2 mm of MnZn the housing is screened: it adds only a little.
        let plain = mnzn(2.0).analyze(&s);
        let with_steel = stack(vec![layer(LayerMaterial::MnZnFerrite, 2.0)], steel).analyze(&s);
        assert!(with_steel.inductance_factor > plain.inductance_factor);
        assert!(with_steel.attraction_n > plain.attraction_n);
        assert!(with_steel.inductance_factor / plain.inductance_factor < 1.01);
    }

    #[test]
    fn housing_gap_weakens_housing_image() {
        let s = sim();
        let make = |gap| stack(vec![], housing(HousingMaterial::Steel1018, 3.0, gap));
        assert!(make(0.2).analyze(&s).inductance_factor > make(3.0).analyze(&s).inductance_factor);
    }

    #[test]
    fn validation_rejects_bad_thickness_and_gap() {
        let one = |t: f64| {
            stack(
                vec![BackplaneLayer {
                    material: LayerMaterial::FlexFerrite,
                    thickness_m: t,
                }],
                None,
            )
        };
        assert!(one(0.0).validate().is_err());
        assert!(one(-1.0e-3).validate().is_err());
        assert!(one(f64::NAN).validate().is_err());
        assert!(one(MAX_THICKNESS_M * 1.01).validate().is_err());
        assert!(one(0.3e-3).validate().is_ok());
        let bad_gap = stack(vec![], housing(HousingMaterial::Steel1018, 2.0, -1.0));
        assert!(bad_gap.validate().is_err());
    }

    #[test]
    fn image_magnets_strengthen_field_at_pcb_surface() {
        let base = sim();
        let mut with = sim();
        with.backplane = Some(mnzn(2.0));
        let b0 = crate::MagnetArray::new(&base).bfield_at_pcb_surface(&[0.0], 0.0, 0.0)[0][2];
        let b1 = crate::MagnetArray::new(&with).bfield_at_pcb_surface(&[0.0], 0.0, 0.0)[0][2];
        assert!(
            b1 > b0,
            "image should add field above a magnetic plane: {b0} -> {b1}"
        );
    }

    #[test]
    fn housing_folds_into_one_image_set() {
        let mut with = sim();
        with.backplane = Some(stack(
            vec![layer(LayerMaterial::MnZnFerrite, 2.0)],
            housing(HousingMaterial::Steel1018, 3.0, 0.5),
        ));
        let n = with.magnet_count as usize;
        let assembly = crate::MagnetArray::new(&with).build_assembly(0.0);
        assert_eq!(assembly.iter().count(), 2 * n);
    }
}
