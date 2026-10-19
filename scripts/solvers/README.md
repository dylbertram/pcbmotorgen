# Offline solver prototypes

Kata `pcbmotorgen#ytgr`, `#04n2`, `#q9nw`. These jobs test external solvers
before any application integration. They do not replace the fast analytical
preview or turn its estimates into qualified motor predictions.

## Installation

For a fresh checkout on another computer, start with
[the portability guide](PORTABILITY.md). It covers host prerequisites, pinned
Python dependencies, private solver installation, example-free smoke tests and
the boundary between committed tooling and external raw study archives.

On Debian 12 x86_64, with CMake, GCC/G++, make, curl and Python 3.11+ available:

```sh
scripts/solvers/install_linux.sh
. ~/.local/opt/solver-prototypes/env.sh
python3 -m venv .magpy-venv
.magpy-venv/bin/pip install -r scripts/requirements-validation.txt
```

`SOLVER_OPT` selects a user-owned installation directory. Nothing is installed
system-wide. The installer builds serial Elmer without GUI/MPI, selects the
magnetic and output modules, and retains dependency package versions/hashes.
Do not run an installation over tools that are executing jobs.

Pinned archives, checked on 2026-10-18:

| Tool | Source | SHA-256 |
|---|---|---|
| GetDP 3.5.0 | https://getdp.info/bin/Linux/getdp-3.5.0-Linux64c.tgz | `d3c28fa18f20d6147b4c7367d4dd802e9f7ddb58c608688bbb71919dbca8041d` |
| Gmsh 4.13.1 | https://gmsh.info/bin/Linux/gmsh-4.13.1-Linux64.tgz | `6c9f030d20388392968e40d15f6ebb5e1d46f29c92b7afb14cee728d30e8a08f` |
| Elmer 26.2 | https://github.com/ElmerCSC/elmerfem/releases/download/release-26.2/elmerfem-release-26.2.tar.gz | `7addfb102d735929a40929be08be0c16703d734498d33bc70c96e7d526fe249c` |

The Elmer archive hash also matches the GitHub release asset digest. GetDP
and Gmsh hashes record the downloaded release artifacts; they are not a separate
publisher signature. Debian runtime/compiler packages are resolved from signed
APT metadata, and their exact downloaded versions/hashes go in `deps/`.

## Free-space gate

Both formulations use `cuboid.geo`, a 5 x 5 x 3 mm cuboid, Br 1.34 T, with its
bottom 0.5 mm above the sample line. GetDP uses a quadratic scalar magnetic
potential. Elmer uses the Whitney vector potential. The outer boundary conditions
differ, so each backend must independently pass air-domain refinement.

```sh
.magpy-venv/bin/python scripts/solvers/check_free_space.py \
  --gmsh "$(command -v gmsh)" --getdp "$(command -v getdp)" \
  --work "$SOLVER_OPT/free-space-getdp"
.magpy-venv/bin/python scripts/solvers/check_free_space.py \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)" --coarse-mesh 0.00025 --fine-mesh 0.0002 \
  --work "$SOLVER_OPT/free-space-elmer"
```

The field vector is compared at 25 points with Magpylib 5.2.3. Gates are 5%
relative field-norm agreement and 2% field-norm change under mesh and outer-domain
refinement. These are numerical acceptance gates, not fitted model constants.
GetDP uses PETSc CG/GAMG and requires an explicit convergence reason. Elmer
aborts unconverged linear solves. Jobs retain input files, meshes and logs.
Completed comparisons also write raw fields, timings and SHA-256 inputs in
`summary.json`.
Failures, timeouts and cancelled processes cannot produce an accepted result.
Each command also writes a receipt beside its log. A rerun marks its summary
`running` before any work, so an earlier success cannot survive an incomplete
rerun. The default command timeout is 600 seconds; set
`PCB_MOTOR_SOLVER_TIMEOUT=1800` for longer nonlinear diagnostics. This changes
the time limit, not a numerical acceptance threshold.

Measured so far:

- GetDP first-order nodal fields failed: 14.36% error at 0.4 mm, 6.36% at
  0.2 mm. The final domain run was cancelled after this failure, not accepted.
- Quadratic GetDP passed: 1.51%, 1.65%, 0.834% vector field errors for
  0.4 mm, 0.3 mm and expanded-domain runs. Both refinement gates pass.
  Mesh times 4.7/6.5/8.3 s; solves 53/85/178 s on this shared 4 GB host.
  The original summary is retained in `results/free-space-getdp-2026-10-18.json`.
  It predates the explicit running/passed status field and is archived unchanged.
- Early Elmer jobs were rejected. ElmerGrid renumbered boundary 3 to 1,
  so the boundary condition did not apply. Inputs now include
  `mesh/mesh.names` and use named boundary IDs. Corrected first-order Elmer
  now passes: 1.693% / 1.063% / 0.976% field errors at 0.25 / 0.20 mm and the
  expanded domain, with 1.716% mesh and 1.475% domain changes. Disabling
  unnecessary bandwidth optimization for the iterative solves removed the
  long reordering stage. Solves took 38 / 65 / 144 s on this shared host.
  An incomplete quadratic trial used about 2.5 GB
  resident memory and was cancelled. It is not an accepted reference.

## Upstream Elmer checks

```sh
ctest --test-dir "$SOLVER_OPT/elmer-build" \
  -R '^(mgdyn_bh|mgdyn_airgap_force|mgdyn_faraday_disc)$' \
  --output-on-failure -j 1
```

All three passed on the pinned source build: nonlinear B-H tetrahedra, PM
force, and Faraday-disc electric-potential cancellation. This verifies those
upstream formulations, not our motor geometry. Total runtime was 58.4 s.

## Nonlinear plate gate

`plate2d.geo` and `check_plate2d.py` compare Elmer and GetDP nonlinear 2D
vector potentials with the archived FEMM thin-sheet and failed thick-plate cases.
Elmer and FEMM receive the same two-slope B-H table. GetDP evaluates this law
analytically with its exact Newton tangent. No effective permeability is fitted.
A half-period uses natural A_z side boundaries,
equivalent to the alternating-row symmetry. It is not a finite array.

```sh
python3 -I scripts/femm/femm_backplane.py --new-only \
  --work "$HOME/.local/opt/femm-runs/solver-reference"
.magpy-venv/bin/python scripts/solvers/check_plate2d.py \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)" \
  --femm-work "$HOME/.local/opt/femm-runs/solver-reference" \
  --work "$SOLVER_OPT/plate-reference"
```

Use `--getdp "$(command -v getdp)"` instead of the Elmer arguments for the
second backend. The comparison uses the curl of raw A_z inside each air triangle. It does not
smooth flux across a permeability jump. Force is a Maxwell-stress integral on
three different air paths; the no-plate stress floor, path sensitivity, mesh
refinement and domain refinement must each pass 2% on the fine runs.
Field ratio and pressure
must agree with FEMM within 5%. `--quick` is only a setup comparison and cannot
pass a refinement gate. The initial coarse prototype was not accepted.

The first coarse thin-sheet jobs from both solvers give a field ratio of
1.045386 and pressure 7.424 kPa. They agree with FEMM within 0.51% and 3.10%,
but fail stress-path sensitivity at 7.48%. Inspection found that the most
distant air path lay on the fine-mesh band's edge. The fine band now extends
beyond all three paths. Elmer stress integration uses exact triangle/line
intersection lengths instead of uniform sampling. Region areas, nonzero PM
excitation and nonlinear convergence are asserted. Refined jobs were required
before accepting either backend; the accepted Elmer subsets are recorded below.

With the expanded fine-air band, Elmer completed all three 0.2 mm sheet levels.
Field ratios are 1.045589 / 1.045780 / 1.045609 and net pressures
7427.43 / 7425.69 / 7427.35 Pa. Mesh/domain changes are below 0.03%; fine
stress-path sensitivity is below 1.3%, and the no-plate stress floor is below
0.8% of the reference force. This thin-sheet subset passes the numerical gates
and matches FEMM within 0.49% field / 3.14% force. The same batch timed out on
the fine 5 mm plate, so the whole batch is NOT accepted. The coarse 5 mm plate
gave field ratio 1.29670 and pressure 65.927 kPa, within 0.67% / 0.085% of FEMM,
but that original batch's refinement is incomplete. Separate fresh thick-flex
and MnZn batches now pass, as recorded in the subset audit section below.

