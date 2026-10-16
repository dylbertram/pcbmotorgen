# pcbmotorgen-simulation API

**Status:** Active (SI-unit physics core, workspace version 0.5.0)
**Owner:** `crates/pcbmotorgen-simulation` — analytical magnetic B-field,
Lorentz-force thrust / torque, force ripple, PCB stackup, power budget, friction
budget, and vertical height stack.
**Canonical reference:** this document is the primary API contract for the
simulation crate. Deferred features / known issues / wishes live in
[`PLAN.md`](../PLAN.md).

---

## 1. Overview and scope

`pcbmotorgen-simulation` implements the physics and multiphysics estimators for
a **coreless linear PCB motor with a flying mover**. The mover carriage (magnet
array) slides along the `+x` travel axis over a stationary PCB stator; the
3-phase winding in the PCB is energised by a commutation strategy to maximise
continuous thrust.

The crate is **parent-free**: it does not depend on the monolithic `pcbmotorgen`
app crate or on `pcbmotorgen-export`. It depends on:

| Dependency | Role |
| --- | --- |
| `pcbmotorgen-routing` | Coil geometry — `PhaseCoil`, `CoilSegment`, `CoilArc`, `PHASE_NAMES` (re-exported at the crate root). |
| `magba` (0.6.2) | Analytical closed-form B-field of cuboid magnets (Magpylib formulas). |
| `nalgebra` | Vectors / points / quaternions for the Lorentz and torque loops. |
| `rayon` | Point-parallel B-field sampling and position-parallel force sweeps. |
| `serde` / `serde_json` | Serialization of `SimulationInput` and all result DTOs. |

### Module map

| Module | Purpose |
| --- | --- |
| `units` | SI conversion helpers, physical constants, copper-weight presets. |
| `magnet_grades` | NdFeB grade → remanence lookup (N35…N52, suffix-tolerant). |
| `params` | `SimulationInput` (input + validation + derived geometry) and shared result DTOs. |
| `physics` | Thin adapter over `magba` — B-field and source-assembly construction. |
| `magnetic::magnet_model` | `MagnetArray` — the plain alternating array and B-field sampling. |
| `magnetic::coil_model` | `CoilCurrentModel` — geometry → sampled conductor sub-segments. |
| `magnetic::force_eval` | `ForceEvaluator`, `CommutationMode`, `ForceResult`. |
| `stackup` | `HeightStackCalculator`, `PowerEstimator`, `FrictionEstimator`. |
| `equilibrium` | Mover equilibrium rest positions + travel envelope (Clarke baseline). |
| `equilibrium::charge` | Charge-based travel endpoints (kata k5r5) — first/last magnet equilibrium under the phase-band charge state. |

### Re-exported routing types

The crate re-exports the coil presentation types it consumes (owned by
`pcbmotorgen-routing`) so consumers only need this crate:

```rust
pub use pcbmotorgen_routing::{CoilArc, CoilSegment, PhaseCoil, PHASE_NAMES};
```

---

## 2. Units and coordinate conventions

| Quantity | Convention |
| --- | --- |
| Units | **SI**: metres (`m`), Tesla (`T`), Amperes (`A`), Ohms (`Ω`), Watts (`W`). |
| X axis | Travel axis (stator length). |
| Y axis | Across board width, perpendicular to travel. |
| Z axis | Vertical (magnet axis); `z = 0` = PCB top surface. |
| B-field frame | Lab frame: `Bx` = along travel, `By` = across board, `Bz` = vertical. |
| Routing boundary | `pcbmotorgen-routing` geometry is in millimetres; conversion to metres happens inside `CoilCurrentModel` before the physics call. |

