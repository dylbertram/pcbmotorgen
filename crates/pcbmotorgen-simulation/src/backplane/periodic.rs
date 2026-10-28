//! On-demand periodic static reference, not a finite-motor force backend.
//!
//! Coupled odd Fourier modes and linear depth elements minimize the vector
//! two-slope magnetic energy. Air is eliminated by exact boundary operators.
//! The block-tridiagonal Newton solve is the same physical model checked by
//! scripts/solvers/spectral_plate.py. No coefficients are fitted to FEMM.
use super::{BackplaneStack, MU_0};
use crate::params::SimulationInput;
use nalgebra::{DMatrix, DVector};
use serde::Serialize;
use std::f64::consts::PI;
use std::time::Instant;

#[derive(Debug, Clone, Serialize)]
pub struct PeriodicStaticRun {
    pub depth_cells: usize,
    pub odd_modes: usize,
    pub angular_samples: usize,
    pub newton_iterations: usize,
    pub relative_gradient_residual: f64,
    pub field_ratio_at_pm_centre_pcb_top: f64,
    pub mean_pressure_over_magnet_width_pa: f64,
    pub reflected_normal_modes_t: Vec<f64>,
    pub quadrature_sampled_peak_b_t: f64,
    pub quadrature_saturated_fraction: f64,
    pub isolated_sheet_dc_factors_per_alignment: [f64; 2],
    pub differential_relative_residual: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PeriodicStaticReference {
    pub scope: String,
    pub magnetic_thickness_m: f64,
    pub mu_initial: f64,
    pub saturation_polarization_t: f64,
    pub elapsed_seconds: f64,
    pub runs: Vec<PeriodicStaticRun>,
    pub max_field_refinement_change: f64,
    pub max_pressure_refinement_change: f64,
    pub max_dc_factor_absolute_refinement_change: f64,
    pub warnings: Vec<String>,
}

struct Plate {
    cells: usize,
    modes: usize,
    samples: usize,
    step: f64,
    mu: f64,
    bsat: f64,
    pcb: f64,
    width: f64,
    pitch: f64,
    k: DVector<f64>,
    incident: DVector<f64>,
    sine: Vec<DVector<f64>>,
    q: Vec<DVector<f64>>,
}

struct Evaluation {
    energy: f64,
    gradient: Vec<DVector<f64>>,
    diagonal: Vec<DMatrix<f64>>,
    upper: Vec<DMatrix<f64>>,
    peak: f64,
    saturated_fraction: f64,
}

impl Evaluation {
    fn norm(&self) -> f64 {
        self.gradient
            .iter()
            .map(|g| g.norm_squared())
            .sum::<f64>()
            .sqrt()
    }

    fn direction(&self) -> Result<Vec<DVector<f64>>, String> {
        let mut gains: Vec<DMatrix<f64>> = Vec::new();
        let mut values: Vec<DVector<f64>> = Vec::new();
        for i in 0..self.diagonal.len() {
            let mut diagonal = self.diagonal[i].clone();
            let mut rhs = -&self.gradient[i];
            if i > 0 {
                let lower = self.upper[i - 1].transpose();
                diagonal -= &lower * &gains[i - 1];
                rhs -= lower * &values[i - 1];
            }
            let chol = diagonal
                .cholesky()
                .ok_or("Periodic Newton Hessian is not positive definite")?;
            values.push(chol.solve(&rhs));
            if i < self.upper.len() {
                gains.push(chol.solve(&self.upper[i]));
            }
        }
        for i in (0..gains.len()).rev() {
            let correction = &gains[i] * &values[i + 1];
            values[i] -= correction;
        }
        Ok(values)
    }
}

impl Plate {
    fn new(
        sim: &SimulationInput,
        thickness: f64,
        mu: f64,
        bsat: f64,
        cells: usize,
        modes: usize,
        samples: usize,
    ) -> Result<Self, String> {
        let pitch = sim.pole_pitch_m();
        let width = sim.magnet_dims_m[0];
        let height = sim.magnet_dims_m[2];
        let pcb = sim.pcb_thickness_m;
        let gap = sim.air_gap_m;
        let br = sim.magnet_remanence_t;
        if ![pitch, width, height, pcb, gap, br, thickness, mu, bsat]
            .iter()
            .all(|v| v.is_finite() && *v > 0.0)
            || width >= pitch
            || mu <= 1.0
            || cells < 2
            || modes == 0
            || samples < 8 * modes
            || samples % 4 != 0
        {
            return Err("Periodic reference requires positive geometry, a saturable layer and separated magnets".into());
        }
        let k = DVector::from_fn(modes, |i, _| (2 * i + 1) as f64 * PI / pitch);
        let incident = DVector::from_fn(modes, |i, _| {
            2.0 * br / (PI * (2 * i + 1) as f64)
                * (k[i] * width / 2.0).sin()
                * (1.0 - (-k[i] * height).exp())
                * (-k[i] * (pcb + gap)).exp()
        });
        // For odd sine A modes, the other three quadrants reproduce the same
        // energy, gradient and Hessian exactly under x/z sign changes. This
        // folds the full midpoint quadrature, not its angular resolution.
        let mut sine = Vec::with_capacity(samples / 4);
        let mut q = Vec::with_capacity(samples / 4);
        for sample in 0..samples / 4 {
            let theta = (sample as f64 + 0.5) * 2.0 * PI / samples as f64;
            sine.push(DVector::from_fn(modes, |i, _| {
                ((2 * i + 1) as f64 * theta).sin()
            }));
            q.push(DVector::from_fn(modes, |i, _| {
                k[i] * ((2 * i + 1) as f64 * theta).cos()
            }));
        }
        Ok(Self {
            cells,
            modes,
            samples,
            step: thickness / cells as f64,
            mu,
            bsat,
            pcb,
            width,
            pitch,
            k,
            incident,
            sine,
            q,
        })
    }

