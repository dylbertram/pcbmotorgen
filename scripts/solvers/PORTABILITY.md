# Running the validation tools on another computer

The repository contains source, numerical inputs, tests and compact evidence
indexes. It does not contain solver binaries, user DXF/PMMOTOR examples or the
large raw studies referenced by historical hashes. Those studies lived outside
the checkout. A hash index is not enough to reconstruct a missing raw result;
rerun a study into a new directory or obtain its original archive separately.

## Supported environment

The original executable installer workflow is for **Debian 12 x86_64 Linux**.
An Apple Silicon diagnostic installer is described below. Windows and other
distributions have not been qualified. Python-only helper
tests do not require installing FEMM, Elmer or GetDP, but Linux process/display
tests exercise Linux facilities. The two display-socket tests skip when the
host has no writable X11 socket directory. Solver downloads require network access.

Host prerequisites include Python 3.11+ with `venv`/pip, Git, Rust/Cargo, C/C++
build tools, CMake, curl, tar, apt-get and dpkg. Building the desktop fixture
exporter also requires the application's normal Tauri/WebKit/GTK development
dependencies, documented in the project setup instructions. `xdpyinfo` is
required for FEMM display health; the private installer fetches it if absent.

### Apple Silicon macOS diagnostics

```sh
PYTHON=/path/to/python3.12 bash scripts/solvers/install_macos.sh
. "$HOME/.local/opt/solver-prototypes-macos/env.sh"
"$SOLVER_PYTHON" scripts/solvers/check_free_space.py \
  --gmsh "$GMSH" --getdp "$GETDP" --coarse-mesh 0.0003 --fine-mesh 0.0002 \
  --work "$SOLVER_OPT/new-free-space-check"
```

This uses native ARM GetDP **4.0.0**, not the historical Linux 3.5.0 binary,
and the Gmsh **4.13.1** Python wheel. The GetDP archive is SHA256-pinned in the
installer. Its hash records this download, not a separate publisher signature.
Python numerical versions remain pinned in `requirements-validation.txt`.
The installer records all resolved Python package versions outside the checkout.
It does not install Elmer or FEMM, or qualify macOS production packaging.

Use `$GMSH`, not an unrelated `gmsh` on PATH. The wheel's script uses
`/usr/bin/env python`; the installed wrapper explicitly invokes the validation
interpreter to prevent accidentally loading another Gmsh installation.
Do not rerun installation while a solver is using that installation.

macOS worker identity uses `proc_pidinfo` microsecond-resolution start times
and the boot-session UUID rather than Linux `/proc`. Real-process tests cover
timeout, nonzero exit and supervisor SIGTERM descendant cleanup on both hosts.
Liveness still does not establish solver progress or numerical convergence.
Native ARM results require their own unchanged numerical gates; historical
Linux results are not transferred qualifications.

### Read-only long-job watchdog

`watch_solver_jobs.py` monitors explicitly configured receipt patterns and
identity-checked batch supervisors. It reads job receipts, summary/log file
activity, recent error output and descendant CPU/RSS once per minute. It never
signals/restarts a worker or edits numerical evidence. Twenty minutes without
file activity and little observed CPU triggers investigation; active CPU with
quiet files is reported separately, not declared a failed solve.

The current watchdog writes `latest.json` and change events beneath
`$SOLVER_OPT/solver-health-watch-coreless-20261020`. It follows the housing-motion
chain until its supervisor finishes or the user's window ends around
2026-10-21 03:20UTC. The original two-chain watchdog correctly alerted when
the user-scoped5mm ferrite study was intentionally cancelled; its observations
remain in `solver-health-watch-20261020`, and that excluded chain is not
restarted. On a
new error or suspected stall it exits with an alert, so background completion
returns control to the agent. An alert is an observation, not automatic cleanup.
If it stops, inspect the alert before starting another watchdog. Do not ignore
or relabel a failed receipt merely to keep monitoring green.

