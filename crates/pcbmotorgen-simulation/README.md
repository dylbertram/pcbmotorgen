# pcbmotorgen-simulation

`pcbmotorgen-simulation` is the Rust crate that performs all physics and
multiphysics simulation for the coreless linear PCB motor: analytical magnetic
B-field, Lorentz-force thrust / torque, force ripple, PCB stackup, power budget,
friction budget, and the vertical height stack. It is **parent-free**: it does
not depend on the monolithic `pcbmotorgen` app crate or on
`pcbmotorgen-export`. It MAY depend on the sibling `pcbmotorgen-routing` crate
for coil geometry (`PhaseCoil` / `CoilSegment`) and on `magba` for the B-field
computation.

**The full API reference is [`docs/API.md`](docs/API.md).** Deferred features,
known issues, and wishes are tracked in [`PLAN.md`](PLAN.md).

## Architecture Decision: Pure Rust (Tauri + Svelte + magba)

### Decision

The library is a **pure Rust** crate. All physics computation — including
analytical magnetic B-field, Lorentz force, and torque — runs natively in Rust.
**No Python runtime or sidecar is required.**

### Rationale

- **magba** (v0.7.2, BSD-3-Clause) is a Rust crate that explicitly implements
  Magpylib's analytical closed-form B-field formulas for cuboid magnets,
  validated against Magpylib itself. It provides `CuboidMagnet`,
  `PathCurrent` (polyline conductors), the `sources!` collection macro, and
  Rayon-parallel `compute_B_batch`.
- **Lorentz force** (`F = I·∫dL×B`) is a trivial ~20-line integration loop in
  Rust using `nalgebra` — sample B along each conductor segment, cross-product,
  sum. No external crate needed.
- **Torque** about a pivot is `τ = Σ(rᵢ × Fᵢ)` — 5 lines of `nalgebra`.
- **cfsem** (v11.2.0, MIT) is available as an optional complement for advanced
  Biot-Savart filament modeling or eddy-current body forces if needed in future
  phases.
- **Zero Python dependency**: No PyInstaller, no JSON-RPC socket overhead, no
  serialization boundary. Single compiled binary (~15 MB). Native Rayon
  multi-threading. (Python _plugin runners_ are supported by the routing layer
  as an optional generator-authoring surface, not a runtime dependency.)

## Scope and ownership

The crate owns:

- the `physics` adapter layer that insulates every upstream module from direct
  `magba` API usage (B-field computation, source assembly, path currents);
- the magnet array (`MagnetArray`): a fixed plain Z-polarised alternating
  arrangement (Halbach and back-iron variants were removed from the product
  scope to simplify the app and simulation);
- the coil current model (`CoilCurrentModel`) — converts `PhaseCoil` geometry
  into sampled conductor sub-segments for Lorentz integration;
- the force evaluator (`ForceEvaluator`): commutation, self-calibration guard,
  force sweep, per-phase forces, and torque;
- the `SimulationInput` contract, its validation cascade, and all derived
  geometry accessors;
- the stackup / power / friction / height estimation modules; and
- the serde-serializable result DTOs (`ForceResult`, `StackupResult`,
  `HeightStackResult`, `PowerBudget`, `FrictionBudget`, `BFieldSample2D`).

It does **not** own:

- coil geometry generation — that lives in `pcbmotorgen-routing`
  (`PhaseCoil`, `CoilSegment`, `CoilArc`, `PHASE_NAMES`, re-exported here);
- KiCad / DXF export — that lives in `pcbmotorgen-export`;
- the UI / IPC orchestration — that lives in the `pcbmotorgen` parent crate.

## Units and coordinate axes

- All internal calculations use **SI units**: metres (`m`), Tesla (`T`),
  Amperes (`A`), Ohms (`Ω`), Watts (`W`).
- Routing geometry arrives in **millimetres** and is converted to metres at the
  `CoilCurrentModel` / physics boundary.