The first fine GetDP job completed its nonlinear solve but timed out while
sampling its final stress line. It is rejected as incomplete. The new
postprocessor exports raw element potentials and performs exact triangle/line
integration, avoiding thousands of repeated searches in the strongly graded
mesh. Its cache is invalidated when an output file changes. Comparison helpers
reject incomplete, unrefined or mismatched-mesh reports.

## Finite 3D diagnostic

`check_finite_plate.py` uses a single 5 x 5 x 3 mm PM above a finite 12 x 12 mm
plate. It is intentionally not the planar alternating row. Both backends run
bare, linear and nonlinear materials on the same geometry. The bare field must
match Magpylib within 5%. Material volumes and the spherical outer boundary
are checked before solving. A completed run is labelled `comparison-only`,
not accepted, until mesh/domain and cross-backend checks are complete.

```sh
.magpy-venv/bin/python scripts/solvers/check_finite_plate.py \
  --gmsh "$(command -v gmsh)" --getdp "$(command -v getdp)" \
  --work "$SOLVER_OPT/finite-plate-getdp"
.magpy-venv/bin/python scripts/solvers/check_finite_plate.py \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)" --work "$SOLVER_OPT/finite-plate-elmer"
```

Use `--mesh`, `--gap-mesh`, `--radius` and separate work directories for
refinement. The default 5 mm flexible-ferrite plate is a normal-saturation
diagnostic using the same provisional two-slope material law, not measured
commercial ferrite data. The scalar GetDP formulation is current-free. It
cannot model induced currents or housing drag.

Closed-air-box Maxwell force can be reprocessed from completed GetDP solutions
without another solve:

```sh
.magpy-venv/bin/python scripts/solvers/post_finite_force.py \
  --getdp "$(command -v getdp)" --work "$SOLVER_OPT/finite-plate-getdp" \
  --subdivisions 32
```

Repeat at 64 subdivisions. This samples all six faces at three clearances,
including side traction; top-minus-bottom pressure alone is not a closed 3D
force integral. The helper tests recover zero net force in a uniform field
and converge toward zero force on an empty box exposed to a Magpylib PM.
Elmer's fixed finite-plate case now passes the mesh, domain, force-surface,
empty-box floor, transverse-symmetry and 32/64 quadrature gates. This is not
qualification of arbitrary materials, footprints or moving housings.

First finite-plate results, 2026-10-18, 0.8 mm solid / 0.3 mm gap mesh:

| Backend | Bare centre Bz | Linear plate Bz | Nonlinear plate Bz | Bare vector error vs Magpylib |
|---|---:|---:|---:|---:|
| GetDP | 0.404784 T | 0.576625 T | 0.526741 T | 0.805% |
| Elmer | 0.403694 T | 0.573600 T | 0.524535 T | 1.699% |

Bare and linear vector fields differ between backends by 1.72% and 1.73%.
The Elmer nonlinear potential converged in 16 iterations to relative change
8.99e-9. Its field gain is 1.2993 rather than the linear 1.4209. These are
coarse diagnostic results, not refined force or motion predictions. The first
GetDP nonlinear job exceeded 600 seconds after seven nonlinear iterations;
the full-Newton retry converged in 10 iterations and 805 s. Changing solver relaxation does
not alter the material law or acceptance thresholds.

The initial Python convergence parser incorrectly mixed nonlinear-potential
iterations with field-projection solves. It now checks only `mgdynamics`, and
a unit test covers that distinction. The finished Elmer job was reprocessed
without rerunning or modifying its inputs/logs:

```sh
.magpy-venv/bin/python scripts/solvers/recover_finite_elmer.py \
  --work "$SOLVER_OPT/finite-plate-elmer-coarse"
```

This writes `postprocessed-summary.json`, including input/log/VTU hashes.
It requires a normal solver finish and nonlinear convergence and cannot rescue
a timeout or unconverged solution.

At the refined 0.6 mm solid / 0.2 mm gap mesh, Elmer and GetDP vector fields
differ by 1.015% bare, 0.930% linear and 0.936% nonlinear. Raw closed-surface
normal force at 0.6 mm clearance is 1.80625 / 1.81076 N linear and
1.48650 / 1.48589 N nonlinear, Elmer / GetDP. This uses raw element B, not a
nodal projection across material interfaces. Elmer's worst field change under
refinement is 1.987%; worst normal-force change is 0.696%. GetDP also passes
all finite-static gates. Its largest mesh/domain field changes are 0.906% /
0.561%; mesh/domain normal-force changes are 0.254% / 0.042%.
Its fine nonlinear solve took 1032 s;
Elmer's fine and expanded-domain nonlinear solves took 115 and 160 s. These
shared-host timings are not a controlled performance benchmark.

After generating each level and its 32/64 force reports, audit it with:

```sh
.magpy-venv/bin/python scripts/solvers/check_finite_convergence.py \
  --coarse-work "$SOLVER_OPT/finite-plate-elmer-coarse" \
  --coarse-summary postprocessed-summary.json \
  --fine-work "$SOLVER_OPT/finite-plate-elmer-fine" \
  --domain-work "$SOLVER_OPT/finite-plate-elmer-domain" \
  --output "$SOLVER_OPT/finite-plate-elmer-convergence.json"
```

For Elmer force reprocessing, omit `--getdp`; raw cell fields are the default.
`--elmer-field nodal` retains the old smoothed-field diagnostic for comparison,
but the acceptance audit requires the raw-element reports.

## Finite eddy-current closure, weak-induction limit

`check_eddy_disk.py` solves a finite 6 mm-radius, 1 mm-thick conducting disk in
uniform Bz with Elmer's complex 3D A-v formulation. The source is a 10 mT **peak**
field; reported losses are time averages, with the factor 1/2 explicit. This is
a 1–2 Hz numerical benchmark using sigma 25 MS/m, not a 100 kHz motor prediction.

```sh
.magpy-venv/bin/python scripts/solvers/check_eddy_disk.py \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)" --work "$SOLVER_OPT/eddy-plain"
.magpy-venv/bin/python scripts/solvers/check_eddy_disk.py \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)" --slot 0.0005 \
  --work "$SOLVER_OPT/eddy-slotted"
.magpy-venv/bin/python scripts/solvers/eddy_disk_network.py \
  --output "$SOLVER_OPT/eddy-weak-oracle.json"
```

The intact disk has analytical weak-limit loss
`pi*sigma*omega^2*Bpk^2*t*a^4/16`. The independent SciPy oracle solves a
current-stream Poisson problem on the actual disk/slot cross-section with
zero boundary-normal current. It includes charge-driven return paths, not
just the removed conductor volume. Its 96/192/384 refinements pass 2%.
It cannot model skin effect, magnetic reaction, nonlinear bias or motion.

Initial 1 Hz mean-loss results:

| Cross-section | Elmer volume integral | Independent weak reference | Difference |
|---|---:|---:|---:|
| Intact disk | 25.0973 nW | 25.1151 nW analytical | -0.071% |
| 0.5 mm radial slot | 12.9262 nW | 12.7515 nW SciPy | +1.37% |

The losses scale with frequency squared at 1 and 2 Hz. Raw intact-disk current
phasors agree within 0.04%; the supplied-field error is below 1e-7 relative.
Impressed-field work and Joule heating agree within 0.5%. Direct exterior
Poynting traces on the coarse far-air mesh differ by about 10%. A fine 2 Hz
trial also produced a spurious large exterior trace despite matching current,
loss and impressed-field work. Exterior electric-field/gauge and trace
reconstruction are NOT qualified. Do not use those outputs as a flux result.
They are reported, not silently renormalized. Disk near-mesh and domain loss
refinements now pass. Near-mesh changes are 0.045% intact / 0.50% slotted;
domain changes are below 0.001%. The combined oracle comparison emits
`passed-weak-limit`. This status applies to conductor loss and impressed-field
work at 1 and 2 Hz, not the rejected exterior Poynting traces.

Two setup failures are retained: a tree-gauged nonzero-source trial did not
reproduce the prescribed field, and nodal current projection smeared conductor
current into adjacent air. Exact vector-potential boundary data with iterative
gauge treatment recover the prescribed uniform field; raw element currents
recover the analytic phasor. Source-field, current, power and convergence gates
must pass before using a changed setup.

