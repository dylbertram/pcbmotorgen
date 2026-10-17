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
//! - Each boundary gets one image reflection, with strength
//!   `K = (μ−1)/(μ+1) · f_t`. Multiple reflections between boundaries are
//!   neglected.
//! - Finite thickness uses `f_t = 1 − exp(−π·T/τ)`, the same decay form as
//!   [`HeightStackCalculator::field_at_gap`](crate::stackup::HeightStackCalculator::field_at_gap).
//! - Eddy-current loss and eddy drag in conductive housings are not modelled.
//!   Silicon steel above 20 kHz is flagged as a warning instead.
//! - Layer and housing flux is a 1-D flux-conservation estimate, so it is
//!   conservative.
//!
//! Material values are typical handbook numbers, not supplier data. Check
//! them against the datasheet of the part you buy.

use serde::{Deserialize, Serialize};

use crate::params::SimulationInput;
use crate::stackup::HeightStackCalculator;

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
    /// Total thickness of the magnetic layers [m].
    pub magnetic_thickness_m: f64,
    /// Series-combined permeability of the magnetic layers.
    pub mu_eff: f64,
    /// Backplane image strength `(μ−1)/(μ+1)·f_t`. Zero when there is no
    /// magnetic layer.
    pub image_strength: f64,
    /// Housing image strength. Zero for non-magnetic housings.
    pub housing_image_strength: f64,
    /// z of the backplane image plane [m] (PCB bottom is `−pcb_thickness_m`).
    pub image_plane_z_m: f64,
    /// z of the housing image plane [m], when a housing is present.
    pub housing_plane_z_m: Option<f64>,
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

    /// Derive the image strengths, planes, inductance factor, attraction and
    /// saturation estimates for `sim`.
    pub fn analyze(&self, sim: &SimulationInput) -> BackplaneAnalysis {
        let tau = sim.pole_pitch_m();
        let k = std::f64::consts::PI / tau;
        let t_pcb = sim.pcb_thickness_m;
        let stack_t = self.stack_thickness_m();
        let mut warnings = Vec::new();

        // Spacer: non-magnetic thickness above the first magnetic layer.
        let first_mag = self.layers.iter().position(|l| l.material.is_magnetic());
        let spacer = first_mag.map_or(0.0, |i| {
            self.layers[..i].iter().map(|l| l.thickness_m).sum()
        });

        // Magnetic layers combine in series (same flux per unit width).
        let t_m: f64 = self
            .layers
            .iter()
            .filter(|l| l.material.is_magnetic())
            .map(|l| l.thickness_m)
            .sum();
        let reluctance: f64 = self
            .layers
            .iter()
            .filter(|l| l.material.is_magnetic())
            .map(|l| l.thickness_m / l.material.mu_r())
            .sum();
        let mu_eff = if t_m > 0.0 { t_m / reluctance } else { 1.0 };
        let image_strength = if t_m > 0.0 {
            (mu_eff - 1.0) / (mu_eff + 1.0) * (1.0 - (-k * t_m).exp())
        } else {
            0.0
        };

        // Planes are measured from the magnet bottom face (z = air_gap).
        let plane_bp_dist = sim.air_gap_m + t_pcb + spacer;
        let image_plane_z = -(t_pcb + spacer);
        let (housing_image_strength, housing_plane_z, housing_dist) = match &self.housing {
            Some(h) => {
                let mu = h.material.mu_r();
                let s = (mu - 1.0) / (mu + 1.0) * (1.0 - (-k * h.thickness_m).exp());
                let z = -(t_pcb + stack_t + h.gap_m);
                (s, Some(z), sim.air_gap_m + t_pcb + stack_t + h.gap_m)
            }
            None => (0.0, None, 0.0),
        };

        // Peak field at each boundary, from the existing 1st-harmonic estimate.
        let b_bp = if image_strength > 0.0 {
            HeightStackCalculator::field_at_gap(sim, plane_bp_dist)
        } else {
            0.0
        };
        let b_h = if housing_image_strength > 0.0 {
            HeightStackCalculator::field_at_gap(sim, housing_dist)
        } else {
            0.0
        };

        // Attraction pressure estimate: s · B²/(4μ0) over the magnet area.
        // The factor 1/4 is B²/(2μ0) times the mean of the square of an
        // alternating field.
        let magnet_area = sim.magnet_count as f64 * sim.magnet_dims_m[0] * sim.magnet_dims_m[1];
        let attraction_n = (image_strength * b_bp * b_bp + housing_image_strength * b_h * b_h)
            * magnet_area
            / (4.0 * MU_0);

        // Inductance: image currents at the coil midplane raise phase self
        // inductance. The coil sits at the PCB midplane.
        let d_coil = t_pcb / 2.0;
        let inductance_factor = 1.0
            + image_strength * (-2.0 * k * (d_coil + spacer)).exp()
            + housing_image_strength * (-2.0 * k * (d_coil + stack_t + self.housing_gap_m())).exp();

        // Flux-conservation saturation estimate. A half-pitch of flux,
        // Φ/width = B·τ/π, returns through each magnetic layer in series.
        let flux_per_width = |b_pk: f64| b_pk * tau / std::f64::consts::PI;
        let layer_peak_b_t: Vec<f64> = self
            .layers
            .iter()
            .enumerate()
            .map(|(i, layer)| {
                if !layer.material.is_magnetic() || b_bp <= 0.0 {
                    return 0.0;
                }
                let b = flux_per_width(b_bp) / layer.thickness_m;
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
            Some(h) if b_h > 0.0 => {
                let b = flux_per_width(b_h) / h.thickness_m;
                if let Some(bsat) = h.material.bsat_t() {
                    if b > bsat {
                        warnings.push(format!(
                            "Housing ({}): estimated peak {:.2} T exceeds Bsat {:.2} T. Increase wall thickness or use a non-magnetic grade.",
                            h.material.label(),
                            b,
                            bsat
                        ));
                    }
                }
                b
            }
            _ => 0.0,
        };

        BackplaneAnalysis {
            stack_thickness_m: stack_t,
            spacer_m: spacer,
            magnetic_thickness_m: t_m,
            mu_eff,
            image_strength,
            housing_image_strength,
            image_plane_z_m: image_plane_z,
            housing_plane_z_m: housing_plane_z,
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
    fn thicker_layer_gives_more_image_strength_up_to_saturation_of_f_t() {
        let s = sim();
        let thin = stack(LayerMaterial::MnZnFerrite, mm(0.5)).analyze(&s);
        let thick = stack(LayerMaterial::MnZnFerrite, mm(5.0)).analyze(&s);
        assert!(thick.image_strength > thin.image_strength);
        assert!(thick.image_strength < 1.0);
    }

    #[test]
    fn spacer_above_magnetic_layer_moves_image_plane_down() {
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
        assert!(spaced.image_plane_z_m < bare.image_plane_z_m);
        assert!((spaced.image_plane_z_m + (s.pcb_thickness_m + mm(1.0))).abs() < 1e-12);
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
        assert_eq!(a.housing_image_strength, 0.0);
        assert_eq!(a.housing_peak_b_t, 0.0);
        assert!(a.housing_plane_z_m.is_some());
        let bare = stack_of_one(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        assert!((a.inductance_factor - bare.inductance_factor).abs() < 1e-12);
    }

    #[test]
    fn magnetic_housing_adds_inductance_and_attraction() {
        let s = sim();
        let plain = stack_of_one(LayerMaterial::MnZnFerrite, mm(2.0)).analyze(&s);
        let with_steel = BackplaneStack {
            layers: vec![BackplaneLayer {
                material: LayerMaterial::MnZnFerrite,
                thickness_m: mm(2.0),
            }],
            housing: Some(HousingSpec {
                material: HousingMaterial::Steel1018,
                thickness_m: mm(3.0),
                gap_m: mm(0.5),
            }),
        }
        .analyze(&s);
        assert!(with_steel.housing_image_strength > 0.0);
        assert!(with_steel.inductance_factor > plain.inductance_factor);
        assert!(with_steel.attraction_n > plain.attraction_n);
    }

    #[test]
    fn housing_gap_weakens_housing_image_inductance() {
        let s = sim();
        let make = |gap| BackplaneStack {
            layers: vec![BackplaneLayer {
                material: LayerMaterial::MnZnFerrite,
                thickness_m: mm(2.0),
            }],
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
    fn image_count_matches_each_magnetic_boundary() {
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
        assert_eq!(assembly.iter().count(), 3 * n);
    }
}
