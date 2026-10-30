//! Charge-based travel endpoints (kata k5r5): the first/last magnet
//! equilibrium under the phase-band charge state.
//!
//! The geometric flush clamp ([`super::travel_envelope_over_slots`], kata
//! 5c7r) gives the MECHANICAL travel limits. The true min/max mover position
//! is ELECTROMAGNETIC: it derives from the charge within the first and last
//! phase bands of each phase. With the first phase band of the reference
//! phase fully charged and the remaining phases at their commutation-model
//! offsets, that three-phase charge state fixes where the FIRST magnet
//! settles (its resting position); the last phase bands fix the LAST magnet
//! the same way. With 1:1 spacing (magnet pitch = coil pitch) only the two
//! end magnets need solving — the rigid mover at fixed pitch puts every
//! interior magnet on the same equilibrium lattice.
//!
//! ## The solve
//!
//! **Numerical authority** — [`solve_end_magnet_rest_m`]: the net axial
//! Lorentz force on the END magnet alone (single-magnet assembly, fixed
//! charge excitation on the coils, reusing the existing
//! `magnetic::coil_model` + `physics` force model — no new field solver),
//! bracketed over the settle window at the relevant copper end and bisected
//! ([`REST_TOLERANCE_M`], deterministic grid + bisection). Zeros are
//! classified stable/unstable by the full-array (rigid mover) force slope;
//! the outermost stable zero is the end magnet's rest.
//!
//! **Analytic reference** — [`charge_state_electrical_angle`]: the crate's
//! pinned equilibrium convention ([`super::rest_phase_m`], the skill
//! reference's worked example) maps a charge state to its Clarke angle and
//! hence to the ideal continuous-winding lattice
//! `x ≡ θe·P_e/(2π) (mod P_e)` (baseline `(1, 0, −1)` → θe = π/6 →
//! `P_e/12`). The DISCRETE leg model's zero positions carry a documented
//! layout phase and edge distortion the pure lattice cannot express (the
//! tests characterise both), so the solved rests — not the lattice — are the
//! endpoint authority. The lattice INVARIANTS the tests pin instead: the
//! interior zero recurrence at exactly `P_e`, the reversed-charge half-period
//! symmetry, and the interior rigid pitch `τ_p`.
//!
//! With 1:1 spacing (magnet pitch = coil pitch) only the two END magnets
//! need solving — the rigid mover at fixed pitch puts every interior magnet
//! on the same equilibrium lattice (pinned by the interior-pitch test).
//!
//! ## Integration shape (kata k5r5 option b)
//!
//! [`travel_envelope_charge_based`] derives the envelope endpoints from the
//! solved charge equilibria and clamps them INTO the span-aware flush
//! limits — the geometric clamp remains the documented mechanical LIMIT (the
//! charge refinement can only pull endpoints inward, never past the
//! copper-bounded design range) and the FALLBACK whenever the charge solve
//! is unavailable (no coils, non-3-phase layouts, degenerate copper). The
//! existing [`super::travel_envelope_over_slots`] /
//! [`super::travel_envelope_from_phase_bands`] outputs are unchanged: the
//! authority's reference output for the desktop pins (36 → 111 mm) is
//! untouched by this module — on the reference fixture BOTH raw charge rests
//! overhang the design limits, so the refined envelope equals the flush
//! clamp exactly (measured and pinned).
//!
//! ## Declared phase bands (kata hzs2 discipline)
//!
//! [`band_charge_state`] consumes the declared band centerlines when
//! `SimulationInput.phase_bands` carries them (matched per distinct phase
//! label, ordered spatially) and falls back to the analytic slot model
//! (`slot s ∈ [s·τ_band, (s+1)·τ_band]` anchored at the copper start,
//! `phase(s) = s mod phases`) otherwise. Both ends anchor on the phase
//! owning the relevant TRACK edge band — spatially first for the min
//! endpoint, spatially last for the max endpoint (the min state's mirror;
//! the two owners coincide only when the layout's end permutation puts the
//! reference phase last). The production endpoint solve
//! ([`charge_based_endpoints_m`]) instead uses
//! [`band_charge_state_from_coils`], which derives the end-band anchors
//! from the generated coil geometry — the truthful end permutation, which
//! the declared-band records (first-instance centerlines only) cannot
//! express. The requester's "120° offset" phrasing is the classic
//! balanced-law convention (glossary "Commutation"): the crate's per-coil
//! offset law `π·τ_band/τ_p` gives 60° for the default 3-phase 1:1 layout
//! — the solver consumes whatever offsets the commutation model declares,
//! which is the general case.

use std::f64::consts::PI;

use nalgebra::UnitQuaternion;

use crate::magnetic::coil_model::CoilCurrentModel;
use crate::magnetic::magnet_model::MagnetArray;
use crate::params::SimulationInput;
use crate::physics;
use pcbmotorgen_routing::{PhaseCoil, PHASE_NAMES};

use super::TravelEnvelope;

/// Which end of the mover array an endpoint solve targets.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EndMagnet {
    /// The leading magnet (index 0, +Z polarisation) — fixes the MIN endpoint.
    First,
    /// The trailing magnet (index N−1) — fixes the MAX endpoint.
    Last,
}

/// One phase's normalized charge in an endpoint charge state.
///
/// `charge` is the phase current in units of the peak current, with the
/// reference phase (spatially first band of the triplet) fully charged
/// (`charge = 1`). `label` matches the coil `phase_name` for the numerical
/// solve; the vector order is the SPATIAL phase-axis order required by the
/// Clarke transform (the spatially first phase is the Clarke A axis).
#[derive(Debug, Clone, PartialEq)]
pub struct PhaseCharge {
    /// Phase/net label (matches `PhaseCoil::phase_name`).
    pub label: String,
    /// Normalized charge [1] — phase current over the peak current.
    pub charge: f64,
}

/// Bisection convergence tolerance for the numerical rest solve [m].
pub const REST_TOLERANCE_M: f64 = 1e-9;

/// Conductor sub-segment meshing used by the numerical solve (matches the
/// `ForceEvaluator` default).
const SOLVE_MESHING: usize = 20;

/// Bracketing-grid samples per one-electrical-period scan window.
const SCAN_SAMPLES: usize = 96;

/// Finite-difference step for the stability (force slope) probe [m].
const SLOPE_STEP_M: f64 = 1e-6;