`compare_eddy_disk.py` checks the archived plain/slotted results against the
independently refined oracle and impressed-field work. Optional `--plain-fine`,
`--slotted-fine`, `--plain-domain` and `--slotted-domain` require the separate
2% mesh/domain gates before it emits `passed-weak-limit`.

Joule-density projection can have a tiny negative cell even though physical
Joule density is nonnegative. The domain trial had negative integrated energy
only 6.1e-10 of the total. The postprocessor retains the signed integral without
clipping, records the negative contribution and rejects it above one part per
million of total power. This is a projection audit, not a relaxation of the
physical loss/work/refinement gates. A unit test checks both harmless ringing
and rejection of meaningful negative projected energy.

`--reuse-completed` avoids rerunning a successful solver after a postprocessing
failure. Reuse requires the same solver command, byte-identical SIF and mesh,
a completed zero-exit receipt, a normal solver finish and a single archived VTU.
The result records reuse and the original receipt hash.

## Finite motional-current diagnostic

`weak_motion.py` uses Magpylib's prescribed PM field and a separate SciPy
finite-volume charge-continuity solve for a 12 x 12 x 1 mm conductor.
Every exterior face is insulating; potential differences determine closed
current paths. It is not the uncompensated `sigma*(v cross B)` approximation.
Slot faces coincide with grid boundaries, preserving the actual removed volume
as the mesh changes. Tests check uniform-field charge cancellation, zero speed,
velocity reversal, KCL and mechanical/electrical power balance.

```sh
.magpy-venv/bin/python scripts/solvers/weak_motion.py \
  --output "$SOLVER_OPT/weak-motion-slot-0.json"
.magpy-venv/bin/python scripts/solvers/weak_motion.py --slot 0.0005 \
  --output "$SOLVER_OPT/weak-motion-slot-0.0005.json"
```

At conductor velocity +0.01 m/s in the stationary-PM frame, the refined intact
plate gives Fx = -66.5523 microN, loss 0.665523 microW. The one-sided 0.5 mm slot
gives Fx = -46.0566 microN and loss 0.460566 microW. The unslotted/slotted last
loss changes are 0.093% / 0.247% across 24/36/48 lateral and 4/6/8 depth cells.
The asymmetric slot also gives a nonzero normal force. These are prescribed-field
weak-induction results, not accepted operating-speed drag predictions.
Magnetic Reynolds number is 0.00377; the CLI rejects values above 0.01 because
it omits field reaction and magnetic memory.

`check_weak_motion_elmer.py` compares Elmer's steady A-v solve with that oracle.
It includes conductor velocity and the charge potential. The coarse pilot
matches loss / force within 1.82% / 1.56%, but FAILS the independent 2% drag/Joule
power gate at 3.44%. Its result stays failed. A separate finer 0.4 mm solid /
0.2 mm gap mesh passes that gate at 1.24%, with loss / force oracle errors
0.933% / 0.301% and field error 1.36%. The expanded-domain check also passes
the single-job gates, with 1.25% power balance, 0.811% loss-oracle error,
0.431% force-vector error and 0.913% field error. Its loss / drag changes from
the fine job are 0.124% / 0.134%. A further 0.3 mm solid / 0.15 mm gap trial
timed out during matrix setup at 600 s under shared-host memory/swap pressure.
It remains incomplete and supplies no additional convergence evidence.
No correction factor or looser power tolerance is applied. The geometry is a
frozen instantaneous diagnostic, not a translating-boundary transient.

## Saved-project finite-array jobs

`project_static.py` reads one explicit zero-based `.pmmotor` version without
changing the source. It uses that version's magnet count, alternating polarity,
remanence, dimensions, electrical pitch, PCB thickness, magnet gap, magnetic
layer thicknesses, material overrides and housing wall/gap. No winding current
is applied. It does not substitute PCB settings for imported copper depths,
because copper is not part of this magnetostatic source problem.

The saved project has no finite housing footprint or unambiguous global mover
pose. Both must be provided. The script does not treat saved preview position
as an imported physical coordinate. The example below is an explicitly chosen
36 x 12 mm rectangular footprint at a centred frozen array pose, not measured
housing dimensions from the supplied file:

```sh
.magpy-venv/bin/python scripts/solvers/project_static.py \
  --project star_2-layer.pmmotor --version 1 \
  --footprint-mm 36 12 --array-centre-mm 0 0 \
  --gap-mesh 0.0002 --work "$SOLVER_OPT/project-star2-v1-pilot" \
  --gmsh "$(command -v gmsh)" --elmer "$(command -v ElmerSolver)" \
  --elmergrid "$(command -v ElmerGrid)"
```

Omit tool paths to generate inputs only, or supply only `--gmsh` to check mesh
material membership, exact volumes and outer-boundary tags. An empty output
directory is required so an earlier job or source cannot be overwritten.
GetDP is available as the independent current-free scalar backend by replacing
`--elmer` and `--elmergrid` with `--getdp "$(command -v getdp)"`. A generated
one-PM smoke initially timed out because the entire thick solid was refined at
the gap size. Local interface bands now avoid that waste while retaining the
solid mesh, and the corrected smoke completes: 1.30% bare field error,
1.48–1.51 N nonlinear force over the three paths and a 1.05e-11 nonlinear
residual after 10 logged iterations. The five-magnet quadratic scalar mesh
produced 2.52 million DOFs and its bare worker was terminated by SIGKILL.
A first-order scalar trial now refines magnet geometry instead of using a
quadratic basis everywhere. It keeps the same 5% bare-field and 2% force-control
gates; no first-order result is accepted merely to fit memory. The adapter still
needs independent mesh/domain/backend checks.
`--mesh-from <previous-job-directory>` reuses a mesh only when the generated
geometry and mesh settings are byte-identical, then rechecks region volumes and
the outer boundary. This permits a same-mesh backend comparison.
The original Elmer five-magnet pilot is not accepted. Its bare field error was
4.59%, with substantial 32-point square-box force-floor errors, and the nonlinear
worker terminated with SIGKILL after 617 s under shared-host memory pressure.
The bare solve took 945 s. No nonlinear result is recovered from that worker.
The adapter now supports the actual rectangular footprint in force integration
and explicit `--force-subdivisions`, default 64, for separate quadrature studies.
It also disables the unused current-fixing solve and uses diagonal scaling in
the current-free vector formulation. Those changes still need a fresh run.
A successful single job remains
`comparison-only`, even if its bare array agrees with Magpylib. Repeat mesh,
domain, quadrature and backend checks before interpreting differences as design
predictions. The common rectangular footprint is not general housing CAD.

Each magnetic layer uses its own provisional BH table. Housing conductivity
is zero for this static problem and never presented as eddy-current loss.
The output includes a source hash, chosen geometry, numerical inputs, field
tables, solver receipts, nonlinear convergence and six-face Maxwell force at
three clearances. Force quadrature and path checks need independent qualification
on this five-magnet geometry; the single-PM gates do not transfer automatically.

`post_project_force.py --work <job> --case bare --subdivisions 64 128` reprocesses
the completed bare control on rectangular surfaces without rerunning a solver.
It verifies the original field/formulation hashes and successful case receipt.
It can recover a completed case from an incomplete batch, but never an unfinished
nonlinear case. Each report remains `comparison-only`; it does not suppress a
large empty-box force floor or supply the missing nonlinear solution.

## Complete subsets of interrupted planar batches

The fresh full-Newton Elmer thick batch completed every 5 mm flex-ferrite
mesh/domain job, then stopped on unconverged MnZn. The original batch remains
incomplete. `audit_plate2d.py` can qualify a completed material subset without
changing that summary or accepting the other material:

```sh
.magpy-venv/bin/python scripts/solvers/audit_plate2d.py \
  --work "$SOLVER_OPT/plate2d-elmer-thick-full-newton" --case flex_5 \
  --femm-work "$HOME/.local/opt/femm-runs/simulation-validation" \
  --output "$SOLVER_OPT/plate2d-elmer-flex5-qualified-subset.json"
```

The audit recomputes fields and exact stress paths from archived raw potentials,
checks input hashes, successful command receipts and the original nonlinear
tolerance, and requires all three refinement levels. The 5 mm flex subset
passes. Field ratios are 1.296701 / 1.298083 / 1.296494 and pressures
65.9273 / 65.9371 / 65.9375 kPa. Field agreement with FEMM is within 0.69%,
pressure within 0.10%. This independently confirms the thick-sheet case where
the analytical screening attraction overpredicts FEMM by 51.9%; it does not
repair that analytical model.