    fn evaluate(&self, a: &[DVector<f64>], hessian: bool) -> Evaluation {
        self.evaluate_tangent(a, hessian, 0)
    }

    fn evaluate_tangent(&self, a: &[DVector<f64>], hessian: bool, phase: usize) -> Evaluation {
        let mut out = Evaluation {
            energy: 0.0,
            gradient: vec![DVector::zeros(self.modes); self.cells + 1],
            diagonal: if hessian {
                vec![DMatrix::zeros(self.modes, self.modes); self.cells + 1]
            } else {
                Vec::new()
            },
            upper: if hessian {
                vec![DMatrix::zeros(self.modes, self.modes); self.cells]
            } else {
                Vec::new()
            },
            peak: 0.0,
            saturated_fraction: 0.0,
        };
        let knee = self.bsat * self.mu / (self.mu - 1.0);
        let weight = self.step / (2.0 * self.sine.len() as f64);
        for cell in 0..self.cells {
            let derivative = (&a[cell + 1] - &a[cell]) / self.step;
            for position in [0.5 - 1.0 / 12.0_f64.sqrt(), 0.5 + 1.0 / 12.0_f64.sqrt()] {
                let mid = &a[cell] * (1.0 - position) + &a[cell + 1] * position;
                for sample in 0..self.sine.len() {
                    let sine = &self.sine[sample];
                    let q = &self.q[sample];
                    let x = derivative.dot(sine);
                    let z = mid.dot(q);
                    let b = x.hypot(z);
                    out.peak = out.peak.max(b);
                    let (energy, nu, extra) = if b > knee {
                        out.saturated_fraction += 1.0 / (2 * self.cells * self.sine.len()) as f64;
                        let d = b - knee;
                        (
                            knee * knee / (2.0 * MU_0 * self.mu)
                                + knee * d / (MU_0 * self.mu)
                                + d * d / (2.0 * MU_0),
                            (b - self.bsat) / (MU_0 * b),
                            self.bsat / (MU_0 * b.powi(3)),
                        )
                    } else {
                        (b * b / (2.0 * MU_0 * self.mu), 1.0 / (MU_0 * self.mu), 0.0)
                    };
                    out.energy += weight * energy;
                    let (hx, hz) = (nu * x, nu * z);
                    let (dxx, dxz, dzz) = (nu + extra * x * x, extra * x * z, nu + extra * z * z);
                    for i in 0..self.modes {
                        let lx = -sine[i] / self.step;
                        let lz = (1.0 - position) * q[i];
                        let rx = -lx;
                        let rz = position * q[i];
                        out.gradient[cell][i] += weight * (hx * lx + hz * lz);
                        out.gradient[cell + 1][i] += weight * (hx * rx + hz * rz);
                        if hessian {
                            // Mirror symmetry makes sine/cosine perturbation
                            // spaces uncoupled around this sine-only PM bias.
                            // Keep the original bias fields/energy unchanged.
                            let (si, qi) = if phase == 0 {
                                (sine[i], q[i])
                            } else {
                                (q[i] / self.k[i], -self.k[i] * sine[i])
                            };
                            let (lx, lz, rx, rz) = (
                                -si / self.step,
                                (1.0 - position) * qi,
                                si / self.step,
                                position * qi,
                            );
                            for j in 0..self.modes {
                                let (sj, qj) = if phase == 0 {
                                    (sine[j], q[j])
                                } else {
                                    (q[j] / self.k[j], -self.k[j] * sine[j])
                                };
                                let jlx = -sj / self.step;
                                let jlz = (1.0 - position) * qj;
                                let jrx = -jlx;
                                let jrz = position * qj;
                                let product = |ax: f64, az: f64, bx: f64, bz: f64| {
                                    weight
                                        * (dxx * ax * bx
                                            + dxz * (ax * bz + az * bx)
                                            + dzz * az * bz)
                                };
                                out.diagonal[cell][(i, j)] += product(lx, lz, jlx, jlz);
                                out.diagonal[cell + 1][(i, j)] += product(rx, rz, jrx, jrz);
                                out.upper[cell][(i, j)] += product(lx, lz, jrx, jrz);
                            }
                        }
                    }
                }
            }
        }
        for i in 0..self.modes {
            let boundary = self.k[i] / (2.0 * MU_0);
            let top = a[0][i] - 2.0 * self.incident[i] / self.k[i];
            let bottom = a[self.cells][i];
            out.energy += 0.5 * boundary * (top * top + bottom * bottom);
            out.gradient[0][i] += boundary * top;
            out.gradient[self.cells][i] += boundary * bottom;
            if hessian {
                out.diagonal[0][(i, i)] += boundary;
                out.diagonal[self.cells][(i, i)] += boundary;
            }
        }
        out
    }