/// Normalized charge state of the FIRST or LAST phase-band triplet [peak 1].
///
/// The reference phase — the owner of the spatially first band — is fully
/// charged (`charge = 1`); every other phase carries
/// `cos(π·(x_p − x_ref)/τ_p)` with `x_p` its band centerline of the SAME
/// (first or last) occurrence and `x_ref` the reference phase's. This is the
/// commutation model's per-coil offset law (kata hzs2 declared bands when
/// present, analytic `p·π·τ_band/τ_p` fallback) evaluated at the state where
/// the reference phase's band is fully charged.
///
/// The analytic fallback models the stator as ideal slots anchored at the
/// copper start: slot `s` spans `[copper_start + s·τ_band,
/// copper_start + (s+1)·τ_band]` with centerline `(s + 0.5)·τ_band` and
/// `phase(s) = s mod phases` — so the LAST band of each phase carries the
/// layout's end permutation (for the reference fixture the last triplet is
/// ordered B, C, A), which is exactly the electromagnetic information the
/// geometric flush clamp cannot see.
///
/// Returns `None` when the charge state is undefined: non-positive pole
/// pitch, no phases, more phases than `PHASE_NAMES` labels (analytic path),
/// fewer slots than phases, or an empty/degenerate declared band set.
#[must_use]
pub fn band_charge_state(
    config: &SimulationInput,
    end: EndMagnet,
    copper_region_start_m: f64,
    copper_region_end_m: f64,
) -> Option<Vec<PhaseCharge>> {
    let phases = config.phases as usize;
    if phases == 0 {
        return None;
    }
    let tau_p = config.pole_pitch_m();
    if !(tau_p > 0.0) {
        return None;
    }
    let tau_band = config.phase_band_pitch_m();
    if !(tau_band > 0.0) {
        return None;
    }

    // (label, first-occurrence centerline, last-occurrence centerline) per
    // distinct phase, ordered by the first-occurrence centerline (spatial
    // phase-axis order for the Clarke transform).
    let mut per_label: Vec<(String, f64, f64)> = Vec::new();
    if config.phase_bands.is_empty() {
        if phases > PHASE_NAMES.len() {
            return None;
        }
        let region_len = copper_region_end_m - copper_region_start_m;
        let n_slots = (region_len / tau_band).floor();
        if n_slots < phases as f64 {
            return None;
        }
        let n_slots = n_slots as i64;
        for p in 0..phases as i64 {
            let first_slot = p;
            // Largest slot s ≤ n_slots − 1 with s ≡ p (mod phases).
            let last_slot = n_slots - 1 - ((n_slots - 1 - p).rem_euclid(phases as i64));
            per_label.push((
                PHASE_NAMES[p as usize].to_string(),
                copper_region_start_m + (first_slot as f64 + 0.5) * tau_band,
                copper_region_start_m + (last_slot as f64 + 0.5) * tau_band,
            ));
        }
    } else {
        for band in &config.phase_bands {
            if let Some(entry) = per_label.iter_mut().find(|(l, _, _)| *l == band.phase) {
                entry.1 = entry.1.min(band.centerline_m);
                entry.2 = entry.2.max(band.centerline_m);
            } else {
                per_label.push((band.phase.clone(), band.centerline_m, band.centerline_m));
            }
        }
        per_label.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
    }
    if per_label.is_empty() {
        return None;
    }

    // Reference anchor: the owner of the SPATIALLY FIRST band for
    // EndMagnet::First, and — mirroring that construction exactly — the
    // owner of the SPATIALLY LAST band (the track's edge band) for
    // EndMagnet::Last. The two owners coincide only when the layout's end
    // permutation puts the reference phase last (e.g. the 73-slot reference
    // fixture, whose last slot is phase A); anchoring the reference phase's
    // own last band instead mis-places the max-endpoint charge state by the
    // end permutation whenever it does not (requester-reported: the max
    // charges must be the min charges mirrored, A↔C with B unchanged, which
    // is exactly this edge anchoring when phase C owns the last band).
    let (reference, use_first) = match end {
        EndMagnet::First => (per_label[0].1, true),
        EndMagnet::Last => {
            let edge = per_label
                .iter()
                .max_by(|a, b| a.2.partial_cmp(&b.2).unwrap_or(std::cmp::Ordering::Equal))
                .expect("per_label is non-empty");
            (edge.2, false)
        }
    };
    Some(
        per_label
            .iter()
            .map(|(label, first_cl, last_cl)| {
                let cl = if use_first { *first_cl } else { *last_cl };
                let delta = PI * (cl - reference) / tau_p;
                PhaseCharge {
                    label: label.clone(),
                    charge: delta.cos(),
                }
            })
            .collect(),
    )
}

/// Charge state of the FIRST or LAST phase-band triplet derived from the
/// GENERATED COIL GEOMETRY [peak 1] — the authoritative endpoint state.
///
/// The end-band anchor positions come from the coils' active conductor
/// segments — the same geometry the force solve consumes — so the state
/// reflects the LAID-OUT end permutation (which phase actually owns the
/// track's edge band) instead of the analytic slot model's assumption.
/// The declared-band contract (kata hzs2) carries only each phase's
/// FIRST-instance centerline, so it cannot express the end bands; the coil
/// geometry can. For each phase the first (resp. last) active-segment x
/// position plays the band-centerline role (routing geometry is
/// millimetres, converted to SI), the anchor is the owner of the spatially
/// first (resp. last) leg, and the charges follow the same per-coil offset
/// law as [`band_charge_state`]: `cos(π·(x_p − x_anchor)/τ_p)`.
///
/// On fixtures whose leg layout matches the analytic slot model this
/// reproduces [`band_charge_state`] exactly (the offsets are what the law
/// consumes); on laid-out patterns whose end permutation differs — e.g. the
/// infinity braid, whose last active leg belongs to phase C — it re-anchors
/// the max state onto the true edge band.
///
/// Returns `None` when the coils carry no active conductor segments or the
/// pole pitch is non-positive.
#[must_use]
pub fn band_charge_state_from_coils(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    end: EndMagnet,
) -> Option<Vec<PhaseCharge>> {
    let tau_p = config.pole_pitch_m();
    if !(tau_p > 0.0) {
        return None;
    }
    // (label, first active-segment x, last active-segment x) per phase
    // [mm], ordered by the first position (spatial phase-axis order).
    let mut per_label: Vec<(String, f64, f64)> = Vec::new();
    for coil in coils {
        let mut xs: Vec<f64> = coil
            .segments
            .iter()
            .filter(|segment| segment.is_active)
            .flat_map(|segment| [segment.start.0, segment.end.0])
            .collect();
        if xs.is_empty() {
            continue;
        }
        xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let (first, last) = (xs[0], xs[xs.len() - 1]);
        if let Some(entry) = per_label.iter_mut().find(|(l, _, _)| *l == coil.phase_name) {
            entry.1 = entry.1.min(first);
            entry.2 = entry.2.max(last);
        } else {
            per_label.push((coil.phase_name.clone(), first, last));
        }
    }
    if per_label.is_empty() {
        return None;
    }
    per_label.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

    let (reference_mm, use_first) = match end {
        EndMagnet::First => (per_label[0].1, true),
        EndMagnet::Last => {
            let edge = per_label
                .iter()
                .max_by(|a, b| a.2.partial_cmp(&b.2).unwrap_or(std::cmp::Ordering::Equal))
                .expect("per_label is non-empty");
            (edge.2, false)
        }
    };
    let to_m = 1e-3;
    Some(
        per_label
            .iter()
            .map(|(label, first, last)| {
                let x_mm = if use_first { *first } else { *last };
                let delta = PI * (x_mm - reference_mm) * to_m / tau_p;
                PhaseCharge {
                    label: label.clone(),
                    charge: delta.cos(),
                }
            })
            .collect(),
    )
}