MnZn's full-Newton base result reached 100 iterations with relative change
1.45e-7, above the unchanged 1e-9 requirement. The process finished normally,
but its result is rejected. A separate damped retry changed relaxation only,
not the BH curve or convergence tolerance, and passed every MnZn mesh/domain
gate. Its pressures are 84.5460 / 84.5495 / 84.5521 kPa and FEMM force error
is below 0.18%. Earlier failed results remain unchanged.

## Coupled spatial-harmonic normal saturation reference

`vector_harmonic_screen.py` tested a biaxial describing-function closure using
the full vector B-H law. It improved the thick-sheet discrepancy but remained
6–7% high on thin-sheet force. That experiment is rejected as a general
replacement. Adding more source modes to its bias did not repair the missing
nonlinear mode coupling. No correction factor was fitted.

`spectral_plate.py` instead minimizes the vector magnetic energy with coupled
odd Fourier modes of A and linear depth elements. It uses the same two-slope
material law as the references and exact air-boundary operators above/below
the layer. Newton uses the physical differential-reluctivity tensor. Unit tests
check energy gradients, tensor/Hessian finite differences, positive definiteness
and the exact linear-slab reflection limit. This is an offline reduced planar
experiment, not a native 3D FEM engine or selected production dependency.

Independent refinements used 32/64/128 depth cells, 9/17/33 odd modes and
512/1024 angular samples. All numerical 2% gates and five-material-case 5%
FEMM comparison gates pass without fitting. Refined results:

| Material | Field ratio | Pressure | Pressure difference vs FEMM |
|---|---:|---:|---:|
| Flex 0.1 mm | 1.023947 | 3.80386 kPa | +3.70% |
| Flex 0.2 mm | 1.045567 | 7.44377 kPa | +3.37% |
| Flex 1 mm | 1.164140 | 31.0779 kPa | +1.49% |
| Flex 5 mm | 1.297084 | 66.0071 kPa | +0.21% |
| MnZn 2 mm | 1.405343 | 84.6652 kPa | +0.31% |

Against separately qualified Elmer thin/thick/MnZn subsets, maximum field-ratio
difference is 0.046%, pressure difference 0.222%. The fresh MnZn Elmer damped
batch passes at the original 1e-9 tolerance; the earlier unconverged full-Newton
trial remains rejected. Fresh thin jobs also reproduce the earlier passing
thin subset with explicit command receipts, rather than inventing receipts for
historical jobs that predated them.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/spectral_plate.py \
  --femm-work "$HOME/.local/opt/femm-runs/simulation-validation" \
  --output "$SOLVER_OPT/coupled-spectral-pinned-baseline.json"
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/spectral_plate.py \
  --cells 64 128 --modes 17 33 --angle-samples 1024 \
  --femm-work "$HOME/.local/opt/femm-runs/simulation-validation" \
  --output "$SOLVER_OPT/coupled-spectral-pinned-refined.json"
```

`compare_spectral_plate.py` compares those batches and three `audit_plate2d.py`
reports, requiring independent depth/mode/angle changes, identical material
inputs, convergence, finite reflected modes and 2% independent FEM agreement.
The resulting `spectral-planar-qualified.json` has status
`passed-planar-static-reference`, which does not qualify application integration,
incremental inductance, biased AC transfer or finite moving housings.
The unchanged aggregate audit is archived in
`results/spectral-planar-2026-10-18.json`, including the source-report hashes.

At 64 depth cells / 17 modes / 512 angles, measured solves took 0.5–2.4 s across
the cases on this host. The 128/33/1024 refinement took 6.8–29.2 s. These are
reference-solver timings, not a UI latency promise.

`check_project_spectral.py` reads a selected saved project and compares its
single-layer periodic DC limit with fresh real FEMM jobs:

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_project_spectral.py \
  --project star_2-layer.pmmotor --version 1 --run-femm \
  --work "$SOLVER_OPT/project-star2-v1-periodic-spectral"
```

The supplied version passes that comparison at 0.48% field / 4.62% pressure.
A separate held-out synthetic fixture changes PCB thickness to 1.6 mm, gap to
0.8 mm, magnet width/height to 4.5/2.5 mm, Br to 1.2 T and material mu/Bsat to
200/0.35 T. It agrees with fresh FEMM within 0.030% field / 1.52% pressure.
Those synthetic values are test inputs, not measured supplier properties.
Single-layer and nonmagnetic housing restrictions are explicit. The finite
magnet count and cross width are recorded as **not modelled**, and conductivity
has no static effect. No finite-array or eddy qualification follows from this.

The FEMM harness also had a material-override bug: renaming an overridden mu
removed its nonlinear BH curve. It now applies both mu and Bsat overrides,
retains defaults for null overrides and gives distinct layers distinct material
identities. Default archived cases are unchanged. Regression tests cover this.

## Static differential coil response, still under evaluation

`spectral_incremental.py` adds both spatial phases around the qualified static
bias without changing the static reference implementation. It solves the full
energy Hessian for differential source response, including the vector
differential-reluctivity tensor and coupling between spatial modes. Nonlinear
central differences at 1e-4 and 1e-5 of the PM fundamental check that derivative.
Passivity, phase symmetry and linear-solve residuals are checked separately.

`check_spectral_incremental.py` generates new **knee-law** FEMM bias and
incremental jobs. It does not compare the hard-knee model with the older
tanh-biased FEMM archive. Both cases use the same source geometry and two
isolated finite-thickness coil sheets, at two spatial alignments. FEMM's
previous-solution incremental mode uses the static PM bias; the PM is turned
off as an incremental source.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_spectral_incremental.py \
  --quick --case flex_0.2 --run-femm \
  --work "$SOLVER_OPT/incremental-spectral-knee-pilot"
```

Omit `--quick` for separate depth/mode/angle studies. Added-inductance
agreement must be within max(0.001 absolute factor,
5% of the added factor), rather than allowing a near-unity total factor to hide
a wrong magnetic contribution. Refined added factors use a 2% gate with the
same absolute floor. These checks do not validate complex AC impedance,
conductive-housing eddy screening, PWM or finite-array magnet coverage.

The thin 0.2 mm and 2 mm MnZn comparisons pass those spectral refinements and
FEMM agreement gates. The initial 1 mm flex case failed its low-inductance
alignment: 1.010567 spectral versus 1.011790 FEMM, an absolute error of 0.001223
against the unchanged 0.001 floor. Sampling the exact same B-H knee down to
1e-6 changed this by less than 2e-8. Independently refining the strip source from
96 to 192 strips instead reduced the error to 0.000585, within the original
gate. The 384-strip bias timed out at 300 s; that trial remains rejected.
Its separate 1200 s retry completed: FEMM factors 1.011312 / 1.229270, versus
spectral 1.010567 / 1.226912. Both still pass the unchanged comparison limits.
The 192→384 source changes also pass max(0.001 absolute factor, 2% of the
added factor). No fitted correction or tolerance change was used.

`backplane_dump` also contained a misleading linear-control limit: the 3 T user
override cap can still saturate a very thin plate. Its **example-only** linear
reference now uses an unreachable finite knee and records `linear_reference`.
Magnetic housings are rejected in that mode. Production material override limits
are unchanged. Tests verify 0.1/0.2 mm sheets keep both secant and incremental
mu at 130; the six-case dump confirms all selected linear controls stay linear.

### DC-biased complex response

`spectral_biased_ac.py` transfers the full static Hessian into a complex A solve
with conductive-layer mass terms and a resolved finite Al wall. It checks the
linear multilayer skin limit, passive response, zero-frequency limit and
source-work/Joule balance. `check_spectral_biased_ac.py` compares real FEMM
previous-solution incremental AC, with PMs used only for the DC bias and identical
bias/AC geometry. Two isolated sheets and two spatial phases are compared.

The 0.2 mm flex / 1 mm Al / 0.1 mm gap / 100 kHz pilot passed its predeclared
comparison gates. Coil factors were 0.567318-0.071195i and 0.655308-0.065871i,
versus FEMM 0.569334-0.071465i and 0.657626-0.066076i. Normalized Joule losses
agree within 0.083%; FEMM's independently extracted source work balances loss.
The specific thin-sheet preset now passes the complete nine-level
`audit_biased_ac.py` study: separate layer-depth, harmonic, angular, wall-depth
and gap-depth studies, followed by FEMM near-mesh, far-air and source-strip
refinement. This qualifies that periodic small-signal reference only.
It verifies source snapshots, input/output hashes and successful process receipts
before applying the 2% refinement and 5% comparison gates to **added** reactive
and resistive factors and loss. Legacy outputs without receipts cannot pass it.

The 192-strip source run first timed out on its bare sheet at 900 s; the audit
correctly rejected the incomplete study. The longer-timeout retry completed
with identical archived inputs. The accepted audit verifies original sources,
case/output hashes and successful receipts for every FEMM case. Maximum
independent loss change is 0.0747%; maximum independent FEMM loss disagreement
is 0.153%. The worst added-complex-factor error uses 20.93% of its predeclared
gate. `results/biased-ac-thin-refinement-2026-10-18.json` records the measured
scope, fixed geometry/material inputs, physics hashes and full-audit hash.
The 1 mm flex pilot also passes its comparison gates, without this complete
independent refinement qualification.
The 2 mm MnZn pilot fails its low-effect reactive alignment at an absolute
factor error of 0.001463 against the unchanged 0.001 floor. Higher spectral
resolution reduces that error to 0.001234 but still fails. The MnZn failure is
not hidden by total-factor relative error or a looser tolerance.
Doubling its source strips to 192 changes the low-effect error only to 0.001200,
still above the unchanged floor. A separate half-mesh FEMM study at the same
192 strips also fails, with a low-effect error of 0.002165. Its loss agreement
improves, but that does not rescue the reactive gate or prove convergence.
`results/biased-ac-mnzn-unqualified-2026-10-18.json` retains all four failed
summary hashes. Source discretization and bias-field/tangent accuracy remain
unresolved controls for that material.

One attempted FEMM mesh refinement correctly failed the geometry guard because
the harness scaled a shared source rectangle twice. `refined_mesh` now copies
each case first; a regression test checks the bare/stack source meshes stay
identical. The rejected run remains archived, with no AC result accepted.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_spectral_biased_ac.py \
  --run-femm --work "$SOLVER_OPT/biased-ac-new-pilot"
```