    fn differential_benchmark(&self, a: &[DVector<f64>]) -> Result<([f64; 2], f64), String> {
        let sheet = 0.00002;
        if self.pcb < 2.0 * sheet {
            return Err("Periodic DC benchmark requires room for two isolated 20 μm sheets".into());
        }
        let k = self.k[0];
        let u = k * sheet;
        let self_weight = 2.0 * (u + (-u).exp_m1()) / (u * u);
        let image_weight = ((u / 2.0).sinh() / (u / 2.0)).powi(2)
            * (((-k * sheet).exp() + (-2.0 * k * (self.pcb - sheet / 2.0)).exp()) / 2.0)
            / self_weight;
        if !self_weight.is_finite()
            || self_weight <= 0.0
            || !image_weight.is_finite()
            || image_weight <= 0.0
        {
            return Err("Unresolved or nonfinite isolated-sheet geometry".into());
        }
        let mut factors = [0.0; 2];
        let mut worst_residual = 0.0_f64;
        for (phase, factor) in factors.iter_mut().enumerate() {
            let mut evaluation = self.evaluate_tangent(a, true, phase);
            evaluation.gradient.iter_mut().for_each(|g| g.fill(0.0));
            evaluation.gradient[0][0] = -1.0 / MU_0;
            let response = evaluation.direction()?;
            let mut norm = 0.0;
            for i in 0..=self.cells {
                let mut residual = &evaluation.diagonal[i] * &response[i] + &evaluation.gradient[i];
                if i > 0 {
                    residual += evaluation.upper[i - 1].transpose() * &response[i - 1];
                }
                if i < self.cells {
                    residual += &evaluation.upper[i] * &response[i + 1];
                }
                norm += residual.norm_squared();
            }
            let residual = norm.sqrt() * MU_0;
            if !residual.is_finite() || residual > 1e-9 {
                return Err("Unconverged periodic differential response".into());
            }
            worst_residual = worst_residual.max(residual);
            let reflection = k * response[0][0] - 1.0;
            if !reflection.is_finite() || !(-1e-8..=1.0 + 1e-8).contains(&reflection) {
                return Err("Nonpassive periodic differential response".into());
            }
            *factor = 1.0 + reflection * image_weight;
            if !factor.is_finite() {
                return Err("Nonfinite periodic DC factor".into());
            }
        }
        Ok((factors, worst_residual))
    }