The existing job supervisors' timeout values were fixed when each
`process.wait` started. Editing receipts, source or environment variables does
not extend an active deadline. Keep these workers undisturbed; longer budgets
must be chosen at a subsequent launch. Watchdog presence does not waive whole
job/numerical acceptance gates or guarantee timely completion.

On 2026-10-19, native GetDP 4.0.0 passed the cuboid gate with 0.3/0.2 mm
meshes. Mesh/domain changes were 1.195%/0.458%, against the unchanged 2%
gate. The initial 0.4/0.3 mm study failed and remains archived. See
`results/macos-arm64-free-space-2026-10-19.json`. The local helper suite passed
132 tests, including real macOS process cleanup. FEMM helper checks passed
8 tests with 2 X11 tests skipped. No FEMM solve was run on this Mac.

Optional native Elmer build, using an existing gfortran installation:

```sh
FC=/opt/homebrew/bin/gfortran bash scripts/solvers/install_elmer_macos.sh
. "$HOME/.local/opt/solver-prototypes-macos/env-elmer.sh"
```

The source archive is pinned to Elmer 26.2. The native build uses the SDK
Accelerate BLAS/LAPACK and bundled UMFPACK; no source-level physics changes are
applied. Upstream BH, air-gap force and Faraday-disc tests pass. The initial
0.25/0.20mm free-space study failed refinement; the 0.20/0.15mm study passes
unchanged gates. The finite five-PM P1 bare control still fails near-source
maps and exact self-force, so this installation is not a qualified finite
backend. Input generation supports physically restored stretched meshes with
Elmer as well as GetDP, but quarter symmetry remains restricted to scalar
GetDP cases. Native source/build and numerical evidence indexes are in
`results/native-elmer-installation-2026-10-19.json` and
`results/five-pm-elmer-bare-failed-2026-10-19.json`.

## Python and helper tests

### Optional NGSolve diagnostic environment

The reduced-source experiment used Python 3.12 and NGSolve/Netgen 6.2.2608,
with netgen-occt 7.8.1 and the pinned validation packages. Install it into a
separate environment, not over an environment running jobs:

```sh
python3.12 -m venv "$SOLVER_OPT/ngsolve-venv"
"$SOLVER_OPT/ngsolve-venv/bin/python" -m pip install \
  -r scripts/requirements-validation.txt ngsolve==6.2.2608 \
  netgen-mesher==6.2.2608 netgen-occt==7.8.1
"$SOLVER_OPT/ngsolve-venv/bin/python" -m pip check
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$SOLVER_OPT/ngsolve-venv/bin/python" -m unittest discover \
  -s scripts/solvers -p 'test_ngsolve_energy.py'
```

PyPI metadata inspected on 2026-10-20 lists Python 3.12 wheels for macOS
universal2 and Windows amd64. Their SHA256 values are respectively
`bfb0fd0acea589ed27aa893513de55a4bc428eb3c5b494c482d3d839ae9d74cd` and
`dbc1aa1d5faf70c9c3ecc5d2eaad48c882d40e8e35259ef9b7b9c84e7ba2faf1`.
Wheel availability is not a Windows execution or packaging qualification.
Source: <https://pypi.org/pypi/ngsolve/6.2.2608/json>.

The installed NGSolve and Netgen wheel licenses contain LGPL 2.1 text;
netgen-occt metadata declares LGPLv2+. These observations are not a complete
transitive-dependency distribution review. The application has GPLv3 license
text. No external engine is bundled into the application by this work.
Before distribution, retain the exact binary/source versions and required
notices, inspect dependency-specific licenses and exceptions, and establish
source/relinking obligations for the chosen distribution method. Elmer's 26.2
release contains GPL 2.0 text; its GitHub release assets inspected on that date
contain source archives, not a verified Windows installer. Native Windows
runtime, cancellation, memory limits and installers remain untested.