This does not determine a safe large-ripple amplitude, validate a nonlinear
transient, model finite winding coverage or qualify actual housing currents.
Application warnings now explicitly say a saturated-backplane inductance
estimate is not the minimum across mover position/coil phase, even without
a conductive housing.

### Read-only saved-project thickness studies

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/study_project_backplane.py \
  --project star_2-layer.pmmotor --version 1 --thickness-mm 0.1 0.2 1 5 \
  --work "$SOLVER_OPT/project-thickness-study"
```

Each trial separately refines depth, harmonics and angular quadrature, checking
static field/pressure and differential coil factors with nonlinear finite
differences. The JSON preserves the source project hash, original stack and
source snapshots. It reports periodic pressure rather than multiplying by the
finite motor area, and does not apply guessed magnet-coverage weighting.
Overrides need independent FEM verification; a numerical convergence pass is
not a new material validation. Only a single magnetic layer and nonmagnetic
DC-transparent housing are supported. The source project is never rewritten.

The supplied `star_2-layer.pmmotor` version 1 study completed all four thicknesses
and all separate refinement/finite-difference gates, retaining the original
source SHA256 `0ed215f6ff403b927dbeac1ea3d4d9587489a1f1c0680e4ce3a2a48658475d82`.
Full study SHA256 is
`71476476a9b658f705ebecd8bbc765a983d41a99740de080348044352b56017f`.
For mu=130 and saturation polarization 0.25 T:

| Magnetic thickness | PCB-top field ratio | Periodic pressure | Two DC coil factors |
|---|---:|---:|---:|
| 0.1 mm | 1.023947 | 3.804 kPa | 1.00165 / 1.03026 |
| 0.2 mm | 1.045567 | 7.444 kPa | 1.00290 / 1.05856 |
| 1 mm | 1.164142 | 31.078 kPa | 1.01057 / 1.22691 |
| 5 mm | 1.297077 | 66.006 kPa | 1.09090 / 1.43070 |

The nonlinearity is directional: an average coil factor would hide a much lower
response at the other alignment. The 0.2 mm layer is above the ideal knee at
all sampled quadrature points. Its sampled peak B is 0.588 T, which is not an
unphysical claim that polarization exceeds 0.25 T: above saturation, B still
increases through the mu0*H term. These are ideal-law periodic results, not
hardware measurements or finite-area bearing loads.

### Actual five-magnet static job

The finer-magnet Q1 GetDP trial passed the unchanged bare-field gate at 4.591%
against Magpylib but its nonlinear stack timed out after 1800 s. The last logged
nonlinear residual was 0.01194, far above 1e-9; no stack output is accepted.
A separate retry used Newton relaxation 0.7 and a 7200 s timeout, reusing only
the byte-identical, region-validated mesh. It received SIGKILL before completion;
the last nonlinear residual was 0.02665 after five iterations, not 1e-9.
Material laws and all residual, field/force and force-floor gates are unchanged.
Neither failed job supplies a finite-array force prediction.

`project_static.py --quarter` now verifies exact x/y mirror symmetry before
clipping the geometry. It is restricted to the scalar GetDP formulation, with
natural zero-normal-flux symmetry planes and Dirichlet only on the spherical
exterior. Full signed fields are reconstructed on the **original full closed-air
force surfaces**; no guessed force multiplier or relaxed gate is used. Tests
verify unchanged quarter volumes and mirror reconstruction against the original
five-magnet Magpylib array. Mesh validation checks both physical symmetry planes
and the spherical exterior. `post_project_force.py` records and preserves this
reconstruction for independent quadrature refinement. A real supplied-project
quarter mesh passed physical-volume, spherical-exterior and symmetry-plane
validation, including 1011 x-plane and 2447 y-plane nodes. Its first invocation
failed to load Gmsh's shared library; the explicit library-path retry is separate.
The one-PM full/quarter comparison now passes: bare/stack vector differences
1.475% / 1.193%, maximum normal-force difference 0.110%, with identical physical
models and checked original input/field hashes plus successful receipts. The
quarter bare field is within 0.741% of Magpylib. Its nonlinear solve took 53.7 s,
nine iterations to 4.60e-12, and passes the unchanged force-path/empty-stack
controls. `results/getdp-quarter-one-pm-2026-10-18.json` retains the evidence
hashes. The actual five-magnet quadratic quarter pilot ran from the
validated quarter mesh. It still requires its own field, nonlinear, force-floor,
quadrature, mesh and air-domain acceptance before a finite-array prediction.
It subsequently timed out at 1800 s in the nonlinear stack solve. Its completed
bare run agreed with Magpylib within 0.231%, but needed 570453 DOFs and reported
3402.64 MB final memory. No nonlinear force is accepted. The unchanged partial
summary, completed timeout receipt and log hashes are recorded in
`results/getdp-five-pm-quarter-timeout-2026-10-18.json`.

`audit_project_symmetry.py` independently recomputes the same parity from the
completed raw air fields and validates material volumes, sphere/plane tags,
element order, actual nonlinear residual logs and original completed-job
receipts. It captures sources before calculation and refuses changed sources
or inputs. An initial source-capture race was marked superseded, not accepted;
the frozen-source rerun passed with the same numerical results. The accepted
resource audit reports 86586→21899 DOFs and 661.84→208.059 MB in GetDP's final
log measurement, **not an independently sampled peak RSS**. The archive is
`results/getdp-quarter-raw-audit-2026-10-18.json`.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/audit_project_symmetry.py \
  --full "$SOLVER_OPT/project-getdp-local-interface-mesh" \
  --quarter "$SOLVER_OPT/project-one-pm-quarter-parity" \
  --output "$SOLVER_OPT/new-quarter-parity-audit.json"
```

`post_project_balance.py` adds a stricter force audit: it independently encloses
the stator and mover, checks each bare/self-force floor and each closed-air
path, compares direct action/reaction, and refines quadrature independently.
It never defines mover force by negating stator force. Force boxes must stay in
air, separate the two bodies and avoid the exterior boundary. This audit is
additional to symmetry parity and does not replace material/mesh/domain gates.