    fn solve(&self) -> Result<PeriodicStaticRun, String> {
        let mut a: Vec<DVector<f64>> = (0..=self.cells)
            .map(|cell| {
                DVector::from_fn(self.modes, |i, _| {
                    self.incident[i] / self.k[i] * (-self.k[i] * cell as f64 * self.step).exp()
                })
            })
            .collect();
        let scale = self.incident.norm() / MU_0;
        if !scale.is_finite() || scale <= 0.0 {
            return Err("Periodic source underflow".into());
        }
        for iteration in 1..=100 {
            let current = self.evaluate(&a, true);
            let residual = current.norm() / scale;
            if !residual.is_finite() {
                return Err("Nonfinite periodic residual".into());
            }
            if residual <= 1e-9 {
                let reflected =
                    DVector::from_fn(self.modes, |i, _| self.k[i] * a[0][i] - self.incident[i]);
                let bare: f64 = (0..self.modes)
                    .map(|i| self.incident[i] * (self.k[i] * self.pcb).exp())
                    .sum();
                let image: f64 = (0..self.modes)
                    .map(|i| reflected[i] * (-self.k[i] * self.pcb).exp())
                    .sum();
                let pressure = self.incident.dot(&reflected) / MU_0 * self.pitch / self.width;
                let ratio = 1.0 + image / bare;
                if !ratio.is_finite() || !pressure.is_finite() || pressure <= 0.0 {
                    return Err("Invalid periodic field/pressure".into());
                }
                let (dc_factors, differential_residual) = self.differential_benchmark(&a)?;
                return Ok(PeriodicStaticRun {
                    depth_cells: self.cells,
                    odd_modes: self.modes,
                    angular_samples: self.samples,
                    newton_iterations: iteration,
                    relative_gradient_residual: residual,
                    field_ratio_at_pm_centre_pcb_top: ratio,
                    mean_pressure_over_magnet_width_pa: pressure,
                    reflected_normal_modes_t: reflected.as_slice().to_vec(),
                    quadrature_sampled_peak_b_t: current.peak,
                    quadrature_saturated_fraction: current.saturated_fraction.clamp(0.0, 1.0),
                    isolated_sheet_dc_factors_per_alignment: dc_factors,
                    differential_relative_residual: differential_residual,
                });
            }
            let direction = current.direction()?;
            let slope: f64 = current
                .gradient
                .iter()
                .zip(&direction)
                .map(|(g, d)| g.dot(d))
                .sum();
            if !slope.is_finite() || slope >= 0.0 {
                return Err("Invalid periodic Newton direction".into());
            }
            let mut relaxation = 1.0;
            let mut accepted = false;
            for _ in 0..40 {
                let trial: Vec<DVector<f64>> = a
                    .iter()
                    .zip(&direction)
                    .map(|(v, d)| v + d * relaxation)
                    .collect();
                let next = self.evaluate(&trial, false);
                if next.energy <= current.energy + 1e-4 * relaxation * slope
                    || ((next.energy - current.energy).abs()
                        < 1e-12 * current.energy.abs().max(1.0)
                        && next.norm() < current.norm())
                {
                    a = trial;
                    accepted = true;
                    break;
                }
                relaxation *= 0.5;
            }
            if !accepted {
                return Err("Periodic Newton line search failed".into());
            }
        }
        Err("Periodic static reference did not converge".into())
    }
}

impl BackplaneStack {
    /// Slow, explicit reference request. Never called by analytical previews.
    /// Supports one magnetic layer and a nonmagnetic DC-transparent housing.
    pub fn periodic_static_reference(
        &self,
        sim: &SimulationInput,
    ) -> Result<PeriodicStaticReference, String> {
        let started = Instant::now();
        self.validate()?;
        if self.layers.len() != 1
            || self
                .housing
                .as_ref()
                .is_some_and(|h| h.material.mu_r() != 1.0)
        {
            return Err(
                "Periodic reference supports one magnetic layer and a nonmagnetic housing only"
                    .into(),
            );
        }
        let layer = &self.layers[0];
        let mu = layer.mu_r();
        let bsat = layer
            .bsat_t()
            .ok_or("Periodic reference requires saturation polarization data")?;
        let mut runs: Vec<PeriodicStaticRun> = Vec::new();
        let (mut max_field, mut max_pressure) = (0.0_f64, 0.0_f64);
        let mut max_dc_change = 0.0_f64;
        for (cells, modes, samples) in [(32, 9, 512), (64, 9, 512), (64, 17, 512), (64, 17, 1024)] {
            let run =
                Plate::new(sim, layer.thickness_m, mu, bsat, cells, modes, samples)?.solve()?;
            if let Some(previous) = runs.last() {
                for (old, new) in previous
                    .isolated_sheet_dc_factors_per_alignment
                    .iter()
                    .zip(run.isolated_sheet_dc_factors_per_alignment)
                {
                    let change = (old - new).abs();
                    max_dc_change = max_dc_change.max(change);
                    if change > 0.001_f64.max(0.02 * (new - 1.0).abs()) {
                        return Err("Periodic DC benchmark failed separate depth/mode/angular refinement gates".into());
                    }
                }
                max_field = max_field.max(
                    (previous.field_ratio_at_pm_centre_pcb_top
                        / run.field_ratio_at_pm_centre_pcb_top
                        - 1.0)
                        .abs(),
                );
                max_pressure = max_pressure.max(
                    (previous.mean_pressure_over_magnet_width_pa
                        / run.mean_pressure_over_magnet_width_pa
                        - 1.0)
                        .abs(),
                );
            }
            runs.push(run);
        }
        if max_field > 0.02 || max_pressure > 0.02 {
            return Err(
                "Periodic reference failed separate 2% depth/mode/angular refinement gates".into(),
            );
        }
        Ok(PeriodicStaticReference {
            scope: "Periodic static reference with isolated-sheet DC benchmarks, infinite cross-depth; not finite-motor force or actual winding/eddy prediction".into(),
            magnetic_thickness_m: layer.thickness_m, mu_initial: mu, saturation_polarization_t: bsat,
            elapsed_seconds: started.elapsed().as_secs_f64(),
            runs, max_field_refinement_change: max_field, max_pressure_refinement_change: max_pressure,
            max_dc_factor_absolute_refinement_change: max_dc_change,
            warnings: vec![
                "Array ends, housing edges and magnet cross-width are not modelled. Do not use this pressure as a finite-motor bearing load.".into(),
                "DC coil factors describe two isolated 20 μm sinusoidal sheets at the PCB faces and two spatial alignments. They are not your winding inductance or its minimum across travel.".into(),
                "The nonmagnetic housing is DC-transparent here. AC impedance, eddy currents, motion, hysteresis and PWM are not solved.".into(),
                "Ideal two-slope material law. Numerical convergence does not validate unmeasured material properties.".into(),
            ],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sim() -> SimulationInput {
        SimulationInput {
            magnet_dims_m: [0.005, 0.005, 0.003],
            magnet_remanence_t: 1.34,
            magnet_pitch_m: 0.006,
            air_gap_m: 0.0005,
            pcb_thickness_m: 0.0008,
            ..SimulationInput::default()
        }
    }

    #[test]
    fn coupled_static_port_matches_python_at_the_same_resolution() {
        for (t, mu, bsat, ratio, pressure) in [
            (0.0002, 130.0, 0.25, 1.0452565662360171, 7452.2858249040355),
            (0.005, 130.0, 0.25, 1.298055085497814, 65829.55260659744),
            (0.002, 2500.0, 0.45, 1.4052436790657683, 84543.20605607255),
        ] {
            let result = Plate::new(&sim(), t, mu, bsat, 8, 3, 128)
                .unwrap()
                .solve()
                .unwrap();
            assert!(result.relative_gradient_residual <= 1e-9);
            assert!((result.field_ratio_at_pm_centre_pcb_top / ratio - 1.0).abs() < 1e-10);
            assert!((result.mean_pressure_over_magnet_width_pa / pressure - 1.0).abs() < 1e-10);
        }
    }

    #[test]
    fn differential_benchmark_matches_both_python_phases_without_a_scalar_mu() {
        let saturated = Plate::new(&sim(), 0.0002, 130.0, 0.25, 8, 3, 128)
            .unwrap()
            .solve()
            .unwrap();
        for (actual, expected) in saturated
            .isolated_sheet_dc_factors_per_alignment
            .iter()
            .zip([1.0025047027960015, 1.05867102521367])
        {
            assert!((actual - expected).abs() < 1e-10);
        }
        assert!(saturated.differential_relative_residual <= 1e-9);
        let linear = Plate::new(&sim(), 0.0002, 130.0, 1000.0, 8, 3, 128)
            .unwrap()
            .solve()
            .unwrap();
        assert!(
            (linear.isolated_sheet_dc_factors_per_alignment[0]
                - linear.isolated_sheet_dc_factors_per_alignment[1])
                .abs()
                < 1e-8
        );
    }

    #[test]
    fn block_newton_direction_solves_the_full_hessian() {
        let plate = Plate::new(&sim(), 0.001, 130.0, 0.25, 3, 3, 128).unwrap();
        let a = vec![DVector::from_element(3, 0.0001); 4];
        let evaluation = plate.evaluate(&a, true);
        let direction = evaluation.direction().unwrap();
        let mut norm = 0.0;
        for i in 0..4 {
            let mut residual = &evaluation.diagonal[i] * &direction[i] + &evaluation.gradient[i];
            if i > 0 {
                residual += evaluation.upper[i - 1].transpose() * &direction[i - 1];
            }
            if i < 3 {
                residual += &evaluation.upper[i] * &direction[i + 1];
            }
            norm += residual.norm_squared();
        }
        assert!(norm.sqrt() / evaluation.norm() < 1e-10);
    }

    #[test]
    fn energy_gradient_and_vector_tangent_match_finite_differences() {
        let plate = Plate::new(&sim(), 0.001, 130.0, 0.25, 3, 3, 128).unwrap();
        let a: Vec<_> = (0..4)
            .map(|c| DVector::from_fn(3, |i, _| 0.0001 / (1 + c + i) as f64))
            .collect();
        let direction: Vec<_> = (0..4)
            .map(|c| DVector::from_fn(3, |i, _| 0.00001 * (c * 3 + i + 1) as f64))
            .collect();
        let original = plate.evaluate(&a, true);
        let epsilon = 1e-5;
        let plus: Vec<_> = a
            .iter()
            .zip(&direction)
            .map(|(v, d)| v + d * epsilon)
            .collect();
        let minus: Vec<_> = a
            .iter()
            .zip(&direction)
            .map(|(v, d)| v - d * epsilon)
            .collect();
        let plus = plate.evaluate(&plus, false);
        let minus = plate.evaluate(&minus, false);
        let slope: f64 = original
            .gradient
            .iter()
            .zip(&direction)
            .map(|(g, d)| g.dot(d))
            .sum();
        assert!(((plus.energy - minus.energy) / (2.0 * epsilon) / slope - 1.0).abs() < 1e-6);
        for i in 0..4 {
            let difference = (&plus.gradient[i] - &minus.gradient[i]) / (2.0 * epsilon);
            let mut expected = &original.diagonal[i] * &direction[i];
            if i > 0 {
                expected += original.upper[i - 1].transpose() * &direction[i - 1];
            }
            if i < 3 {
                expected += &original.upper[i] * &direction[i + 1];
            }
            assert!((&difference - &expected).norm() / expected.norm() < 1e-6);
        }
    }

    #[test]
    fn unsupported_stacks_and_nonfinite_inputs_fail_explicitly() {
        use super::super::{BackplaneLayer, HousingMaterial, HousingSpec, LayerMaterial};
        let layer = BackplaneLayer::new(LayerMaterial::FlexFerrite, 0.0002);
        let mut stack = BackplaneStack {
            layers: vec![layer.clone(), layer.clone()],
            housing: None,
        };
        assert!(stack
            .periodic_static_reference(&sim())
            .unwrap_err()
            .contains("one magnetic layer"));
        stack.layers.pop();
        stack.housing = Some(HousingSpec {
            material: HousingMaterial::Steel1018,
            thickness_m: 0.001,
            gap_m: 0.0001,
        });
        assert!(stack
            .periodic_static_reference(&sim())
            .unwrap_err()
            .contains("unsupported for coreless screening"));
        stack.housing = None;
        let mut invalid = sim();
        invalid.magnet_remanence_t = f64::NAN;
        assert!(stack.periodic_static_reference(&invalid).is_err());
        stack.layers[0] = BackplaneLayer::new(LayerMaterial::Fr4, 0.001);
        assert!(stack.periodic_static_reference(&sim()).is_err());
        let mut unresolved = sim();
        unresolved.magnet_pitch_m = 1e18;
        let plate = Plate::new(&unresolved, 0.0002, 130.0, 0.25, 4, 1, 32).unwrap();
        assert!(plate
            .differential_benchmark(&vec![DVector::zeros(1); 5])
            .is_err());
    }
}
