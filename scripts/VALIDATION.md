# Magnetic and branch-current regression tests

Run from the repository root.

Force sweeps use physical outer-edge travel limits. The reported position
is the absolute center of the first magnet. Routed sweeps run from
`copper_start + width / 2` to
`copper_end - (count - 1) * pitch - width / 2`, using the solved
current-carrying copper extent, not the configured board length. A winding
shorter than the magnet group has no full-overlap sweep and returns an error.
Analytic fixtures without routing use the configured active area. The field model and
commutation receive that same coordinate. Vernier phase offsets must not
translate mechanical travel limits. Array span is `(count - 1) * pitch + width`,
not `count * pitch`. Do not crop low-force samples to suppress real fringe
effects. Reference values recorded before this correction need rerunning.

Driver ripple is a 50%-duty RL estimate, not a switched-controller
simulation. The driver thrust check uses mean sweep Kf, not a position-specific
holding force. Neither check independently validates the imported terminal
polarity, FOC phase mapping, or actual PWM modulation scheme.

The ripple estimate now includes winding resistance in that assumed loop:
`Ipp = Vbus/(2Rphase) * tanh(Rphase/(4*f*Ls))`. The old `Vbus/(8*f*Ls)`
limit ignores resistance and can wildly overestimate ripple when `L/R` is
short relative to a PWM period. Tests compare the RL result to independently
marched exponential half-cycles and verify the required-frequency inversion.

## Reported closed-infinity project

`app/desktop/src-tauri/src/commands/fixtures/closed_infinity_pattern.config.json`
is the `versions[0].state.config` object of the supplied `.pmmotor` project. It
contains generated Star/wye copper, not imported CAD: five magnets, three
strands, 0.2 mm traces, 1 oz, 12 V, 1 A, 100 kHz. Reference result:
`ripple_pp_a` ≈ 2.39 A at R ≈ 2.51 Ω. Do not substitute earlier
feasibility-search settings.

```sh
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen closed_infinity_user_project_diagnostics --bin pcbmotorgen -- --ignored --nocapture
```

This reruns all 50 positions at mesh densities 10, 20, 40 and 80, compares their
pointwise forces, prints phase contributions and electrical checks, and
asserts the design still misses its thrust target and ripple allowance.

The five-to-six magnet transition also has a normal backend regression:

```sh
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen closed_infinity_six_magnets_simulates --bin pcbmotorgen
```

Changing magnet count also changes configured winding length. A braid repeat
count sharing a divisor with the strand count splits each phase into several
closed rings. Magnet-aware generation now selects the largest fitting repeat
count coprime to the strand count. Pole pitch is unchanged; the usable copper
span can be shorter than the requested routing domain. Sweeps continue to use
that actual copper span. Connectivity tests cover multiple strand counts and
lengths, and floating closed copper must not acquire invented terminal buses.

## Normal regression suite

The backplane panel also has an explicit **Run periodic reference** action.
It keeps previews/driver analysis unchanged and has no browser mock fallback.
It reports periodic field/pressure and two isolated-sheet DC differential
benchmarks, with no finite-motor bearing load, actual winding inductance,
coverage-weighted impedance or PWM qualification. Native/Python parity includes
four independent resolutions and held-out geometry/material inputs; source,
binary and aggregate hashes are in `scripts/solvers/results/`.

```sh
CARGO_BUILD_JOBS=1 cargo test -p pcbmotorgen-simulation periodic::tests --lib
CARGO_BUILD_JOBS=1 OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_rust_periodic.py \
  --release --work "$SOLVER_OPT/new-native-parity-run"
```

Five native reference tests pass, as do production frontend build and four
browser tests covering explicit/scoped results, no mock fallback, in-flight
staleness and rejected solves. The complete core-suite cargo retry timed out
after its compile queue and partial execution. Running the resulting compiled
test binary directly then passed **177 tests, 2 ignored**, in 359 s; the timeout
is not counted as a passing run. The desktop retry passed **100 tests, 5 ignored**,
including the reference command's fail-closed checks. Host
`cargo check -p pcbmotorgen` passes. Keep heavy linker/3D solver concurrency low.