`post_project_exact_force.py` independently cuts each original full rectangular
force face through the archived air tetrahedra. It clips the intersection
polygons to the face bounds and integrates the affine field's quadratic
Maxwell stress with a degree-two triangle rule. This removes midpoint-surface
quadrature error for that raw field, not the underlying FEM mesh error. It
does not smooth across elements. Coincident tetra faces use the box-interior
side exactly once; all six integrated areas must match their full rectangular
areas within 1e-8 relative error. Quarter fields are explicitly reconstructed
with their signed x/y components before integration, without multiplying a
quarter-domain force. Analytic constant/affine-field tests verify individual
tractions, closed force, coincident faces and missing/duplicated coverage.

The audit retains separate stator and mover surfaces, all three clearances,
bare/self-force controls and direct action/reaction. The original 2% force
gates and absolute floors remain unchanged. Both raw solves must have
successful receipts and matching original field/formulation hashes, and the
nonlinear residual must pass before this audit can run. Its output cannot
rescue an incomplete nonlinear solve or replace mesh/domain refinements.

The original coarse one-PM quarter field **fails** these stricter independent
mover controls, even with exact integration. All force-face areas close within
2.67e-15 relative error, but the bare mover self-force reaches 0.0416 N and
action/reaction differs by 0.0422 N on the 0.2 mm path, exceeding its unchanged
0.0309 N limit. A separate 64/128 midpoint study also fails. Thus surface
quadrature alone does not explain or fix the coarse-field error. No bare-force
subtraction is applied to hide it. The stator-only and full/quarter symmetry
comparisons remain narrower checks, not complete force qualification. Archive:
`results/getdp-one-pm-exact-stress-failed-2026-10-18.json`.

`post_finite_exact_force.py` applies the same stricter separate-body controls to
the original fixed one-PM Elmer/GetDP finite-plate benchmark. It checks original
input hashes, successful solve/export receipts, nonlinear residuals and the
raw-field hashes in the original force report. Smoothed Elmer nodal fields are
rejected. Both archived fine meshes **fail** the new mover controls. Their
exact stator normal forces still agree within 0.72%, but GetDP fails mover-path
sensitivity and the 0.4 mm reaction check; Elmer fails its mover self-force floor,
path sensitivity and all three reaction checks. Full force-face areas agree to
6.67e-15 relative error, so the additional failure is not missing surface area
or midpoint integration. The measured results and unchanged thresholds are in
`results/finite-backend-exact-stress-failed-2026-10-19.json`. Earlier stator-only
force agreement is retained as a narrower check, not a mover-force prediction.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/post_project_exact_force.py \
  --work "$SOLVER_OPT/project-one-pm-quarter-parity" \
  --output "$SOLVER_OPT/new-exact-stress-audit.json"
```

`--z-stretch` is an experimental anisotropic mesh construction, disabled by
default. It stretches CAD Z while meshing, then divides every node's Z by the
same factor **before** invoking the physical PDE. Polarization, BH laws, source
strength, air radius and force surfaces never change. The original scaled mesh
is retained. OCC dilated-sphere faces have approximate CAD tolerances, so only
tagged exterior nodes within 0.1 micrometre of the original sphere are projected
back onto that exact sphere. An interface mistakenly tagged as exterior is
rejected, not projected. Final material volumes, exact exterior-node radius
and symmetry-plane coordinates must pass the original unrelaxed validators.

The first one-PM trial was rejected before solving because OCC's enlarged face
bounding boxes excluded a symmetry face from the selector. The corrected
selector expands only the CAD entity query; the final physical plane tolerance
stays 1e-10 m. Unit tests also cover shared magnet-size aliases, inverse node
coordinates, unchanged element tags and refusal to overwrite prior meshes.
The supplied-project corrected mesh passes region/exterior/plane checks with
12531 nodes and 72994 elements. The first corrected one-PM/array solves and the
near-knee study were interrupted without final receipts; their original partial
files and hashes are retained in `results/interrupted-workers-2026-10-19.json`.
A fresh supplied-project solve converged at residual 3.67e-10 in 21 iterations,
with 92802 DOFs and 710.32 MB solver-reported final memory. Its original
stator-only controls pass, but the exact separate-body audit **fails** mover
self-force, path and reaction controls badly: bare mover self-force is
0.763–0.964 N and reaction imbalance 0.768–0.976 N against about 0.024 N limits.
All six surfaces have full area coverage to 1.02e-14 relative error. Stable
stator-only force near 1.194 N is not an accepted finite-array attraction.
`results/five-pm-stretched-force-controls-2026-10-19.json` records the distinction.
The finer near-mesh solve is running with unchanged physical inputs and gates.
This is not yet accepted as field/force mesh convergence or a qualified
finite-array result.

`--far-mesh` separates far-air element size from exterior radius. The default
remains radius/6 for backward compatibility, so older radius studies that used
the default must not be called independent far-air-resolution studies. In a
new domain study hold `--far-mesh 0.01` fixed while increasing `--radius` from
0.06 to 0.09; separately halve `--far-mesh` at fixed radius. The override changes
only global maximum and background exterior mesh targets, never geometry,
near-solid targets or materials. Mesh reuse still requires byte-identical GEO
inputs, and full/quarter parity rejects different far-air controls. Prepared
meshes are not accepted as solved field or force refinements.

`--magnet-face-mesh` adds a separate local target at the actual magnet/air
interfaces, without changing the magnet dimensions, remanence, material laws,
far-air target or original stack refinement. Artificial quarter-domain mirror
cuts are excluded. Thin bands on both sides of each interface receive the
target, and the global minimum is lowered only enough to permit it. As with
`--mesh`, this is the X/Y meshing-coordinate target; restoring `--z-stretch 4`
divides the physical Z spacing by four. The 0.2 mm-interface supplied-project
mesh passes unchanged material-volume, exterior and symmetry checks with
67942 nodes/411409 elements. This is only mesh preparation, not qualification.

`--bare-only` runs just the successful prescribed-PM/free-space control, then
stops with `completed-bare-field-only-unqualified`. The separate
`post_project_bare_force.py` measures exact closed-surface mover self-force
before committing to an expensive nonlinear material job. It deliberately does
not manufacture a relative force gate without a completed stack result and
cannot turn a failed/partial material study into an accepted bare-only control.

`audit_project_bare_map.py` adds off-symmetry X/Y field maps on the same three
heights just below the magnet bottoms. It retains every Magpylib/FEM vector in
a hash-checked NPZ and applies the original 5% bare vector-field gate separately
on each plane. A centreline with symmetry-forced transverse components is not a
substitute for this map. This remains analytical source equivalence, not
soft-material, force or housing-current qualification.

The original supplied-project coarse field fails the first two map planes:
vector errors are 9.90%, 7.88% and 4.92% at 0.1/0.2/0.3 mm below the magnets,
against the unchanged 5% gate. Its earlier 0.798% centreline error used the PCB
midplane, farther from the source and on a symmetry line. That narrower result
does not qualify the near-interface field. Full raw probe vectors and the
failed audit are retained; hashes are in
`results/five-pm-bare-map-failed-2026-10-19.json`.

The independent 0.4 mm global-near refinement also completed, with successful
bare/stack receipts and nonlinear residual 8.87e-10 after 20 iterations. Its
2924 s nonlinear solve still fails the stricter mover audit: bare self-force
0.571 to 0.773 N and direct reaction imbalance 0.575 to 0.776 N, against about
0.024 N reaction limits. Stator forces remain 1.192 to 1.195 N, but those are not
accepted complete mover/stator attraction evidence. Off-symmetry map errors
improve to 6.20%/3.39%/2.45%; the nearest plane still fails the unchanged 5%
gate. Hashes and numerical values are retained in
`results/five-pm-near-mesh-failed-force-2026-10-19.json`.

`post_project_exact_force.py --remote-air-paths` is a separate diagnostic family,
not a replacement or relabelling of failed near-interface controls. It places
the separating faces at fixed 35%/50%/65% fractions of the physical open gap
and expands the other faces by 1/2/3 mm. The surfaces are chosen from geometry
before reading fields, remain closed and outside both bodies, and avoid ideal
magnet corners. The exact affine-field stress, three-path sensitivity, raw
bare-force and direct reaction gates remain unchanged. Physical boxes and the
path family are archived in each report. A pass on this family alone is not
mesh/domain/backend qualification, and no bare floor is subtracted.

Both archived coarse and global-near-refined fields fail this remote family
too. Direct reaction imbalances are 0.508/0.188/0.0368 N on the coarse field
and 0.392/0.141/0.0730 N on the refined field, against about 0.024 N limits.
The smallest individual bare floor is not evidence that all controls passed;
the errors do not improve monotonically at every surface under refinement.
The failed reports are indexed by
`results/five-pm-remote-force-failed-2026-10-19.json`.

The 0.2 mm PM-interface bare-only solve completed in 504 s. Its three
off-symmetry map errors are 2.87%/1.81%/1.29%, all within the unchanged 5%
analytical source-field gate. Near-interface mover self-force remains
0.450 to 0.644 N. No nonlinear stack was solved in this control, so there is no
material-force acceptance claim. The full diagnostics, probe vectors and hashes
are indexed by `results/five-pm-interface02-bare-control-2026-10-19.json`.

Adding `audit_project_bare_map.py --both-sides` reveals that the corresponding
above-PM errors are 6.01%/5.51%/6.18%, all failing the same 5% gate. These
supplemental maps do not relabel the earlier below-only result. Exact face
contributions show the top/bottom traction mismatch accounts for most of the
remaining mover self-force. Raw vectors and hashes are indexed by
`results/five-pm-interface02-top-map-failed-2026-10-19.json`.

Mesh target size and refinement support are different controls. By default,
the interface band half-width is the target size in CAD meshing coordinates.
At Z stretch 4, a 0.2 mm target therefore has only 0.05 mm physical Z half-width
before its transition. It does not cover the full top stress-plane region.
`--magnet-face-band 0.0004` instead specifies an explicit 0.4 mm **physical**
half-width on every axis while keeping the mesh target separate. Its CAD Z
extent is multiplied by the stretch before restoration. This changes only
mesh support, not material geometry, remanence or force gates. Both controls
are recorded, symmetry parity rejects mismatched bands, and new project jobs
retain source snapshots as well as source hashes. The earlier narrow-band
0.1 mm mesh also passes geometry checks with 355245 nodes/2189142 elements,
but is mesh preparation only, not a solved refinement or force qualification.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/project_static.py \
  --project star_2-layer.pmmotor --version 1 --footprint-mm 36 12 \
  --array-centre-mm 0 0 --mesh 0.0008 --gap-mesh 0.0001 \
  --radius 0.06 --far-mesh 0.01 --magnet-face-mesh 0.0002 \
  --quarter --z-stretch 4 --element-order 2 --bare-only \
  --gmsh "$SOLVER_OPT/gmsh-4.13.1-Linux64/bin/gmsh" \
  --getdp "$SOLVER_OPT/getdp-3.5.0-Linux64/bin/getdp" \
  --work "$SOLVER_OPT/new-interface-bare-control"
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/post_project_bare_force.py \
  --work "$SOLVER_OPT/new-interface-bare-control" \
  --output "$SOLVER_OPT/new-interface-bare-self-force.json"
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/audit_project_bare_map.py \
  --work "$SOLVER_OPT/new-interface-bare-control" \
  --output "$SOLVER_OPT/new-interface-bare-map.json"
```