Use the [`units`](#15-units-module) helpers (`mm`, `mils_to_m`, `oz_to_m`) when
buildings inputs by hand — never write a bare millimetre number as metres.

---

## 3. Input contract: `SimulationInput`

`SimulationInput` (`crate::params::SimulationInput`) is the full set of inputs,
all in SI units. `active_area_length_m` is the **primary input**; `travel` is
derived as `active_area_length − the magnet array span`.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulationInput {
    // Magnet parameters
    pub magnet_dims_m: [f64; 3],        // (width_travel, width_cross, height) [m]
    pub magnet_count: u32,              // ≥ 2; odd and even counts supported
    pub magnet_pitch_m: f64,            // centre-to-centre spacing = pole pitch [m]
    pub magnet_remanence_t: f64,        // Br at 20 °C [T]

    // Geometry
    pub active_area_length_m: f64,      // PRIMARY INPUT — stator copper length [m]
    pub board_width_m: f64,             // across-travel PCB dimension [m]
    pub pcb_thickness_m: f64,           // substrate thickness [m]
    pub air_gap_m: f64,                 // magnet face → copper clearance [m]
    pub strands_per_phase: u32,         // parallel strands (serpentine paths) per phase
                                        // (default 1)

    // Coil
    pub phases: u32,
    pub spacing_ratio: f64,             // 1.0 = standard 1:1; 0.8 = 4:5 Vernier

    // Drive electronics
    pub max_current_a: f64,             // peak phase current [A]
    pub supply_voltage_v: f64,

    // DFM rules
    pub min_trace_m: f64,
    pub min_space_m: f64,
    pub min_via_drill_m: f64,
    pub min_via_annular_ring_m: f64,
    pub max_layers: u32,                // even, ≥ 2
    pub num_layers: u32,                // UI-selected layers (serde default 4)
    pub drive_frequency_hz: f64,
    pub max_temperature_rise_c: f64,

    // Force / motion targets
    pub target_force_n: f64,            // minimum continuous thrust [N]
    pub peak_force_n: f64,              // burst thrust target [N] (≥ target_force_n)
    pub friction_n: f64,                // estimated total mechanical friction [N]
    pub carriage_mass_kg: f64,
    pub max_accel_m_s2: f64,
    pub capacitor_bank_uf: f64,         // burst capacitor bank [µF]

    // Declared phase bands (kata hzs2, serde default = empty)
    pub phase_bands: Vec<PhaseBandPosition>, // per-(layer, net) band records [m]
}
```

### 3.1 Construction and validation

```rust
SimulationInput::default()               // reasonable defaults (10×12×4 mm magnets, 3-phase, …)
SimulationInput::new(self) -> Result<Self, SimulationError>  // validate-then-return
SimulationInput::validate(&self) -> Result<(), SimulationError>
```

Validation rejects (first error wins): non-positive or non-3-tuple magnet dims,
`magnet_count < 2`, non-positive pitch or negative `pitch − width`,
`remanence ∉ (0, 2.5]`, `phases < 1`, `spacing_ratio ∉ (0, 2]`, non-positive
current / voltage / trace / space / via sizes, negative air gap, odd or < 2
layer counts, `num_layers > max_layers`, non-positive drive /
temperature / active-length / board-width bounds, `active_area_length ≤ the
magnet array span` (zero travel), `strands_per_phase < 1` or
footprint violation, and the force / mass / accel / capacitor targets.

### 3.2 Serde defaults

- `num_layers` defaults to **4** when absent.
- `strands_per_phase` defaults to **1** when absent (historical single-strand).
- `phase_bands` defaults to **empty** when absent (kata hzs2): the analytic
  commutation offsets and the caller's copper region remain the fallback.

### 3.3 Derived-geometry accessors

| Method | Value |
| --- | --- |
| `magnet_array_span_m()` | `(magnet_count − 1) × magnet_pitch + magnet_width` — physical outer-edge span [m] |
| `travel_m()` | `active_area_length − magnet array span` [m] |
| `active_length_m()` | `active_area_length_m` [m] |
| `pole_pitch_m()` | `magnet_pitch_m` [m] |
| `phase_band_pitch_m()` | `(pole_pitch / phases) × spacing_ratio` [m] |
| `rest_offset_m()` | vernier rest offset, clamped `[0, pole_pitch]` [m] |
| `magnet_gap_m()` | `magnet_pitch − magnet_width` — inter-magnet gap along the travel axis, distinct from the motor air gap `air_gap_m` [m] |
| `min_via_pad_m()` | `via_drill + 2 × annular_ring` [m] |
| `acceleration_force_n()` | `carriage_mass × max_accel` [N] |
| `minimum_drive_force_n()` | `friction × SAFETY_MARGIN` (1.3) [N] |

### 3.4 Enums

```rust
#[serde(rename_all = "snake_case")]
pub enum BearingType { PlasticChannel, PtfeLined, BallBearing }
// PtfeLined (PTFE, Teflon-lined) bearing surface.
```

The magnet array is **always** the plain alternating arrangement (Halbach and
back-iron variants were removed from the product scope), so there is no
`MagnetArrangement` enum and no `back_iron_thickness_m` field.

### 3.5 Error type

```rust
#[derive(Debug, Clone, PartialEq)]
pub struct SimulationError(pub String);   // Display + std::error::Error
```

---

## 4. Magnet array: `MagnetArray`

`crate::magnetic::MagnetArray<'a>` builds and manages the magnet source
assembly. The mover always uses the **plain alternating** arrangement:
`magnet_count` Z-polarised cuboids alternating `±Br` along `z`, spaced
`magnet_pitch_m` apart. (Halbach interleaves and method-of-images back-iron
copies were removed from the product scope to simplify the app and simulation.)

### 4.1 Public methods

```rust
MagnetArray::new(config: &SimulationInput) -> Self

build_assembly(&self, mover_position_m: f64) -> physics::MagbaSourceAssembly
magnet_z_center_m(&self) -> f64
magnet_x_centers_m(&self, mover_position_m: f64) -> Vec<f64>
polarizations_t(&self) -> Vec<[f64; 3]>                 // main-magnet ±Z [T]

bfield_at_pcb_surface(&self, x_sample: &[f64], mover_position_m: f64,
                      z_observer: f64) -> Vec<[f64; 3]>  // B [T] at (x, y_center, z)
bfield_grid(&self, x_sample: &[f64], z_sample: &[f64],
            mover_position_m: f64) -> Vec<BFieldSample2D>
```

`bfield_grid` returns one [`BFieldSample2D`](#41-bfield-sample-dto) per
`(x, z)` pair, **row-major with Z as the slow axis**:
`samples[i_z * n_x + i_x]`; total length `x_sample.len() × z_sample.len()`.
Samples sit at `y = board_width_m / 2` (board centre-line).

### 4.2 B-field sample DTO

```rust
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BFieldSample2D {
    pub x: f64,     // observer X [m]
    pub z: f64,     // observer Z [m]
    pub bx: f64,    // B along travel [T]
    pub by: f64,    // B across board [T]
    pub bz: f64,    // B vertical [T]
}
```

The IPC DTO (`BFieldSampleIpc`) adds a precomputed `mag_t = sqrt(bx²+by²+bz²)`
for the renderer; the crate DTO keeps the raw components.

---

## 5. Coil current model: `CoilCurrentModel`

`crate::magnetic::coil_model::CoilCurrentModel` converts `PhaseCoil` objects
(routing crate, millimetres) into sampled conductor sub-segments (metres) for
Lorentz integration.

```rust
pub const DEFAULT_MESHING: usize = 20;

pub struct CoilCurrentModel {
    pub meshing: usize,           // sub-segments per conductor (default 20)
    pub include_end_turns: bool,  // default false
    pub layer_z_m: f64,           // conductor-plane Z [m], 0 = PCB top
}

impl Default for CoilCurrentModel { ... }   // (20, false, 0.0)

impl CoilCurrentModel {
    pub fn new(meshing: usize, include_end_turns: bool, layer_z_m: f64) -> Self; // panics if meshing < 1
    pub fn build_phase_samples(&self, coil: &PhaseCoil) -> Vec<ConductorSample>;
    pub fn build_all_phases_samples<'a>(&self, coils: &'a [PhaseCoil],
        currents_a: &[f64]) -> Vec<(&'a PhaseCoil, f64, Vec<ConductorSample>)>; // panics on length mismatch
    pub fn bfield_at_conductor_midpoints(&self, coil: &PhaseCoil,
        b_at: impl Fn(&[[f64; 3]]) -> Vec<[f64; 3]>) -> Vec<[f64; 3]>;
}
```

```rust
#[derive(Debug, Clone, Copy)]
pub struct ConductorSample {
    pub midpoint_3d: [f64; 3],   // sub-segment midpoint [m]
    pub dl_3d: [f64; 3],         // direction × length — the dL in dL×B [m]
}
```

Only **active** segments produce force (end-turns excluded by default — their
net X thrust cancels and they roughly double cost). The serpentine vertex
ordering encodes alternating current direction: even-indexed conductors run
`(x,0)→(x,W)` (+Y), odd-indexed run `(x,W)→(x,0)` (−Y).

---

## 6. Force evaluation: `ForceEvaluator`, `CommutationMode`, `ForceResult`

`crate::magnetic::force_eval::ForceEvaluator` computes the mover thrust/torque
as a function of mover position.

### 6.1 Physical model

```text
F = I · Σ(dLᵢ × Bᵢ)          member (mover) forces
τ = Σ(rᵢ × Fᵢ)
```

`Bᵢ` is sampled at each sub-segment midpoint via the `physics` adapter (magba),
point-parallel over rayon. **Newton's third law:** `magpy.getFT`-style integrals
yield the force on the stationary coils; all returned values are **mover**
forces (`F_mover = −F_stator`).

### 6.2 Evaluator

```rust
pub struct ForceEvaluator {
    pub n_positions: usize,              // sweep size (default 50)
    pub meshing: usize,                  // sub-segment density (default 20)
    pub commutation: CommutationMode,    // default MaxThrust
    pub layer_z_m: f64,                  // conductor-plane Z [m] (default 0)
    // phase_shift + calibrated are private (set by the self-calibration guard)
}

impl Default for ForceEvaluator { ... }

impl ForceEvaluator {
    pub fn new(n_positions: usize, meshing: usize,
               commutation: CommutationMode, layer_z_m: f64) -> Self;
        // panics if n_positions < 2 or meshing < 1

    pub fn evaluate(&mut self, config: &SimulationInput,
                    coils: &[PhaseCoil]) -> Result<ForceResult, SimulationError>;
        // position sweep over [rest, travel + rest]; parallel; runs self-calibration once

    pub fn evaluate_at(&mut self, config: &SimulationInput, coils: &[PhaseCoil],
                       mover_position_m: f64) -> Result<([f64; 3], [f64; 3]), SimulationError>;
        // single position → (F_mover [N], T_mover [N·m]) as [f64; 3] each

    pub fn electrical_angle(config: &SimulationInput, mover_position_m: f64) -> f64;
        // 2π·x / (2·τ_p) — one electrical cycle per two pole pitches
}
```

### 6.3 Self-calibration guard (FOC spec §4.3)

On first `evaluate` / `evaluate_at`, the evaluator runs a **3-point polarity +
alignment check** at `{0.1, 0.6, 1.1} × τ_p`. It accepts the polarity state
(`phase_shift = 0`, falling back to `phase_shift = π`) that yields
`F_mover.x ≥ 0` at all three test points; if neither does, it returns
`Err(SimulationError)` (FOC formula misconfiguration: sin vs cos, wrong
per-coil offset).

### 6.4 Commutation (FOC, `id = 0`)

```rust
#[serde(rename_all = "snake_case")]
pub enum CommutationMode {
    MaxThrust,    // sinusoidal FOC drive maximizing thrust (default);
                  // wire value "max_thrust" (renamed from "max_torque")
    PhaseAOnly,   // only Phase A at peak current; B, C = 0
}
```

`MaxThrust` implements the glossary-normative FOC law with the **pinned
d-axis convention** (product-owner approved): **`id = 0`, pure q-axis**.
Coreless motors have no saliency, so `id = 0` is the standard
maximum-thrust-per-ampere choice; the glossary's 90-degree rule (stator
field orthogonal — 90° electrical — to the mover field) is realized by
q-axis current only.

**Derivation chain** (90° rule → per-coil law):

1. **d-axis pinned along the mover field**: the alternating array has
   `B_z` peaking at the magnet centre, so the d-axis frame is
   `x ≡ 0 (mod τ_p)` with the mover-field phasor along d and
   `θ_e = π·x/τ_p = 2π·x/(2τ_p)`.
2. **q-axis alignment**: pure q-axis drive puts each coil's current in
   phase with its local `B_z` (`B_z ∝ cos(π(x−p)/τ_p)`), which maximizes
   the Lorentz thrust per ampere — the 90° rule expressed in the field
   frame.
3. **General per-coil offset law** (glossary): a coil displaced Δx
   spatially carries an electrical phase shift `π·Δx/τ_p`; adjacent coils
   are one phase-band pitch apart (`Δx = τ_band = r·τ_p/phases`), giving
   the per-coil offset `π·τ_band/τ_p` (60° for the default 3-phase 1:1
   layout).

```text
θ_e        = 2π·x / (2τ_p) + phase_shift      (phase_shift ∈ {0, π}: polarity)
I_p(x)     = I_pk · cos(θ_e − p · phase_offset)
phase_off  = π · τ_band / τ_p                 (τ_band = phase-band pitch)
```

For the default 3-phase config `phase_offset = π/3` (60°), giving
`(I_A, I_B, I_C) = (1, 0.5, −0.5)` at `x = 0` — the coils are 60° apart,
not 120°; the 3-phase sum is `+1.0`, which is correct. The 4:5 Vernier
(`spacing_ratio = 0.8`) gives `phase_offset = 0.8·π/3`.

Whether the per-phase current is `sin` or `cos` of θ_e is a reference-frame
(d-axis alignment) convention, not a physics difference. The glossary's
classic balanced 120° law `I_p = I_pk·sin(θ_e − p·2π/3)` is the special
case for coils spaced `2τ_p/3` (`phase_offset = 2π/3`) viewed from a frame
rotated 90° electrical from the one pinned here; those currents sum to zero
at every θ_e (pinned by `test_balanced_120deg_law_special_case`). The
implemented alignment is empirically pinned as thrust-optimal (pure
q-axis) by `test_foc_thrust_peaks_at_zero_phase_tilt`: sweeping a phase
tilt δ over [−90°, +90°] through the real force sweep, the mean thrust
peaks at δ = 0 and is symmetric about it.

**Declared phase bands (kata hzs2).** When `SimulationInput.phase_bands`
carries the routing contract's resolved band records, each coil slot is
matched to a band **by phase label** and runs the general per-coil offset
law read from the laid-out geometry:

```text
offset_p = π · (x_p − x_ref) / τ_p     (declared band centerlines)
```

with `x_ref` the first coil slot's band centerline. This generalizes the
uniform analytic offset (coil slots for one phase split across layers share
the same offset, and non-uniform layouts get their real positions). The
analytic `p·π·τ_band/τ_p` law remains the fallback whenever no bands are
declared, any coil slot is unmatched, or the pole pitch is unknown — on the
reference fixture (ideal `τ_band = τ_p/phases` layout) the two paths are
exactly equal (`test_declared_bands_match_analytic_on_reference_fixture`,
plus the evaluator-level parity pin
`test_declared_phase_bands_parity_and_engagement`).

### 6.5 `ForceResult`

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForceResult {
    pub positions_m: Vec<f64>,       // mover positions [m]
    pub force_x_n: Vec<f64>,         // thrust [N] (mover)
    pub force_y_n: Vec<f64>,         // lateral [N]
    pub force_z_n: Vec<f64>,         // normal / magnet-attraction [N]
    pub per_phase_force_x: Vec<f64>, // flat n_positions × n_phases [N]
    pub n_phases: usize,
    pub commutation: CommutationMode,
    pub current_a: f64,              // applied peak current [A]
}

impl ForceResult {
    pub fn mean_thrust_n(&self) -> f64;
    pub fn peak_thrust_n(&self) -> f64;
    pub fn min_thrust_n(&self) -> f64;
    pub fn ripple_pct(&self) -> f64;  // (F_max − F_min) / |F_mean| × 100
    pub fn n_positions(&self) -> usize;
}
```

---

## 7. Physics adapter: `physics`

`crate::physics` is the single place direct `magba` calls live, insulating all
upstream modules from magba API breaks.

### 7.1 magba ↔ Magpylib mapping

| Magpylib (Python) | magba (Rust) | Wrapper |
| --- | --- | --- |
| `magpy.magnet.Cuboid(polarization, position, dimension)` | `CuboidMagnet::new(pos, quat, pol, dim)` | `make_cuboid_magnet` |
| `magpy.Collection(*magnets)` | `SourceAssembly::new(...)` / `sources!` | `make_source_assembly` |
| `magpy.getB(collection, observers)` | `Source::compute_B_batch(&assembly, &points)` | `compute_b_batch(_parallel)` |
| `magpy.current.Polyline(current, vertices)` | `PathCurrent::new(pos, quat, current, vertices)` | `make_path_current` |
| `magpy.getFT(magnets, polylines)` | **native** Lorentz loop `F = I·Σ(dL×B)` | `ForceEvaluator` |

### 7.2 Public items

```rust
pub use magba::collections::SourceAssembly as MagbaSourceAssembly;
pub use magba::currents::PathCurrent as MagbaPathCurrent;
pub use magba::magnets::CuboidMagnet as MagbaCuboidMagnet;

make_cuboid_magnet(pos: [f64; 3], orientation: UnitQuaternion<f64>,
                   polarization: [f64; 3], dimensions: [f64; 3]) -> CuboidMagnet;
make_path_current(pos: [f64; 3], orientation: UnitQuaternion<f64>, current: f64,
                  vertices: Vec<[f64; 3]>) -> PathCurrent;
make_source_assembly(magnets: Vec<CuboidMagnet>) -> SourceAssembly;
compute_b_at(source: &impl Source<f64>, point: Point3<f64>) -> Vector3<f64>;
compute_b_batch(source: &impl Source<f64>, points: &[Point3<f64>]) -> Vec<Vector3<f64>>;
compute_b_batch_parallel(source: &(impl Source<f64> + Sync), points: &[Point3<f64>])
    -> Vec<Vector3<f64>>;                 // point-parallel rayon (preferred)
point3(arr: [f64; 3]) -> Point3<f64>;
points3(arr: &[[f64; 3]]) -> Vec<Point3<f64>>;
```

---

## 8. Stackup / power / friction / height

### 8.1 `HeightStackCalculator`

```rust
pub struct HeightStackCalculator {
    pub outer_copper_oz: f64,   // default 1.0
    pub tolerance_m: f64,       // default 3e-4 (assembly/adhesive fillet)
}

impl HeightStackCalculator {
    pub fn calculate(&self, config: &SimulationInput) -> HeightStackResult;
    pub fn fits_in_budget(&self, config: &SimulationInput, budget_m: f64) -> bool;
    pub fn headroom_m(&self, config: &SimulationInput, budget_m: f64) -> f64;
    pub fn max_air_gap_for_budget(&self, config: &SimulationInput, budget_m: f64) -> f64;
    pub fn field_sensitivity_per_mm(config: &SimulationInput) -> f64;  // −π/τ_p × 1e-3
    pub fn field_at_gap(config: &SimulationInput, air_gap_m: f64) -> f64;
        // Bz ≈ (4/π)·Br·(1 − exp(−π·tm/τ))·exp(−π·h/τ)
}
```

### 8.2 `PowerEstimator`

```rust
pub struct PowerEstimator {
    pub layers_per_phase: Option<u32>,   // default None (derived from stackup, else 2)
}

impl PowerEstimator {
    pub fn estimate(&self, config: &SimulationInput,
                    stackup: Option<&StackupResult>) -> PowerBudget;
}
```

Trace length is a conservative analytical estimate
(`2 × board_width × 2 × magnet_count`); DC resistance via
`ρ/(w·t)`; `R_thermal = 15 °C/W`; burst 0.1 s with 10% voltage droop for
capacitor sizing; efficiency at `0.10 m/s` rated velocity.

The **continuous (thermal) chain is RMS-referenced**, per the glossary
("Thermal Resistance & Power Dissipation"): `P_loss = I_rms² · R_phase`
with `I_rms = I_peak/√2` for sinusoidal drive (`max_current_a` is the PEAK
phase current). This feeds `continuous_power_w`, `temperature_rise_c`
(= `P_loss · R_thermal`), and the efficiency chain
(`p_elec = V_supply · I_rms` at the rated operating point).

The **burst / capacitor-sizing chain stays PEAK-referenced**: the burst is
a short transient (0.1 s) at full instantaneous current, so
`burst_power_w = phases · i_burst² · R_phase` and `capacitor_required_uf`
use `i_burst = I_peak · peak_force_n/target_force_n` (peak, guarded for
`target_force_n ≤ 0`).

### 8.3 `FrictionEstimator`

```rust
pub fn mu_bearing(bt: BearingType) -> f64;   // PlasticChannel 0.25, PtfeLined 0.12, BallBearing 0.003

pub struct FrictionEstimator {
    pub bearing_type: BearingType,
    pub ffc_conductor_count: u32,   // default 26
    pub has_wiper_contact: bool,    // default false
    pub normal_force_n: f64,        // default 0.0
    pub cogging_n: f64,             // default 0.0
}

impl FrictionEstimator {
    pub fn estimate(&self) -> FrictionBudget;                       // FFC drag = 0.020 N/conductor, wiper = 0.055 N
    pub fn estimate_for_config(&self, config: &SimulationInput) -> FrictionBudget; // split config.friction_n
    pub fn from_config(bearing_type: BearingType,
                       ffc_conductor_count: u32, has_wiper_contact: bool) -> Self;
        // normal force always 0 (no back-iron pull-in in the current scope)
}
```

---

## 9. Result DTOs

All DTOs are `#[derive(Debug, Clone, Serialize, Deserialize)]`.

### 9.1 `StackupResult` + `HeightStackResult`

```rust
pub struct StackupResult {
    pub layer_count: u32,
    pub trace_widths_m: Vec<f64>,     // per layer [m]
    pub cu_thickness_m: Vec<f64>,     // per layer [m]
    pub via_drill_m: f64,
    pub via_annular_ring_m: f64,
    pub via_grid_rows: u32,
    pub via_grid_cols: u32,
    pub estimated_force_n: f64,
    pub estimated_dc_resistance_ohm: f64,
    pub notes: Vec<String>,           // serde default []
}

impl StackupResult {
    pub fn validate(&self) -> Result<(), SimulationError>;
    pub fn outer_layer_ids(&self) -> (usize, usize);         // (0, layer_count − 1)
    pub fn inner_layer_ids(&self) -> Vec<usize>;             // 1 .. layer_count − 1
    pub fn via_pad_m(&self) -> f64;                          // drill + 2 × annular
    pub fn via_grid_count(&self) -> u32;                     // rows × cols
    pub fn summary(&self) -> String;
}

pub struct HeightStackResult {
    pub pcb_thickness_m: f64,
    pub cu_protrusion_m: f64,
    pub solder_mask_m: f64,      // 20 µm nominal
    pub air_gap_m: f64,
    pub magnet_height_m: f64,
    pub tolerance_m: f64,
}

impl HeightStackResult {
    pub fn total_height_m(&self) -> f64;               // sum of all layers
    pub fn fits_in_budget(&self, budget_m: f64) -> bool;
    pub fn headroom_m(&self, budget_m: f64) -> f64;    // negative = over budget
    pub fn summary(&self) -> String;
}
```

### 9.2 `PowerBudget` + `FrictionBudget`

```rust
pub struct PowerBudget {
    pub phase_resistance_ohm: f64,
    pub continuous_power_w: f64,
    pub burst_power_w: f64,
    pub temperature_rise_c: f64,
    pub capacitor_required_uf: f64,
    pub efficiency_pct: f64,
}
impl PowerBudget { pub fn summary(&self) -> String; }

pub struct FrictionBudget {
    pub bearing_friction_n: f64,
    pub cable_drag_n: f64,
    pub wiper_contact_n: f64,   // serde default 0
    pub cogging_n: f64,         // serde default 0
}
impl FrictionBudget {
    pub fn total_n(&self) -> f64;
    pub fn minimum_drive_force_n(&self) -> f64;   // total × SAFETY_MARGIN (1.3)
    pub fn summary(&self) -> String;
}
```

---

## 10. Magnet grades: `magnet_grades`

```rust
pub const CUSTOM_GRADE: &str = "Custom";
pub const MAGNET_GRADES: &[(&str, f64, f64, f64)];  // (name, br_min, br_typ, br_max) T
// N35 1.17/1.19/1.21 · N38 1.21/1.23/1.25 · N42 1.28/1.30/1.32
// N44 1.32/1.34/1.36 · N48 1.38/1.40/1.42 · N52 1.43/1.45/1.48

pub struct MagnetGrade { pub name: String, pub br_min_t: f64, pub br_typ_t: f64, pub br_max_t: f64 }

pub fn grade_names() -> Vec<&'static str>;
pub fn get_remanence(grade: &str) -> Option<f64>;   // handles suffixes: "N44H" → N44
pub fn get_grade(grade: &str) -> Option<MagnetGrade>; // same suffix tolerance
```

---

## 10b. Mover equilibrium: `equilibrium`

Stable rest positions of the mover array centre under the fixed balanced
baseline excitation (`I_A = +I`, `I_B = 0`, `I_C = −I`). The Clarke transform
gives θe = π/6, i.e. an N-pole field peak at `x_peak = P_e/12` inside each
electrical cycle; alternating poles (τ_p = P_e/2) lock onto successive peaks,
so every stable rest centre satisfies `x ≡ φ (mod P_e)` with
`φ = (x_peak + ((N−1)/2)·τ_p) mod P_e`.

```rust
pub struct TravelEnvelope {
    pub min_position_m: f64,      // smallest travel limit [m]: leading edge flush with copper start
    pub max_position_m: f64,      // largest travel limit [m] (≥ min): trailing edge flush with copper end
    pub rest_phase_m: f64,        // track-frame lattice phase (copper_region_start + φ) mod P_e
    pub electrical_period_m: f64, // P_e = 2 × pole pitch (one full 360° electrical cycle)
}

pub fn baseline_electrical_angle() -> f64;                // π/6
pub fn baseline_field_peak_m(electrical_period_m) -> f64; // P_e/12
pub fn rest_phase_m(electrical_period_m, magnet_count) -> f64;
pub fn travel_envelope_over_slots(electrical_period_m, magnet_count,
                                  copper_region_start_m,
                                  copper_region_end_m) -> TravelEnvelope;

// Declared phase bands (kata hzs2) — copper region from the bands' extents.
pub fn copper_region_from_phase_bands(bands: &[PhaseBandPosition])
    -> Option<(f64, f64)>;
pub fn travel_envelope_from_phase_bands(electrical_period_m, magnet_count,
                                        bands: &[PhaseBandPosition])
    -> Option<TravelEnvelope>;
```

The envelope endpoints are the glossary-normative SPAN-AWARE FLUSH LIMITS
of the copper active area (kata 5c7r, 2026-09-02; supersedes the xb16
rest-snapped revisions after field verification):

- **Span-aware flush clamp**: `centre ∈ [copper_region_start + span/2,
  copper_region_end − span/2]` with the glossary "Mover Span"
  `span = N · τ_p` (τ_p = P_e/2). At the lower limit the array's leading
  edge sits exactly on the copper start; at the upper limit the trailing
  edge sits exactly on the copper end. The swept range equals the
  configured free travel (`travel = copper_length − span`) EXACTLY, and
  the endpoints DEPEND on N.
- **The endpoints are MECHANICAL LIMITS, not stable rest positions**: the
  stable rests remain on the `x ≡ φ (mod P_e)` lattice (reported via
  `rest_phase_m`) and are marked by the holding-force chart zeros; the
  slider may hold position between rests (a closed-loop drive compensates
  the non-zero fixed-excitation force there). History: the endpoints were
  rest-snapped under kata xb16 — inward snapping lost up to `2·P_e` of
  travel (36% at the app defaults); nearest snapping left the array
  overhanging the copper start at min and short of the copper end at max
  (field-observed as "a bit short on the max and a bit too far on the
  min"). The flush clamp realizes the configured travel with zero
  overhang, verified with the screenshot tooling (kata 8tc4).
- Defaults (N = 12, P_e = 12 mm, copper region [0, 147] mm in track
  coords): span = 72 mm → **36 → 111 mm** — strip 0–72 mm at min,
  75–147 mm at max, a 75 mm sweep = the configured travel exactly
  (N = 4 gives 12 → 135 mm on the same copper and period).
- Degenerate (copper shorter than the span): the clamp inverts, so `max`
  clamps to `min`; the envelope never inverts, but the array necessarily
  overhangs the copper at that single position.
- `rest_phase_m` is the TRACK-FRAME phase `(copper_region_start + φ) mod P_e`
  (= 10 mm for the defaults), so holding-force zero markers align to the
  stable rests.
- Declared phase bands (kata hzs2): when the routing contract carries
  resolved band records, `copper_region_from_phase_bands` unions their
  along-travel extents into the copper region and
  `travel_envelope_from_phase_bands` applies the same flush clamp to it.
  Both return `None` when no bands are declared — callers keep their
  analytic copper arguments.

Exposed to the desktop UI as the `travel_envelope` command
(`TravelEnvelopeIpc`) — composed with §10c's charge-based refinement, so the
UI envelope is the refined (charge-based, flush-clamped) endpoints.

## 10c. Charge-based travel endpoints: `equilibrium::charge` (kata k5r5)

The ELECTROMAGNETIC refinement of §10b's endpoints: the true min/max mover
position derives from the charge within the first and last phase bands of
each phase. Each end's charge state is the MIRROR of the other's (requester
symmetry observation): the min state anchors on the phase owning the
SPATIALLY FIRST band (fully charged, remaining phases at their
commutation-model offsets), and the max state anchors on the phase owning
the SPATIALLY LAST band the same way — the two owners coincide only when the
layout's end permutation puts the reference phase last (e.g. the 73-slot
reference fixture, whose last slot is phase A). With 1:1 spacing only the
two end magnets need solving (rigid mover, interior magnets follow at fixed
pitch — pinned by test).

```rust
pub enum EndMagnet { First, Last }

pub struct PhaseCharge { pub label: String, pub charge: f64 }  // normalized, peak = 1

// Charge state of the first/last phase-band triplet (declared bands when
// present — hzs2 discipline — analytic slot-model fallback otherwise).
// Both ends anchor on the phase owning the relevant track EDGE band.
pub fn band_charge_state(config: &SimulationInput, end: EndMagnet,
                         copper_region_start_m: f64, copper_region_end_m: f64)
    -> Option<Vec<PhaseCharge>>;

// AUTHORITATIVE endpoint states, derived from the generated coil geometry:
// the end-band anchors come from the coils' first/last active-segment x
// positions, reflecting the LAID-OUT end permutation (the declared-band
// records carry only each phase's FIRST-instance centerline, so they cannot
// express the end bands). Reproduces band_charge_state exactly on
// analytic-layout fixtures; re-anchors on laid-out patterns whose edge band
// differs (e.g. the infinity braid, whose last active leg is phase C —
// giving the mirrored max charges (−0.5, 0.5, 1)).
pub fn band_charge_state_from_coils(config: &SimulationInput, coils: &[PhaseCoil],
                                    end: EndMagnet)
    -> Option<Vec<PhaseCharge>>;

// Clarke electrical angle [rad] of a 3-phase charge state, (−π, π] — the
// analytic reference (baseline (1, 0, −1) → π/6, the P_e/12 lattice pin).
pub fn charge_state_electrical_angle(charge: &[f64]) -> Option<f64>;

// THE SOLVE: stable rest of the end magnet [m] (track coords of its centre)
// under the fixed charge excitation — zero of the end magnet's force curve
// (single-magnet assembly, the exact per-magnet decomposition of the
// ForceEvaluator model), deterministic grid bracketing + bisection to
// REST_TOLERANCE_M = 1e-9 m; zeros classified by the rigid mover's
// total-force slope (restoring = stable). First: window
// [copper_start − P_e/2, copper_start + P_e], leftmost stable zero;
// Last: [copper_end − P_e, copper_end + P_e/2], rightmost stable zero.
pub fn solve_end_magnet_rest_m(config: &SimulationInput, coils: &[PhaseCoil],
                               charge: &[PhaseCharge], end: EndMagnet,
                               copper_region_start_m: f64, copper_region_end_m: f64)
    -> Option<f64>;

// RAW endpoints (array centre) from both end solves (coil-derived charge
// states, config-only fallback). May sit outside the design limits; None
// when either solve is undefined.
pub fn charge_based_endpoints_m(config: &SimulationInput, coils: &[PhaseCoil],
                                copper_region_start_m: f64, copper_region_end_m: f64)
    -> Option<(f64, f64)>;

// Refined envelope: the raw endpoints CLAMPED INTO the span-aware flush
// limits of travel_envelope_over_slots — the geometric clamp is the
// documented mechanical LIMIT (the refinement only pulls endpoints inward)
// and the FALLBACK (no coils / non-3-phase / degenerate copper → the flush
// envelope unchanged). rest_phase_m / electrical_period_m unchanged.
pub fn travel_envelope_charge_based(config: &SimulationInput, coils: &[PhaseCoil],
                                    copper_region_start_m: f64, copper_region_end_m: f64)
    -> TravelEnvelope;
```

Measured reference-fixture behaviour (N = 12, P_e = 12 mm, copper [0, 147] mm,
serpentine fixture — its leg layout matches the analytic slot model, so the
coil-derived states reproduce the analytic ones): the first-band charge state
`(1, 0.5, −0.5)` settles the first magnet at ≈ −2.89 mm and the last-band
state `(1, −0.5, 0.5)` the last magnet at ≈ +147.02 mm — BOTH raw rests
overhang the copper-bounded design limits (raw endpoints ≈ [30.11, 114.02] mm
array centre), so the refined envelope EQUALS the flush clamp **[36, 111] mm**:
the authority's reference output is unchanged by the refinement (no desktop
pin churn; kata ab30 pins stay valid). On laid-out patterns the rests can
land inside the limits and the refinement pulls the endpoints inward — on
the desktop's default infinity-braid build the last active leg belongs to
phase C (A ends ≈ 136.6 mm, B ≈ 138.6 mm, C ≈ 140.6 mm), so the max state
re-anchors onto C (charges (−0.5, 0.5, 1) — the min state mirrored) and the
measured refined envelope is **[36, 107.97] mm**. The pinned invariants:
interior zero recurrence at exactly P_e, reversed-charge half-period (P_e/2)
symmetry, and the interior rigid pitch τ_p. Residual end-offset asymmetry
(first vs last magnet rest relative to the copper ends) on non-mirror-closed
layouts is geometric — edge-band distances, the end permutation, and the
end-magnet polarity (an even magnet count puts a −Z magnet at the max end,
shifting its rest by up to half an electrical period) — not a charge-state
defect. The requester's "120° offset" phrasing is the classic balanced-law
convention (glossary "Commutation"); the solver consumes whatever offsets
the commutation model declares (60° for the default 3-phase 1:1 layout —
the general per-coil offset law).