/// Clarke electrical angle [rad] of a 3-phase charge state, normalized to
/// `(−π, π]`.
///
/// Standard Clarke transform (the crate's pinned equilibrium convention, see
/// [`super::baseline_electrical_angle`]):
///
/// ```text
/// I_α = q_A − 0.5·q_B − 0.5·q_C
/// I_β = (√3/2)·(q_B − q_C)
/// θe  = atan2(I_β, I_α)
/// ```
///
/// The zero-charge singularity (all charges ≈ 0 — undefined holding state,
/// glossary "Stable Rest Position") returns `None`. Exactly three charges
/// are required: the αβ transform is the 3-phase construction.
#[must_use]
pub fn charge_state_electrical_angle(charge: &[f64]) -> Option<f64> {
    if charge.len() != 3 {
        return None;
    }
    let alpha = charge[0] - 0.5 * charge[1] - 0.5 * charge[2];
    let beta = (3.0_f64).sqrt() / 2.0 * (charge[1] - charge[2]);
    if alpha.abs() < 1e-12 && beta.abs() < 1e-12 {
        return None;
    }
    Some(beta.atan2(alpha))
}

/// Charge-based RAW travel endpoints (kata k5r5) [m], as the ARRAY CENTRE
/// positions `(min, max)`, from the force-model equilibrium solve.
///
/// Runs [`solve_end_magnet_rest_m`] for both ends with the charge states of
/// [`band_charge_state_from_coils`] — the end-band charges derived from the
/// generated coil geometry, so the max state anchors on the phase that
/// actually owns the track's edge band (the min state's mirror, per the
/// requester's symmetry observation) — falling back to the config-only
/// [`band_charge_state`] when the coils carry no usable geometry, and
/// converts each end-magnet rest to the array centre with the
/// `(N−1)/2·τ_p` offset. The rests are the RAW
/// electromagnetic equilibria — they may sit outside the copper-bounded
/// design limits ([`super::travel_envelope_over_slots`]); the envelope
/// composer clamps them.
///
/// Returns `None` when either end's solve is undefined (no coils, non-3-phase
/// charge geometry, no stable zero in the scan window) — callers fall back to
/// the geometric flush clamp.
#[must_use]
pub fn charge_based_endpoints_m(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    copper_region_start_m: f64,
    copper_region_end_m: f64,
) -> Option<(f64, f64)> {
    let tau_p = config.pole_pitch_m();
    if !(tau_p > 0.0) || config.magnet_count == 0 {
        return None;
    }
    let q_first = band_charge_state_from_coils(config, coils, EndMagnet::First).or_else(|| {
        band_charge_state(config, EndMagnet::First, copper_region_start_m, copper_region_end_m)
    })?;
    let q_last = band_charge_state_from_coils(config, coils, EndMagnet::Last).or_else(|| {
        band_charge_state(config, EndMagnet::Last, copper_region_start_m, copper_region_end_m)
    })?;
    let first_rest = solve_end_magnet_rest_m(
        config,
        coils,
        &q_first,
        EndMagnet::First,
        copper_region_start_m,
        copper_region_end_m,
    )?;
    let last_rest = solve_end_magnet_rest_m(
        config,
        coils,
        &q_last,
        EndMagnet::Last,
        copper_region_start_m,
        copper_region_end_m,
    )?;
    let centre_offset = (f64::from(config.magnet_count) - 1.0) / 2.0 * tau_p;
    Some((first_rest + centre_offset, last_rest - centre_offset))
}

/// Travel envelope with the charge-based electromagnetic endpoint refinement
/// (kata k5r5) — the kata's option-(b) integration shape.
///
/// The endpoints come from [`charge_based_endpoints_m`] (the force-model
/// equilibria of the first/last magnet under the first/last phase-band charge
/// states) CLAMPED INTO the span-aware flush limits of
/// [`super::travel_envelope_over_slots`]: the geometric clamp remains the
/// documented mechanical LIMIT — the electromagnetic refinement can only pull
/// endpoints inward (reduce travel), never push them past the copper-bounded
/// design range — and the documented FALLBACK: whenever the charge solve is
/// unavailable (no coils, non-3-phase config, no stable rest in the scan
/// window) the flush-clamp envelope is returned unchanged.
///
/// `rest_phase_m` and `electrical_period_m` are unchanged from the flush
/// envelope: the stable-rest lattice still belongs to the baseline
/// excitation (holding-force chart zeros).
#[must_use]
pub fn travel_envelope_charge_based(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    copper_region_start_m: f64,
    copper_region_end_m: f64,
) -> TravelEnvelope {
    let electrical_period_m = 2.0 * config.pole_pitch_m();
    let base = super::travel_envelope_over_slots(
        electrical_period_m,
        config.magnet_count,
        copper_region_start_m,
        copper_region_end_m,
    );
    // Refinement is meaningful only on a non-degenerate flush range (copper
    // at least as long as the mover span).
    let span = f64::from(config.magnet_count) * electrical_period_m / 2.0;
    let non_degenerate = (copper_region_end_m - copper_region_start_m) >= span
        && base.max_position_m > base.min_position_m;
    if !non_degenerate {
        return base;
    }
    let Some((raw_min, raw_max)) =
        charge_based_endpoints_m(config, coils, copper_region_start_m, copper_region_end_m)
    else {
        return base;
    };
    if !(raw_min <= raw_max) {
        return base;
    }
    let min = raw_min.max(base.min_position_m);
    let mut max = raw_max.min(base.max_position_m);
    // Never inverted (mirrors the base clamp's degenerate rule).
    if max < min {
        max = min;
    }
    TravelEnvelope {
        min_position_m: min,
        max_position_m: max,
        rest_phase_m: base.rest_phase_m,
        electrical_period_m: base.electrical_period_m,
    }
}