Details of nonlinear periodic time/motion prototypes and their narrower
qualification limits are in `scripts/solvers/README.md`. They do not validate
actual finite housing drag or replace the application's screening drive model.

```sh
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen-simulation drive:: --lib
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen drv8311_star_reference_passes_all_checks --bin pcbmotorgen
```

The slower explicit 12 V comparison is:

```sh
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen drv8311_compare_five_and_twelve_volts --bin pcbmotorgen -- --ignored --nocapture
```

It asserts that the nine-strand-per-period reference passes at 12 V and does
not pass at 5 V. The seven-strand case is printed for comparison. Current,
speed, trace width, copper weight and allowances are held constant. As with
the five-strand 5 V reference, this is an electrical-model regression, not a
manufacturability guarantee.

The reference uses Star/wye, 0.5 mm traces, 3 oz copper on both layer classes,
5 V, 1.1 A, 200 kHz PWM, 35% ripple allowance and 95% usable bus. The force
constant comes from the real routed-current force evaluator, not a supplied
constant. All driver checks must pass. This is not a DRC or thermal prototype
qualification; the ripple margin is deliberately small.

## Independent field and Lorentz-force calculation

```sh
python3 -m venv .magpy-venv
.magpy-venv/bin/python -m pip install -r scripts/requirements-validation.txt
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen export_magpylib_validation_fixture --bin pcbmotorgen -- --ignored
.magpy-venv/bin/python scripts/validate_magpylib.py
```

The exporter writes an ignored JSON fixture under `app/desktop/src-tauri`.
The exporter records explicit drive settings and resistor graphs. To use the
live copper, terminal picks, depths and drive settings from a saved project:

```sh
PCB_MOTOR_PROJECT_PATH="$PWD/star_4-layer.pmmotor" RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen export_magpylib_validation_fixture --bin pcbmotorgen -- --ignored
.magpy-venv/bin/python scripts/validate_magpylib.py
```

`PCB_MOTOR_VERSION_INDEX` selects a zero-based version, default 0. Soft magnetic
backplanes are rejected by this free-space exporter. Use FEMM for material
checks. The standalone force command now rejects missing drive settings rather
than silently selecting default copper. Its caller must pass the same settings
to driver analysis. This does not cryptographically bind a supplied Kf to a
particular driver request; cached or external callers must keep them paired.

The Python check independently builds the alternating cuboid array with
Magpylib in SI units. It now reconstructs physical trace/barrel resistance and
3D trace/via quadrature from the exported geometric edges, rather than trusting
Rust resistance values or dL samples. Force is checked at nine mover positions.
Field, geometric-sample and force mismatches fail with numerical tolerances.
This does not by itself establish mesh convergence. SciPy's sparse direct solve
separately recovers branch currents from the exported resistor graph, asserting
signed branch
agreement, Kirchhoff balance at every internal node, terminal current return
and Joule/terminal power balance. It replaces the old audit that incorrectly
assigned equal current to stored drawing directions and only printed violations.
Graph connectivity and arc tessellation still come from Rust. Magpylib and magba
use related cuboid formulas, so machine-precision agreement is an analytical
equivalence check, not independent validation of magnetic materials.

Rust tests separately pin signed branch division, Kirchhoff current balance,
power balance, reversal invariance and rejection of malformed inputs.
They also cover curved conductors, disconnected copper, overlapping terminal
buses, imported signed Z positions, and mismatched force coil lists.
Never infer current direction from stored drawing endpoint order. Imported
terminals and actual layer depths must be used for imported copper.

Before qualifying another geometry, also check mesh and position convergence,
terminal selection, DRC, layer stackup, waveform assumptions, and prototype
line-to-line resistance and inductance. Delta electrical analysis remains
blocked until its separate model is implemented.

## Signed-current follow-up, k9t4

- Imported network KCL and power are asserted on the mapped two-layer fixture,
  inner-only landings of a four-layer through hole, and every imported version
  checked by `imported_user_project_connectivity`. That optional test requires
  `PCB_MOTOR_PROJECT_PATH`. It passed on the supplied `star_4-layer.pmmotor`.
