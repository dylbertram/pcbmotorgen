//! Backplane and housing stackup below the PCB (tickets t707, 04n2, q9nw).
//!
//! The stack sits under the PCB and is ordered from the PCB downward:
//! `layers[0]` touches the PCB. A housing can sit below the stack with an
//! air gap between them.
//!
//! # Conventions
//!
//! - `u` is the depth below the PCB bottom face. Every medium is a planar
//!   slab `(μr, σ, T)`; FR4 and air gaps are `(1, 0, T)`.
//! - Phasors use `e^(jωt)`. A spatial mode `e^(j(ωt − k·x − k_y·y))` has
//!   `κ = √(k² + k_y²)` and travels toward `+x` when `ω > 0`.
//! - In a medium the vector potential goes as `e^(±γu)` with
//!   `γ = √(κ² + jωμ0μσ)`, `Re γ > 0`. `A` and `(1/μ)·∂A/∂u` are continuous,
//!   so an interface between an upper and a lower medium reflects with
//!   `ρ = (η_up − η_low)/(η_up + η_low)`, `η = γ/μ`.
//! - The whole stack, housing included, becomes one reflection coefficient
//!   `R` at the PCB bottom, built bottom up with
//!   `R_top = (ρ + R_b·e^(−2γT)) / (1 + ρ·R_b·e^(−2γT))`. For `σ = 0` this is
//!   the magnetostatic recursion with `ρ = (μ_low − μ_up)/(μ_low + μ_up)`.
//!   `R > 0` adds normal field (soft magnetic), `R → −1` is a perfect
//!   conductor (normal field expelled).
//!
//! # Magnet field (DC)
//!
//! - Only the fundamental `k = π/τ` of the bare array is used. Its normal
//!   amplitude at the stack top is the 2-D `B0` (infinitely deep magnets).
//! - Saturation. Each soft-magnetic layer and the housing follow the
//!   two-slope curve `B = μ0·H + J`, `J = clip(μ0(μi − 1)·H, ±Bsat)`. The
//!   in-plane field in a layer varies as `H1·sin(kx)`, so the fundamental
//!   sees the describing-function permeability
//!   `μ_eff = 1 + (μi − 1)·(2/π)·(asin x + x·√(1 − x²))`, `x = H_knee/H1`,
//!   `H_knee = Bsat/(μ0(μi − 1))`. `H1` is the thickness mean of the in-plane
//!   field, from the layer's own flux `|A_top − A_bottom|/T`. A layer whose
//!   linear in-plane field reaches Bsat on a face is split into sublayers of
//!   `k·T ≤ 0.1` (at most 32), each with its own `μ_eff`, so a thick plate can
//!   saturate near its face and stay linear deeper down. The fixed point
//!   `μ_eff = f(H1(μ_eff))` is solved per sublayer by bisection, sweeping
//!   until the stack settles. Reported `μ_eff` and `μ_inc` are thickness
//!   means over the sublayers: in-plane flux runs through them in parallel.
//! - Only the in-plane field saturates a layer. Under the magnet centres the
//!   field enters a thick plate normally and saturates a skin at its face,
//!   which lowers `R`; the model misses that, so for plates thicker than
//!   about `1/k` near `flux_overload ≈ 1` it overstates `R`, K_f and the
//!   attraction (FEMM: +13 % field and +52 % attraction for 5 mm flex sheet,
//!   +14 % attraction for 2 mm MnZn, both on a 0.8 mm PCB). The suggested
//!   thicknesses are lower bounds.
//! - The magnet field model mirrors the array across the PCB bottom with the
//!   saturated `R`, which sets K_f. Attraction is the mean Maxwell stress
//!   `Re R(κ)·B(κ)²/μ0` summed over the cross-travel spectrum of the
//!   magnets, see [`magnet_forces`]. Array ends in the travel direction are
//!   ignored.
//! - Reported peak `|B|` is the larger of the in-plane `B(H)` on the layer
//!   faces and the normal field, at the solved state. A saturated sheet shows
//!   `Bsat + μ0·H`: the polarization is clamped, the field through it is not.
//!   The linear demand is reported separately.
//!
//! # Coil field (small signal)
//!
//! - The coil is `N` equal-current copper sheets (`N = num_layers ≥ 2`) at
//!   `d_i = i·T_pcb/(N−1)` above the PCB bottom. Each sees its own image, so
//!   the complex inductance factor is `F = 1 + R·(1/N)·Σ e^(−2k·d_i)`. Flux
//!   linkage is `L0·F·i`, so `L = L0·Re F` and the added resistance is
//!   `−ω·L0·Im F ≥ 0`. Sheets are evenly spaced; real 4- and 6-layer
//!   stackups have uneven core and prepreg thicknesses.
//! - Under the magnets a saturated layer is biased by
//!   `H = (H1·sin kx, Hz·cos kx)`, in-plane and normal, `Hz` from the normal
//!   field at the solved state. A small in-plane coil field sees the
//!   differential permeability along the bias (`μi` below the knee, 1 above
//!   it) and the secant permeability `B/(μ0·|H|)` across it, so
//!   `μ_xx = μ_diff·cos²α + μ_sec·sin²α`, `α` the bias angle to the plane.
//!   Coil flux runs along the layer through all of it in series, so the coil
//!   sees the harmonic mean of `μ_xx` over a pole pitch, per sublayer. This
//!   ignores where the coil flux sits relative to the saturated regions,
//!   which moves with the mover (a saliency); FEMM gives a spread around the
//!   model value. Away from the magnets the layer keeps `μi`. `R` is averaged
//!   over the winding length with weight `N·τ / active_area_length` under the
//!   magnets.
//! - The drive evaluates `F` at the PWM frequency for the ripple and at the
//!   electrical frequency `v/(2τ)` for the `ω·L` voltage terms.
//!
//! # Eddy currents
//!
//! - In the stator frame the magnet fundamental is a travelling wave with
//!   `ω = k·v`. Each mode presses on the stack with `Re R·B²/μ0` and pushes it
//!   along `+x` with `−(k/κ)·Im R·B²/μ0`; the magnets feel the opposite, the
//!   eddy drag. Drag power is `F·v`. The sweep's K_f uses the static `R`.
//! - The saturated layer keeps its DC `μ_eff` for the moving field. Hysteresis
//!   and core loss in the layers are not modelled.
//! - Silicon steel is one flat sheet, so its in-plane eddy currents see the
//!   bulk conductivity. Its linear `μr` overstates it at PWM frequencies;
//!   above 20 kHz a warning is raised instead.
//!
//! # Limits
//!
//! Boundaries are planar and infinite. Edge and corner effects are ignored.
//! Material values are typical handbook or supplier numbers (see each
//! function). Per-layer `mu_r` and `bsat_t` override them with datasheet
//! values.

