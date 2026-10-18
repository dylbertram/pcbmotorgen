use super::*;
use crate::units::mm;

fn sim() -> SimulationInput {
    SimulationInput::default()
}

fn layer(material: LayerMaterial, t_mm: f64) -> BackplaneLayer {
    BackplaneLayer::new(material, mm(t_mm))
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

/// `s` with every layer's Bsat raised to the override limit, so nothing in
/// it saturates under the default magnets.
fn linear(mut s: BackplaneStack) -> BackplaneStack {
    for l in &mut s.layers {
        l.bsat_t = Some(MAX_BSAT_T);
    }
    s
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
        active_area_length_m: mm(92.0),
        num_layers: 2,
        ..sim()
    }
}

/// The user's "version 2": the benchmark on a 0.8 mm PCB over a 0.2 mm
/// flexible ferrite sheet and a 1 mm aluminium 6061 housing 0.1 mm below it.
fn version_two() -> (SimulationInput, BackplaneStack) {
    let sim = SimulationInput {
        pcb_thickness_m: mm(0.8),
        ..benchmark()
    };
    let stack = stack(
        vec![layer(LayerMaterial::FlexFerrite, 0.2)],
        housing(HousingMaterial::Aluminum6061, 1.0, 0.1),
    );
    (sim, stack)
}

fn k() -> f64 {
    PI / sim().pole_pitch_m()
}

fn media(pairs: &[(f64, f64)]) -> Vec<Medium> {
    pairs
        .iter()
        .map(|&(mu, t)| Medium {
            mu,
            sigma: 0.0,
            t,
            bsat: None,
        })
        .collect()
}

// --- The magnetostatic model before saturation and eddy currents (e02d2ec),
// --- kept to check that σ = 0 and unsaturated stacks reproduce it exactly.