- `x` is the travel axis (stator length); `y` is across the board width; `z` is
  vertical (magnet axis). B-field components are reported in the lab frame:
  `Bx` = along travel, `By` = across board, `Bz` = vertical.
- Use the [`units`](src/units.rs) helpers (`mm`, `mils_to_m`, `oz_to_m`, …) for
  human-readable input.

## Module layout

| Module | Purpose |
| --- | --- |
| `units` | SI conversion helpers and physical constants (`RHO_CU`, `MU_0`, …). |
| `magnet_grades` | NdFeB grade → remanence lookup (N35…N52, suffix-tolerant). |
| `params` | `SimulationInput`, validation, derived geometry, result DTOs. |
| `physics` | Thin adapter over `magba` (B-field, source assembly). |
| `magnetic` | Magnet arrays, coil current model, force evaluator. |
| `stackup` | Height stack, power budget, friction budget. |

## Key equations

```text
Lorentz force:   F = I · Σ(dLᵢ × Bᵢ)           (mover force; Newton's 3rd law)
Torque:          τ = Σ(rᵢ × Fᵢ)                (about the coil origin)
Commutation:     I_p = I_pk · cos(θ_e − p · π·τ_s/τ_p)
Electrical angle θ_e = 2π·x / (2·τ_p) + phase_shift
```

- `dLᵢ` = sub-segment direction-length vector, `Bᵢ` = field at its midpoint.
- `τ_p` = pole pitch, `τ_s` = phase-band pitch, `I_pk` = peak phase current.

## Commands

Run these from the repository root:

```bash
# Focused simulation tests (physics, magnet arrays, stackup, force evaluator)
cargo test -p pcbmotorgen-simulation

# Compile the simulation package without running tests
cargo build -p pcbmotorgen-simulation
cargo check -p pcbmotorgen-simulation

# Check the simulation consumers (KiCad/DXF adapter + app)
cargo check -p pcbmotorgen-export -p pcbmotorgen-simulation

# Full workspace verification
cargo test --workspace
cargo build --workspace
```

## Cross-validation against the Python oracle

`tests/test_vectors.rs` loads `scripts/fixtures/test_vectors.json` (the Python
oracle output) and asserts the Rust core matches within tolerance:

- Config derived values: exact;
- B-field (`Bx`, `By`, `Bz`): ±1% relative or ±1e-6 T absolute;
- Force sweep (`force_x`, `force_y`, `force_z`): ±2% relative or ±0.1 mN
  absolute;
- Ripple percentage: ±0.5 percentage points.

The FOC was corrected (phase-band-pitch offset + cos-FOC + 3-point polarity
guard), so some force aliases in the fixture are regenerated from the Rust
code path; the tests document this explicitly.

## Tests and guarantees

`cargo test -p pcbmotorgen-simulation` covers:

- unit conversion and magnet-grade lookups;
- `SimulationInput` validation cascade and serde defaults (`num_layers = 4`,
  `strands_per_phase = 1` when absent);
- derived-geometry accessors (travel, phase-band pitch, rest offset, via pad, …);
- the plain alternating magnet array (magnet counts, B-field polarity);
- B-field 1D and 2D grid sampling (row-major `BFieldSample2D`);
- conductor meshing, Lorentz force integration, commutation phase laws
  (1:1 and 4:5 Vernier offsets, the balanced-120° special case, and the
  thrust-vs-tilt 90°-rule optimality sweep), the 3-point FOC polarity +
  alignment self-calibration guard, ripple statistics;
- stackup, power, friction, and height estimators;
- Python-oracle cross-validation vectors.

## Extension links

- API reference: [`docs/API.md`](docs/API.md)
- Deferred / bugs / wishes: [`PLAN.md`](PLAN.md)
- Parent workspace: root [`README.md`](../../README.md)
- Coil geometry source: `pcbmotorgen-routing`
- Python oracle fixtures: `scripts/fixtures/test_vectors.json`