use std::f64::consts::PI;

use nalgebra::Complex;
use serde::{Deserialize, Serialize};

use crate::params::SimulationInput;

/// Vacuum permeability [H/m].
const MU_0: f64 = 4.0e-7 * PI;
/// Switching frequency above which silicon steel is flagged [Hz].
pub const SILICON_STEEL_PWM_LIMIT_HZ: f64 = 20e3;
/// Largest accepted thickness for one layer or the housing [m].
pub const MAX_THICKNESS_M: f64 = 0.02;
/// Largest accepted relative permeability override.
pub const MAX_MU_R: f64 = 1e6;
/// Largest accepted saturation flux density override [T].
pub const MAX_BSAT_T: f64 = 3.0;
/// Sublayer thickness, as `k·T`, of a layer that reaches Bsat.
const SUBLAYER_KT: f64 = 0.1;
/// Most sublayers per layer.
const MAX_SUBLAYERS: usize = 32;

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
    /// Flexible (cracked sintered NiZn) ferrite sheet, as sold for NFC.
    FlexFerrite,
}

impl LayerMaterial {
    /// Relative permeability (typical starting value).
    ///
    /// Flexible sheets: Laird MULL12060-200 gives μ' ≈ 135 from 1 to 10 MHz
    /// (150 at 13.56 MHz), Laird MHLL 130 and Würth WE-FSFS 364001 110 at
    /// 1 MHz. The low-frequency value of these sintered NiZn sheets sits at
    /// the same plateau.
    pub fn mu_r(self) -> f64 {
        match self {
            LayerMaterial::Fr4 => 1.0,
            LayerMaterial::SiliconSteel => 4000.0,
            LayerMaterial::MnZnFerrite => 2500.0,
            LayerMaterial::NiZnFerrite => 500.0,
            LayerMaterial::FlexFerrite => 130.0,
        }
    }

    /// Saturation flux density [T], or `None` for non-magnetic material.
    ///
    /// Flex sheet datasheets give no Bsat. Bulk NiZn of the same μi gives
    /// 0.24–0.25 T (Fair-Rite 61, μi 125, at 1.2 kA/m) to 0.31 T
    /// (Ferroxcube 4M2, μi 140); 0.25 T is the low end.
    pub fn bsat_t(self) -> Option<f64> {
        match self {
            LayerMaterial::Fr4 => None,
            LayerMaterial::SiliconSteel => Some(1.8),
            LayerMaterial::MnZnFerrite => Some(0.45),
            LayerMaterial::NiZnFerrite => Some(0.35),
            LayerMaterial::FlexFerrite => Some(0.25),
        }
    }

    /// Electrical conductivity [S/m]. NiZn (ρ ≈ 10⁵ Ω·m and up) and FR4 are
    /// taken as insulators. MnZn: ρ ≈ 5 Ω·m (Ferroxcube 3C90). Silicon
    /// steel: 3 % Si, ρ ≈ 50 µΩ·cm.
    pub fn sigma_s_per_m(self) -> f64 {
        match self {
            LayerMaterial::Fr4 | LayerMaterial::NiZnFerrite | LayerMaterial::FlexFerrite => 0.0,
            LayerMaterial::SiliconSteel => 2.0e6,
            LayerMaterial::MnZnFerrite => 0.2,
        }
    }