fn old_reflection(k: f64, media: &[(f64, f64)]) -> f64 {
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

fn old_attraction(sim: &SimulationInput, media: &[(f64, f64)]) -> f64 {
    let tau = sim.pole_pitch_m();
    let k = PI / tau;
    let depth = sim.magnet_dims_m[1];
    let d = sim.air_gap_m + sim.pcb_thickness_m;
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
        old_reflection(kappa, media) * b * b * spectrum * spectrum
    };
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

fn old_pairs(s: &BackplaneStack) -> Vec<(f64, f64)> {
    s.media().iter().map(|m| (m.mu, m.t)).collect()
}

#[test]
fn unsaturated_stacks_reproduce_the_magnetostatic_model_exactly() {
    let s = benchmark();
    let k = PI / s.pole_pitch_m();
    for st in [
        mnzn(2.0),
        mnzn(5.0),
        stack(vec![layer(LayerMaterial::NiZnFerrite, 5.0)], None),
        stack(
            vec![
                layer(LayerMaterial::Fr4, 1.0),
                layer(LayerMaterial::MnZnFerrite, 2.0),
            ],
            housing(HousingMaterial::Aluminum6061, 3.0, 1.0),
        ),
        stack(vec![], housing(HousingMaterial::Steel1018, 3.0, 1.0)),
    ] {
        let a = st.analyze(&s);
        assert!(a.layer_states.iter().all(|l| !l.saturated()));
        let pairs = old_pairs(&st);
        let r = old_reflection(k, &pairs);
        let mean = ((-2.0 * k * 0.0).exp() + (-2.0 * k * s.pcb_thickness_m).exp()) / 2.0;
        assert_eq!(a.image_strength, r);
        assert_eq!(a.linear_image_strength, r);
        assert_eq!(a.inductance_factor, 1.0 + r * mean);
        assert_eq!(a.attraction_n, old_attraction(&s, &pairs));
        // σ only enters off DC: a static coil factor ignores it.
        assert_eq!(st.solve(&s).coil_factor(0.0).im, 0.0);
    }
}

#[test]
fn complex_recursion_without_conductivity_matches_the_static_one() {
    // A vanishing σ forces the complex path.
    for (mu, t) in [
        (60.0, mm(0.3)),
        (2500.0, mm(2.0)),
        (4000.0, mm(0.35)),
        (1.5, mm(5.0)),
    ] {
        let mut m = media(&[(1.0, mm(0.5)), (mu, t), (1.0, mm(1.0)), (800.0, mm(3.0))]);
        let r = reflection(k(), &m);
        m[1].sigma = 1e-30;
        let c = reflection_ac(k(), 1e3, &m);
        assert!((c.re - r).abs() < 1e-14 && c.im.abs() < 1e-14, "{c} vs {r}");
    }
}

#[test]
fn perfect_conductor_reflects_minus_one() {
    let mut m = media(&[(1.0, mm(3.0))]);
    m[0].sigma = 1e14;
    let r = reflection_ac(k(), 2.0 * PI * 1e5, &m);
    assert!((r.re + 1.0).abs() < 1e-3 && r.im.abs() < 1e-3, "{r}");
    // A conductor behind a thick ideal plate is invisible, and a thin
    // conductor at low frequency is too.
    let mut behind = media(&[(1e9, mm(20.0)), (1.0, mm(3.0))]);
    behind[1].sigma = 1e14;
    assert!((reflection_ac(k(), 2.0 * PI * 1e5, &behind).re - 1.0).abs() < 1e-6);
    let mut thin = media(&[(1.0, 1e-6)]);
    thin[0].sigma = 1e6;
    assert!(reflection_ac(k(), 1.0, &thin).norm() < 1e-6);
}

#[test]
fn conductor_lowers_inductance_and_adds_resistance() {
    let s = benchmark();
    let solved = stack(vec![], housing(HousingMaterial::Aluminum6061, 3.0, 1.0)).solve(&s);
    let dc = solved.coil_factor(0.0);
    assert_eq!(dc, Complex::new(1.0, 0.0));
    let mut last = dc.re;
    for f in [1e3, 1e4, 1e5, 1e6] {
        let c = solved.coil_factor(f);
        assert!(c.re < last, "{f} Hz: {c}");
        assert!(c.im < 0.0, "{f} Hz: passive load needs Im F < 0, got {c}");
        last = c.re;
    }
    // Perfect-conductor limit: 1 − (1/N)·Σe^(−2k·d_i) with the plate 1 mm down.
    let k = PI / s.pole_pitch_m();
    let limit = 1.0 - ((-2.0 * k * mm(1.0)).exp() + (-2.0 * k * mm(2.6)).exp()) / 2.0;
    assert!((solved.coil_factor(1e9).re - limit).abs() < 2e-3);
}

#[test]
fn default_backplane_is_empty_and_has_no_effect() {
    let stack = BackplaneStack::default();
    let a = stack.analyze(&sim());
    assert_eq!(a.image_strength, 0.0);
    assert_eq!(a.inductance_factor, 1.0);
    assert_eq!(a.attraction_n, 0.0);
    assert_eq!(stack.stack_thickness_m(), 0.0);
    assert!(!stack.solve(&sim()).conducts());
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
    assert!((reflection(k(), &media(&[(mu, 1.0)])) - r).abs() < 1e-12);
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
        assert!((reflection(k(), &media(&[(mu, t)])) - closed).abs() < 1e-12);
    }
}

#[test]
fn reflection_grows_with_permeability_and_thickness() {
    let s = sim();
    let nizn = linear(stack(vec![layer(LayerMaterial::NiZnFerrite, 3.0)], None)).analyze(&s);
    let thin = linear(mnzn(0.5)).analyze(&s);
    let thick = linear(mnzn(3.0)).analyze(&s);
    assert!(thick.image_strength > nizn.image_strength);
    assert!(thick.image_strength > thin.image_strength);
    assert!(thick.image_strength < 1.0);
    assert!(thick.inductance_factor > nizn.inductance_factor);
}

