# Magnetic solver research

This archive belongs in the t707 PR so it reaches main before the next solver
branch is created. Keep the source-review notes with the reports, not just in a
session or an untracked worktree.

Follow-up: [Kata ytgr](https://kata.bertramdesigns.com/kata?issue=01M579582KSBCG2Q4CN30WYTGR#direct=1).
Start Elmer FEM and GetDP + Gmsh trials on a new branch after t707 is finished.

## Reports and evidence

- [Magnetic solver library assessment](../reports/Magnetic%20solver%20library%20assessment.md)
  covers magba, Fenris and sim-femm. Its supporting notes are in
  [Magnetic solver library assessment](Magnetic%20solver%20library%20assessment/).
- [Nonlinear magnetic solver options](../reports/Nonlinear%20magnetic%20solver%20options.md)
  compares existing electromagnetic solvers and the work needed to integrate
  them. Its supporting notes are in
  [Nonlinear magnetic solver options](Nonlinear%20magnetic%20solver%20options/).
- [FEMM results](../scripts/femm/RESULTS.md) contain the numerical comparisons.
  [FEMM setup](../scripts/femm/README.md) documents reproduction.

The candidate assessments are source research dated 2026-10-18, not results
from installing or running Elmer or GetDP. Recheck mutable upstream links
against pinned releases before implementation. The proposed acceptance gates
are not achieved accuracy guarantees.

Keep magba for analytical previews and FEMM for independent 2D checks. The
unresolved cases include normal-face saturation in thick plates and finite
3D housing current closure and drag. Neither proposed backend was verified
as a ready-made coupled nonlinear-bias, incremental-AC and moving-motor model.