## 11. Re-exports

```rust
pub use pcbmotorgen_simulation::{
    phase_bands_from_routing, BearingType, BFieldSample2D, CoilCurrentModel, CommutationMode,
    ConductorSample, FrictionBudget, FrictionEstimator, ForceEvaluator, ForceResult,
    HeightStackCalculator, HeightStackResult, MagnetArray, PhaseBandPosition, PowerBudget,
    PowerEstimator, SimulationError, SimulationInput, StackupResult,
};
pub use pcbmotorgen_simulation::{CoilArc, CoilSegment, PhaseCoil, PHASE_NAMES}; // from routing
```

---

## 12. Commands, tests, and guarantees

Run these from the repository root:

```bash
# Focused simulation tests (all modules + cross-validation vectors)
cargo test -p pcbmotorgen-simulation

# Compile the simulation package without running tests
cargo build -p pcbmotorgen-simulation
cargo check -p pcbmotorgen-simulation

# Check consumers (KiCad/DXF adapter + Tauri app)
cargo check -p pcbmotorgen-export -p pcbmotorgen-simulation

# Full workspace verification
cargo test --workspace
cargo build --workspace
```

The suite covers unit conversion, grade lookup, the validation cascade, serde
defaults, derived geometry, the plain alternating array (counts and polarity),
1D/2D B-field sampling, conductor meshing, Lorentz integration, commutation
(1:1 and 4:5 Vernier offsets, the balanced-120° special case, and the
thrust-vs-tilt 90°-rule optimality sweep), the 3-point FOC guard, ripple
statistics, all stackup
estimators, and Python-oracle cross-validation. `test_vectors.rs` requires
`scripts/fixtures/test_vectors.json` (bundle is present; regenerate with
`scripts/export_test_vectors.py` to refresh).

---

## 13. Field references

- Crate root / re-exports: `src/lib.rs`
- Units: `src/units.rs`
- Magnet grades: `src/magnet_grades.rs`
- Input / validation / derived / DTOs: `src/params/{mod,validation,derived,stackup_result,height_stack_result,power_budget,friction_budget}.rs`
- magba adapter: `src/physics/mod.rs`
- Magnet array: `src/magnetic/magnet_model/`, `src/magnetic/magnet_model/arrangements/`
- Coil model: `src/magnetic/coil_model.rs`
- Force evaluation: `src/magnetic/force_eval/{mod,commutation,force_result}.rs`
- Stackup: `src/stackup/{mod,height_stack,power,friction}.rs`
- Cross-validation: `tests/test_vectors.rs`
- Fixtures: `scripts/fixtures/test_vectors.json`
- Deferred / bugs / wishes: `PLAN.md`