- Imported depth samples are pinned. Empty, extra and same-length wrong-name
  or wrong-index coil lists are rejected by both force entry points.
- Historical pre-via-fix DRV8311 literals were Kf 0.5939989478 N/A, thrust
  0.6533988425 N and speed voltage 4.4777041959 V, each to 1e-8 absolute.
- Historical pre-via-interval-fix four-layer project, Magpylib 5.2.3 plus SciPy 1.17.1: field error
  9.99e-16 T, sampled phase-A force error 3.47e-17 N. Independent branch-current
  error at most 5.27e-11. Phase resistances 7.65050235, 7.65469511 and
  7.67775529 ohm. These use that file's drive settings and terminal picks.
- FOC phase mapping, imported terminal polarity and the physical controller's
  PWM waveform remain unverified. The RL ripple calculation assumes 50% duty,
  not a switched FOC simulation. No hardware-feasibility claim follows.
- The former 8.81% versus 3.80% thrust ripple is window-dependent. No universal
  ripple number is pinned. Use the full physical overlap window described
  above, and independently check position resolution and entry/exit behaviour
  before treating ripple as a design tolerance.

### Via geometry correction, 2026-10-19

The earlier electrical graph assigned full-PCB barrel resistance to every
landed interval of a tapped through via, and routed force sampling omitted
vertical barrel currents. Via edges now retain their physical x/y position and
ordered layer span. Driver and force current solves both use the actual span
between copper heights; force integration includes signed vertical dL. For a
four-layer barrel with intermediate taps, three intervals sum to one physical
barrel length, not three board thicknesses. Imported, nonuniform Z positions
are used without replacing them with an average spacing.

New native tests verify that series barrel resistance, imported span resistance,
signed vertical-current force in constant transverse B, and invariance to stored
trace/via endpoint order. The full simulation suite passes 179 tests with two
existing ignored tests. `scripts/solvers/winding_oracle.py` independently
reconstructs R, solves currents and constructs trace/via quadrature; its analytic
tests pass. A fresh actual-project study passes meshes 10/20/40/80, including
successful exporter/oracle receipts and source/binary hashes. At mesh 80, each
phase includes 21040 nonzero vertical-current samples. Independent phase
resistances are 7.74052706, 7.74471982 and 7.76778000 ohm; maximum branch-current
share error is 3.95e-11 and physical edge-resistance error 4.69e-17 ohm. The last
force-curve change is 3.262e-6 N against the unchanged 0.001948 N norm limit.
`scripts/solvers/results/winding-via-oracle-star4-2026-10-19.json` records the
full study hash. Historical four-layer values above predate this geometry fix.

The corrected DRV8311 fixture was separately checked with all three phases and
its exported excitation commands. Independent geometric-edge resistance,
currents, dL and Magpylib forces reproduce Kf 0.594209515539 N/A against Rust's
0.594209515536 N/A; largest 25-position force discrepancy is 5.74e-12 N. Corrected
model thrust at 1.1 A is 0.6536304671 N and speed voltage 4.0956500486 V. The
original numeric regression failed after the physics correction; its pins were
updated only after this check, retaining the 1e-8 absolute tolerance. The targeted
regression now passes. The default four-layer fixture routes barrels between
layers 0 and 1, not through the entire 1.6 mm board, so its electrical interval
resistance changes as well as its via force. See
`scripts/solvers/results/drv8311-via-corrected-2026-10-19.json`. The exported
excitation is an explicit conditioning input, **not independent FOC/controller
waveform evidence or hardware feasibility**.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_winding_oracle.py \
  --project star_4-layer.pmmotor --version 0 --meshes 10 20 40 80 \
  --work "$SOLVER_OPT/new-star4-via-oracle"