### On-demand application reference

The application now has an explicit **Run periodic reference** action in the
backplane panel. It invokes the Rust `periodic_static_reference` reduced model
on a blocking worker, not on the UI thread. Analytical previews, finite-array
image forces, friction and driver calculations are unchanged. This is not a
native 3D FEM backend or a decision to bundle an external solver.

The Rust port uses the same vector energy, odd coupled modes, depth integration
and exact air boundary operators as the checked Python reference. A
block-tridiagonal Cholesky elimination avoids a global dense factorization.
Symmetry folds the full angular quadrature into four identical contributions
without reducing its resolution. Every request separately refines depth,
harmonics and angular samples, enforcing the existing 2% gates and 1e-9
nonlinear residual. Errors are returned instead of preview fallback values.

The panel reports field ratio, periodic pressure, sampled B, fraction above
the ideal knee and two isolated-sheet DC differential factors. The latter use
the full spatial Hessian for both alignments, not a scalar secant mu. Mirror
symmetry separates sine/cosine perturbation spaces for this symmetric PM bias;
the phase blocks agree with the full-phase Python solver. Each DC factor has
its own depth/mode/angle gate, max(0.001 absolute factor, 2% of the added factor).
These are two isolated 20 μm sinusoidal sheets at the PCB faces, **not the
imported winding**, travel coverage, an AC factor or a safe PWM ripple limit.
The panel hides results when settings change, including changes made
while a request runs, and explains why B can exceed saturation polarization.
It does not multiply pressure by finite magnet area or update a bearing load.
Browser-only mode explicitly refuses the request rather than showing a mock
reference. Unsupported multilayer and magnetic-housing cases fail explicitly.

Small-resolution Rust tests match Python thin/thick/MnZn numbers to 1e-10,
check the block solve against the assembled Hessian and check energy/gradient/
tangent with finite differences. `check_rust_periodic.py` performs a separate
four-resolution implementation-parity study, including a held-out geometry and
material override, preserving build logs, input/output and source/binary hashes:

```sh
CARGO_BUILD_JOBS=1 OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python \
  scripts/solvers/check_rust_periodic.py --release \
  --work "$SOLVER_OPT/rust-periodic-release-parity"
```

Release-build parity passed all four resolutions for thin flex, thick flex,
MnZn and a held-out geometry/material override. Maximum field/pressure/modal
difference from Python was 8.74e-14, against the 1e-7 implementation-parity
gate. Measured reference times were 1.08 / 1.66 / 3.71 / 2.22 s on this host.
The compact measured archive is `results/rust-periodic-parity-2026-10-18.json`,
with source/binary and full-report hashes. This qualifies implementation parity
with the independently checked periodic model, not a new finite-array claim.
The subsequent static-plus-differential port passed the same four cases/levels,
with maximum discrepancy 4.33e-12 and request times 1.53 / 2.24 / 4.58 / 2.57 s.
Its separate archive is `results/rust-periodic-differential-parity-2026-10-18.json`;
the earlier static-only result and source hashes are retained unchanged.
Explicit nonfinite/unresolved isolated-sheet rejection was then added. A fresh
guarded parity run passed with **all four cases and four-resolution run records
identical** to the preceding report, archived in
`results/rust-periodic-differential-guarded-2026-10-18.json`.
An unoptimized debug trial was stopped after excessive runtime under memory/swap
pressure; a desktop test-link job also timed out. Those are failed resource
trials, not accepted performance evidence. Do not run heavy 3D solves, desktop
linking and multiple reference studies concurrently on a memory-limited host.
The subsequent `cargo check -p pcbmotorgen` passed. Four browser tests now cover
missing runtime, explicit scoped results, stale completion after an in-flight
edit, and a rejected solve with no preview fallback. The subsequent full desktop
retry passed 100 tests, 5 ignored. A direct run of the compiled simulation test
binary passed 177 tests, 2 ignored, after the cargo queue/compile/run trial had
timed out. Earlier timeouts remain recorded as failures, not passing evidence.

### Nonlinear periodic time-domain check

`spectral_transient.py` integrates the full nonlinear vector magnetic-energy
equations with implicit midpoint, an attached finite conducting wall and a
sinusoidal coil perturbation. It does not freeze permeability at its DC secant
value. The attached tail's DC equilibrium is solved explicitly, since its
finite-element approximation is not exactly the old infinite-air boundary map.
Every step uses the true differential Hessian and a checked Newton residual.
The last two periods must settle within 1e-5; independent source-work/Joule
balance must hold within 2%.

The linear-limit test refines time toward the complex multilayer skin response
at 1 kHz and verifies passive mass, symmetric stiffness and power balance. A
5-period 100 kHz linear trial was not sufficiently settled to isolate temporal
error, so it supplies no time-refinement evidence. The study uses 32 periods
and tighter settlement checking rather than loosening the physics gates.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_spectral_transient.py \
  --work "$SOLVER_OPT/periodic-transient-flex02-pilot"
