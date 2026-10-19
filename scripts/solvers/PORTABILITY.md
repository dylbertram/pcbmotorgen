# Running the validation tools on another computer

The repository contains source, numerical inputs, tests and compact evidence
indexes. It does not contain solver binaries, user DXF/PMMOTOR examples or the
large raw studies referenced by historical hashes. Those studies lived outside
the checkout. A hash index is not enough to reconstruct a missing raw result;
rerun a study into a new directory or obtain its original archive separately.

## Supported environment

The executable installer workflow is for **Debian 12 x86_64 Linux**. Windows,
macOS and other distributions have not been qualified. Python-only helper
tests do not require installing FEMM, Elmer or GetDP, but Linux process/display
tests exercise Linux facilities. The two display-socket tests skip when the
host has no writable X11 socket directory. Solver downloads require network access.

Host prerequisites include Python 3.11+ with `venv`/pip, Git, Rust/Cargo, C/C++
build tools, CMake, curl, tar, apt-get and dpkg. Building the desktop fixture
exporter also requires the application's normal Tauri/WebKit/GTK development
dependencies, documented in the project setup instructions. `xdpyinfo` is
required for FEMM display health; the private installer fetches it if absent.

## Python and helper tests

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

## macOS transfer status

A separate macOS report supplied after `1d314df` refers to
`scripts/solvers/install_macos.sh`, macOS process-identity/cleanup changes, and
`scripts/solvers/results/macos-arm64-free-space-2026-10-19.json`. Those actual
files/changes were not present in this working copy or the fetched remote when
the application-transfer follow-up was prepared. They must be committed and
transferred from the agent/machine that created them. The report alone does not
supply an executable installer, pinned archive hash, raw results or complete
test implementation. No placeholder installer or invented result index is
included here. Do not run the reported macOS commands until that source is
available, or treat the historical Linux results as ARM/macOS qualification.

## Future winding/finite-field coupling

The winding oracle and finite project solver do not yet share a coupled-field
request. Their coordinate origins differ: the winding fixture places PCB top at
z=0 and its first magnet at x=0, y=board_width/2; `project_static.py` places PCB
bottom at z=0 and centres the array at the explicit pose. A future coupling must
translate conductor points by `[cx-(count-1)*pitch/2, cy-board_width/2,
pcb_thickness]`, with lengths in metres and `pitch` the magnet centre spacing.
Apply the selected mover displacement once. Translation does not change signed
dL; imported physical depths remain unchanged relative to the PCB. This is a
required coordinate conversion, not evidence of validated winding/material
response.

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