    /// Thickness used when a layer is first added [m]. Flexible sheets are
    /// sold with 0.05, 0.1 and 0.2 mm of ferrite (Laird, Würth); 0.1 mm is the
    /// ferrite alone, without adhesive and cover film.
    pub fn default_thickness_m(self) -> f64 {
        match self {
            LayerMaterial::Fr4 => 1.6e-3,
            LayerMaterial::SiliconSteel => 0.35e-3,
            LayerMaterial::MnZnFerrite => 2.0e-3,
            LayerMaterial::NiZnFerrite => 2.0e-3,
            LayerMaterial::FlexFerrite => 0.1e-3,
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

    /// Electrical conductivity at room temperature [S/m]: 6061-T6 43 % IACS,
    /// 5052-H32 35 % IACS, 1018 ≈ 17 µΩ·cm, 304 72 µΩ·cm, 316 74 µΩ·cm,
    /// 430 60 µΩ·cm.
    pub fn sigma_s_per_m(self) -> f64 {
        match self {
            HousingMaterial::Aluminum6061 => 2.5e7,
            HousingMaterial::Aluminum5052 => 2.0e7,
            HousingMaterial::Steel1018 => 5.8e6,
            HousingMaterial::Stainless304 => 1.39e6,
            HousingMaterial::Stainless316 => 1.35e6,
            HousingMaterial::Stainless430 => 1.67e6,
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
    /// Layer thickness [m]. For sheets, the magnetic material only.
    pub thickness_m: f64,
    /// Datasheet relative permeability; `None` uses the material default.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mu_r: Option<f64>,
    /// Datasheet saturation flux density [T]; `None` uses the material
    /// default.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bsat_t: Option<f64>,
}

impl BackplaneLayer {
    /// A layer with the material's default permeability and saturation.
    pub fn new(material: LayerMaterial, thickness_m: f64) -> Self {
        Self {
            material,
            thickness_m,
            mu_r: None,
            bsat_t: None,
        }
    }

    /// Relative permeability in use: the override or the material default.
    pub fn mu_r(&self) -> f64 {
        self.mu_r.unwrap_or(self.material.mu_r())
    }

    /// Saturation flux density in use [T]: the override or the default.
    pub fn bsat_t(&self) -> Option<f64> {
        self.bsat_t.or(self.material.bsat_t())
    }
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

/// Magnetic operating state of one layer or the housing under the magnets.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MagneticState {
    /// Initial relative permeability in use.
    pub mu_initial: f64,
    /// Saturation flux density in use [T]; `None` for linear material.
    pub bsat_t: Option<f64>,
    /// Effective permeability for the magnet field (describing function).
    pub mu_effective: f64,
    /// Small-signal permeability the coil sees under the magnets.
    pub mu_incremental: f64,
    /// Peak `|B|` of the linear model at `mu_initial` [T].
    pub linear_peak_b_t: f64,
    /// Thickness-mean in-plane flux density of the linear model [T].
    pub linear_mean_b_t: f64,
    /// Thickness-mean in-plane flux density of the fundamental at the
    /// solved state, `μ0·μ_eff·H1` [T].
    pub mean_b_t: f64,
    /// Peak `|B|` at the solved, saturation-aware state [T].
    pub peak_b_t: f64,
    /// Linear in-plane flux over the flux the layer carries at Bsat. Above 1
    /// the layer is saturated. Zero for linear material.
    pub flux_overload: f64,
    /// Thickness of this material that carries the linear flux at Bsat [m];
    /// `None` when not saturated or above [`MAX_THICKNESS_M`].
    pub required_thickness_m: Option<f64>,
    /// The same for sintered MnZn ferrite in this position [m].
    pub mnzn_thickness_m: Option<f64>,
}

impl MagneticState {
    /// True when the magnets drive more flux than the layer carries at Bsat.
    pub fn saturated(&self) -> bool {
        self.flux_overload > 1.0
    }
}

/// Derived backplane quantities for one [`SimulationInput`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BackplaneAnalysis {
    /// Total thickness of the backplane layers [m].
    pub stack_thickness_m: f64,
    /// Composite reflection `R` of the stack and housing at the PCB bottom,
    /// at the fundamental, for the magnet field with saturation. Zero when
    /// nothing below the PCB is magnetic.
    pub image_strength: f64,
    /// `R` with every layer at its initial permeability (no saturation).
    pub linear_image_strength: f64,
    /// Fundamental normal field of the bare magnet array at the stack top,
    /// 2-D (infinitely deep magnets) [T].
    pub b0_t: f64,
    /// Copper sheet count `N` used for `inductance_factor` (`num_layers`,
    /// at least 2).
    pub copper_layers: u32,
    /// Height of each copper sheet above the PCB bottom [m], bottom first.
    pub copper_depths_m: Vec<f64>,
    /// Share of the winding length under the magnets, `N·τ / length`.
    pub magnet_coverage: f64,
    /// Low-frequency multiplier on per-phase inductance from the image
    /// currents, with the magnets' bias on saturated layers.
    pub inductance_factor: f64,
    /// Estimated normal attraction between the magnets and the backplane +
    /// housing at standstill [N]. Positive pulls the mover toward the stack.
    pub attraction_n: f64,
    /// Peak flux density in each backplane layer at the solved state [T]
    /// (zero for non-magnetic layers), in the same order as `layers`.
    pub layer_peak_b_t: Vec<f64>,
    /// Peak flux density in the housing wall at the solved state [T] (zero
    /// if none or non-magnetic).
    pub housing_peak_b_t: f64,
    /// Magnetic state of each layer, in the same order as `layers`.
    pub layer_states: Vec<MagneticState>,
    /// Magnetic state of the housing wall.
    pub housing_state: Option<MagneticState>,
    /// Human-readable warnings (saturation, material limits).
    pub warnings: Vec<String>,
}

/// Force of the moving magnets on the stack and housing.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct MagnetForces {
    /// Normal attraction [N]. Positive pulls the mover toward the stack.
    pub normal_n: f64,
    /// Eddy drag on the mover [N], opposing its motion.
    pub drag_n: f64,
}

/// One planar slab below the PCB.
#[derive(Debug, Clone, Copy, PartialEq)]
struct Medium {
    mu: f64,
    sigma: f64,
    t: f64,
    bsat: Option<f64>,
}

impl Medium {
    fn air(t: f64) -> Self {
        Self {
            mu: 1.0,
            sigma: 0.0,
            t,
            bsat: None,
        }
    }

    fn saturable(&self) -> Option<f64> {
        self.bsat.filter(|_| self.mu > 1.0)
    }
}

/// The stack solved for one [`SimulationInput`]: the saturation state under
/// the magnets and the media each field sees.
#[derive(Debug, Clone)]
pub struct SolvedStack {
    k: f64,
    b0: f64,
    /// Initial permeability: the linear model, and the coil field away from
    /// the magnets.
    free: Vec<Medium>,
    /// Effective permeability for the magnet field, layers that reach Bsat
    /// split into sublayers.
    magnet: Vec<Medium>,
    /// Incremental permeability for the coil field under the magnets, split
    /// like `magnet`.
    biased: Vec<Medium>,
    /// Index into `free` of each entry of `magnet` and `biased`.
    owner: Vec<usize>,
    coverage: f64,
    /// `(1/N)·Σ e^(−2k·d_i)`.
    copper_weight: f64,
}

impl SolvedStack {
    /// Composite reflection `R` for the magnet field at standstill.
    pub fn image_strength(&self) -> f64 {
        reflection(self.k, &self.magnet)
    }

    /// Complex inductance factor `F` at `freq_hz`: the inductance scales by
    /// `Re F` and the eddy currents add `−2π·f·L0·Im F` of series resistance.
    pub fn coil_factor(&self, freq_hz: f64) -> Complex<f64> {
        let omega = 2.0 * PI * freq_hz;
        let free = reflection_ac(self.k, omega, &self.free);
        let r = if self.biased == self.free {
            free
        } else {
            reflection_ac(self.k, omega, &self.biased) * self.coverage
                + free * (1.0 - self.coverage)
        };
        Complex::new(1.0, 0.0) + r * self.copper_weight
    }

    /// [`Self::coil_factor`] for a winding entirely away from the magnets
    /// and entirely under them: `[away, under]`.
    pub fn coil_factor_parts(&self, freq_hz: f64) -> [Complex<f64>; 2] {
        let omega = 2.0 * PI * freq_hz;
        [&self.free, &self.biased]
            .map(|m| Complex::new(1.0, 0.0) + reflection_ac(self.k, omega, m) * self.copper_weight)
    }

    /// Fundamental (2-D) reflection seen by the magnet field moving at
    /// `speed_m_s`, in the stator frame.
    pub fn magnet_reflection(&self, speed_m_s: f64) -> Complex<f64> {
        reflection_ac(self.k, self.k * speed_m_s.abs(), &self.magnet)
    }

    /// True when any medium conducts, so motion and PWM induce eddy currents.
    pub fn conducts(&self) -> bool {
        self.free.iter().any(|m| m.sigma > 0.0)
    }

    /// Normal force and eddy drag of the magnets moving at `speed_m_s`.
    pub fn magnet_forces(&self, sim: &SimulationInput, speed_m_s: f64) -> MagnetForces {
        magnet_forces(sim, &self.magnet, self.k * speed_m_s.abs())
    }
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

    /// Check thicknesses, gaps and overrides. Returns the first problem found.
    pub fn validate(&self) -> Result<(), String> {
        for (i, layer) in self.layers.iter().enumerate() {
            let what = format!("backplane layer {}", i + 1);
            check_thickness(&what, layer.thickness_m)?;
            if let Some(mu) = layer.mu_r {
                if !mu.is_finite() || !(1.0..=MAX_MU_R).contains(&mu) {
                    return Err(format!("{what} μr must be between 1 and {MAX_MU_R:.0}"));
                }
            }
            if let Some(b) = layer.bsat_t {
                if !b.is_finite() || b <= 0.0 || b > MAX_BSAT_T {
                    return Err(format!(
                        "{what} Bsat must be greater than 0 and at most {MAX_BSAT_T} T"
                    ));
                }
            }
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

    /// Media below the PCB bottom, top down, at initial permeability.
    fn media(&self) -> Vec<Medium> {
        let mut media: Vec<Medium> = self
            .layers
            .iter()
            .map(|l| Medium {
                mu: l.mu_r(),
                sigma: l.material.sigma_s_per_m(),
                t: l.thickness_m,
                bsat: l.bsat_t(),
            })
            .collect();
        if let Some(h) = &self.housing {
            media.push(Medium::air(h.gap_m));
            media.push(Medium {
                mu: h.material.mu_r(),
                sigma: h.material.sigma_s_per_m(),
                t: h.thickness_m,
                bsat: h.material.bsat_t(),
            });
        }
        media
    }

    /// Solve the saturation state under the magnets of `sim`.
    pub fn solve(&self, sim: &SimulationInput) -> SolvedStack {
        let k = PI / sim.pole_pitch_m();
        let b0 = mode_bz(sim, k);
        let free = self.media();
        let (fine, owner) = split_saturating(k, b0, &free);
        let magnet = saturate(k, b0, &fine);
        let (_, faces) = dc_fields(k, &magnet);
        let biased = fine
            .iter()
            .zip(&magnet)
            .zip(&faces)
            .map(|((m, e), f)| match m.saturable() {
                Some(bsat) => Medium {
                    mu: incremental_mu(
                        m.mu,
                        bsat,
                        f.mean * b0 / (MU_0 * e.mu),
                        (f.a_top.abs() + f.a_bottom.abs()) / 2.0 * b0 / (MU_0 * e.mu),
                    ),
                    ..*m
                },
                None => *m,
            })
            .collect();
        let span = sim.magnet_count as f64 * sim.pole_pitch_m();
        let coverage = if sim.active_area_length_m > 0.0 {
            (span / sim.active_area_length_m).min(1.0)
        } else {
            1.0
        };
        let depths = copper_depths(sim.pcb_thickness_m, sim.num_layers.max(2));
        SolvedStack {
            k,
            b0,
            free,
            magnet,
            biased,
            owner,
            coverage,
            copper_weight: copper_weight(k, &depths),
        }
    }

    /// Composite reflection `R` at the PCB bottom for the magnet field of
    /// `sim`, with saturation.
    pub fn image_strength(&self, sim: &SimulationInput) -> f64 {
        self.solve(sim).image_strength()
    }

    /// Derive the composite reflection, saturation state, inductance factor
    /// and attraction for `sim`.
    pub fn analyze(&self, sim: &SimulationInput) -> BackplaneAnalysis {
        let solved = self.solve(sim);
        let (k, b0) = (solved.k, solved.b0);
        // Equal-current copper sheets spread over the PCB, each with its own
        // image. Validation rejects num_layers < 2; clamp so analyze never
        // divides by zero on unvalidated input.
        let copper_layers = sim.num_layers.max(2);
        let copper_depths_m = copper_depths(sim.pcb_thickness_m, copper_layers);
        let image_strength = solved.image_strength();
        let linear_image_strength = reflection(k, &solved.free);

        let (_, lin_faces) = dc_fields(k, &solved.free);
        let (_, eff_faces) = dc_fields(k, &solved.magnet);
        let state = |i: usize| -> MagneticState {
            let m = &solved.free[i];
            let lin = &lin_faces[i];
            let subs: Vec<usize> = (0..solved.owner.len())
                .filter(|&j| solved.owner[j] == i)
                .collect();
            // In-plane flux runs through the sublayers in parallel, so they
            // lump by their thickness-weighted mean.
            let lumped = |media: &[Medium]| match subs.as_slice() {
                [j] => media[*j].mu,
                _ => subs.iter().map(|&j| media[j].mu * media[j].t).sum::<f64>() / m.t,
            };
            let (first, last) = (subs[0], subs[subs.len() - 1]);
            let peak_b_t = subs
                .iter()
                .map(|&j| {
                    let (e, mu_eff) = (&eff_faces[j], solved.magnet[j].mu);
                    let bh = |b: f64| bh_curve(m.mu, m.bsat, b / (MU_0 * mu_eff));
                    bh(e.top * b0).max(bh(e.bottom * b0)).max(e.normal * b0)
                })
                .fold(0.0, f64::max);
            let linear_mean_b_t = lin.mean * b0;
            let flux_overload = m.saturable().map_or(0.0, |bsat| linear_mean_b_t / bsat);
            let saturated = flux_overload > 1.0;
            let mnzn = Medium {
                mu: LayerMaterial::MnZnFerrite.mu_r(),
                sigma: 0.0,
                t: m.t,
                bsat: LayerMaterial::MnZnFerrite.bsat_t(),
            };
            MagneticState {
                mu_initial: m.mu,
                bsat_t: m.bsat,
                mu_effective: lumped(&solved.magnet),
                mu_incremental: lumped(&solved.biased),
                linear_peak_b_t: lin.peak() * b0,
                linear_mean_b_t,
                mean_b_t: (eff_faces[first].a_top - eff_faces[last].a_bottom).abs() / (k * m.t)
                    * b0,
                peak_b_t,
                flux_overload,
                required_thickness_m: saturated
                    .then(|| thickness_for_bsat(k, b0, &solved.free, i, *m))
                    .flatten(),
                mnzn_thickness_m: saturated
                    .then(|| thickness_for_bsat(k, b0, &solved.free, i, mnzn))
                    .flatten(),
            }
        };
        let layer_states: Vec<MagneticState> = (0..self.layers.len()).map(state).collect();
        let housing_state = self.housing.as_ref().map(|_| state(solved.free.len() - 1));

        let mut warnings = Vec::new();
        for (i, (l, s)) in self.layers.iter().zip(&layer_states).enumerate() {
            let what = format!(
                "Backplane layer {} ({}, {:.2} mm)",
                i + 1,
                l.material.label(),
                l.thickness_m * 1e3
            );
            saturation_warning(
                &mut warnings,
                &what,
                s,
                linear_image_strength,
                image_strength,
            );
        }
        if let (Some(h), Some(s)) = (&self.housing, &housing_state) {
            let what = format!(
                "Housing ({}, {:.2} mm)",
                h.material.label(),
                h.thickness_m * 1e3
            );
            saturation_warning(
                &mut warnings,
                &what,
                s,
                linear_image_strength,
                image_strength,
            );
        }

        let peak = |s: &MagneticState| {
            if s.bsat_t.is_some() && s.mu_initial > 1.0 {
                s.peak_b_t
            } else {
                0.0
            }
        };
        BackplaneAnalysis {
            stack_thickness_m: self.stack_thickness_m(),
            image_strength,
            linear_image_strength,
            b0_t: b0,
            copper_layers,
            copper_depths_m,
            magnet_coverage: solved.coverage,
            inductance_factor: solved.coil_factor(0.0).re,
            attraction_n: solved.magnet_forces(sim, 0.0).normal_n,
            layer_peak_b_t: layer_states.iter().map(peak).collect(),
            housing_peak_b_t: housing_state.as_ref().map_or(0.0, peak),
            layer_states,
            housing_state,
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

fn saturation_warning(
    warnings: &mut Vec<String>,
    what: &str,
    s: &MagneticState,
    r_linear: f64,
    r_eff: f64,
) {
    let Some(bsat) = s.bsat_t.filter(|_| s.mu_initial > 1.0) else {
        return;
    };
    if s.saturated() {
        let fix = match (s.required_thickness_m, s.mnzn_thickness_m) {
            (Some(t), Some(m)) => format!(
                "Carrying it needs at least {:.1} mm of this material, or {:.1} mm of sintered MnZn ferrite.",
                t * 1e3,
                m * 1e3
            ),
            (None, Some(m)) => format!(
                "Carrying it needs more than {:.0} mm of this material, or at least {:.1} mm of sintered MnZn ferrite.",
                MAX_THICKNESS_M * 1e3,
                m * 1e3
            ),
            _ => format!(
                "Carrying it needs more than {:.0} mm of this material.",
                MAX_THICKNESS_M * 1e3
            ),
        };
        warnings.push(format!(
            "{what}: saturated. The magnets drive {:.1}× the flux it carries at Bsat {bsat:.2} T \
             (the linear model needs a mean {:.2} T). Its effective μr drops from {:.0} to {:.1}, \
             so R falls from {r_linear:.3} to {r_eff:.3}. {fix}",
            s.flux_overload, s.linear_mean_b_t, s.mu_initial, s.mu_effective
        ));
    } else if s.linear_peak_b_t > bsat {
        warnings.push(format!(
            "{what}: the linear field at the face reaches {:.2} T, above Bsat {bsat:.2} T, but the mean \
             flux fits ({:.2} T). A skin at the face saturates; effective μr {:.0} of {:.0}.",
            s.linear_peak_b_t, s.linear_mean_b_t, s.mu_effective, s.mu_initial
        ));
    }
}

/// Reflection coefficient at the top of `media` (top down) for a static
/// field `e^(−k·z)` arriving from air above, with air below the last medium.
/// Built bottom up with `R = (ρ + R'·e^(−2kT)) / (1 + ρ·R'·e^(−2kT))`.
fn reflection(k: f64, media: &[Medium]) -> f64 {
    // `g`: reflection seen from inside the medium below, at its top face.
    let mut mu_below = 1.0;
    let mut g = 0.0;
    for m in media.iter().rev() {
        let rho = (mu_below - m.mu) / (mu_below + m.mu);
        g = (rho + g) / (1.0 + rho * g) * (-2.0 * k * m.t).exp();
        mu_below = m.mu;
    }
    let rho = (mu_below - 1.0) / (mu_below + 1.0);
    (rho + g) / (1.0 + rho * g)
}

/// [`reflection`] for a mode of wavenumber `kappa` at angular frequency
/// `omega` (`e^(jωt)`), with eddy currents. Falls back to the static
/// recursion when nothing conducts or `omega` is zero.
fn reflection_ac(kappa: f64, omega: f64, media: &[Medium]) -> Complex<f64> {
    if omega == 0.0 || media.iter().all(|m| m.sigma == 0.0) {
        return Complex::new(reflection(kappa, media), 0.0);
    }
    let one = Complex::new(1.0, 0.0);
    let air = Complex::new(kappa, 0.0);
    let mut eta_below = air;
    let mut g = Complex::new(0.0, 0.0);
    for m in media.iter().rev() {
        let gamma = Complex::new(kappa * kappa, omega * MU_0 * m.mu * m.sigma).sqrt();
        let eta = gamma / m.mu;
        let rho = (eta - eta_below) / (eta + eta_below);
        g = (rho + g) / (one + rho * g) * (-gamma * (2.0 * m.t)).exp();
        eta_below = eta;
    }
    let rho = (air - eta_below) / (air + eta_below);
    (rho + g) / (one + rho * g)
}

/// Static field of the fundamental in one medium, per unit incident normal
/// field at the stack top.
#[derive(Debug, Clone, Copy)]
struct Faces {
    /// Flux function `A` at the top and bottom faces; their difference is
    /// the in-plane flux, per `B0/k`.
    a_top: f64,
    a_bottom: f64,
    /// In-plane `|B|` at the top and bottom faces.
    top: f64,
    bottom: f64,
    /// Larger normal `|B|` of the two faces.
    normal: f64,
    /// Thickness mean of the in-plane `|B|`: the layer's flux over `kT`.
    mean: f64,
}

impl Faces {
    fn peak(&self) -> f64 {
        self.top.max(self.bottom).max(self.normal)
    }
}

/// Static reflection and the field in every medium. In medium `i`,
/// `A = a·(e^(−k·s) + g_top·e^(k·s))` with `s` the depth below its top face;
/// the in-plane field is `∂A/∂u` and the normal field `k·A`. `A` is
/// normalised so that the incident normal field at the stack top is 1.
fn dc_fields(k: f64, media: &[Medium]) -> (f64, Vec<Faces>) {
    let n = media.len();
    let mut g_bottom = vec![0.0; n];
    let mut g_top = vec![0.0; n];
    let mut mu_below = 1.0;
    let mut g = 0.0;
    for i in (0..n).rev() {
        let rho = (mu_below - media[i].mu) / (mu_below + media[i].mu);
        g_bottom[i] = (rho + g) / (1.0 + rho * g);
        g_top[i] = g_bottom[i] * (-2.0 * k * media[i].t).exp();
        g = g_top[i];
        mu_below = media[i].mu;
    }
    let rho = (mu_below - 1.0) / (mu_below + 1.0);
    let r = (rho + g) / (1.0 + rho * g);

    let mut faces = Vec::with_capacity(n);
    let mut a_above = 1.0 + r;
    for i in 0..n {
        let a = a_above / (1.0 + g_top[i]);
        let decay = (-k * media[i].t).exp();
        let a_top = a * (1.0 + g_top[i]);
        let a_bottom = a * decay * (1.0 + g_bottom[i]);
        faces.push(Faces {
            a_top,
            a_bottom,
            top: (a * (g_top[i] - 1.0)).abs(),
            bottom: (a * decay * (g_bottom[i] - 1.0)).abs(),
            normal: a_top.abs().max(a_bottom.abs()),
            mean: (a_top - a_bottom).abs() / (k * media[i].t),
        });
        a_above = a_bottom;
    }
    (r, faces)
}

/// `B(H)` of the two-slope curve, `μ0·H + clip(μ0(μi − 1)·H, Bsat)` [T].
fn bh_curve(mu_i: f64, bsat: Option<f64>, h: f64) -> f64 {
    let j = MU_0 * (mu_i - 1.0) * h;
    MU_0 * h + bsat.map_or(j, |b| j.min(b))
}

/// `H_knee / H1` of a layer with in-plane amplitude `h1`, or `None` below
/// the knee.
fn knee_ratio(mu_i: f64, bsat: f64, h1: f64) -> Option<f64> {
    let h_knee = bsat / (MU_0 * (mu_i - 1.0));
    (h1 > h_knee).then(|| h_knee / h1)
}

/// Describing-function permeability of the two-slope curve for an in-plane
/// field `h1·sin(kx)`.
fn describing_mu(mu_i: f64, bsat: f64, h1: f64) -> f64 {
    match knee_ratio(mu_i, bsat, h1) {
        Some(x) => 1.0 + (mu_i - 1.0) * 2.0 / PI * (x.asin() + x * (1.0 - x * x).sqrt()),
        None => mu_i,
    }
}

/// Harmonic mean over a pole pitch of the small-signal in-plane permeability
/// under the bias `H = (hx·sin kx, hz·cos kx)`: differential along the bias
/// (`μi` below the knee, 1 above it), secant `B/(μ0·|H|)` across it.
fn incremental_mu(mu_i: f64, bsat: f64, hx: f64, hz: f64) -> f64 {
    // A quarter period covers every bias by symmetry.
    const SAMPLES: usize = 256;
    let h_knee = bsat / (MU_0 * (mu_i - 1.0));
    let mean_inverse = (0..SAMPLES)
        .map(|i| {
            let theta = (i as f64 + 0.5) / SAMPLES as f64 * PI / 2.0;
            let (x, z) = (hx * theta.sin(), hz * theta.cos());
            let h = x.hypot(z);
            if h <= h_knee {
                return 1.0 / mu_i;
            }
            let secant = bh_curve(mu_i, Some(bsat), h) / (MU_0 * h);
            let along = (x / h).powi(2);
            1.0 / (along + (1.0 - along) * secant)
        })
        .sum::<f64>()
        / SAMPLES as f64;
    1.0 / mean_inverse
}

/// `media` with each saturable medium whose linear in-plane field reaches
/// Bsat on a face split into sublayers of `k·T ≤ SUBLAYER_KT` (at most
/// [`MAX_SUBLAYERS`]), so saturation can vary with depth. Returns the media
/// and the index of the medium each entry came from.
fn split_saturating(k: f64, b0: f64, media: &[Medium]) -> (Vec<Medium>, Vec<usize>) {
    let (_, faces) = dc_fields(k, media);
    let mut fine = Vec::new();
    let mut owner = Vec::new();
    for (i, (m, f)) in media.iter().zip(&faces).enumerate() {
        let n = match m.saturable() {
            Some(bsat) if f.top.max(f.bottom) * b0 > bsat => {
                ((k * m.t / SUBLAYER_KT).ceil() as usize).clamp(1, MAX_SUBLAYERS)
            }
            _ => 1,
        };
        let t = if n == 1 { m.t } else { m.t / n as f64 };
        fine.extend(std::iter::repeat(Medium { t, ..*m }).take(n));
        owner.extend(std::iter::repeat(i).take(n));
    }
    (fine, owner)
}

/// Effective permeability of every saturable medium under the magnet
/// fundamental `b0`: each layer's `μ_eff = describing_mu(H1(μ_eff))` by
/// bisection on `ln μ`, sweeping the layers until none moves.
fn saturate(k: f64, b0: f64, media: &[Medium]) -> Vec<Medium> {
    let mut eff = media.to_vec();
    let saturable: Vec<(usize, f64)> = media
        .iter()
        .enumerate()
        .filter_map(|(i, m)| m.saturable().map(|b| (i, b)))
        .collect();
    for _ in 0..100 {
        let mut moved: f64 = 0.0;
        for &(i, bsat) in &saturable {
            let mu_i = media[i].mu;
            let residual = |mu: f64, eff: &mut Vec<Medium>| {
                eff[i].mu = mu;
                let h1 = dc_fields(k, eff).1[i].mean * b0 / (MU_0 * mu);
                describing_mu(mu_i, bsat, h1) - mu
            };
            let before = eff[i].mu;
            let solved = if residual(mu_i, &mut eff) >= 0.0 {
                mu_i
            } else {
                // The describing μ is at least 1, so the root lies in [1, μi].
                let (mut lo, mut hi) = (0.0, mu_i.ln());
                for _ in 0..60 {
                    let mid = 0.5 * (lo + hi);
                    if residual(mid.exp(), &mut eff) >= 0.0 {
                        lo = mid;
                    } else {
                        hi = mid;
                    }
                }
                (0.5 * (lo + hi)).exp()
            };
            eff[i].mu = solved;
            moved = moved.max((solved / before).ln().abs());
        }
        if moved < 1e-9 {
            break;
        }
    }
    eff
}

/// Thickness of `replace` in position `i` at which its linear mean in-plane
/// flux density equals its Bsat, the rest of `media` unchanged [m]. `None`
/// above [`MAX_THICKNESS_M`].
fn thickness_for_bsat(k: f64, b0: f64, media: &[Medium], i: usize, replace: Medium) -> Option<f64> {
    let bsat = replace.bsat?;
    let mut trial = media.to_vec();
    let mut mean_at = |t: f64| {
        trial[i] = Medium { t, ..replace };
        dc_fields(k, &trial).1[i].mean * b0
    };
    if mean_at(MAX_THICKNESS_M) > bsat {
        return None;
    }
    let (mut lo, mut hi) = (1e-6_f64.ln(), MAX_THICKNESS_M.ln());
    for _ in 0..60 {
        let mid = 0.5 * (lo + hi);
        if mean_at(mid.exp()) > bsat {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    Some(hi.exp())
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

/// Normal force and eddy drag of the magnet row on `media` [N], at the
/// stator-frame angular frequency `omega = k·v`.
///
/// Each spatial mode `(k, k_y)` of the array field presses on the stack with
/// the mean Maxwell stress `Re R(κ)·B(κ)²/μ0`, `κ = √(k² + k_y²)`, and drags
/// the magnets with `−(k/κ)·Im R(κ)·B(κ)²/μ0`. A row of `N` magnets of depth
/// `D` spans `N·τ` along travel and has the cross-travel spectrum
/// `2·sin(k_y·D/2)/k_y`, so
/// `F = N·τ/(π·μ0) · ∫₀^∞ {Re R, −(k/κ)·Im R}·B(κ)²·(2·sin(k_y·D/2)/k_y)² dk_y`.
/// For `D → ∞` the normal force is `R·B0²/μ0·N·τ·D`.
fn magnet_forces(sim: &SimulationInput, media: &[Medium], omega: f64) -> MagnetForces {
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
        let r = reflection_ac(kappa, omega, media);
        (
            r.re * b * b * spectrum * spectrum,
            -r.im * k / kappa * b * b * spectrum * spectrum,
        )
    };
    // Composite Simpson.
    let (normal, drag) = (0..=n).fold((0.0, 0.0), |(fn_, fd), i| {
        let weight = if i == 0 || i == n {
            1.0
        } else if i % 2 == 1 {
            4.0
        } else {
            2.0
        };
        let (a, b) = integrand(i as f64 * step);
        (fn_ + weight * a, fd + weight * b)
    });
    let scale = sim.magnet_count as f64 * tau / (PI * MU_0);
    MagnetForces {
        normal_n: scale * normal * step / 3.0,
        drag_n: scale * drag * step / 3.0,
    }
}

/// Heights of `n ≥ 2` evenly spaced copper sheets above the PCB bottom [m]:
/// `d_i = i·T/(n−1)`, from the bottom face to the top face.
fn copper_depths(t_pcb: f64, n: u32) -> Vec<f64> {
    (0..n).map(|i| t_pcb * i as f64 / (n - 1) as f64).collect()
}

/// `(1/N)·Σ e^(−2k·d_i)`: each equal-current sheet at `d_i` above the
/// reflecting plane couples to its image `2·d_i` away.
fn copper_weight(k: f64, depths: &[f64]) -> f64 {
    depths.iter().map(|d| (-2.0 * k * d).exp()).sum::<f64>() / depths.len() as f64
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
mod tests;