```

The study snapshots code and records the executed Rust binary, fresh fixture,
independent checks, successful receipts and final quadrature change. It refuses
changed sources, user inputs or exporter binaries. This remains a free-space
current/force check, not backplane material or finite-housing validation.

For the separate generated driver case, use `--driver-reference` instead of
`--project`; output is exclusive-created and never overwrites an earlier fixture.

Post-correction regression reruns pass: native simulation 180 tests with two
existing ignored tests; desktop host 101 tests with five existing ignored tests;
frontend 436 tests with one skipped test; production frontend build passes.
The new read-only excitation diagnostic also rejects uncalibrated runs,
mismatched coils, nonfinite positions and nonfinite current output. These
regressions do not remove the magnetic/drive qualification limits below.

Imported copper must also remain on the PCB side of the first responding
magnetic or conducting stack surface. For example, the four-layer root project
has copper as deep as -4.8 mm but a configured 0.8 mm PCB. Its no-backplane
free-space oracle remains valid. Applying a ferrite sheet at the nominal PCB
bottom does not: some copper would be below the region where the layered image
model applies. Force and driver commands now return the same placement error,
without flattening the imported copper or relocating the stack. Nonmagnetic
spacers and a housing gap are accounted for before testing the first responding
surface. Core and desktop regressions exercise the shared guard.

Drive output now explicitly warns that partial inductance omits via barrels
and terminal return conductors when solved via currents are nonzero. Physical
via resistance and signed via force are included, but this does not qualify a
complete 3D terminal inductance or a safe hardware PWM ripple limit.

Browser regressions also verify that a failed new force model clears the old
sweep and cannot feed its Kf into driver analysis. Independently successful
panels remain visible. Backplane replacement and nested material edits now
invalidate an active simulation. Seven driver/simulation browser tests and
the existing ten coil-preview plus four periodic-reference tests pass.

## Backplane and housing validation boundary

The UI labels these results as screening estimates. A thin-sheet saturation
approximation does not resolve normal-face saturation in a thick plate. The
fresh FEMM rerun reproduces the archived 5 mm flexible-ferrite attraction
overestimate of 51.9%. Linear harmonic and travelling-wave agreement uses
fixed permeability and planar, one-metre depth. It does not qualify finite
housing edges, slots, return currents or nonlinear motion.

See [`femm/README.md`](femm/README.md) for the independent planar reference and
[`solvers/README.md`](solvers/README.md) for pinned GetDP/Gmsh/Elmer prototypes,
rejected jobs, convergence gates, reproducible commands and distribution limits.
Free-space, nonlinear material, induced-current and hardware checks are separate
gates. A passing installation or free-space test cannot pass the others.

Verified in this worktree on 2026-10-18:

- Simulation Rust library: 171 passed, 2 ignored.
- Desktop Rust application: 99 passed, 5 ignored.
- DXF/export Rust library: 123 passed, 1 ignored, plus the opt-in test passed
  separately on all three supplied drawings.
- Frontend unit suite: 432 passed, 1 skipped.
- Coil-layer browser suite: 10 passed. The final zoom-clearance test also passed
  after adding desktop/tablet screenshots; those screenshots were inspected.
- Production Vite build passed after the UI changes, with the existing large
  chunk advisory. No solver binary or source is included in that build.

Ignored and skipped tests do not count as covered physics. The two simulation
library ignores need unimplemented FOC test hooks; desktop ignores include
opt-in project diagnostics and fixture export.

## Supplied DXF exchange checks

```sh
PCB_MOTOR_DXF_PATH="$PWD/star-wye_4-layer.dxf" cargo test -p pcbmotorgen-export user_dxf_import_and_exchange_preserve_copper --lib -- --ignored --nocapture
```

This read-only, opt-in check imports the actual file, exports to an in-memory
3D DXF and reimports it. It checks primitive counts, segment/arc/via positions,
layer spans, physical elevations and copper extents, then verifies the original
bytes are unchanged. It is not a motor mapping or delta-drive qualification.

All three root DXFs passed on 2026-10-18:

| File | Segments | Curves | Vias | Copper Z, mm | Warnings |
|---|---:|---:|---:|---|---|
| `motor-coils_3s_0-4mm_star.dxf` | 533 | 0 | 393 | -1.6, 0 | none |
| `motor-coils_3s_0-4mm_delta.dxf` | 533 | 0 | 396 | -1.6, 0 | three unlanded vias |
| `star-wye_4-layer.dxf` | 1055 | 3 | 789 | -4.8, -3.2, -1.6, 0 | none |

The delta drawing warns about vias at 3.333/9.333, 4.333/8.444 and
6.333/8.889 mm. These must not silently acquire invented connections. Retain
the source elevations instead of substituting the current PCB-thickness setting.

## External-solver evidence added in this worktree

- `q9nw` is completed for the layered screening-model scope. Fresh FEMM
  PWM/travelling-wave checks pass independent near-mesh, far-air and domain
  refinements plus Joule/drag balance. Largest recorded change is 0.741%,
  below the predeclared 2% gate. Finite nonlinear motion is not implied.
- Both Elmer and GetDP pass their own 3D free-space field/refinement gates
  against Magpylib. The final Elmer solve uses named mesh boundaries and avoids
  unnecessary bandwidth reordering. Earlier failed jobs remain documented.
- The finite 12 x 12 x 5 mm plate below a single 5 x 5 x 3 mm PM is a separate
  3D nonlinear reference. Elmer passes field/force mesh, domain, surface,
  transverse-symmetry, empty-box-floor and quadrature gates. Worst field change
  is 1.987%; worst normal-force change is 0.696%. Fine Elmer/GetDP fields differ
  by at most 1.015%; nonlinear normal forces differ by 0.041%. GetDP also passes
  all finite-static refinement gates, including the expanded domain. Its largest
  field change is 0.906%; largest normal-force change is 0.254%. No scalar
  permeability was fitted.
- A finite conducting-disk A-v benchmark now checks actual current closure,
  including a radial slot. At 1–2 Hz the intact-disk current/loss match analytical
  weak-induction limits within 0.04% / 0.08%. Slotted loss matches a separately
  refined SciPy stream-function solve within 1.4%. Source-field work/Joule balance
  is within 0.5%. Disk near-mesh and domain loss refinements pass; exterior electric-field
  and Poynting traces are not qualified. Coarse traces are about 10% off, and
  a fine case has a spurious large trace despite matching conductor loss/work.
  This does not qualify motor-speed drag or 100 kHz PWM.
- A separate finite-volume Magpylib/SciPy motion oracle now enforces current
  continuity and insulating boundaries, including a one-sided slot. Uniform-field
  charge cancellation, zero/reversed velocity and discrete drag/Joule balance
  pass. At 0.01 m/s, the refined intact conductor gives 66.5523 microN drag.
  Elmer fine and expanded-domain A-v jobs agree with that oracle within 0.94%
  loss / 0.44% force and satisfy drag/Joule balance within 1.25%. A further
  mesh refinement timed out in setup and is not accepted evidence. These remain
  weak-induction frozen-geometry comparisons, not actual moving-array predictions.
- `scripts/solvers/project_static.py` adds a read-only saved-project bridge to
  five-magnet finite 3D magnetostatics. It requires explicit footprint and array
  pose rather than inventing missing housing edges. The initial supplied-project
  Elmer nonlinear worker failed; its bare force floor remains excessive after
  separate quadrature refinement. No nonlinear result is accepted from it.
  The corrected scalar adapter passes a one-PM setup comparison and is running
  the actual saved-project five-magnet case with local interface mesh controls.
- Coupled planar spatial harmonics now provide a separately qualified static
  normal-saturation reference, without fitted constants. Independent depth,
  mode and angular refinements pass. Five thin/thick ferrite cases match FEMM
  within 0.64% field / 3.70% pressure; qualified thin/thick/MnZn Elmer subsets
  agree within 0.046% field / 0.222% pressure. This is an offline periodic
  infinite-depth reference, not an application-model or finite-housing repair.
- The actual supplied PMMOTOR version also passes a fresh periodic FEMM
  comparison within 0.48% field / 4.62% pressure. A held-out synthetic geometry
  and mu/Bsat override case agrees within 0.030% / 1.52%. The FEMM override
  harness now correctly retains nonlinear BH data after a mu override and
  honours per-layer Bsat; null/default and distinct-layer regressions pass.

Commands, raw-element versus smoothed-field conventions, provisional material
data, solver hashes and the remaining gates are in `scripts/solvers/README.md`.
`04n2` and `ytgr` remain open. The application's analytical normal-face saturation,
biased differential tensor response and finite moving housing remain unqualified.