```

The 100 kHz nonlinear pilot completed its **time and small-signal** gates at
8 layer cells / 3 modes per phase / 128 angles / 16 wall cells. It independently
refines 64/128/256 steps per period at 1e-3 of the PM fundamental, checks the
small-amplitude tensor limit, then tries 1e-4/1e-3/0.01/0.1 amplitudes without
assuming the linearization stays accurate. At the finest time step, small-source
Joule coefficients differ from the complex tangent solve by at most 0.0031%.
At 0.1 of the PM fundamental, the largest observed loss difference is 0.139%.
This is not an accepted amplitude envelope: spatial refinement and independent
nonlinear reference data remain missing, and this pilot predates knee-crossing
diagnostics. The input amplitude is an incident
field fraction, not a winding-current or safe PWM ripple rating. Layer/mode/
wall spatial refinements remain separate requirements. This is periodic coil
excitation, not a nonlinear moving finite-housing result.

### Periodic translating-magnet nonlinear experiment

`periodic_motion.py` uses the same nonlinear energy plus finite wall, with all
retained PM harmonics translated at the requested velocity. Force comes from
the source's mechanical-position derivative, tested with finite differences;
it is not inferred by dividing Joule heat by speed. Independently extracted
mechanical work, source work and Joule loss must balance within 2%. BDF2 after
one backward-Euler startup step handles the stiff wall without relying on a
frozen magnet-bias permeability. Zero speed is a DC equilibrium, not a fake
time-dependent source.

The independent linear continuous-depth multilayer check agrees within 0.094%
loss at ±20 m/s. Reverse loss matches and force changes sign. At 128 time steps,
source-work/Joule error was 2.258%, so the trial correctly failed the 2% gate.
At 256 steps the error is 0.283%; the mechanical drag/Joule error is 0.021%.
These are linear-limit controls, not accepted nonlinear operating predictions.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_periodic_motion.py \
  --work "$SOLVER_OPT/periodic-nonlinear-motion-flex02-pilot"
```

The nonlinear 20 m/s pilot passed separate time, layer-depth, mode, angular,
wall-depth and gap-depth refinements, plus zero/reverse/slow controls. The finest
periodic result has Joule density 225250.77 W/m² and magnet force density
−11261.96 N/m² at +20 m/s. At −20 m/s, loss is unchanged and force reverses.
At +2 m/s, loss is 2413.72 W/m². These densities are normalized over the
periodic projected area, not over finite magnet faces. **Do not multiply them
by the motor's finite area to claim operating drag or loss.** This is numerical
evidence for the periodic nonlinear prototype only, with an independent linear
limit. Independent nonlinear moving-FEM agreement, near-knee transient evidence
and finite edges/slots/return paths remain unqualified.

New traced studies retain the last two periods of absolute coefficient states,
Joule samples, independently differentiated force and source-work samples in
hash-checked NPZ files. Existing trace files are never overwritten.
`audit_motion_trace.py` recomputes the actual nonlinear equations and BDF2
derivative from those states, instead of trusting reported power totals. It
refuses failed/incomplete studies, changed physics and changed raw traces.

A separate 1 mm flex / 20 m/s smoke case observes knee crossings at 25% of its
sampled quadrature sites, with sampled B spanning 0.163–0.524 T. Its raw-trace
audit passes at a maximum recomputed equation residual of 2.29e-14, direct
drag/Joule error 0.00564% and source-work/Joule error 0.00231%. The archive
`results/periodic-near-knee-trace-2026-10-18.json` includes input/trace/audit
hashes. This is an internally checked **coarse smoke case**, not a spatially
qualified near-knee result or independent nonlinear moving FEM agreement.

The subsequent complete 1 mm near-knee study now passes separate time, plate
depth, mode, angular, wall-depth and gap-depth refinements, plus zero/reverse/slow
controls. Largest measured change is 0.155% against the unchanged 2% gate.
At the finest level 21.875% of sampled quadrature sites cross the knee, with B
samples spanning 0.154–0.528 T. Forward and reverse raw coefficient traces were
independently reprocessed through the full nonlinear equations, BDF2 derivative,
source-derived mechanical force and source-work/Joule integrals. Maximum
recomputed equation residual is 5.37e-14, drag/Joule disagreement 0.00115% and
source/Joule disagreement 0.000689%. Full source/study/trace audit hashes are in
`results/periodic-near-knee-refined-2026-10-19.json`. This qualifies numerical
convergence for this periodic reversible-law experiment, **not independent
nonlinear moving-FEM agreement or actual finite current-return geometry**.

```sh
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/check_periodic_motion.py \
  --thickness-mm 1 --require-knee-crossing --work "$SOLVER_OPT/new-near-knee-study"
OPENBLAS_NUM_THREADS=1 .magpy-venv/bin/python scripts/solvers/audit_motion_trace.py \
  --summary "$SOLVER_OPT/new-near-knee-study/summary.json" --run gap \
  --output "$SOLVER_OPT/new-near-knee-trace-audit.json"
```

FEMM cache reads now reject incomplete, nonfinite, duplicate-field or
mismatched-output cases. New jobs have running/completed/failure receipts;
failed output is content-addressed and removed from the reusable cache.
Historical complete cases can be read without inventing process receipts,
but the stricter AC qualification audit requires real successful receipts.

## Limits and distribution

The periodic static/DC, thin small-signal AC and motion-numerics results above
have their own stated limits. None qualifies actual finite motor-housing
currents at operating speed or PWM frequency, finite-geometry nonlinear moving
transients, actual-winding bias-to-tensor AC transfer, arbitrary PWM,
hysteresis/core loss, irreversible demagnetization or hardware performance.
Agreement of Magpylib and magba is analytical equivalence, not soft-magnetic
material validation. A successful PM/free-space solve is not an eddy-current
solve. Do not infer current closure from a magnetostatic snapshot.

No solver binary or third-party source is bundled with pcbmotorgen. GetDP is
GPL-2.0-or-later; Gmsh uses GPL with its published exceptions/commercial terms.
Elmer has mixed licenses: the inspected WhitneyAVSolver and core use
LGPL-2.1-or-later, while ElmerGrid and other components use GPL. The archive's
`license_texts/ElmerLicensePolicy.md` is only a summary; component notices and
dependency licenses govern distribution. An external process does not by itself
settle copyleft obligations. Windows/macOS packaging and redistribution remain
unqualified.

The external runner now creates a separate **owned POSIX process group** for
each new solver command. Timeout, nonzero exit and interrupted waits kill that
group, not unrelated processes; a SIGTERM of the main-thread supervisor is
recorded as interrupted after cleanup. A zero-exit log containing divergence
is still a failed solve, and a missing executable gets a spawn-failed receipt
rather than a stale running receipt. Linux tests exercise a real child process,
timeout, failed parent and SIGTERM of the supervisor. They verify both solver
and child have stopped. This is not evidence for Windows descendant cleanup,
threaded-supervisor SIGTERM handling, hard-killed supervisors or packaging.
New receipt fields do not retroactively qualify older jobs' cleanup behavior.
The runner rejects non-integer, boolean and PID <= 1 process handles before
sending any signal. Mocked-process tests intercept OS signals explicitly; this
guards against a mock being coerced to process-group id 1. The combined suite
passes 131 solver-helper tests after the subsequent force-path and input guards.
Saved-project field postprocessing additionally requires a completed study
status with no failures, a matching original mesh hash, a successful solver
receipt and matching field/formulation hashes. A successful child receipt alone
cannot recover an unfinished or failed overall study. Explicit bare-only jobs
cannot supply a material field. Older failed diagnostic reports remain archived
with their original source snapshots rather than being silently upgraded.

An archived `running` summary is not proof that a worker still exists. Use
`python3 scripts/solvers/job_status.py --work "$SOLVER_OPT/case"` for a read-only
liveness observation. New runner receipts record process start ticks, boot ID,
PID namespace and supervisor identity. The inspector rejects absent/defunct or
reused worker PIDs; legacy receipts without identity remain uncertain rather
than being promoted to live. Liveness does not prove forward progress or
numerical convergence. `--output` writes an exclusive-created observation and
never modifies original receipts.

At 12:26 UTC on 2026-10-19 the wide-band control had no worker despite its
`running` receipt, while the dense-knee MnZn batch had a timed-out child and no
live supervisor. Neither is accepted evidence. The separate observations are
indexed by `results/stale-workers-band-and-mnzn-2026-10-19.json`. Only the
wide-band bare control was restarted, in a fresh directory using its validated
mesh and a 900-second solver limit. No physics or tolerances were changed.

Python helper checks:

```sh
.magpy-venv/bin/python -m unittest discover -s scripts/solvers -p 'test_*.py'
```