#[test]
fn spacer_scales_reflection_by_its_round_trip() {
    let s = sim();
    let bare = linear(mnzn(2.0));
    let spaced = linear(stack(
        vec![
            layer(LayerMaterial::Fr4, 1.0),
            layer(LayerMaterial::MnZnFerrite, 2.0),
        ],
        None,
    ));
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
    let r = split.analyze(&benchmark()).linear_image_strength;
    assert!(
        r > 0.998 && r < mnzn(2.0).image_strength(&benchmark()),
        "{r}"
    );
}

fn layered(num_layers: u32) -> BackplaneAnalysis {
    let mut s = sim();
    s.num_layers = num_layers;
    linear(mnzn(2.0)).analyze(&s)
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
    let a = linear(mnzn(2.0)).analyze(&s);
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
fn linear_peak_matches_femm() {
    // Linear FEMM, peak |B| 0.01 mm inside the stack top of the benchmark
    // (RESULTS.md): 0.556 T for 2 mm MnZn, 0.439 T for 5 mm and 2.40 T for
    // 0.35 mm Si steel.
    let s = benchmark();
    for (material, t_mm, femm) in [
        (LayerMaterial::MnZnFerrite, 2.0, 0.556),
        (LayerMaterial::MnZnFerrite, 5.0, 0.439),
        (LayerMaterial::SiliconSteel, 0.35, 2.40),
    ] {
        let a = stack(vec![layer(material, t_mm)], None).analyze(&s);
        let peak = a.layer_states[0].linear_peak_b_t;
        assert!((peak / femm - 1.0).abs() < 0.02, "{t_mm} mm: {peak}");
    }
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
fn face_saturation_of_a_thick_plate_warns_but_keeps_mu() {
    // 2 mm MnZn on the benchmark: the face reaches 0.56 T > 0.45 T, the mean
    // flux (0.42 T) fits.
    let a = mnzn(2.0).analyze(&benchmark());
    let st = &a.layer_states[0];
    assert!(!st.saturated());
    assert_eq!(st.mu_effective, st.mu_initial);
    assert!(st.linear_peak_b_t > 0.45 && st.linear_mean_b_t < 0.45);
    assert!(
        a.warnings.iter().any(|w| w.contains("Only a skin")),
        "{:?}",
        a.warnings
    );
}

#[test]
fn saturated_sheet_clamps_polarization_and_loses_reflection() {
    let s = benchmark();
    let a = stack(vec![layer(LayerMaterial::SiliconSteel, 0.35)], None).analyze(&s);
    let st = &a.layer_states[0];
    let bsat = 1.8;
    assert!(st.saturated() && st.linear_peak_b_t > bsat);
    assert!(st.mu_effective < st.mu_initial);
    assert!(a.image_strength < a.linear_image_strength);
    // At the solved state the polarization of the fundamental is at most that
    // of a square wave at Bsat, 4/π·Bsat.
    let solved = stack(vec![layer(LayerMaterial::SiliconSteel, 0.35)], None).solve(&s);
    let mean = dc_fields(solved.k, &solved.magnet).1[0].mean * solved.b0;
    let h1 = mean / (MU_0 * st.mu_effective);
    assert!(mean - MU_0 * h1 <= 4.0 / PI * bsat * (1.0 + 1e-9), "{mean}");
    // The describing function is a fixed point.
    assert!((describing_mu(st.mu_initial, bsat, h1) / st.mu_effective - 1.0).abs() < 1e-9);
    // The peak is the B-H curve, not a linear multi-tesla number.
    assert!(st.peak_b_t < bsat + MU_0 * h1 * 2.0, "{}", st.peak_b_t);
    assert!(st.mu_incremental < st.mu_effective);
    assert!(a.warnings.iter().any(|w| w.contains("saturated")));
}

#[test]
fn describing_function_limits() {
    let (mu, bsat) = (130.0, 0.25);
    let knee = bsat / (MU_0 * (mu - 1.0));
    assert_eq!(describing_mu(mu, bsat, knee * 0.5), mu);
    assert!((describing_mu(mu, bsat, knee * (1.0 + 1e-9)) / mu - 1.0).abs() < 1e-3);
    // Far above the knee the polarization is a square wave: J1 = 4/π·Bsat.
    let h = knee * 1e4;
    let j1 = (describing_mu(mu, bsat, h) - 1.0) * MU_0 * h;
    assert!((j1 / (4.0 / PI * bsat) - 1.0).abs() < 1e-3);
    assert!((incremental_mu(mu, bsat, h) - 1.0).abs() < 1e-3);
}

#[test]
fn thicker_sheet_saturates_less() {
    let s = benchmark();
    let r = |t| stack(vec![layer(LayerMaterial::FlexFerrite, t)], None).analyze(&s);
    let (thin, thick, plate) = (r(0.1), r(1.0), r(8.0));
    assert!(thin.layer_states[0].flux_overload > thick.layer_states[0].flux_overload);
    assert!(thin.image_strength < thick.image_strength);
    assert!(thick.image_strength < plate.image_strength);
    // The thickness the warning suggests carries the flux at Bsat.
    let t_req = thin.layer_states[0].required_thickness_m.unwrap();
    let at_req = r(t_req * 1e3).layer_states[0].clone();
    assert!(
        (at_req.flux_overload - 1.0).abs() < 1e-6,
        "{}",
        at_req.flux_overload
    );
}

#[test]
fn version_two_reports_saturation_instead_of_a_multi_tesla_peak() {
    let (s, st) = version_two();
    let a = st.analyze(&s);
    let sheet = &a.layer_states[0];
    // Before the saturation model this read 5.57 T with R = 0.758.
    assert!(sheet.linear_peak_b_t > 5.0, "{}", sheet.linear_peak_b_t);
    assert!(sheet.saturated() && sheet.flux_overload > 10.0);
    assert!(a.layer_peak_b_t[0] < 1.0, "{}", a.layer_peak_b_t[0]);
    assert!(
        a.image_strength < 0.1 && a.image_strength > 0.0,
        "{}",
        a.image_strength
    );
    assert!(a.linear_image_strength > 0.75);
    // Away from the magnets the sheet still works for the coil field, under
    // them it does not; aluminium is invisible at DC.
    let solved = st.solve(&s);
    let [away, under] = solved.coil_factor_parts(0.0);
    assert!(
        sheet.mu_incremental < 1.1 && (under.re - 1.0).abs() < 0.01,
        "{under}"
    );
    let expected = a.magnet_coverage * under.re + (1.0 - a.magnet_coverage) * away.re;
    assert!(
        (a.inductance_factor - expected).abs() < 1e-12,
        "{}",
        a.inductance_factor
    );
    assert!(a.inductance_factor > 1.3 && a.inductance_factor < away.re);
    assert!(sheet.required_thickness_m.unwrap() > mm(2.0));
    assert!(sheet.mnzn_thickness_m.unwrap() < sheet.required_thickness_m.unwrap());
    assert!(
        a.attraction_n > 0.0 && a.attraction_n < 2.0,
        "{}",
        a.attraction_n
    );
    let w = a.warnings.join(" ");
    assert!(w.contains("saturated") && w.contains("MnZn"), "{w}");
    assert!(!w.contains("5.57"));

    // At 100 kHz the aluminium screens the coil through the saturated part.
    let pwm = solved.coil_factor(100e3);
    assert!(pwm.re < a.inductance_factor && pwm.im < 0.0, "{pwm}");
    // At 20 m/s the eddy drag dwarfs the ~0.1 N thrust.
    let drag = solved.magnet_forces(&s, 20.0).drag_n;
    assert!(drag > 0.5, "{drag}");
}

#[test]
fn drag_vanishes_at_standstill_and_follows_eddy_brake_asymptotics() {
    let s = benchmark();
    let solved = stack(vec![], housing(HousingMaterial::Aluminum6061, 20.0, 1.0)).solve(&s);
    let f = |v: f64| solved.magnet_forces(&s, v);
    assert_eq!(f(0.0).drag_n, 0.0);
    assert_eq!(f(0.0).normal_n, 0.0);
    // Low speed: viscous, F ∝ v.
    let low = f(2e-4).drag_n / f(1e-4).drag_n;
    assert!((low - 2.0).abs() < 1e-3, "{low}");
    // Skin depth ≪ wall: F ∝ v^(−1/2), and the normal force turns to repulsion.
    let high = f(4e5).drag_n / f(1e5).drag_n;
    assert!((high - 0.5).abs() < 0.02, "{high}");
    assert!(f(1e5).normal_n < 0.0);
    // Drag opposes motion either way.
    assert_eq!(f(-3.0).drag_n, f(3.0).drag_n);
}

#[test]
fn ideal_conductor_repels_as_hard_as_ideal_iron_attracts() {
    let s = benchmark();
    let mut iron = media(&[(1e9, mm(20.0))]);
    let mut copper = media(&[(1.0, mm(20.0))]);
    copper[0].sigma = 1e15;
    iron[0].sigma = 0.0;
    let attract = magnet_forces(&s, &iron, 0.0).normal_n;
    let repel = magnet_forces(&s, &copper, PI / s.pole_pitch_m() * 10.0);
    assert!(
        (repel.normal_n / attract + 1.0).abs() < 2e-3,
        "{repel:?} vs {attract}"
    );
    assert!(repel.drag_n.abs() / attract < 2e-3);
}

#[test]
fn non_magnetic_housing_changes_nothing_behind_a_plate() {
    let s = benchmark();
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
    assert!(!alone.housing_state.as_ref().unwrap().saturated());
    // Behind 2 mm of MnZn the housing is screened: it adds only a little.
    let plain = linear(mnzn(2.0)).analyze(&s);
    let with_steel = linear(stack(vec![layer(LayerMaterial::MnZnFerrite, 2.0)], steel)).analyze(&s);
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
fn overrides_replace_material_values() {
    let s = benchmark();
    let mut l = layer(LayerMaterial::FlexFerrite, 0.1);
    assert_eq!(l.mu_r(), 130.0);
    l.mu_r = Some(150.0);
    l.bsat_t = Some(0.38);
    let a = stack(vec![l.clone()], None).analyze(&s);
    assert_eq!(a.layer_states[0].mu_initial, 150.0);
    assert_eq!(a.layer_states[0].bsat_t, Some(0.38));
    let stronger = stack(vec![l], None).analyze(&s);
    let default = stack(vec![layer(LayerMaterial::FlexFerrite, 0.1)], None).analyze(&s);
    assert!(stronger.layer_states[0].flux_overload < default.layer_states[0].flux_overload);
}

#[test]
fn layers_without_overrides_keep_their_file_format() {
    let json = r#"{"layers":[{"material":"flex_ferrite","thickness_m":0.0002}],"housing":null}"#;
    let st: BackplaneStack = serde_json::from_str(json).unwrap();
    assert_eq!(st.layers[0], layer(LayerMaterial::FlexFerrite, 0.2));
    assert_eq!(serde_json::to_string(&st).unwrap(), json);
}

#[test]
fn validation_rejects_bad_thickness_gap_and_overrides() {
    let one = |t: f64| {
        stack(
            vec![BackplaneLayer::new(LayerMaterial::FlexFerrite, t)],
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
    let with = |mu: Option<f64>, bsat: Option<f64>| {
        let mut l = layer(LayerMaterial::FlexFerrite, 0.1);
        l.mu_r = mu;
        l.bsat_t = bsat;
        stack(vec![l], None).validate()
    };
    assert!(with(Some(0.5), None).is_err());
    assert!(with(Some(f64::INFINITY), None).is_err());
    assert!(with(None, Some(0.0)).is_err());
    assert!(with(None, Some(5.0)).is_err());
    assert!(with(Some(150.0), Some(0.3)).is_ok());
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