/// Net axial (x) Lorentz force on a SINGLE mover magnet [N], fixed excitation.
///
/// The magnet at `magnet_index` (0-based, alternating ±Z polarisation) sits
/// with its CENTRE at `magnet_x_m` (track coordinates); the coils carry the
/// fixed per-coil currents `coil_currents_a` (aligned with `coils`). The
/// force is the Newton's-third-law reaction of the coil Lorentz integral
/// `F = I·Σ(dL×B)` evaluated against a single-magnet assembly — the exact
/// per-magnet decomposition of the existing `ForceEvaluator` model (the
/// field superposition is linear), reusing `magnetic::coil_model` +
/// `physics` rather than any new field solver.
fn single_magnet_force_x_n(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    coil_currents_a: &[f64],
    magnet_index: usize,
    magnet_x_m: f64,
) -> f64 {
    let y_center = config.board_width_m / 2.0;
    let z_center = config.air_gap_m + config.magnet_dims_m[2] / 2.0;
    let pol_z = config.magnet_remanence_t * if magnet_index % 2 == 0 { 1.0 } else { -1.0 };
    let magnet = physics::make_cuboid_magnet(
        [magnet_x_m, y_center, z_center],
        UnitQuaternion::identity(),
        [0.0, 0.0, pol_z],
        config.magnet_dims_m,
    );
    let assembly = physics::make_source_assembly(vec![magnet]);
    let coil_model = CoilCurrentModel::new(SOLVE_MESHING, false, 0.0);

    let mut force_x = 0.0_f64;
    for (coil, &current) in coils.iter().zip(coil_currents_a.iter()) {
        if current == 0.0 {
            continue;
        }
        let samples = coil_model.build_phase_samples(coil);
        let points: Vec<nalgebra::Point3<f64>> = samples
            .iter()
            .map(|s| nalgebra::Point3::new(s.midpoint_3d[0], s.midpoint_3d[1], s.midpoint_3d[2]))
            .collect();
        let b_fields = physics::compute_b_batch_parallel(&assembly, &points);
        for (sample, b) in samples.iter().zip(b_fields.iter()) {
            let dl = nalgebra::Vector3::new(sample.dl_3d[0], sample.dl_3d[1], sample.dl_3d[2]);
            // F_segment = I · (dL × B); accumulate the stator-side x force.
            force_x += dl.cross(b).x * current;
        }
    }
    // Newton's third law: the force on the magnet is the reaction.
    -force_x
}

/// Net axial (x) Lorentz force on the WHOLE mover array [N], fixed
/// excitation (full-array assembly at `mover_position_m`, the magnet-0
/// track position). Used for the stability classification of the
/// single-magnet zeros: a rigid-mover rest needs a restoring (negative)
/// total-force slope.
fn total_mover_force_x_n(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    coil_currents_a: &[f64],
    mover_position_m: f64,
) -> f64 {
    let assembly = MagnetArray::new(config).build_assembly(mover_position_m);
    let coil_model = CoilCurrentModel::new(SOLVE_MESHING, false, 0.0);
    let mut force_x = 0.0_f64;
    for (coil, &current) in coils.iter().zip(coil_currents_a.iter()) {
        if current == 0.0 {
            continue;
        }
        let samples = coil_model.build_phase_samples(coil);
        let points: Vec<nalgebra::Point3<f64>> = samples
            .iter()
            .map(|s| nalgebra::Point3::new(s.midpoint_3d[0], s.midpoint_3d[1], s.midpoint_3d[2]))
            .collect();
        let b_fields = physics::compute_b_batch_parallel(&assembly, &points);
        for (sample, b) in samples.iter().zip(b_fields.iter()) {
            let dl = nalgebra::Vector3::new(sample.dl_3d[0], sample.dl_3d[1], sample.dl_3d[2]);
            force_x += dl.cross(b).x * current;
        }
    }
    -force_x
}