The current adoption decision remains offline-only. The 0.6 mm near-mesh
NGSolve nonlinear solve alone took 421 seconds on this Mac. Shared-seed GetDP
equation agreement does not establish acceptable cold-start interactive cost.
Finite DC winding response, motion and housing-current qualifications remain
requirements before a DC production integration decision. AC winding/PWM
studies are currently out of user scope and are not DC completion blockers.

### NGSolve thread control

The earlier serial setting came from the shared 4GB Linux host. It is not a
physics requirement or a macOS limit. The reduced-source, periodic AC,
periodic transient and coupled A-v executables now accept `--threads N`, or
`PCB_MOTOR_SOLVER_THREADS` as a default. They call `SetNumThreads` and run
inside an actual NGSolve `TaskManager`; changing only `OMP_NUM_THREADS` is
not equivalent. Runtime settings are recorded separately from physical mesh
resolution. The default remains one for reproducibility of earlier studies.

```sh
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/ngsolve_periodic_ac.py \
  --threads 8 --work "$SOLVER_OPT/new-eight-thread-check"
```

Keep BLAS/Accelerate pools separate from the outer task count to avoid nested
oversubscription. The macOS installer now respects caller-supplied BLAS limits
instead of overwriting them. `benchmark_solver_threads.py` checks cold-start
1/4/8/16 task-thread runs in forward/reverse order, successful receipts,
identical mesh bytes, 1e-8 field/loss agreement, wall/CPU time and peak memory.
More workers are not assumed to accelerate every sparse direct factorization.

On this 18-core / 24GiB Mac, two runs per count gave median wall times of
8.89 / 2.79 / 1.98 / 1.58 seconds at 1 / 4 / 8 / 16 workers. All meshes were
byte-identical, all runs took 17 Newton iterations, and fields/losses matched
within 1e-8. New local qualification jobs use `--threads 16`; BLAS stays one
to avoid nesting. See `results/solver-thread-performance-2026-10-20.json`.

Large FE transient jobs use16 workers; independently supervised static controls
may use2 workers alongside them. Runtime metadata records the actual choice,
not a claim that every job ran at16. These diagnostic studies still take minutes
and do not establish an interactive production budget.

The optional source cache in `quadrature_source.py` stores analytical values
at an explicitly checked integration rule, not a spatial field interpolator.
It refuses rule mismatches and checks analytical/cache values before use.
Scalar integration-point gridfunctions are filled directly; no projection or
fitted source radius is used. Off-rule field/force and endpoint-energy work
must retain the analytical source. An in-place prescribed-pose update is tested
against the full analytical nonlinear energy/tangent but is not yet a moving
material qualification by itself.

The saved winding pilot places ideal bottom-copper filaments on the nominal
ferrite interface. Its current-difference convergence does not qualify physical
differential inductance. New jobs suppress that unsupported physical quantity
and keep the computed finite-mesh difference explicitly marked unqualified.
Actual finite copper/current distribution and clearance are needed for that
quantity; copper self inductance and total terminal linkage remain separate.

The finite-DC block solver optionally accepts `--pressure-solver amg`.
PyAMG5.3.0 is installed into a separate dependency target, not over an active
NGSolve environment. The inspected CPython3.12/macOS ARM wheel has SHA256
`d7d38303310e8551ae737898577c6ec69a1ee0fa4baf95f525c86f0071d94260`;
PyPI metadata declares MIT. This does not change the licenses of NGSolve,
Netgen or the rest of the dependency stack. Other-platform wheels require
their own pinned hashes and execution checks.

```sh
export PYTHONPATH="$SOLVER_OPT/pyamg-5.3.0-arm64${PYTHONPATH:+:$PYTHONPATH}"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  "$SOLVER_OPT/ngsolve-venv/bin/python" -m unittest discover \
  -s scripts/solvers -p 'test_*.py'
```

