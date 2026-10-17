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
//! - The magnetic layers, and any FR4 between them, are collapsed into one
//!   slab with the series permeability `μ_eff = ΣT / Σ(T/μ)`. A slab of
//!   thickness `T` with air below reflects
//!   `R = r(1 − e^(−2kT)) / (1 − r²e^(−2kT))`, `r = (μ−1)/(μ+1)`. FR4 above
//!   the slab, FR4 below it and the housing gap are air. The housing is folded
//!   in with the standard layered-media recursion, so a non-magnetic housing
//!   changes nothing.
//! - The coil is `N` copper sheets (`N = num_layers ≥ 2`) spread evenly
//!   through the PCB of thickness `T`, at `d_i = i·T/(N−1)` above the PCB
//!   bottom: `d = 0` is the bottom face, `d = T` the top face. Each sheet
//!   sees its own image `2·d_i` away, so the inductance factor is
//!   `1 + R·(1/N)·Σ e^(−2k·d_i)`. For `N = 2` this is `1 + R·(1 + e^(−2kT))/2`.
//! - Every sheet carries the same current, as in a series-connected coil.
//!   Sheets are evenly spaced; real 4- and 6-layer stackups have uneven core
//!   and prepreg thicknesses, so inner-layer depths are approximate.
//! - Attraction is the mean Maxwell stress `R·B0²/μ0` over the array footprint
//!   `N·τ·D`. `B0` is the 2-D fundamental of the bare array at the stack top.
//! - Eddy-current loss and eddy drag in conductive housings are not modelled.
//!   Silicon steel above 20 kHz is flagged as a warning instead.
//! - Saturation is a 1-D flux-conservation estimate: the normal flux
//!   `(1+R)·B0` entering the stack top turns and runs through each magnetic
//!   layer and the housing on its own, so it is conservative.
//!
//! Material values are typical handbook numbers, not supplier data. Check
//! them against the datasheet of the part you buy.

use serde::{Deserialize, Serialize};

use crate::params::SimulationInput;