/// Solve the resting position of the FIRST or LAST magnet [m] (track
/// coordinates of that magnet's centre) under the fixed `charge` excitation,
/// by finding the zero of the end magnet's force-vs-position curve.
///
/// Bracketing: the END magnet's position is scanned over the window where it
/// settles against its FIRST/LAST band triplet — the outermost side included,
/// since the equilibrium may sit up to half an electrical period of the
/// triplet away:
///
/// - [`EndMagnet::First`]: `[copper_start − P_e/2, copper_start + P_e]`,
///   leftmost stable zero — the first magnet settled against the first
///   triplet from the left (the MIN endpoint's rest).
/// - [`EndMagnet::Last`]: `[copper_end − P_e, copper_end + P_e/2]`,
///   rightmost stable zero — the last magnet settled against the last
///   triplet from the right (the MAX endpoint's rest).
///
/// The scan uses [`SCAN_SAMPLES`] uniform samples; every sign change is
/// bisected to [`REST_TOLERANCE_M`] (deterministic bisection, no Newton step
/// needed at this tolerance). Each zero is classified by the RIGID MOVER's
/// total-force slope (central difference, [`SLOPE_STEP_M`]): only a
/// restoring (negative-slope) zero is a stable rest of the mover.
///
/// The RAW rest may sit outside the copper-bounded design limits (the flush
/// clamp) — [`travel_envelope_charge_based`] clamps the derived endpoints
/// into them.
///
/// Returns `None` when no stable zero exists in the window (no coils,
/// non-positive pole pitch, empty charge state, degenerate scan).
#[must_use]
pub fn solve_end_magnet_rest_m(
    config: &SimulationInput,
    coils: &[PhaseCoil],
    charge: &[PhaseCharge],
    end: EndMagnet,
    copper_region_start_m: f64,
    copper_region_end_m: f64,
) -> Option<f64> {
    if coils.is_empty() || charge.is_empty() {
        return None;
    }
    let tau_p = config.pole_pitch_m();
    if !(tau_p > 0.0) {
        return None;
    }
    let period = 2.0 * tau_p;
    let n = config.magnet_count as usize;
    if n == 0 {
        return None;
    }

    // Per-coil currents: match each coil's phase label to the charge state
    // (layer copies share the phase); unmatched coils stay de-energized.
    let peak = config.max_current_a;
    let coil_currents: Vec<f64> = coils
        .iter()
        .map(|coil| {
            charge
                .iter()
                .find(|c| c.label == coil.phase_name)
                .map_or(0.0, |c| c.charge * peak)
        })
        .collect();

    let (window_lo, window_hi) = match end {
        EndMagnet::First => (
            copper_region_start_m - period / 2.0,
            copper_region_start_m + period,
        ),
        EndMagnet::Last => (
            copper_region_end_m - period,
            copper_region_end_m + period / 2.0,
        ),
    };

    // Magnet-index → mover-position conversion for the stability probe.
    let end_index = match end {
        EndMagnet::First => 0_usize,
        EndMagnet::Last => n - 1,
    };
    let mover_position_of =
        |end_magnet_x: f64| end_magnet_x - end_index as f64 * tau_p;

    let force =
        |x: f64| single_magnet_force_x_n(config, coils, &coil_currents, end_index, x);

    // Bracketing scan over the settle window.
    let step = (window_hi - window_lo) / (SCAN_SAMPLES - 1) as f64;
    let mut zeros: Vec<f64> = Vec::new();
    let mut prev_x = window_lo;
    let mut prev_f = force(prev_x);
    for i in 1..SCAN_SAMPLES {
        let x = window_lo + i as f64 * step;
        let f = force(x);
        if prev_f == 0.0 {
            zeros.push(prev_x);
        } else if prev_f * f < 0.0 {
            // Deterministic bisection to REST_TOLERANCE_M.
            let (mut lo, mut hi) = (prev_x, x);
            let mut f_lo = prev_f;
            while hi - lo > REST_TOLERANCE_M {
                let mid = 0.5 * (lo + hi);
                let f_mid = force(mid);
                if f_mid == 0.0 {
                    lo = mid;
                    hi = mid;
                    break;
                }
                if f_lo * f_mid < 0.0 {
                    hi = mid;
                } else {
                    lo = mid;
                    f_lo = f_mid;
                }
            }
            zeros.push(0.5 * (lo + hi));
        }
        prev_x = x;
        prev_f = f;
    }
    if prev_f == 0.0 {
        zeros.push(prev_x);
    }

    // Stability classification via the rigid mover's total-force slope.
    let stable = |x: f64| -> bool {
        let mover = mover_position_of(x);
        let f_minus =
            total_mover_force_x_n(config, coils, &coil_currents, mover - SLOPE_STEP_M);
        let f_plus =
            total_mover_force_x_n(config, coils, &coil_currents, mover + SLOPE_STEP_M);
        (f_plus - f_minus) / (2.0 * SLOPE_STEP_M) < 0.0
    };

    match end {
        EndMagnet::First => zeros
            .into_iter()
            .filter(|&z| stable(z))
            .min_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)),
        EndMagnet::Last => zeros
            .into_iter()
            .filter(|&z| stable(z))
            .max_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const MM: f64 = 0.001;

    /// `v.mod_pos()` in `[0, m)` for `m > 0`.
    fn mod_pos(v: f64, m: f64) -> f64 {
        let r = v % m;
        if r < 0.0 {
            r + m
        } else {
            r
        }
    }

    /// The desktop reference build the travel-envelope pins mirror
    /// (kata ab30): N = 12, P_e = 12 mm (τ_p = 6 mm), copper [0, 147] mm,
    /// 3 phases, 1:1 spacing, 4.5 mm magnet travel width (fill 0.75).
    fn reference_config() -> SimulationInput {
        SimulationInput {
            magnet_dims_m: [4.5 * MM, 10.0 * MM, 4.0 * MM],
            magnet_count: 12,
            magnet_pitch_m: 6.0 * MM,
            active_area_length_m: 147.0 * MM,
            ..SimulationInput::default()
        }
    }

    /// Full-span 3-phase serpentine for `cfg` (mirrors the force_eval test
    /// fixture): active legs every phase-band pitch, phase `p` in slots
    /// ≡ p (mod phases), consecutive same-phase legs alternating direction
    /// (+Y / −Y — the coil-model convention) so all legs of a phase
    /// contribute coherently. Routing geometry is MILLIMETRES (converted
    /// inside `CoilCurrentModel`).
    fn serpentine_coils(cfg: &SimulationInput) -> Vec<PhaseCoil> {
        use pcbmotorgen_routing::CoilSegment;
        let band_mm = cfg.phase_band_pitch_m() * 1e3;
        let width_mm = cfg.board_width_m * 1e3;
        let n_slots = ((cfg.active_area_length_m * 1e3 / band_mm).floor()) as usize;
        let phases = cfg.phases as usize;
        (0..phases)
            .map(|p| {
                let mut segments = Vec::new();
                let legs: Vec<usize> = ((p)..n_slots).step_by(phases).collect();
                for (k, &slot) in legs.iter().enumerate() {
                    let x = slot as f64 * band_mm;
                    let (y0, y1) = if k % 2 == 0 {
                        (0.0, width_mm)
                    } else {
                        (width_mm, 0.0)
                    };
                    segments.push(CoilSegment {
                        start: (x, y0),
                        end: (x, y1),
                        is_active: true,
                    });
                    if let Some(&next) = legs.get(k + 1) {
                        segments.push(CoilSegment {
                            start: (x, y1),
                            end: (next as f64 * band_mm, y1),
                            is_active: false,
                        });
                    }
                }
                PhaseCoil {
                    phase_idx: p as u32,
                    layer_idx: 0,
                    segments,
                    corner_arcs: vec![],
                    phase_name: PHASE_NAMES[p].to_string(),
                    pattern_id: "serpentine-test".to_string(),
                    layer_pair: None,
                    center_via_positions: vec![],
                }
            })
            .collect()
    }

    fn charge_of(labels: &[&str], charges: &[f64]) -> Vec<PhaseCharge> {
        labels
            .iter()
            .zip(charges.iter())
            .map(|(l, &c)| PhaseCharge {
                label: (*l).to_string(),
                charge: c,
            })
            .collect()
    }

    // ------------------------------------------------------------------
    // Charge states
    // ------------------------------------------------------------------

    /// Analytic first-triplet charge state on the reference fixture:
    /// A fully charged, B/C at the layout offsets (60° per the crate's
    /// per-coil offset law): (1, 0.5, −0.5). The LAST triplet is ordered
    /// B, C, A spatially (73 slots: the last A band is the last slot), so
    /// anchoring on A's LAST band gives (1, −0.5, 0.5).
    #[test]
    fn reference_charge_states_match_the_offset_law() {
        let cfg = reference_config();
        let first = band_charge_state(&cfg, EndMagnet::First, 0.0, 147.0 * MM)
            .expect("first-band charge state");
        assert_eq!(
            first.iter().map(|c| c.label.as_str()).collect::<Vec<_>>(),
            ["A", "B", "C"]
        );
        assert!((first[0].charge - 1.0).abs() < 1e-12);
        assert!((first[1].charge - 0.5).abs() < 1e-12);
        assert!((first[2].charge + 0.5).abs() < 1e-12);

        let last = band_charge_state(&cfg, EndMagnet::Last, 0.0, 147.0 * MM)
            .expect("last-band charge state");
        assert!((last[0].charge - 1.0).abs() < 1e-12, "A still the reference");
        assert!((last[1].charge + 0.5).abs() < 1e-12);
        assert!((last[2].charge - 0.5).abs() < 1e-12);
    }

    /// Declared bands (kata hzs2 path) at the ideal positions reproduce the
    /// analytic charge state; a shifted declaration changes it (engagement).
    #[test]
    fn declared_bands_reproduce_analytic_and_engage_shifts() {
        use crate::params::PhaseBandPosition;
        let cfg = reference_config();
        let tau_band = cfg.phase_band_pitch_m();
        let mut declared = cfg.clone();
        declared.phase_bands = (0..3)
            .map(|p| PhaseBandPosition {
                phase: PHASE_NAMES[p].to_string(),
                centerline_m: (p as f64 + 0.5) * tau_band,
                start_m: p as f64 * tau_band,
                end_m: (p as f64 + 1.0) * tau_band,
            })
            .collect();
        let analytic =
            band_charge_state(&cfg, EndMagnet::First, 0.0, 147.0 * MM).expect("analytic");
        let declared_state =
            band_charge_state(&declared, EndMagnet::First, 0.0, 147.0 * MM).expect("declared");
        for (a, d) in analytic.iter().zip(declared_state.iter()) {
            assert_eq!(a.label, d.label);
            assert!((a.charge - d.charge).abs() < 1e-12, "declared parity broken");
        }

        // Shift B's first centerline by 1 mm → its charge must move.
        let mut shifted = declared.clone();
        shifted.phase_bands[1].centerline_m += 1.0 * MM;
        let shifted_state =
            band_charge_state(&shifted, EndMagnet::First, 0.0, 147.0 * MM).expect("shifted");
        assert!(
            (shifted_state[1].charge - declared_state[1].charge).abs() > 1e-6,
            "shifted declaration had no effect"
        );
    }

    /// End-band anchoring (requester symmetry fix): the MAX state anchors on
    /// the phase owning the SPATIALLY LAST band — the mirror of the min
    /// state's spatially-first anchoring. On the 73-slot reference fixture
    /// phase A owns both edge bands, so the Last state is unchanged
    /// (1, −0.5, 0.5); on a 72-slot layout (L = 144 mm) the last slot is
    /// phase C, and the old reference-phase anchoring produced (1, 0.5, −0.5)
    /// — the min state verbatim, 4 mm off the edge — where the mirrored
    /// edge-anchored state is (−0.5, 0.5, 1).
    #[test]
    fn last_state_anchors_on_the_spatially_last_band() {
        let cfg = SimulationInput {
            magnet_dims_m: [4.5 * MM, 10.0 * MM, 4.0 * MM],
            magnet_count: 12,
            magnet_pitch_m: 6.0 * MM,
            active_area_length_m: 144.0 * MM,
            ..SimulationInput::default()
        };
        let last = band_charge_state(&cfg, EndMagnet::Last, 0.0, 144.0 * MM).expect("last");
        assert!((last[0].charge + 0.5).abs() < 1e-12, "A {}", last[0].charge);
        assert!((last[1].charge - 0.5).abs() < 1e-12, "B {}", last[1].charge);
        assert!((last[2].charge - 1.0).abs() < 1e-12, "C owns the edge band");
    }

    /// Coil-derived endpoint states (the production path): on fixtures whose
    /// leg layout matches the analytic slot model they reproduce
    /// [`band_charge_state`] exactly; on the laid-out infinity braid — whose
    /// last active leg belongs to phase C (A ends at 136.6 mm, B at
    /// 138.6 mm, C at 140.6 mm against a 147 mm track) — the max state
    /// re-anchors onto C, giving the requester's mirrored charges
    /// (A −0.5, B +0.5, C +1) and pushing the max endpoint outward.
    #[test]
    fn coil_derived_states_reanchor_the_max_endpoint() {
        use crate::equilibrium::travel_envelope_over_slots;
        use pcbmotorgen_routing::{generate_coils_from_context, RoutingContext};

        // Parity with the analytic model on the reference fixture.
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        for end in [EndMagnet::First, EndMagnet::Last] {
            let from_coils = band_charge_state_from_coils(&cfg, &coils, end).expect("coils");
            let analytic = band_charge_state(&cfg, end, 0.0, 147.0 * MM).expect("analytic");
            for (c, a) in from_coils.iter().zip(analytic.iter()) {
                assert_eq!(c.label, a.label);
                assert!(
                    (c.charge - a.charge).abs() < 1e-12,
                    "{end:?}: coil-derived {} vs analytic {}",
                    c.charge,
                    a.charge
                );
            }
        }

        // The laid-out braid: C owns the last active leg → mirrored max state.
        let ctx = RoutingContext {
            active_area_length_mm: 147.0,
            board_width_mm: 20.0,
            num_layers: 4,
            phases: 3,
            min_trace_mm: 0.127,
            trace_width_mm: 0.127,
            min_space_mm: 0.127,
            expects_continuous: false,
            params: Default::default(),
            magnet_pitch_mm: Some(6.0),
            magnet_array_span_mm: Some(72.0),
            phase_clearance_mm: None,
        };
        let braid = generate_coils_from_context(&ctx, "infinity-braid");
        let first = band_charge_state_from_coils(&cfg, &braid, EndMagnet::First).expect("first");
        assert!((first[0].charge - 1.0).abs() < 1e-12);
        assert!((first[1].charge - 0.5).abs() < 1e-12);
        assert!((first[2].charge + 0.5).abs() < 1e-12);
        let last = band_charge_state_from_coils(&cfg, &braid, EndMagnet::Last).expect("last");
        assert!((last[0].charge + 0.5).abs() < 1e-9, "A {}", last[0].charge);
        assert!((last[1].charge - 0.5).abs() < 1e-9, "B {}", last[1].charge);
        assert!((last[2].charge - 1.0).abs() < 1e-9, "C owns the braid's edge band");

        // The re-anchored max state pushes the max endpoint outward (toward
        // the copper end) versus the old reference-phase anchor.
        let config_only = band_charge_state(&cfg, EndMagnet::Last, 0.0, 147.0 * MM).expect("cfg");
        let rest_new = solve_end_magnet_rest_m(
            &cfg, &braid, &last, EndMagnet::Last, 0.0, 147.0 * MM,
        )
        .expect("edge-anchored rest");
        let rest_old = solve_end_magnet_rest_m(
            &cfg, &braid, &config_only, EndMagnet::Last, 0.0, 147.0 * MM,
        )
        .expect("old-anchor rest");
        assert!(
            rest_new > rest_old,
            "edge-anchored rest {:.3} mm not outward of {:.3} mm",
            rest_new / MM,
            rest_old / MM
        );

        // The composed envelope keeps the flush-clamp discipline.
        let env = travel_envelope_charge_based(&cfg, &braid, 0.0, 147.0 * MM);
        let base = travel_envelope_over_slots(12.0 * MM, 12, 0.0, 147.0 * MM);
        assert!(env.min_position_m >= base.min_position_m - 1e-9);
        assert!(env.max_position_m <= base.max_position_m + 1e-9);
        assert!(env.max_position_m > env.min_position_m);
    }

    /// The Clarke angle of the crate's baseline excitation (1, 0, −1) is the
    /// pinned π/6 — the analytic reference reproduces the crate's own
    /// lattice pin (and the skill reference's worked example: P_e = 12 mm
    /// → 1.0 mm).
    #[test]
    fn baseline_charge_angle_is_the_pinned_pi_over_six() {
        let theta = charge_state_electrical_angle(&[1.0, 0.0, -1.0]).expect("baseline angle");
        assert!((theta - super::super::baseline_electrical_angle()).abs() < 1e-12);
        let lattice = mod_pos(theta * 12.0 * MM / (2.0 * PI), 12.0 * MM);
        assert!((lattice - 1.0 * MM).abs() < 1e-12);
    }

    // ------------------------------------------------------------------
    // Acceptance 1 (kata k5r5): the solved rest matches the analytic
    // expectation for a symmetric charge state — checked as the
    // holding-force LATTICE invariants (the closed form of the equilibrium
    // structure), since the discrete-leg model's zero positions carry a
    // documented sub-pitch layout phase the pure Clarke lattice cannot
    // express.
    // ------------------------------------------------------------------

    /// Lattice invariant: under the symmetric baseline charge state
    /// (1, 0, −1) an INTERIOR magnet's solved rest repeats with EXACTLY the
    /// electrical period — the force at rest ± P_e (and + 2·P_e) vanishes
    /// against the profile amplitude. This is the closed-form structure of
    /// the holding-force equilibrium: x ≡ rest (mod P_e). (The END magnet's
    /// own rest is edge-shifted by the truncated copper — the recurrence is
    /// an interior property, which is exactly why the end magnets need a
    /// dedicated solve.)
    #[test]
    fn solved_rest_repeats_with_exactly_the_electrical_period() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let baseline = charge_of(&["A", "B", "C"], &[1.0, 0.0, -1.0]);
        let peak = cfg.max_current_a;
        let currents: Vec<f64> = coils
            .iter()
            .map(|coil| {
                baseline
                    .iter()
                    .find(|c| c.label == coil.phase_name)
                    .map_or(0.0, |c| c.charge * peak)
            })
            .collect();
        let period = 2.0 * cfg.pole_pitch_m();
        // Interior magnet 5: solve its rest by bisection in the periodic
        // interior, then verify the lattice recurrence around it.
        let k = 5_usize;
        let force = |x: f64| single_magnet_force_x_n(&cfg, &coils, &currents, k, x);
        let centre = 5.0 * cfg.pole_pitch_m() + 8.0 * MM; // interior lattice region
        let (lo, hi) = (centre - period / 2.0, centre + period / 2.0);
        let mut solved = None;
        let mut prev_x = lo;
        let mut prev_f = force(lo);
        for i in 1..=64 {
            let x = lo + (hi - lo) * i as f64 / 64.0;
            let f = force(x);
            if prev_f * f < 0.0 {
                let (mut a, mut b) = (prev_x, x);
                let mut fa = prev_f;
                while b - a > REST_TOLERANCE_M {
                    let m = 0.5 * (a + b);
                    let fm = force(m);
                    if fa * fm < 0.0 {
                        b = m;
                    } else {
                        a = m;
                        fa = fm;
                    }
                }
                solved = Some(0.5 * (a + b));
                break;
            }
            prev_x = x;
            prev_f = f;
        }
        let rest = solved.expect("interior magnet must have a stable-class force zero");
        // Amplitude scale: force at a quarter period off the rest.
        let scale = force(rest + period / 4.0).abs().max(1e-12);
        for k in [1_usize, 2] {
            let f = force(rest + k as f64 * period);
            eprintln!("[lattice] F(rest + {k}·P_e) = {f:+.3e} N (amplitude {scale:.3e} N)");
            assert!(
                f.abs() < 1e-3 * scale,
                "lattice recurrence broken at +{k}·P_e: |F| = {:.3e} vs amplitude {:.3e}",
                f.abs(),
                scale
            );
        }
    }

    /// Physical anchoring: the solved first-magnet rest under the FIRST-band
    /// charge state lies within half an electrical period of the FIRST band
    /// triplet — the magnet settles against the bands whose charge state
    /// fixes it (the kata's core claim).
    #[test]
    fn solved_first_magnet_rest_settles_against_the_first_band_triplet() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let q = band_charge_state(&cfg, EndMagnet::First, 0.0, 147.0 * MM).expect("charge");
        let rest = solve_end_magnet_rest_m(&cfg, &coils, &q, EndMagnet::First, 0.0, 147.0 * MM)
            .expect("first-band rest must exist");
        let tau_p = cfg.pole_pitch_m();
        let triplet_end = 3.0 * cfg.phase_band_pitch_m(); // first triplet [0, τ_p]
        let distance = if rest < 0.0 {
            -rest
        } else if rest > triplet_end {
            rest - triplet_end
        } else {
            0.0
        };
        eprintln!(
            "[anchor] first-band rest = {:.6} mm, first triplet [0, {:.3}] mm, distance {:.6} mm (bound P_e/2 = {:.3} mm)",
            rest / MM,
            triplet_end / MM,
            distance / MM,
            tau_p / MM
        );
        assert!(
            distance <= tau_p,
            "first-magnet rest {:.6} mm not anchored to the first triplet",
            rest / MM
        );
    }

    // ------------------------------------------------------------------
    // Acceptance 2: endpoint symmetry under the reversed charge state —
    // the solved rest under q → −q sits P_e/2 away (the two zero classes
    // of the holding-force lattice swap).
    // ------------------------------------------------------------------

    #[test]
    fn reversed_charge_state_shifts_solved_rest_by_half_period() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let q = band_charge_state(&cfg, EndMagnet::First, 0.0, 147.0 * MM).expect("charge");
        let q_rev: Vec<PhaseCharge> = q
            .iter()
            .map(|c| PhaseCharge {
                label: c.label.clone(),
                charge: -c.charge,
            })
            .collect();
        let rest = solve_end_magnet_rest_m(&cfg, &coils, &q, EndMagnet::First, 0.0, 147.0 * MM)
            .expect("rest");
        let rest_rev =
            solve_end_magnet_rest_m(&cfg, &coils, &q_rev, EndMagnet::First, 0.0, 147.0 * MM)
                .expect("reversed rest");
        let shift = mod_pos(rest - rest_rev, 12.0 * MM);
        eprintln!(
            "[reversal] rest(q) = {:.6} mm, rest(−q) = {:.6} mm, shift = {:.6} mm (expect P_e/2 = 6.0)",
            rest / MM,
            rest_rev / MM,
            shift / MM
        );
        // Tolerance 0.25 mm: the END-magnet rests sit in the edge-distorted
        // copper window, which shifts the two zero classes slightly
        // asymmetrically (measured 6.158 mm vs the exact 6.0).
        assert!(
            (shift - 6.0 * MM).abs() < 0.25 * MM,
            "reversed-charge shift {:.6} mm vs P_e/2 = 6 mm",
            shift / MM
        );
    }

    // ------------------------------------------------------------------
    // Acceptance 3: the 1:1-spacing rigid-body property — solving an
    // INTERIOR magnet independently puts it on the same equilibrium lattice
    // (one pitch per index), and the total mover force at the solved rest
    // is far smaller than a single magnet's force scale.
    // ------------------------------------------------------------------

    #[test]
    fn interior_magnets_follow_the_rigid_pitch_relation() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let q = band_charge_state(&cfg, EndMagnet::First, 0.0, 147.0 * MM).expect("charge");
        let peak = cfg.max_current_a;
        let coil_currents: Vec<f64> = coils
            .iter()
            .map(|coil| {
                q.iter()
                    .find(|c| c.label == coil.phase_name)
                    .map_or(0.0, |c| c.charge * peak)
            })
            .collect();

        let rest0 = solve_end_magnet_rest_m(
            &cfg, &coils, &q, EndMagnet::First, 0.0, 147.0 * MM,
        )
        .expect("first-magnet rest");
        let tau_p = cfg.pole_pitch_m();

        // Independently bisect interior magnets 4 and 5's force zeros and
        // verify the 1:1 rigid pitch between them (both live in the
        // periodic interior, free of the end-magnet edge shift).
        let solve_interior = |k: usize, near: f64| -> f64 {
            let force = |x: f64| single_magnet_force_x_n(&cfg, &coils, &coil_currents, k, x);
            let (lo, hi) = (near - tau_p, near + tau_p);
            let mut prev_x = lo;
            let mut prev_f = force(lo);
            for i in 1..=96 {
                let x = lo + (hi - lo) * i as f64 / 96.0;
                let f = force(x);
                if prev_f * f < 0.0 {
                    let (mut a, mut b) = (prev_x, x);
                    let mut fa = prev_f;
                    while b - a > REST_TOLERANCE_M {
                        let m = 0.5 * (a + b);
                        let fm = force(m);
                        if fa * fm < 0.0 {
                            b = m;
                        } else {
                            a = m;
                            fa = fm;
                        }
                    }
                    return 0.5 * (a + b);
                }
                prev_x = x;
                prev_f = f;
            }
            panic!("interior magnet {k} has no force zero near {:.3} mm", near / MM);
        };
        let rest4 = solve_interior(4, rest0 + 4.0 * tau_p);
        let rest5 = solve_interior(5, rest0 + 5.0 * tau_p);
        eprintln!(
            "[rigid] rest0 = {:.6} mm (edge), rest4 = {:.6} mm, rest5 = {:.6} mm, rest5 − rest4 = {:.6} mm (τ_p = {:.3} mm)",
            rest0 / MM,
            rest4 / MM,
            rest5 / MM,
            (rest5 - rest4) / MM,
            tau_p / MM
        );
        assert!(
            (rest5 - rest4 - tau_p).abs() < 0.02 * MM,
            "interior pitch relation broken: {:.6} mm vs τ_p = {:.6} mm",
            (rest5 - rest4) / MM,
            tau_p / MM
        );

        // Total mover force at the interior-lattice rest ≈ 0 against the
        // single-magnet force scale (edge effects keep it from vanishing
        // exactly): place magnet 5 on its solved rest and evaluate the
        // whole-array force.
        let mover_at_lattice = rest5 - 5.0 * tau_p;
        let total = total_mover_force_x_n(&cfg, &coils, &coil_currents, mover_at_lattice);
        // Amplitude scale of one magnet's force profile (quarter period off
        // the rest), not the near-zero force at the rest itself.
        let single_scale =
            single_magnet_force_x_n(&cfg, &coils, &coil_currents, 5, rest5 + tau_p / 2.0)
                .abs()
                .max(1e-12);
        eprintln!(
            "[rigid] |F_total| at the interior lattice = {:.3e} N (single-magnet scale {:.3e} N)",
            total.abs(),
            single_scale
        );
        assert!(
            total.abs() < 0.5 * single_scale,
            "total force at the interior lattice not rigid-body consistent"
        );
    }

    // ------------------------------------------------------------------
    // Reference-fixture endpoints + acceptance 4 (clamp discipline)
    // ------------------------------------------------------------------

    /// Reference-fixture endpoint pins (kata k5r5, measured on the
    /// serpentine fixture): the first-band charge state (1, 0.5, −0.5)
    /// settles the first magnet at ≈ −2.893 mm (against the first triplet
    /// from the left — OUTSIDE the copper-bounded design limit; the edge
    /// -truncated copper shifts the rest ~0.1 mm off the interior lattice)
    /// → raw min array centre ≈ 30.107 mm; the last-band charge state
    /// (1, −0.5, 0.5) settles the last magnet at ≈ 147.02 mm (against the
    /// last triplet from the right — also outside) → raw max ≈ 114.02 mm.
    #[test]
    fn reference_fixture_raw_endpoints_pin() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let (raw_min, raw_max) =
            charge_based_endpoints_m(&cfg, &coils, 0.0, 147.0 * MM).expect("raw endpoints");
        eprintln!(
            "[raw] min centre = {:.6} mm, max centre = {:.6} mm",
            raw_min / MM,
            raw_max / MM
        );
        assert!((raw_min - 30.107 * MM).abs() < 0.05 * MM, "raw min {raw_min}");
        assert!((raw_max - 114.020 * MM).abs() < 0.05 * MM, "raw max {raw_max}");
    }

    /// Refined envelope (acceptance 4): the raw charge endpoints clamp
    /// INTO the geometric flush limits [36, 111] mm — on the reference
    /// fixture BOTH raw rests overhang the design limits, so the refined
    /// envelope EQUALS the flush clamp [36, 111] mm: the authority's
    /// reference output is unchanged by the charge refinement (no desktop
    /// pin churn). rest phase (10 mm) and period (12 mm) unchanged.
    #[test]
    fn reference_refined_envelope_equals_the_flush_clamp() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let env = travel_envelope_charge_based(&cfg, &coils, 0.0, 147.0 * MM);
        assert!((env.min_position_m - 36.0 * MM).abs() < 1e-9);
        assert!((env.max_position_m - 111.0 * MM).abs() < 1e-9);
        assert!((env.rest_phase_m - 10.0 * MM).abs() < 1e-12);
        assert!((env.electrical_period_m - 12.0 * MM).abs() < 1e-12);
    }

    /// Clamp discipline (acceptance 4, general): the refined endpoints
    /// always lie WITHIN the geometric flush limits — the refinement only
    /// pulls inward. Swept over several geometries.
    #[test]
    fn refined_endpoints_stay_within_the_flush_limits() {
        for (n, p_e, len) in [
            (12_u32, 12.0, 147.0),
            (10, 24.0, 195.0),
            (6, 12.0, 147.0),
            (12, 18.0, 147.0),
        ] {
            let cfg = SimulationInput {
                magnet_dims_m: [4.5 * MM, 10.0 * MM, 4.0 * MM],
                magnet_count: n,
                magnet_pitch_m: p_e / 2.0 * MM,
                active_area_length_m: len * MM,
                ..SimulationInput::default()
            };
            let coils = serpentine_coils(&cfg);
            let base = super::super::travel_envelope_over_slots(p_e * MM, n, 0.0, len * MM);
            let env = travel_envelope_charge_based(&cfg, &coils, 0.0, len * MM);
            assert!(
                env.min_position_m >= base.min_position_m - 1e-9,
                "N={n} P_e={p_e}: refined min below the flush limit"
            );
            assert!(
                env.max_position_m <= base.max_position_m + 1e-9,
                "N={n} P_e={p_e}: refined max above the flush limit"
            );
            assert!(env.max_position_m >= env.min_position_m, "refined inverted");
        }
    }

    /// Fallbacks: no coils / non-3-phase configs / degenerate copper return
    /// the flush-clamp envelope unchanged (the documented fallback), and
    /// the raw endpoints return None.
    #[test]
    fn refinement_falls_back_to_the_flush_clamp() {
        let cfg = reference_config();
        let coils = serpentine_coils(&cfg);
        let base = super::super::travel_envelope_over_slots(12.0 * MM, 12, 0.0, 147.0 * MM);

        // No coils: no force model → flush clamp unchanged.
        let env = travel_envelope_charge_based(&cfg, &[], 0.0, 147.0 * MM);
        assert_eq!(env, base);
        assert!(charge_based_endpoints_m(&cfg, &[], 0.0, 147.0 * MM).is_none());

        // Degenerate copper (shorter than the span): refinement meaningless.
        let degenerate_base =
            super::super::travel_envelope_over_slots(12.0 * MM, 12, 0.0, 10.0 * MM);
        let env = travel_envelope_charge_based(&cfg, &coils, 0.0, 10.0 * MM);
        assert_eq!(env, degenerate_base);
    }
}