All278 helper tests pass with that target present, including a saved-copper-
resistivity/internal-interface comparison against the full mixed direct solve.
The symmetric aggregation V-cycle is only a linear preconditioner. No pressure
LU fallback, relaxed residual gate or changed current physics is permitted.
The full winding AMG control and5.74M-DOF curvature solve now complete with
all original equation/current/power gates. The baseline takes39.1s at1.98GB
maximum RSS; the larger solve takes171.6s at3.48GB maximum RSS/5.29GB peak
footprint. These are measured offline prototype costs, not an interactive
application or cross-platform performance guarantee. The prior exact pressure
factor had336M entries and a9.09GB measured peak footprint on the1.97M-DOF
case; extrapolation rejected the5.74M-DOF factor-based retry before launch.
Native RAM is24GiB on this host; Docker's20GB limit is a separate setting.

Optional explicit nonlinear assembly and factor reuse are verified against the
original automatic-energy equations, but do not yet demonstrate a speedup.
The smoke cases took39.5s for historical automatic assembly and73.6/75.2s for
explicit/direct and explicit/PCG. Do not promise interactive performance from
fewer factorizations alone. Large incomplete retries are retained as such.
The3D vacuum-reference preconditioner changes linear iteration only, not the
material law; each direction is checked against the current full Jacobian.

An exploratory stdin probe at2026-10-20 14:13:48+0200 crashed in native
NGSolve IRDiffOp/BlockDifferentialOperator evaluation. It used vector IR storage
and a mismatched integration degree; no project was loaded. The supported
cache avoids both conditions. Never use an integration-point gridfunction as
a spatial interpolator or with an unrelated integration rule. A negative
regression now rejects the reported rule mismatch in Python without repeating
the unsafe native call. This is distinct from the earlier Netgen mesh crash.
Evidence: `results/ngsolve-ir-probe-crash-correlation-2026-10-20.json`.

From the repository root:

```sh
bash scripts/solvers/bootstrap_python.sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.magpy-venv/bin/python -m unittest discover -s scripts/solvers -p 'test_*.py'
.magpy-venv/bin/python -m unittest discover -s scripts/femm -p 'test_*.py'
```

NumPy, SciPy and Magpylib versions are pinned in
`scripts/requirements-validation.txt`. An existing environment can be used
instead, but verify its versions and run `python -m pip check`.

## Install external engines

```sh
# Optional: choose user-writable locations before installing.
export SOLVER_OPT="$HOME/.local/opt/solver-prototypes"
export FEMM_OPT="$HOME/.local/opt"
bash scripts/solvers/install_linux.sh
. "$SOLVER_OPT/env.sh"
bash scripts/femm/install_femm.sh
```

The installer pins GetDP 3.5.0, Gmsh 4.13.1 and Elmer 26.2 archives by SHA256.
The FEMM installer pins its 22 October 2023 executable archive. Debian package
versions depend on the configured repositories; download manifests record
their actual hashes. This is not a completely frozen OS image. Review the
license/distribution notes before redistributing any third-party binary.

For a stale or occupied X display, select an unused `FEMM_DISPLAY`, for example
`:79`. Do not remove an unknown display socket or kill another user's server.
Keep heavy solver jobs serial. Timeouts affect job supervision, not physics or
acceptance tolerances.

## Small first checks

```sh
.magpy-venv/bin/python scripts/solvers/check_free_space.py \
  --gmsh "$SOLVER_OPT/gmsh-4.13.1-Linux64/bin/gmsh" \
  --getdp "$SOLVER_OPT/getdp-3.5.0-Linux64/bin/getdp" \
  --work "$SOLVER_OPT/new-free-space-check"

CARGO_BUILD_JOBS=1 cargo test -p pcbmotorgen-simulation --example backplane_dump
CARGO_BUILD_JOBS=1 .magpy-venv/bin/python scripts/solvers/check_winding_oracle.py \
  --meshes 10 20 --work "$SOLVER_OPT/new-generated-winding-check"
```