/// Vacuum permeability [H/m].
const MU_0: f64 = 4.0e-7 * std::f64::consts::PI;
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
    /// Every material, in UI order.
    pub const ALL: [LayerMaterial; 5] = [
        LayerMaterial::Fr4,
        LayerMaterial::SiliconSteel,
        LayerMaterial::MnZnFerrite,
        LayerMaterial::NiZnFerrite,
        LayerMaterial::FlexFerrite,
    ];

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

    /// True when the material carries flux (μr > 1).
    pub fn is_magnetic(self) -> bool {
        self.mu_r() > 1.0
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
    /// Every housing material, in UI order.
    pub const ALL: [HousingMaterial; 6] = [
        HousingMaterial::Aluminum6061,
        HousingMaterial::Aluminum5052,
        HousingMaterial::Steel1018,
        HousingMaterial::Stainless304,
        HousingMaterial::Stainless316,
        HousingMaterial::Stainless430,
    ];

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
    /// Non-magnetic thickness between the PCB and the first magnetic layer [m].
    pub spacer_m: f64,
    /// Thickness from the first to the last magnetic layer, including any FR4
    /// between them [m].
    pub magnetic_thickness_m: f64,
    /// Series-combined permeability over `magnetic_thickness_m`.
    pub mu_eff: f64,
    /// Composite reflection `R` of the stack and housing at the PCB bottom,
    /// at the fundamental. Zero when nothing below the PCB is magnetic.
    pub image_strength: f64,
    /// Always zero: the housing is folded into `image_strength`.
    pub housing_image_strength: f64,
    /// z of the image plane [m]: the PCB bottom, `−pcb_thickness_m`.
    pub image_plane_z_m: f64,
    /// z of the housing top face [m], when a housing is present.
    pub housing_plane_z_m: Option<f64>,
    /// Fundamental normal field of the bare magnet array at the stack top [T].
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

    /// Derive the composite reflection, inductance factor, attraction and
    /// saturation estimates for `sim`.
    pub fn analyze(&self, sim: &SimulationInput) -> BackplaneAnalysis {
        let tau = sim.pole_pitch_m();
        let k = std::f64::consts::PI / tau;
        let t_pcb = sim.pcb_thickness_m;
        let stack_t = self.stack_thickness_m();
        let mut warnings = Vec::new();

        // Magnetic span: first to last magnetic layer. Non-magnetic layers
        // above and below it act as air.
        let first_mag = self.layers.iter().position(|l| l.material.is_magnetic());
        let last_mag = self.layers.iter().rposition(|l| l.material.is_magnetic());
        let (spacer, t_m, mu_eff) = match (first_mag, last_mag) {
            (Some(i), Some(j)) => {
                let span = &self.layers[i..=j];
                let t: f64 = span.iter().map(|l| l.thickness_m).sum();
                // Series rule for normal flux.
                let reluctance: f64 = span.iter().map(|l| l.thickness_m / l.material.mu_r()).sum();
                let spacer = self.layers[..i].iter().map(|l| l.thickness_m).sum();
                (spacer, t, t / reluctance)
            }
            _ => (0.0, 0.0, 1.0),
        };

        // Media below the PCB bottom, top down, as (μr, thickness).
        let mut media = vec![(1.0, spacer), (mu_eff, t_m)];
        if let Some(h) = &self.housing {
            let below = stack_t - spacer - t_m + h.gap_m;
            media.extend([(1.0, below), (h.material.mu_r(), h.thickness_m)]);
        }
        let image_strength = reflection(k, &media);

        // Fundamental of the bare array at the stack top, 2-D.
        let [w, depth, h_mag] = sim.magnet_dims_m;
        let b0 = 2.0 / std::f64::consts::PI
            * sim.magnet_remanence_t
            * (std::f64::consts::PI * w / (2.0 * tau)).sin()
            * (1.0 - (-k * h_mag).exp())
            * (-k * (sim.air_gap_m + t_pcb)).exp();

        // Mean Maxwell stress R·B0²/μ0 over the array footprint N·τ·D.
        let footprint = sim.magnet_count as f64 * tau * depth;
        let attraction_n = image_strength * b0 * b0 / MU_0 * footprint;

        // Equal-current copper sheets spread over the PCB, each with its own
        // image. Validation rejects num_layers < 2; clamp so analyze never
        // divides by zero on unvalidated input.
        let copper_layers = sim.num_layers.max(2);
        let copper_depths_m = copper_depths(t_pcb, copper_layers);
        let inductance_factor = inductance_factor(image_strength, k, &copper_depths_m);

        // Flux-conservation saturation estimate. The normal flux (1+R)·B0
        // entering the stack top, a half-pitch of it per unit width
        // (Φ/width = B·τ/π), turns and runs through each magnetic part alone.
        let flux_per_width = if image_strength > 0.0 {
            (1.0 + image_strength) * b0 * tau / std::f64::consts::PI
        } else {
            0.0
        };
        let layer_peak_b_t: Vec<f64> = self
            .layers
            .iter()
            .enumerate()
            .map(|(i, layer)| {
                if !layer.material.is_magnetic() {
                    return 0.0;
                }
                let b = flux_per_width / layer.thickness_m;
                if let Some(bsat) = layer.material.bsat_t() {
                    if b > bsat {
                        warnings.push(format!(
                            "Backplane layer {} ({}): estimated peak {:.2} T exceeds Bsat {:.2} T. The linear model is not valid here; add thickness or change material.",
                            i + 1,
                            layer.material.label(),
                            b,
                            bsat
                        ));
                    }
                }
                b
            })
            .collect();

        let housing_peak_b_t = match &self.housing {
            Some(h) => match h.material.bsat_t() {
                Some(bsat) => {
                    let b = flux_per_width / h.thickness_m;
                    if b > bsat {
                        warnings.push(format!(
                            "Housing ({}): estimated peak {:.2} T exceeds Bsat {:.2} T. Increase wall thickness or use a non-magnetic grade.",
                            h.material.label(),
                            b,
                            bsat
                        ));
                    }
                    b
                }
                None => 0.0,
            },
            None => 0.0,
        };

        BackplaneAnalysis {
            stack_thickness_m: stack_t,
            spacer_m: spacer,
            magnetic_thickness_m: t_m,
            mu_eff,
            image_strength,
            housing_image_strength: 0.0,
            image_plane_z_m: -t_pcb,
            housing_plane_z_m: self.housing.as_ref().map(|h| -(t_pcb + stack_t + h.gap_m)),
            b0_t: b0,
            copper_layers,
            copper_depths_m,
            inductance_factor,
            attraction_n,
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

    fn stack(material: LayerMaterial, thickness_m: f64) -> BackplaneStack {
        BackplaneStack {
            layers: vec![BackplaneLayer {
                material,
                thickness_m,
            }],
            housing: None,
        }
    }

    #[test]
    fn fr4_only_adds_height_and_no_flux() {
        let s = sim();
        let a = stack(LayerMaterial::Fr4, mm(1.6)).analyze(&s);
        assert_eq!(a.image_strength, 0.0);
        assert_eq!(a.inductance_factor, 1.0);
        assert_eq!(a.attraction_n, 0.0);
        assert!((a.stack_thickness_m - mm(1.6)).abs() < 1e-12);
        assert!(a.warnings.is_empty());
    }

    #[test]
    fn higher_permeability_gives_more_image_strength() {
        let s = sim();
        let nizn = stack(LayerMaterial::NiZnFerrite, mm(3.0)).analyze(&s);
        let mnzn = stack(LayerMaterial::MnZnFerrite, mm(3.0)).analyze(&s);
        assert!(mnzn.image_strength > nizn.image_strength);
        assert!(mnzn.image_strength <= 1.0);
        assert!(mnzn.inductance_factor > nizn.inductance_factor);
        assert!(mnzn.inductance_factor > 1.0);
    }

    #[test]
    fn thicker_layer_gives_more_image_strength_up_to_r() {
        let s = sim();
        let thin = stack(LayerMaterial::MnZnFerrite, mm(0.5)).analyze(&s);
        let thick = stack(LayerMaterial::MnZnFerrite, mm(5.0)).analyze(&s);
        assert!(thick.image_strength > thin.image_strength);
        assert!(thick.image_strength < 1.0);
    }

    #[test]
    fn thick_slab_reflects_r() {
        let mu = LayerMaterial::FlexFerrite.mu_r();
        let r = (mu - 1.0) / (mu + 1.0);
        let k = std::f64::consts::PI / mm(6.0);
        assert!((reflection(k, &[(mu, 1.0)]) - r).abs() < 1e-12);
    }

    #[test]
    fn slab_closed_form_matches_recursion() {
        let k = std::f64::consts::PI / mm(6.0);
        for (mu, t) in [
            (60.0, mm(0.3)),
            (2500.0, mm(2.0)),
            (4000.0, mm(0.35)),
            (1.5, mm(5.0)),
        ] {
            let r: f64 = (mu - 1.0) / (mu + 1.0);
            let e = (-2.0 * k * t).exp();
            let closed = r * (1.0 - e) / (1.0 - r * r * e);
            // One step of R_top = (r + R_b·e)/(1 + r·R_b·e) with air below, R_b = −r.
            let step = (r - r * e) / (1.0 - r * r * e);
            assert!((reflection(k, &[(mu, t)]) - closed).abs() < 1e-12);
            assert!((step - closed).abs() < 1e-12);
        }
    }

    #[test]
    fn unit_permeability_changes_nothing() {
        let k = std::f64::consts::PI / mm(6.0);
        assert_eq!(reflection(k, &[(1.0, mm(1.0)), (1.0, mm(3.0))]), 0.0);
        let a = BackplaneStack {
            layers: vec![],
            housing: Some(HousingSpec {
                material: HousingMaterial::Aluminum6061,
                thickness_m: mm(3.0),
                gap_m: mm(1.0),
            }),
        }
        .analyze(&sim());
        assert_eq!(a.inductance_factor, 1.0);
        assert_eq!(a.attraction_n, 0.0);
    }

    #[test]
    fn attraction_scales_with_count_and_depth() {
        let st = stack(LayerMaterial::MnZnFerrite, mm(2.0));
        let base = sim();
        let a = st.analyze(&base).attraction_n;
        let mut more = sim();
        more.magnet_count *= 2;
        let mut deeper = sim();
        deeper.magnet_dims_m[1] *= 3.0;
        assert!(a > 0.0);
        assert!((st.analyze(&more).attraction_n / a - 2.0).abs() < 1e-9);
        assert!((st.analyze(&deeper).attraction_n / a - 3.0).abs() < 1e-9);
    }

    #[test]
    fn spacer_above_magnetic_layer_weakens_reflection() {
        let s = sim();
        let bare = stack(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        let spaced = BackplaneStack {
            layers: vec![
                BackplaneLayer {
                    material: LayerMaterial::Fr4,
                    thickness_m: mm(1.0),
                },
                BackplaneLayer {
                    material: LayerMaterial::MnZnFerrite,
                    thickness_m: mm(2.0),
                },
            ],
            housing: None,
        }
        .analyze(&s);
        assert!((spaced.spacer_m - mm(1.0)).abs() < 1e-12);
        assert_eq!(spaced.image_plane_z_m, -s.pcb_thickness_m);
        let k = std::f64::consts::PI / s.pole_pitch_m();
        let decay = (-2.0 * k * mm(1.0)).exp();
        assert!((spaced.image_strength - bare.image_strength * decay).abs() < 1e-12);
        assert!(spaced.inductance_factor < bare.inductance_factor);
    }

    fn layered(num_layers: u32) -> (SimulationInput, BackplaneAnalysis) {
        let mut s = sim();
        s.num_layers = num_layers;
        let a = stack(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        (s, a)
    }

    #[test]
    fn two_layers_match_closed_form() {
        let (s, a) = layered(2);
        let k = std::f64::consts::PI / s.pole_pitch_m();
        let t = s.pcb_thickness_m;
        let expected = 1.0 + a.image_strength * (1.0 + (-2.0 * k * t).exp()) / 2.0;
        assert_eq!(a.copper_layers, 2);
        assert_eq!(a.copper_depths_m, vec![0.0, t]);
        assert!((a.inductance_factor - expected).abs() < 1e-12);
    }

    #[test]
    fn four_layers_match_closed_form() {
        let (s, a) = layered(4);
        let k = std::f64::consts::PI / s.pole_pitch_m();
        let t = s.pcb_thickness_m;
        let sum: f64 = [0.0, t / 3.0, 2.0 * t / 3.0, t]
            .iter()
            .map(|d| (-2.0 * k * d).exp())
            .sum();
        let expected = 1.0 + a.image_strength * sum / 4.0;
        assert!((a.inductance_factor - expected).abs() < 1e-12);
    }

    #[test]
    fn many_layers_tend_to_continuous_average() {
        let (s, a) = layered(201);
        let x = 2.0 * std::f64::consts::PI / s.pole_pitch_m() * s.pcb_thickness_m;
        let limit = (1.0 - (-x).exp()) / x;
        let mean = (a.inductance_factor - 1.0) / a.image_strength;
        assert!((mean / limit - 1.0).abs() < 0.01, "{mean} vs {limit}");
    }

    #[test]
    fn fewer_than_two_layers_clamp_to_two() {
        assert_eq!(layered(0).1, layered(2).1);
        assert_eq!(layered(1).1, layered(2).1);
    }

    #[test]
    fn spacer_lowers_image_and_inductance() {
        let s = sim();
        let bare = stack(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        let gapped = BackplaneStack {
            layers: vec![
                BackplaneLayer {
                    material: LayerMaterial::Fr4,
                    thickness_m: mm(0.1),
                },
                BackplaneLayer {
                    material: LayerMaterial::MnZnFerrite,
                    thickness_m: mm(2.0),
                },
            ],
            housing: None,
        }
        .analyze(&s);
        assert!(gapped.image_strength < bare.image_strength);
        assert!(gapped.inductance_factor < bare.inductance_factor);
    }

    #[test]
    fn thin_silicon_steel_saturates_and_warns() {
        let s = sim();
        let a = stack(LayerMaterial::SiliconSteel, mm(0.35)).analyze(&s);
        assert!(a.layer_peak_b_t[0] > LayerMaterial::SiliconSteel.bsat_t().unwrap());
        assert!(a.warnings.iter().any(|w| w.contains("Silicon steel")));
    }

    #[test]
    fn non_magnetic_housing_adds_gap_but_no_image() {
        let s = sim();
        let stack = BackplaneStack {
            layers: vec![BackplaneLayer {
                material: LayerMaterial::MnZnFerrite,
                thickness_m: mm(2.0),
            }],
            housing: Some(HousingSpec {
                material: HousingMaterial::Aluminum6061,
                thickness_m: mm(3.0),
                gap_m: mm(1.0),
            }),
        };
        let a = stack.analyze(&s);
        assert_eq!(a.housing_peak_b_t, 0.0);
        assert!(a.housing_plane_z_m.is_some());
        let bare = stack_of_one(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        assert_eq!(a.image_strength, bare.image_strength);
        assert_eq!(a.inductance_factor, bare.inductance_factor);
        assert_eq!(a.attraction_n, bare.attraction_n);
    }

    #[test]
    fn magnetic_housing_adds_inductance_and_attraction() {
        let s = sim();
        let steel = HousingSpec {
            material: HousingMaterial::Steel1018,
            thickness_m: mm(3.0),
            gap_m: mm(0.5),
        };
        let alone = BackplaneStack {
            layers: vec![],
            housing: Some(steel.clone()),
        }
        .analyze(&s);
        assert!(alone.inductance_factor > 1.0);
        assert!(alone.attraction_n > 0.0);
        // Behind 2 mm of MnZn the housing is screened: it adds only a little.
        let plain = stack_of_one(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        let with_steel = BackplaneStack {
            layers: plain_layers(),
            housing: Some(steel),
        }
        .analyze(&s);
        assert!(with_steel.inductance_factor > plain.inductance_factor);
        assert!(with_steel.attraction_n > plain.attraction_n);
        assert!(with_steel.inductance_factor / plain.inductance_factor < 1.01);
    }

    fn plain_layers() -> Vec<BackplaneLayer> {
        vec![BackplaneLayer {
            material: LayerMaterial::MnZnFerrite,
            thickness_m: mm(2.0),
        }]
    }

    #[test]
    fn housing_gap_weakens_housing_image_inductance() {
        let s = sim();
        let make = |gap| BackplaneStack {
            layers: vec![],
            housing: Some(HousingSpec {
                material: HousingMaterial::Steel1018,
                thickness_m: mm(3.0),
                gap_m: gap,
            }),
        };
        let near = make(mm(0.2)).analyze(&s);
        let far = make(mm(3.0)).analyze(&s);
        assert!(near.inductance_factor > far.inductance_factor);
    }

    #[test]
    fn validation_rejects_bad_thickness_and_gap() {
        assert!(stack(LayerMaterial::FlexFerrite, 0.0).validate().is_err());
        assert!(stack(LayerMaterial::FlexFerrite, -1.0e-3)
            .validate()
            .is_err());
        assert!(stack(LayerMaterial::FlexFerrite, f64::NAN)
            .validate()
            .is_err());
        assert!(stack(LayerMaterial::FlexFerrite, 0.3e-3).validate().is_ok());
        let bad_gap = BackplaneStack {
            layers: vec![],
            housing: Some(HousingSpec {
                material: HousingMaterial::Steel1018,
                thickness_m: mm(2.0),
                gap_m: -1.0,
            }),
        };
        assert!(bad_gap.validate().is_err());
    }

    #[test]
    fn default_backplane_is_empty_and_has_no_effect() {
        let stack = BackplaneStack::default();
        let a = stack.analyze(&sim());
        assert_eq!(a.image_strength, 0.0);
        assert_eq!(a.inductance_factor, 1.0);
        assert_eq!(stack.stack_thickness_m(), 0.0);
    }

    fn stack_of_one(material: LayerMaterial, thickness_m: f64) -> BackplaneStack {
        stack(material, thickness_m)
    }

    #[test]
    fn image_magnets_strengthen_field_at_pcb_surface() {
        let base = sim();
        let mut with = sim();
        with.backplane = Some(stack(LayerMaterial::MnZnFerrite, mm(2.0)));
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
        with.backplane = Some(BackplaneStack {
            layers: vec![BackplaneLayer {
                material: LayerMaterial::MnZnFerrite,
                thickness_m: mm(2.0),
            }],
            housing: Some(HousingSpec {
                material: HousingMaterial::Steel1018,
                thickness_m: mm(3.0),
                gap_m: mm(0.5),
            }),
        });
        let n = with.magnet_count as usize;
        let assembly = crate::MagnetArray::new(&with).build_assembly(0.0);
        assert_eq!(assembly.iter().count(), 2 * n);
    }
}