The winding command uses an explicit generated fixture when no project is
provided. The native exporter test and its simulation source dependencies are
included in the repository. For your own project, provide an existing file
with `--project /path/example.pmmotor --version 0`. The Magpylib oracle rejects
backplanes rather than pretending to validate material response.

For a read-only DXF exchange check:

```sh
PCB_MOTOR_DXF_PATH=/path/example.dxf PCB_MOTOR_DXF_LAYERS=4 \
  CARGO_BUILD_JOBS=1 cargo test -p pcbmotorgen-export \
  user_dxf_import_and_exchange_preserve_copper -- --ignored --nocapture
```

For finite project jobs, read `scripts/solvers/README.md` first. Supply the
finite footprint and array pose explicitly. Never use periodic force density
as a finite motor force by multiplying it by the motor area.

The winding oracle and finite project solver do not yet share a coupled-field
request. Their coordinate origins differ: the winding fixture places PCB top at
z=0 and its first magnet at x=0, y=board_width/2; `project_static.py` places PCB
bottom at z=0 and centres the array at the explicit pose. A future coupling must
translate conductor points by `[cx-(count-1)*pitch/2, cy-board_width/2,
pcb_thickness]` before sampling the finite field, with lengths in metres and
`pitch` the magnet centre spacing. Apply the selected mover displacement once,
not once in each coordinate system. Translation does not change signed dL.
Imported physical depths must remain unchanged relative to the PCB. This is a
required coordinate conversion, not evidence that actual winding/material
response has been validated.

`export_bias_winding.py` now archives a material-bearing saved version and
exports its exact copper through a derived free-space copy. It removes only
the copy's backplane, validates conductor geometry/current/quadrature, and
checks that restoring this field reproduces the original project exactly.
`winding_coordinates.py` checks magnet dimensions, polarity and PCB thickness
before translating points. The prior 1.6mm PCB fixture cannot stand in for
the material-bearing 0.8mm saved version.

`audit_winding_bias.py` samples completed bias fields on these signed conductor
elements at the saved pose, with explicit air-side observation-limit checks.
It reports force on copper per phase ampere, not mover Kf. The magnetic stator
can carry incremental force, so do not negate the copper result and feed it
to driver analysis. Position sweeps must solve new bias fields with the
material geometry held fixed. Shifting conductor samples through one centred
field alone does not qualify a moving-magnet/backplane sweep. Evidence:
`results/fixed-bias-winding-coupling-2026-10-20.json`.

## Results and interrupted jobs

Use empty output directories; retain failed controls and original inputs.
New jobs archive source snapshots, geometry, hashes, logs and receipts.
Check an apparently stalled job without modifying it:

```sh
python3 scripts/solvers/job_status.py --work "$SOLVER_OPT/case"
```

`running` is not completion evidence. Worker liveness is not convergence or
proof of forward progress. Never accept a timed-out, interrupted, mismatched
or incomplete batch, even if some child output files exist.

The wide-band retry discussed in the historical evidence was cancelled by
the user. It has no accepted result and is not automatically resumed by any
of these tools. App UI work and browser tests were excluded from the initial
tooling commit `1d314df`. The application-transfer follow-up includes the
remaining local command guards, reference UI, stale-result handling and their
regression test sources. They are not prerequisites for offline Python checks.

## Application transfer follow-up

The initial tooling commit omitted command-layer guards even though the force
library validator was present. The follow-up includes these sources together:

- `app/desktop/src-tauri/src/commands/physics.rs`: force sweeps require explicit
  drive settings; imported driver analysis validates copper placement before
  using a backplane. Tests cover both rejection paths and matching error text.
- `app/desktop/src-tauri/src/main.rs`: periodic reference command registration.
- `app/desktop/src/lib/ipc/physics.ts` and `types/periodicReference.ts`: explicit
  drive/reference IPC and result types.
- `app/desktop/src/DocumentEditor.svelte`: failed results cannot retain an old
  sweep/Kf; backplane edits invalidate active results.
- `app/desktop/src/lib/components/design/`: reference panel, scope warnings and
  associated preview/control changes.
- `app/desktop/src/lib/ipc/{cadMapping,periodicReference}.test.ts` and
  `app/desktop/e2e/{coil-layers,driver-simulation,periodic-reference}.spec.ts`:
  regression test sources for the transferred application behavior.

The follow-up was checked for source completeness and whitespace only. Its
Rust/application/browser tests were **not rerun**: the attempted fresh build
exhausted the container's memory, and no further builds or solver runs were
started. Historical application test results are not verification of a new
machine or this follow-up checkout. Run those tests on a sufficiently provisioned
host before relying on application/backplane results.

After the Mac worktree repair, a fresh local rerun passed: simulation library
180 tests / 2 ignored, desktop host 101 / 5 ignored, frontend 436 / 1 skipped,
production Vite build, and all 21 targeted coil-layer, driver-simulation and
periodic-reference browser tests. Application sources remained byte-identical
to `22e602b`. The browser checks use Chromium/Vite and explicit test bridges,
not the native macOS WKWebView shell or actual numerical solves. Frontend and
browser runs used Node 24.18.0 after the older Playwright installer stalled on
Node 26.5.0. The build still reports its large-chunk warning. Log hashes and
scope are in `results/macos-application-regressions-2026-10-19.json`.

## macOS transfer status

When the application-transfer follow-up was prepared on Linux, the macOS
installer, process-identity changes and evidence indexes were not present there.
Those files are now present as uncommitted work in this Mac worktree. Their
installation and numerical limits are recorded above; they have not been
committed or pushed by this session. Historical Linux results are not ARM/macOS
qualification, and the external raw study archives are not included in Git.

The paused Mutagen session had propagated Git metadata from the main checkout
without synchronizing this external worktree's files. This advanced the branch
and index to `22e602b` while application files remained at `1d314df`, and copied
a Linux worktree path into the Mac's registry. The local registration was
repaired and all 14 application paths were verified against the old commit
before restoring their committed `22e602b` contents. Solver changes and root
examples were preserved. The replacement Mutagen session remains paused, uses
two-way-safe mode and excludes `.git`; Git metadata must not be synchronized
between machines. External worktrees require their own Git-based updates.

A later local consolidation moved this session and all Mac solver changes into
the shared folder `simulation-add-femm-and-improve`, on the existing
`simulation/add-femm-and-improve` branch. Its `.git` now points to the Mac's
local repository metadata, not `/home/openchamber/workspaces/pcbmotorgen`.
Both source folders and Git metadata were backed up before transfer, and files
unique to the shared folder were retained. The retired `origin-` folder is
preserved under `~/.local/state/opencode/repair-backups/`; it is no longer an
active worktree. The Python environment was recreated at the canonical path.
The moved Tauri cache contained old absolute permission paths, so it was
preserved in the backup and rebuilt rather than patched. Post-consolidation
checks passed 132 solver helpers, 436 frontend tests / 1 skipped, and both
targeted Rust drive/placement guard tests. No Mutagen sessions were modified
during this consolidation.

## Future winding/finite-field coupling

The required coordinate translation is documented in the finite-project
instructions above. No actual winding/material response qualification follows
from that coordinate convention or the worktree repair.

## Verification of the committed subset

Before committing `1d314df`, an index-only copy was checked without
the unstaged UI changes or root user examples. On the existing Debian host:

- Solver helper suite: 131 passed.
- FEMM helper suite: 10 passed.
- Native simulation library: 180 passed, 2 existing ignored tests.
- `backplane_dump` example: 2 passed.
- Generated winding oracle: meshes 10 and 20 passed independent resistance,
  current, conductor geometry and free-space force checks.
- Installer/bootstrap shell syntax and `pip check` passed.

This checks source completeness on a clean file tree, not a full installation
on a second OS image. No external FEM solver study was rerun for this commit,
and none of the unresolved finite-force or housing-current gates is thereby
qualified.
