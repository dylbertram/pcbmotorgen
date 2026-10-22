# Offline solver prototypes

Kata `pcbmotorgen#ytgr`, `#04n2`, `#q9nw`, with current app work in `#d458`
and `#bs7k`. External finite-FEM jobs remain offline references. Separate
verification supports the app's experimental analytical capabilities; it does
not turn screening estimates into hardware ratings.

## Current scope: DC motor windings

### Current-driven coupling and DC03 physical decision

`audit_copper_magnetic_overlap.py --geometry-work ACCEPTED_GEOMETRY --work NEW_AUDIT --picture`
reloads the immutable finite-copper BRep and its original rectangular magnetic
envelope. It verifies input hashes, reproduces the original intersection volume,
and produces a saved-geometry projection plus a local section. It never cuts,
moves or reassigns either material. OCCT tolerance-padded bounds are reported
separately from nominal physical layer extents.

The recorded two-layer case has 35 µm copper centered at the nominal PCB-bottom
plane and a ferrite envelope ending at that plane. Their exact intersection is
2.090425 mm³; nominal penetration is 17.5 µm. No option is applied automatically.
The user subsequently approved 35 µm nominal copper-surface-to-ferrite clearance,
omitting an explicit soldermask region, and moving ferrite and housing together
to preserve their 100 µm gap. The recorded approval is
`cases/star2-v1-copper-ferrite-clearance-approval-20261021.json`.
`derive_copper_clearance_model.py --geometry-work ACCEPTED_GEOMETRY --current-work ACCEPTED_CURRENT --approval APPROVAL_JSON --work NEW_DERIVED_STUDY`
constructs that explicitly derived model without changing the copper, PMs or
original files. BRep booleans check zero overlap and exact minimum distances
for both original copper and the closed-return current-source copper. It also
checks unchanged layer volumes and internal spacing. The approved whole-stack
translation is 52.5 µm downward; ferrite top becomes Z=-52.5 µm and housing top
Z=-352.5 µm in the nominal PCB-bottom frame. The 35 µm is a nominal study input,
not a measured manufacturing tolerance or thermal model. FE interface tagging,
source coverage and coupled-field controls still require qualification.
Do not reuse the old provisional ferrite law as a hardware rating.

`audit_finite_dc_winding_sections.py --work ACCEPTED_CURRENT --output NEW_REPORT --all-eligible`
expands the historical deterministic 6-trace/12-via sample to all eligible signed
sections, keeping the same 2% saved-area and 5% independent network-current gates.
Eligibility remains explicit: active phases, a trace's longest straight piece
at least 1 mm, merged physical via locations and expected signed share above
0.05 in magnitude. This does not silently qualify excluded short/near-zero or
junction-interior fields. A running checkpoint is written every ten sections;
only the final report and whole successful receipt establish acceptance.

`export_rt0_current_source.py --current-work ACCEPTED_CURRENT --work NEW_SOURCE`
exports every affine source tetrahedron and its exact RT0 coefficients, retaining
`J(y)=mean_J+slope*(y-cell_centroid)`. Source volume, power, mean-current and
held-out polynomial identities are checked against the immutable saved solution.
No constant-cell approximation or line-current replacement is made.

`finite_tetra_current_field.py` integrates that finite source analytically via
outward triangle potentials and the divergence theorem. It rejects observations
inside/on copper and uses neither softening nor fitted radii. Unit tests compare
independent Gauss/Duffy volume integration, near-face/thin-copper geometry,
orientation/scaling and the affine term. The kernel is not a coupled solver.
`audit_finite_current_source_field.py --source-work SOURCE --material-work APPROVED_GEOMETRY --section-audit WHOLE_SECTION_AUDIT --work NEW_PILOT --orders 6 8 10`
compares it with separately refined tetrahedron volume quadrature at explicit
physical material pilot points. A passing pilot is not full-domain source-field,
nonlinear force, material, hardware or arbitrary-CAD qualification.

`finite_current_zero_bias.py --material-work APPROVED_GEOMETRY --source-work SOURCE --work NEW_BASELINE`
checks named material volumes/interfaces, the HCurl tree gauge, zero-source and
vacuum limits, and the nonlinear zero-current PM bias. Use `--mesh-only` first
and reuse that accepted mesh with `--mesh-work`. The recorded baseline passed
in 11.1 s, with a 3.46e-15 relative nonlinear residual and 2.38e-6 N force-balance
and force-quadrature differences. These are single-mesh controls, not convergence
or independent magnetic-solve qualification.

The reaction decomposition retains copper and fixed-remanence, mu=1 PMs as
separate prescribed sources. Their particular vacuum field satisfies the source
equations; the reaction energy is `W(B_source+curl(a))-B_source·curl(a)/mu0`,
up to constants. In mu=1 regions only `|curl(a)|²/(2mu0)` remains. Thus no
magnetic copper/PM interface is needed in that reaction mesh, and neither source
geometry nor winding connectivity is replaced by air. This assumes prescribed
static current, mu=1 copper/PM incremental response and the declared reversible
material law. It is not a magnetoresistance, thermal or demagnetization model.

`finite_current_tree.py` accelerates the same affine-cell source with translated
second-order volume moments and exact near-cell integration. Every observation
set needs opening refinement and direct checks; no a-priori error bound is
claimed. `audit_finite_current_tree.py` checks the existing six-point pilot.
`cache_finite_current_material_source.py --preflight-only` measures actual material
quadrature-point costs before full preparation with `--preflight-work`. A full
cache must pass 2% opening refinement at every point and 5% direct-reference
agreement at the declared deterministic spot checks. These checks do not qualify
magnetic force mesh/domain/quadrature convergence or every unsampled direct field.

The first degree-8 cache attempt crashed with SIGTRAP and macOS heap-corruption
diagnostics after both full field evaluations. The unsafe call was Python
MeshPoint-array evaluation of an IntegrationRuleSpace field: matching coordinates
do not preserve integration-point indices. `finite_current_quadrature.py` now
uses native-rule integrals, exact DOF readback and native weighted-value extraction.
Never evaluate an IR field through Python points, including nominal rule points.
The failed attempt and crash report remain evidence, not an accepted cache.
The cache writer checkpoints unaccepted arrays before native validation; an
archive alone, a running report or failed whole-command receipt never qualifies.

`finite_current_coupling.py` is a guarded offline pilot runner, not app output.
It requires an accepted full cache, matching zero-current baseline and immutable
bare finite-current PM-force reference at the exact same pose. Nonlinear current,
linear/vacuum controls and incremental balance are still required alongside
independent formulation, pose, mesh, domain and quadrature controls before app
integration. Existing housing screening and all original design files stay unchanged.

`finite_current_scalar.py` supplies an independent H1 reaction-H formulation.
The prescribed source carries all free current; only the reaction is a scalar
gradient. The reversible coenergy law is inverse to the reaction-B constitutive
law, tested at zero, linear and saturated fields. This is an independent magnetic
discretization with shared physical source data, not an independent current solve.
Use `--formulation scalar-h --scalar-order 2` in the baseline or coupled runner.
`compare_finite_current_controls.py` checks immutable input/solution/snapshot
hashes and whole receipts, then applies the 2% refinement or 5% formulation gate.
Current-induced force is checked separately from the PM bias so a large static
attraction cannot hide an inaccurate current effect. The force floor is 1e-8 N.

Recorded zero-current followup passes spatial refinement in both formulations,
degree-8/10 quadrature and 40/60 mm outer-domain checks. The refined scalar/vector
force difference is 0.7255%, below 5%; vector/scalar mesh changes are 0.5405% and
0.02284%, below 2%. These remain zero-current results only. The first revised full
source cache completed numerical checks and native storage but correctly rejected
an implementation change during its run. Preserve that failed receipt; repeat
with unchanged snapshots rather than overriding its status.

The full degree-8 source cache now passes on all 44,160 material points, with
1.917% worst opening refinement, 0.06652% direct spot-check difference and
5.93e-15 native storage error. It completed in 421.3 s. This remains a numerical
cache for one mesh/rule, not a force-convergence result. The vacuum and linear/
nonlinear vector-B pilots now pass at 0, +/-0.1 and +/-0.5 loop A. Preserve their
recorded-case scope until independent and current-dependent refinement matrices
pass. Linear current parity and current-induced balance are separate controls.

Solver supervisors reserve log/receipt names exclusively. Reusing a name fails
before spawning and cannot truncate active or completed evidence. Use a fresh
name for every retry. A loaded Netgen mesh may serialize to different bytes;
coupled jobs therefore require and reload the exact original mesh hash consumed
by both accepted source-cache and bias jobs, rather than accepting count-only
identity or comparing a reserialized copy as if it were the original.

The initial nonlinear current/polarity matrix passes independent scalar-H versus
vector-B force comparison at 0, +/-0.1 and +/-0.5 loop A. Worst total-force
difference is 1.241%, and worst current-induced difference is 0.1852%, below 5%.
This does not override the failed linear-material control: the first linear
comparison differs by about 25.3% in total force and 11.1% in current-induced
force. Both failures remain archived. Higher magnetic basis orders and physical
mesh controls are being checked without changing source geometry, constitutive
parameters, near-zero floors or agreement gates. Do not expose this pilot as a
qualified app capability until that limit and all current-dependent controls pass.
The higher-order linear vector-B order-2/scalar-H order-3 comparison passes at
1.134% total and 0.5007% current-induced difference, but scalar order-2/3 refinement
still fails at 14.76% total and 6.694% current-induced change. Agreement alone does
not override that unconverged linear control. The degree-6 material source cache
passes in 251.9 s and enables a separate degree-6/8 coupled force comparison.

Subsequent physical-mesh refinement passes at the selected higher linear orders
and at the nonlinear orders in both magnetic formulations. Refined scalar/vector
current-induced force differences are 0.0691% linear and 0.0281% nonlinear. The
40/60 mm domain comparisons and degree-6/8 linear force quadrature controls also
pass their unchanged gates. These are nominal-pose, recorded-source controls;
they do not qualify arbitrary geometry or current-driven mover poses.

`finite_current_pose_force.py` builds new bare-current force references for
0 and +/-100 um lateral PM positions from every archived affine RT0 cell, with
independent copper-Lorentz and PM-face kernels. Its runtime preflight is timing
only, not an accepted partial source. Volume checks distinguish strict mesh reload
from the existing mesh/CAD geometry check: the first attempt incorrectly used
CAD volume as the strict reload reference and is preserved as failed. Both gates
remain unchanged at 1e-9 reload and 2% geometry agreement.
`finite_current_pose_inputs.py` rejects partial, stale, wrong-pose, failed-control
or incorrectly normalized references. Coupled `--pm-offset-x` requires the exact
pose bias baseline and `--pose-reference-work`; it never replays nominal bare
force at another pose. Current-only quadrature storage is reusable only because
the copper/material observation geometry is unchanged and the PM source is
recomputed for each explicit pose. Application integration remains gated.
Pose spatial refinement now passes in both formulations, and refined independent
current-induced force differences remain below 0.053%. The tighter 0.075-opening
material cache also passes; its coupled-force controls are still separate work.
An accepted zero-current baseline may supply its exact material mesh to another
pose only after whole-receipt, model/version, mesh-hash and physical-input checks.
This avoids regenerating a nominally similar mesh or changing material priority.

`audit_dc_case_matrix.py --archive-root ARCHIVE --work NEW_AUDIT` now verifies
the complete recorded case: 37 magnetic jobs, 185 saved current states, 44
recomputed refinement/formulation pairs and all 501 eligible signed sections.
It checks job-bound successful receipts, immutable inputs/solutions/implementation
snapshots, exact source/model identity, declared current/pose/basis/rule coverage,
finite converged states and force balance. All enumerated case gates pass.
The audit covers sampled points and vector-norm gates, not arbitrary geometry,
continuous interpolation or componentwise relative accuracy near zero. Its
archived forces are evidence, never a substitute for live app recalculation.
Broader supported-geometry qualification and application integration remain open.

### Live-request preparation

The desktop command `prepare_dc_winding_geometry` now serializes the request's
actual generated or mapped imported routing, terminal choices, copper dimensions,
explicit layer depths, resistivity settings and checked electrical graph. It
emits geometry only, not force results or an implicit physical return. Curves,
splines, IO fan-out, malformed depths and out-of-cap graphs are rejected without
generated fallback or chord substitution. The IPC client has no browser mock.
This command does not claim every prepared geometry is numerically qualified.

`dc_request_contract.py` admits exact qualified-case copper/graphs, explicit finite
return/drive geometry and acknowledged disjoint material placement at the sampled
current/pose points. It independently recalculates graph currents and resistance,
checks nominal UI stack settings against the explicit material geometry/law, and
rejects unsupported changes without rounding/interpolation. Eligibility output
contains no force. `finite-dc-live-request-v1` names the recorded source basis;
`finite-dc-live-request-v2`, sent by the desktop host, names none.

Admission is per design. `dc-qualified-linear-cases-v1.json` in the evidence root
lists cases whose whole 37-job force-matrix audit passed. Write entries only with
`register_linear_dc_case.py` (`--recorded`, or `--case-audit AUDIT --case-plan PLAN`
for a declared case). Registration copies the live cache/bias/bare/pose inputs
from the audited finest-opening job receipts and verifies the entry exactly as the
worker does; entries are never rewritten. The registry is not trusted by itself:
before each request the worker re-hashes every registered audit and its evidence.

`recalculate_dc_request.py --request REQUEST --archive-root EVIDENCE --work NEW_JOB`
is the restricted live-request worker. Exactly one verified case must match the
request; zero or several matches stop with `Qualification required` and the
per-case reason before any numerical job. It reuses that case's exact-keyed,
audited finite-current basis and material rule, but recomputes the nonlinear
reaction field and forces in a fresh job. It does not replay archived forces.
Request-content changes or failed numerical/source-snapshot checks suppress
results. The numerical child inherits the outer job's process group so
cancellation cannot leave an orphaned solve.

A new design is qualified offline, never inside the 360 s app job: actual export
and explicit study/return (`prepare_linear_dc_studies.py`), exact copper
(`prepare_linear_dc_copper.py`, analytic union gate), source controls
(`plan_linear_dc_source_campaign.py`), magnetic matrix
(`plan_linear_dc_case_campaign.py`, both run by `run_linear_dc_campaign.py`), the
aggregate `audit_dc_case_matrix.py --case-plan`, then registration. Case A of
2026-10-22 took roughly 0.5 h of source work and several hours of magnetic
caches; budget each design from its own measured preflights.

The simulation dock now has a separate **Static DC (experimental)** tab. It takes
only explicit `material_model` and `return_geometry` objects, sampled current and
pose, and a fresh placement acknowledgement. No study geometry is prefilled or
silently corrected. The host rebuilds actual copper from the submitted generated
or imported design; the browser never supplies a replacement winding snapshot.
Results are separate from the existing force sweep, housing screening and driver
calculations. Changes, tab departure and unmount immediately hide old forces and
request cancellation, including a start response that arrives after invalidation.

**Check this design** is a separate, read-only applicability inspection. The host
rebuilds the active design's actual copper and `dc_applicability.py` re-verifies
the registered evidence. It reports **Qualified design**, **Preparation
required**, or **Unsupported request**, with current-source and force scope
listed separately. It never calculates or returns a force or starts implicit
preparation. Edits and tab departure discard late inspection responses. Each
inspection has a 30 s budget, owns its child process group, and stops on normal
app shutdown. Inspection and numerical jobs share the one-owned-worker policy;
neither may start while the other is active.

The recorded case's fresh-worker path and all three real saved-design inspection
paths are exercised separately from UI fixtures. New designs still need the
offline preparation and complete qualification workflow described above; this
inspection does not complete the missing in-app preparation lifecycle.

Applicability also rejects sufficient geometric proofs of non-star cross-phase
via-pad contacts. `audit_linear_dc_pad_contacts.py` records a positive-radius
contact witness inside both saved annular pads and outside every actual bore.
No witness is not a clearance pass. Other contact types still need their own
checks, and no geometry is repaired by this test.

Case B exposed why the local gates matter: the exact copper union retained 41
cross-phase pad contacts at 0.4 mm centre spacing with 0.5 mm diameter pads.
All 82 layer witnesses lie in its solved copper mesh. Global residual/power,
return-current and H1-resistance checks pass, but 500 of 504 active and 249 of
251 passive sections fail. That design is unsupported, not awaiting a finer
mesh. Its original geometry and failed/interrupted evidence remain preserved.
The source campaign planner now defaults to serial execution and requires
passing baseline active/passive/return/H1 gates before expensive refinements
or an accepted RT0-export stage.

The experimental desktop worker is disabled unless its launch environment sets
all three absolute host paths. This is a local installed-solver integration, not
a redistributed or packaged solver. Install the pinned worker into a new
virtualenv (macOS arm64, CPython 3.12; exact versions in
`requirements-dc-worker.txt`):

```sh
scripts/solvers/install_dc_worker_macos.sh "$HOME/.local/opt/pcbmotorgen-dc-worker" /opt/homebrew/bin/python3.12
export PCB_MOTOR_DC_SOLVER_ROOT="$PWD/scripts/solvers"
export PCB_MOTOR_DC_PYTHON="$HOME/.local/opt/pcbmotorgen-dc-worker/bin/python"
export PCB_MOTOR_DC_ARCHIVE_ROOT="$HOME/.local/opt/solver-prototypes-macos"
```

`check_dc_worker.py` and `desktop_dc_job.py` refuse a missing or differently
versioned package, another Python series or another platform before any job
evidence is written. Do not set `PYTHONPATH`. The archive root is required
evidence, not an optional cache. Other platforms remain unqualified.
NGSolve/Netgen are LGPL-2.1 and OCCT LGPL-2.1 with exception; this local
installation redistributes nothing.

`DcJobs` admits one numerical job at a time, preserves a unique evidence directory
under `dc-desktop-jobs`, and owns the worker's POSIX process group. The whole-job
cap is 360 s, with a 350 s nested supervisor cap. Cancellation, timeout and normal
app shutdown stop the group; late geometry preparation cannot launch after exit
cleanup. Abrupt host termination/power loss is not a qualified cleanup path.
`desktop_dc_job.py` and nested solvers inherit that same group. Failed, cancelled,
timed-out or mismatched jobs return no force. The host checks request identity and
content, successful receipt, force vector, fresh magnetic report and solution
hashes, and the selected fresh current state before publishing a result.

The explicit real-FEM Rust integration test is ignored in ordinary unit runs
because it requires the pinned external installation and original project. Run
it separately with `--ignored`; do not count the ordinary ignored inventory as
all-pass numerical evidence. It exercises a fresh saved-design job, rejection of
changed copper depths, and cancellation after a real numerical state was saved.
Browser tests use labelled UI fixtures only; those do not establish numerical
agreement or native WKWebView interaction. The panel lists registered cases and
can fill a case's audited placement/return, but acknowledgement stays a separate
user action and the copper still has to match. Native interaction remains
unproven without an observed session. No new delivery bundle is produced.

### Broader imported source qualification

`star_2-layer.pmmotor` version 1 is a **generated** routing source, not imported
CAD. Its numerical evidence is unchanged. The original four-layer imported
project is a separate, still-unqualified source. The live production command
correctly rejects its three circular primitives. The offline-only
`circular_qualification_snapshot` retains those exact three-point circles, actual
mapped routes, explicit depths and full raw via records. It is not an IPC
capability and its schema is rejected by the live force request contract.

`prepare_imported_dc_source.py --export-log SUCCESSFUL_ACTUAL_EXPORT --declaration EXPLICIT_SOURCE_STUDY --work NEW_GEOMETRY`
builds exact finite circular trace solids with OCCT arc edges, not graph chords.
The graph chord length is independently compared with analytic arc length under
the unchanged 2% geometry gate. The actual imported trace width is 127 µm,
copper is 35 µm thick, and layer depths remain 0, −1.6, −3.2 and −4.8 mm despite
the saved nominal PCB thickness of 0.8 mm. Neither the root file nor those depths
is changed to reconcile that nominal setting.

Raw physical vias, not only graph landing intervals, determine the copper. There
are 789 physical spans at 396 XY positions: 393 positions have two separate
blind-via spans with a real gap, and three full through-vias extend beyond their
electrical landings. Each declared span retains its plated barrel and annular
pads at the saved copper planes it traverses. The new path preserves gaps and
unlanded stubs. `finite_copper_eligibility.py` now rejects legacy network-only
construction that would fill a gap, shorten a barrel, omit pads or replace a
native circle by chords. The qualified generated two-layer case passes this
guard unchanged.

`cases/star4-v0-source-only-return-20261021.json` explicitly declares an A-positive,
C-negative screening return outside the saved winding. It is not recovered
cable CAD or a material-placement approval. No magnetic model or corrected stack
is added. `finite_copper_circuit.py` accepts this source-only return preparation
without requiring an unrelated unqualified magnetic trial.

`audit_imported_dc_cad.py --geometry-work EXACT_GEOMETRY --work NEW_AUDIT` queries
the saved BRep independently. It checks all 393 gap windows, all 789 drill bores,
and six isolated through-via stub sections. These are CAD controls, not current,
mesh, magnetic-force or hardware qualification. The accepted v4 geometry reuses
only hash-verified CAD from v3's post-CAD report-path failure and verifies exact
reload volume/topology and unchanged construction dependencies. It imports no
failed field or acceptance. Original failures and the earlier 240 s construction
timeout remain preserved. A single exact union of bore tools avoids repeatedly
cutting the whole CAD body; it changes the Boolean evaluation order, not the
physical holes or a tolerance.

The imported case is not registered for app forces. Current continuity/power,
local active/passive/stub controls, mesh/curvature/drive-port refinement and the
independent current formulation must pass before any coupled-field study.
The first coarse solve passes global DC gates and all 13 selected passive,
native-arc and stub zero-current checks, but two active via sections fail the
2% area gate at 3.50% and 2.32%. Those failures are preserved, not waived by the
passing global volume/current checks. Native circular controls use the actual
saved midpoint and tangent-normal plane rather than a chord section; both
active arc sections pass the current and area gates on this coarse trial.
`audit_imported_dc_zero_sections.py --all-eligible-passive` expands the initial
passive pilot before final source acceptance, retaining the 1e-8 A-per-loop
zero-current floor. Curvature-safety refinement changes only numerical boundary
tessellation, never the physical radius, plating, trace width or clearance.

The coarse imported H1 electrical reference now passes the original equation,
power and mean-current gates. Its resistance is 14.9504825942 ohm versus the
mixed source's 15.0546436682 ohm, a 0.6967% difference under the 5% gate.
This is resistance agreement on the same coarse mesh, not pointwise-current or
mesh-convergence qualification. The first direct H1 run failed power balance
at 1.9476e-8 against the unchanged 1e-8 gate and remains archived. A subsequent
run permits at most three residual corrections using the original matrix and
its existing factorization. One correction passed at 3.8481e-9. It changes no
physical input, source scaling or gate. New H1 jobs bind resistivity to the
saved geometry, hash their saved potential, and recheck input/implementation
hashes. They do not retroactively establish hashes for historical potentials.

The first imported curvature4 trial timed out after 1800 s without a saved
mesh. Its sparse checkpoint cannot identify which CAD/meshing operation stalled.
`finite_copper_curvature.py --reuse-cad-from-source-mesh --mesh-only` offers a
separate input-only checkpoint path. It checks the original source mesh bytes,
engine, retained copper/drive material partition, CAD volumes and drive centroid,
then generates a fresh tessellation of its embedded OCC geometry. It does not
reuse a current field or rebuild the drive split with another Boolean operation.
`meshing-progress.json` distinguishes CAD loading, identity and meshing stages.
Only a finished mesh-only job or verified pre-assembly resource-cap failure can
supply `--mesh-work` to a fresh DC solve. Reused mesh bytes are copied unchanged,
and all new solves consume the exact saved/reloaded mesh, never count-based
identity. A mesh-only checkpoint is not current-source acceptance.

`audit_dc_mesh_section_areas.py --source-work ORIGINAL_DC --mesh-work FINISHED_MESH_CHECKPOINT --output NEW_REPORT --all-eligible`
checks the existing active/passive/native-arc/full-stub planes before assembling
another current system. It verifies the finished checkpoint receipt, unchanged
mesh/CAD/input hashes and archived implementation, and refuses electric solution
files in that checkpoint. It applies the original 2% physical area gate and
emits no current result. A small finite-barrel regression exercises the same
geometric section integration without a current solution. A passing area check
does not establish continuity, current or power balance.

The completed full coarse audit covers 1004 active sections and 507 passive/stub
sections. All signed active-current comparisons and passive zero-current checks
pass, but 41 active barrels and 18 passive barrels fail the 2% area gate. The
worst active area error is 4.7025%, at `via:C:613`; the worst passive error is
3.9158%, at `passive-via:B:424`. The original two sampled barrel failures remain
archived. Global current agreement does not waive these 59 geometric failures.

`finite_copper_drive_profile.py` is a separate original-mesh gauge control.
It replaces the uniform isolated-port field with `6*s*(1-s)/L`, retaining an
exact one-volt line integral and identical drive geometry. The difference is
the gradient of `3*s^2-2*s^3-s`, zero at both port ends. It compares raw compatible
current in a resistivity-weighted L2 norm and unit-EMF loop current under the
unchanged 2% gate. No fitted rescaling is allowed. Its ring regression checks
current invariance; it does not establish the imported numerical result.
This control does not replace drive-length or spatial/curvature refinement.
The imported coarse gauge run now passes. The raw resistivity-weighted L2 current
difference is 3.3026e-12 and unit-EMF loop-current difference is 5.3291e-15, both
under the original 2% gate without rescaling. It took 247.17 s with a 3.05 GB
maximum resident set. This confirms drive-profile invariance on that mesh, not
acceptance of its failing barrel areas.

Daytime supervision recovery: a conversation-owned solver and its watcher were
both interrupted again after about 619 seconds. Actual process identities were
absent despite stale `running`/`watching` files. The cause is not established.
For offline jobs that must outlive conversation cancellation, use an explicit
bounded declaration with `run_declared_solver_job.py` and `one_shot_launchd.py`.
The latter bootstraps `KeepAlive=false`, `RunAtLoad=true` plists from the evidence
directory, never installs them in a login/startup directory. Solver and read-only
watcher have separate owned labels. Do not use `launchctl submit`: its probe
restarted after completion; exclusive evidence creation prevented duplicate work
and the probe label was removed. The corrected probe ran once and exited zero.
Check the command receipt, launcher report and actual service/process identities;
unload only completed owned labels and retain all evidence. The wrapper enforces
immutable input hashes, full-budget-before-cutoff and the sampled native-memory
guard. It never accepts a numerical result or retries automatically. This is not
a guarantee across logout/reboot. Independent five-minute session checks catch
ended jobs when OpenChamber is available. Production desktop jobs retain their
existing managed ownership; this offline recovery does not change app admission.

Long runs need both an explicit whole-job timeout and a background
`watch_solver_jobs.py` observation configured with their actual supervisor process
identity and receipt patterns. The read-only watcher checks receipts, new error
output, process identity and file/CPU activity, and exits with a notification
when errors or finished chains are observed. Quiet but busy native meshing is
not automatically a failure. Keep original command completion notifications
enabled too, and replace a watcher if an alert ends it while its chain continues.
The user-approved 12-hour window ends at 2026-10-22 06:53:31 UTC; subsequent
longer budgets must fit its remaining time. The first retained-CAD mesh retry
keeps its original 1800 s launch-time bound. Watcher observations never qualify
a mesh, source or force result.

The long imported curvature4 mesh finished in 2817 s but correctly stopped at
the original 12-million-DOF pre-assembly cap. Its saved mesh contains 5,433,450
tetrahedra and an estimated 18,182,843 mixed DOFs. Global volume error is 0.1443%.
The subsequent mesh-only audit passes all 1511 existing section areas, with a
worst error of 1.0790%, under the unchanged 2% gate. This resolves the coarse
area failures without changing physical copper, but does not qualify a current
field. Only verified mesh/CAD inputs, never a failed field, feed the next solve.

The fresh refined solve has an explicit 19-million-DOF budget, a two-hour
whole-job timeout and a separate completion/error watcher. It also opts into
`check_free_space.run(..., memory_limit_bytes=18*1024**3)`. This samples the sum
of native macOS `proc_pid_rusage` physical footprint in the owned POSIX group
every second. It records current/peak memory separately and kills only that
owned group on a budget breach, preserving a `memory-limit` receipt and log.
RSS is not silently substituted for footprint. The default runner is unchanged
unless the caller supplies this option. This sampled guard is not a kernel
allocation guarantee; its budget leaves 6 GiB outside the solver on the 24 GiB
host. A real subprocess regression verifies the failure/cleanup path. The
refined solve now passes global electrical and curvature-resistance gates in
1021.71 s. Resistance is 15.0453990189 ohm, changing by 0.06145% under the 2%
gate. Measured peak footprint is 12.869 GB, versus the guard's sampled owned-group
peak of 12.870 GB, both below 18 GiB. The subsequent refined checks pass all 1004
active sections, 507 passive/arc/stub sections and four return sections.
Independent H1 resistance is 14.9849381390 ohm, differing by 0.4035% under the 5%
reference gate. All original area/current gates and zero-current floors remain
unchanged. Spatial/drive-length convergence, finite-source fields and coupled
forces remain unqualified.

`finite_copper_refinement.py --source-work REFINED_DC --kind mesh --value 0.0003 --work NEW_TRIAL`
prepares an isolated spatial control using the exact source mesh's retained
CAD, unchanged curvature setting and unchanged drive geometry. `--kind port
--value 0.4` instead shortens the central imposed-field partition while keeping
physical copper and curvature fixed. It checks the CAD union and drive volumes,
uses a fresh saved/reloaded mesh and fresh unit-EMF solve, and applies the existing
2% resistance-control gate. These two modes are separate trials, not combined
changes. `--mesh-only` stops before assembly. Input-policy tests pass, but each
actual trial needs its own completed receipt and local/refinement evidence.

`audit_dc_section_refinement.py` compares completed all-eligible active reports
bound to their immutable source solutions. It requires identical physical
section labels, centres, normals, windows and signed references, plus an isolated
mesh or port axis with fixed curvature. The local-current refinement gate is 2%
of the larger current magnitude with a 1e-8 A-per-loop floor; section-area change
must also remain within 2%. The imported 0.4-to-0.3 mm spatial control passes all
1004 comparisons. The largest current difference uses 3.79% of that gate,
equivalent to a 0.0757% relative change. This does not qualify every interior
current value or the finite-source magnetic field.

The imported spatial source subsequently passes all 1511 eligible local current
and area checks, four return sections and the independent H1 resistance check,
with 0.4035% disagreement under the 5% gate. Its exact affine RT0 export retains
all 5,449,004 cells and radial terms. Reloaded power error is 1.93e-14 and the
64-cell held-out affine identity error is 5.27e-15. No filament substitution,
constant-cell smoothing or fitted current normalization is used.

`audit_exterior_current_field.py` is a separate source-only integration pilot.
It chooses two deterministic trace XY positions and places observations 1 and
2 mm below the entire saved source. Those positions do not declare ferrite,
housing, PMs or approved material clearances. Analytical cell-face integration
is compared with tetrahedron volume quadrature orders 2, 4 and 6 under the
unchanged 2% refinement and 5% agreement gates, with a 1e-12 T floor. Both the
curvature4 baseline and spatial source pass these two-point pilots in about
28 seconds each. They are not all-near-field or material-quadrature evidence.

`audit_exterior_field_refinement.py` binds those pilots to the original current
states and requires identical observations and isolated spatial controls. Both
raw saved-1V and per-loop-A vector fields must pass the 2% gate. Per-A scaling
divides only by the saved effective loop current, never a fitted scale. The
maximum spatial difference is 1.067e-5 in the raw basis and 1.029e-5 per A. No
force, saturation, imported app admission or general-CAD qualification follows.

The drive-length trial was interrupted during native meshing without a saved
mesh or current. Its watcher also stopped at 22:05 UTC; the cause is unknown.
Neither a running summary nor the old watcher proves continuous overnight
coverage. One-shot session health checks at 06:10 and 06:40 UTC supplement new
shell watchers; scheduled execution still requires OpenChamber to be available.
Keep the remaining drive-length verification distinct from drive-profile gauge
invariance, and do not extend the compute window beyond 06:53:31 UTC.
The selected spatial source's fresh drive-profile control now passes in 678.80 s:
raw resistivity-weighted L2 current difference is 4.609e-12 and loop-current
difference is 8.438e-15, both below the original 2% gate without rescaling.
Peak physical footprint is 12.974 GB. This does not complete drive-length
verification or qualify imported coupled forces.

User scope update, 2026-10-22: imported PM/ferrite/housing geometry is deferred
until supported in the app; rotary-specific qualification waits for rotary app
expansion. The evidence inventory, failed/passing controls, applicability limits
and pickup conditions are in
[`results/rotary-dc-qualification-handoff-2026-10-22.md`](results/rotary-dc-qualification-handoff-2026-10-22.md).
Kata `pcbmotorgen#rxjp` tracks rotary app support; child `pcbmotorgen#dtcv` tracks
deferred qualification. Generic unfinished linear-source checks remain separate
under `pcbmotorgen#ytgr`. Deferral does not qualify imported coupled forces.

Evidence correction: earlier 306-test helper logs included four or five skipped
tests, not 306 passes. Preserve those logs and historical delivery manifests.
A fresh explicit NGSolve/PyAMG/Rust-entrypoint run covers the omitted checks.
The packaging verifier now requires the declared unittest count to finish with
plain `OK`, rejecting `OK (skipped=...)`; `--helper-count` declares a new inventory.
This corrects future evidence claims without rebuilding historical deliveries.

### Bounded followup on 2026-10-21

### Higher-harmonic release verification

`check_housing_harmonics_reference.py` verifies the upgraded linear housing/FR4
path against independent complex P1 diffusion solves. It separately refines
depth and cross-travel sampling, retains the 2% refinement/5% agreement gates,
and checks four further odd terms against the production omitted-power bound.
Use a new evidence directory on every run. It does not replace nonlinear
shielding, finite-housing or hardware qualification.

The linear production method `linear_planar_odd_harmonics_region_joule_v2`
uses physical odd Fourier coefficients and harmonic-specific motion frequency.
It integrates region Joule loss and independently evaluates surface work for
each harmonic. Simpson sample refinement and the 15-to-30 cross-travel cutoff
comparison are separate checks. Conservative passive-admittance bounds limit
the omitted travel-source and cross-travel powers, each to 0.5% of computed
housing power with a 1e-12 W numerical floor. A bounded workload rejects cases
that cannot meet these checks. These bounds concern the declared linear
periodic source model, not finite arrays, slots, startup, or thermal accuracy.

For positive linear materials, the surface admittance has nonnegative real
part, so the reflection magnitude is at most one. With pole pitch tau, source
separation d, magnet depth D and h an odd travel harmonic, surface work is
bounded by `C*exp(-2*h*pi*d/tau)/h^2`, where
`C = N*tau*abs(v)/mu0*(2*Br/pi)^2*D`. The omitted odd series uses its first
omitted denominator and geometric exponential ratio. For cross-travel
wavenumbers above K, use `|spectrum| <= D` and
`integral_K^infinity exp(-2*d*y)/y dy <= exp(-2*d*K)/(2*d*K)`.
The implementation records both bounds and the highest included harmonic.

Magnetic shielding retains `planar_travelling_fundamental_region_joule_v1`
with explicit unresolved higher-harmonic heating and effective-DC saturation
warnings. Independent linear harmonic superposition is not promoted through
saturated shielding. Driver drag diagnostics remain fundamental-only and are
not a same-model check of upgraded housing results. The earlier fundamental
reference script and archived results retain their historical scope.

Workspace regression reproduction uses `pnpm --dir app/desktop test:workspace`
with a fresh absolute `CORELESS_BROWSER_ARTIFACTS` directory. It runs both
viewport projects against an isolated server, including imported geometry,
keyboard menus, dock scroll retention and housing request lifecycle tests.
`test:coreless` remains the smaller 100-check release subset. Browser transport
fixtures do not establish native WKWebView or numerical qualification.

`package_housing_harmonic_release.py` preserves existing delivery directories.
For a subsequent full-workspace release, pass the final `--browser-work`,
`--browser-count`, `--browser-log`, `--regression-tag`, `--build-log` and
`--startup-tag`. It rejects incomplete/flaky/skipped browser matrices and
unsuccessful command receipts, verifies numerical/reference source hashes and
root designs, and includes source/app hashes and exact receipts. Native build
source manifests and startup executable hashes are checked when supplied.
The app is a debug arm64 experimental build without developer signing or
notarization. A live startup process is not a native interaction test.
`verify_housing_harmonic_package.py DELIVERY --output NEW_RECEIPT.json` reads
every app file back from the ZIP and every source file from the tar archive,
checks complete inventories and hashes, and compares the standalone app to
the manifest. It never executes the app or overwrites prior receipts.

Kata `04yx` tracks a separate 3–4 hour reference window. Current progress is
in `results/housing-followup-progress-2026-10-21.json`; running trajectories
are not accepted from partial results.

`compare_housing_model_scope.py` maps actual PM dimensions, pitch, remanence,
material conductivity and PM-to-housing separation between the offline
PCB-bottom coordinate convention and the app's PCB-top convention. Removing
ferrite from a housing-only comparison does not move the housing upward.
The finite reference must have completed control evidence whose input hash
matches the selected trajectory. Centre-region instantaneous finite losses
remain distinct from the app's established steady periodic estimate; a
full-entry/exit average is never used as steady drag.

`housing_spectral_diagnostic.py` independently solves linear planar P1
diffusion for odd travel harmonics through15, with separate depth, sample,
cross-travel cutoff and series checks. It rejects magnetic/conducting shielding
rather than silently linearizing it. This diagnostic does not change the app
or supply a fitted correction. Initial held-out narrow-magnet/small-gap cases
show28–32% more heat with these harmonics than with the fundamental alone.
The production5% quadrature check therefore must not be read as a physical
accuracy bound or as convergence of the omitted source harmonics.

`audit_material_motion_mirror.py` checks two complete x-symmetric nonlinear
short strokes with opposite constant speeds. Housing and ferrite longitudinal
forces are checked separately from their vector norms, so a large static
normal attraction cannot hide a drag failure. A mirrored run is not a
start/stop/reversal cycle with retained state. `audit_housing_followup_time.py`
checks the housing-only full-stroke time pair using the original2% heat/work,
force-history, stored-energy-history and endpoint gates.

Program scope is coreless PCB motors with at most3 backplane layers, each
no thicker than2mm, not a2mm total-stack cap. All housing walls are at
most5mm. Current housing scope is aluminum and nominally non-magnetic
annealed304/316 stainless; ferromagnetic steel1018 and magnetic430 stainless
housing are deferred. Magnetic ferrite shielding remains in scope.
Housing gap is at most10mm, magnet count at most12 and PCB copper layer
count at most16. These are user-confirmed input bounds, not a statement that
every configuration inside them is already qualified. The
UI/backend/typed-JSON entrypoint guards implement this envelope; legacy
research scripts retain their historical mathematical cases and are not app
support declarations. No further monolithic5mm ferrite studies should run; historical
evidence is retained, not a current completion requirement. The desired100C
temperature ceiling means absolute temperature, not a100C rise. Thermal
assumptions and predictions must remain explicit and must not be clamped to
that desired ceiling. The shielding cap does not limit PCB thickness.

The user has explicitly excluded AC winding excitation for now. Do not start
new periodic/PWM/envelope or AC-loss studies as part of completing this work.
Historical AC evidence and failures are retained below, but are not current
completion gates. The remaining owned AC queue was stopped, with its inputs
and interrupted receipt preserved.

Focus is saved-file finite copper geometry, DC current distribution/resistance,
static saturation/fields/forces, DC linkage and differential inductance, and
separate motion-induced housing effects. Copper dimensions come from PMMOTOR,
including trace width, via drill/annulus/plating and layer weight. The actual
finite geometry and bounded DC solve are indexed in
`results/dc-finite-copper-progress-2026-10-20.json`.

### Experimental housing motion and heating

The user wants theoretical motion-induced housing eddy-current drag and heat
generation as opt-in experimental capabilities that improve over time, with
explicit model assumptions and declared numerical targets. Hardware rating claims are deferred until a
future prototype. Initial app integration now exists; it does not relabel
failed strict-reference studies as passed or qualify arbitrary finite housing.

Keep application numerical targets separate from the offline reference gates. Coarser
mesh/time resolution is acceptable only with explicit applicability limits and
reference checks. Failed solves, lost current continuity, negative dissipation
or broken energy checks must still be rejected. Low-Rm source-only results
cannot be scaled to operating speeds where magnetic feedback matters.

Report drag, heat-generation power and motion-profile energy distinctly.
Temperature rise additionally needs explicit heat-capacity/mass and cooling
assumptions. The existing fast application drag-power estimate is for the
whole conducting stack; do not relabel it as housing-only heat without a
per-region loss calculation or a verified housing-only conducting case.
AC winding excitation, PWM, skin/proximity and core loss remain excluded.

The opt-in setting is `DriveSettings.housing_motion: { duration_s }`.
`target_speed_m_s` supplies the constant travel speed. The result is the tagged
`analyze_housing_motion` command returns a tagged `experimental` estimate or
`unavailable` reason without numbers. The UI owns an independent request
lifecycle: driver delta/current-loop compatibility cannot block PM-induced
housing physics, and late responses cannot replace a newer request. There is
no fabricated browser substitute when the desktop backend is absent. The
optional `DriveBackplane.housing_motion` diagnostic remains available for
consistency checks but is not the UI's request dependency. Disabled/missing
settings preserve the previous driver-analysis contract.

`backplane/housing_motion.rs` integrates each conducting region's electric
field, including magnetic feedback. Housing Joule power is not the total
stack loss. It verifies region-loss sums against independent boundary work
and refines the cross-travel spectral integral. Housing drag is a steady
power-equivalent opposing contribution, not a separately qualified body force.
Energy means an established steady field maintained for the declared exposure,
not a transient entry/exit/stopping simulation. Conductivity remains at its
room-temperature material value; there is no temperature output or thermal
feedback. Finite housing edges, slots and full moving nonlinear shielding
remain outside this planar model.

The field source here is the moving PM array. Winding-current reaction and
induced PCB-copper shielding are omitted. Under that explicit assumption,
changing only the winding pattern does not change housing heat if PM/PCB/
backplane/housing inputs stay fixed; routed copper still determines the
electrical and force calculations. This is not a reference-geometry lookup.

An independent complex P1 diffusion FEM matrix covers12 material/geometry/
speed cases, including all4 supported housing materials, maximum wall/gap/
magnet/layer input values, reversal and conducting-backplane loss partition.
It passes2% reference mesh refinement and5% Rust/FEM region-loss agreement;
maximum observed difference is0.122%. This qualifies only the declared
periodic-planar operator, not finite-housing or hardware accuracy. Raw evidence
is `$SOLVER_OPT/housing-motion-independent-planar-v2-20261020`; the first
attempt's final provenance writer failed on a string/path mismatch and remains
failed, with the corrected whole-job rerun stored separately.

```sh
CARGO_BUILD_JOBS=2 cargo build -p pcbmotorgen-simulation --example housing_motion_dump
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/check_housing_motion_reference.py \
  --binary target/debug/examples/housing_motion_dump --work "$SOLVER_OPT/new-housing-reference"
```

Run through `check_free_space.run` for a whole-job receipt. Browser tests in
`e2e/housing-motion.spec.ts` verify opt-in rendering, separate housing/stack
labels, pending/error invalidation and input controls with explicit transport
fixtures; they do not substitute for the independent numerical tests.

## Installation

For Apple Silicon diagnostics see the [macOS portability instructions](PORTABILITY.md#apple-silicon-macos-diagnostics).
That installation uses native GetDP 4.0.0 and requires fresh numerical checks;
it does not inherit the Linux 3.5.0 qualifications below.

An optional native serial Elmer 26.2 build is now available through
`install_elmer_macos.sh`, with a separately installed Fortran compiler. Its
three upstream magnetic tests and a refined free-space study pass, but its
first full five-PM bare control fails near-source maps and self-force. See
`results/native-elmer-installation-2026-10-19.json` and
`results/five-pm-elmer-bare-failed-2026-10-19.json`. Installation is not force
qualification, and no nonlinear five-PM job is accepted from that control.

## Handover review follow-up

### Interrupted-work reporting and finite-source progress, 2026-10-20

No worker remained running when the apparently stuck run was inspected. The
GetDP continuation was failed/interrupted, and a standalone force audit still
said `running` despite its supervisor receipt saying `interrupted`. The original
records were preserved. New supervised Python jobs receive their authoritative
receipt path, and force reports link it. `job_status.py` can inspect standalone
reports with `--summary`, and historical reports with an explicit `--receipt`.
An interrupted receipt overrides a stale or prematurely completed report; an
explicit whole-job receipt is not mixed with unrelated trials in a shared prefix.

Force postprocessing now checkpoints each complete surface. A fresh bounded
audit reused 18 matching quadrature units from the interrupted audit, recomputed
the six missing units, reran every gate and finished successfully in 121 seconds.
This does not relabel the interrupted job as accepted. The original source,
mesh, nonlinear solution, physics-code hashes, surface coverage and quadrature
settings were verified before reuse. No new FEM solve was started for recovery.

The centred five-PM nonlinear source/response case now passes the original
surface, bare-floor, action/reaction and quadrature gates. Stator force is
1.189–1.190 N and mover force about −1.186 N, with 0.24–0.33% imbalance. This is
numerical consistency on that fixed provisional-material case, not hardware
accuracy or full motor qualification. Independent mesh/far/domain and converged
cross-backend checks remain separate. See
`results/finite-source-response-progress-2026-10-20.json`.

The review found a pending-request Kf race missed by the earlier rejection-only
browser test. It was reproduced before the fix: a changed bus voltage reached
driver analysis with the previous sweep's Kf while the replacement sweep was
still pending. Simulation-generation changes now invalidate thrust/Kf and
driver state immediately. All 22 targeted browser regressions pass afterward;
see `results/pending-kf-race-review-2026-10-19.json`.

### Explicit GetDP equilibrium and controlled refinements

The legacy GetDP `SolveJac` log label "Nonlinear Residual norm" is a relative
solution-update proxy, not an assembled equation residual. Historical evidence
retains its original labels. `getdp_equilibrium_check.py` instead certifies
`||b-A*x||_2`, normalized by the full-source residual at zero response, at 1e-9.
The centred case passed at 1.2341e-10 after two updates. Its initial guess came
from NGSolve. `getdp_initial_guess.py` verified that P2 transfer over all 43,117
elements, with maximum gradient discrepancy 5.50e-15 T. Transfer alone does not
solve or certify any equations.

The resulting GetDP force audit passes the unchanged surface and quadrature
gates. `compare_reduced_fields.py` also passes the unchanged 5% cross-backend
gate for total fields, material-response fields and all six force paths.
Maximum probe-set discrepancies are 0.000983% for total B and 0.04145% for the
material response; force differences are below 0.8 microN. Both backends share
the source, mesh, material law and initial guess. This checks their separately
assembled equations, not cold-start convergence or hardware accuracy.

The 0.8/0.6 mm near-mesh comparison passes the 2% field gate, including the
material response, whose largest probe-set change is 1.807%. Its finer force
audit timed out after 22 complete surface integrals. A new supervised audit
verified and reused those units, computed the two missing units and reran all
gates successfully. The full mesh comparison passes for all six force paths,
with maximum force change 0.000905 N. The original timeout remains unaccepted.
Far-air refinement also passes the unchanged field/force gates. The expanded
domain cold start timed out at 650 seconds and remains unaccepted. A separate
same-physics initial-guess retry converged in 17 updates to a relative equation
residual of 2.64e-15. The expanded 60/75mm domain comparison passes all unchanged
field/force controls, including the material response at 1.363% maximum change
and all six force paths with maximum change 0.000761N. This completes those
numerical controls for the single fixed static case, not other poses/materials
or a coupled winding/motion solve. Shared-seed provenance remains explicit.
See the dated progress index for completed
evidence and outstanding work:
`results/reduced-equilibrium-and-refinement-2026-10-20.json`.

Direct GetDP evaluations at 32 off-symmetry air-cell interiors match the archived
affine reader to 3.56e-15 T. This rules out that export/reader path as an
explanation of the large self-force, not the FEM discretization itself. Both
root PMMOTOR v0 windings pass independent 10/20/40/80 resistance, sparse-current,
signed trace/via sample and prescribed-source force checks. The four-layer DXF
also passes read-only copper-preserving import/exchange. None establishes
nonlinear winding response; the compact evidence is
`results/getdp-export-and-winding-review-2026-10-19.json`.

New project jobs snapshot the actual input project and validate source/input
hashes **before** publishing a completed status. A changed input or analysis
cannot leave a completed comparison behind after raising an error. Explicit
far-air controls now disable CAD curvature sizing: the stretched sphere's pole
curvature otherwise introduced a hidden radius-dependent size cap. Legacy
geometry without `--far-mesh` remains unchanged, and old failed trials are not
rewritten or reused as if generated with the corrected control. Helper tests
cover these changes. Finite forces, actual winding/material response, finite
housing motion/current closure, MnZn AC agreement and deployment qualification
remain open.

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

`ngsolve_eddy_av.py` adds an independent 3D reaction-A / conductor-potential
implementation, including induced magnetic feedback. It has a coupled weak-disk
pilot, zero-source and frequency-reversal controls. A separate sphere reference
matches the spherical-Bessel interior field to vacuum and cross-checks dipole
source work against volume Joule heating. Coarse strong-diffusion sphere trials
fail the unchanged 5% reference gate despite passing equation and power checks.
An order-2 Coulomb-gauged trial timed out. A tree gauge, checked against Coulomb
at both low and higher order using identical quadrature, completes the sphere
reference. Separate mesh/domain/quadrature controls pass unchanged 2% gates;
final loss agrees with the coupled analytic solution within 0.316%. Magnetic
feedback reduces loss to 58.55% of the weak-induction result, so this is not just
another negligible-reaction check. These are benchmark qualifications, not
finite motor predictions. The disk/slotted and moving-PM studies remain separate. See
`results/coupled-3d-av-progress-2026-10-20.json`.

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

### Coupled translating-PM housing baseline

`ngsolve_housing_motion.py` now advances a finite 3D nonmagnetic housing with
translating analytical cuboid PMs. It solves reaction A and charge potential
together, including magnetic feedback at Rm=22.6 rather than extrapolating a
weak-induction snapshot to 20m/s. The first model explicitly excludes ferrite
and winding, retaining their original geometric spacing. It is not a full
motor prediction.

The 24mm / 20m/s baseline passes independent time, mesh, domain and quadrature
controls, plus zero/reverse controls and the independent closed/slotted weak
limit. The coarse 24/48 time pair fails stored-energy convergence at 4.834%;
the finer 48/96 pair passes the unchanged 2% gates. Exact source-work accounting
includes stored magnetic energy instead of imposing steady drag/Joule equality
at entry/exit. A separate postprocessor reconstructs current from saved fields
and calculates PM force from magnetization/Biot-Savart face integrals. It does
not negate a conductor result. At three snapshots, independently extracted
PM and total housing forces agree within 0.00060N, passing original force and
quadrature controls without subtracting the housing self-force term.

The tested single-sided 0.5mm slit removes 0.694% of metal volume and gives
7.25% less heat over this short profile. That is not a general slot rating.
Whole-array 120mm entry/exit profiles now complete their equation/current/energy
and reverse/weak-limit checks, with PMs starting and ending beyond the housing.
The closed case dissipates 0.02953J over this pass; the slotted case 0.02801J.
Their full-path average includes travel outside the housing and is not a steady
drag rating. Separate full-stroke 480/960-step and 1.5/1.2mm mesh checks now pass
for both closed and slotted housings. Force histories, heat/source work, complete
stored-energy histories and endpoints retain their unchanged 2% gates. Source
current/PM interaction forces also pass independent entry/centre/exit extraction
for both full profiles; worst total balance error is 0.075%, a numerical metric,
not hardware accuracy. Source
currents and magnetic fields remain self-consistent, but nonlinear ferrite,
actual winding returns and hardware validation remain open. Evidence:
`results/finite-housing-moving-pm-progress-2026-10-20.json`.

`ngsolve_vector_static.py` is the next nonlinear-coupling prerequisite. Its
full-vector B-energy solve with exact tree gauge agrees with the separately
qualified scalar-H response: maximum material-response field difference 2.95%,
force difference 0.000072N, both within the unchanged 5% reference gate. Volume
magnetization force and its source-derivative quadrature pass 2% controls.
This static check is not yet moving ferrite/current feedback. See
`results/static-vector-material-progress-2026-10-20.json`.

`ngsolve_material_motion.py` now builds the full ferrite/metal geometry and
solves its nonlinear static bias before any time stepping. The reversible
two-slope energy and automatic tangent are spatial vector laws. Mechanical
source work includes the ferrite position derivative as well as current work;
neither a frozen secant permeability nor Joule heat alone is substituted.
The source-position derivatives are checked against finite differences.
The zero-motion pilot retains the real 1.19N-scale static ferrite interaction
while producing exactly zero eddy heat/current force. Its initial failed
zero-control exposed lazy-vector FMA roundoff, corrected by subtracting equal
states before derivative scaling rather than relaxing current gates. A moving
20m/s pilot is separate and unaccepted until its whole receipt and energy
checks finish; even then refinement/force controls remain. Evidence:
`results/nonlinear-ferrite-housing-progress-2026-10-20.json`.

The first moving nonlinear trajectory timed out after 60/96 steps at 900s.
It remains unaccepted; a separate full rerun has a 2400s cap. The completed
full-domain static material PM-force audit passes volume and source-derivative
integration checks. Separate static mesh, remote-air and tetrahedral-quadrature
controls are now dispatched; the comparison also checks the scalar-H reference.
Those jobs and force audits completed, but the coarse full-domain air mesh
fails response-field convergence: up to 18% mesh/domain changes despite less
than 0.36% total-field changes and stable integrated forces. The independent
material-response check therefore rejects the mesh rather than letting the
dominant PM source mask its error. Quadrature refinement passes. Explicit
air refinement around the PM/ferrite observation region is required next;
the earlier quarter-domain Gmsh vector comparison remains separate evidence.
The96-step nonlinear moving rerun and independent near-centre PM-force audit
have now completed. Integrated source-work/heat/magnetic-energy mismatch is
0.0018%; the force kernels include current and nonlinear material contributions
separately. The coarse mesh failure still prevents qualification of those
operating numbers. No failed or interrupted trial was promoted to completion.
`audit_material_motion_controls.py` keeps the nonlinear dynamic controls separate
and compares current and material force histories individually, plus magnetic
energy changes rather than a potentially masking static energy offset.

`closed_winding.py` checks a physically closed balanced two-phase circuit from
the saved trace/via resistor graph plus explicit external-return waypoints.
`closed_wire_source.py` supplies off-wire Biot-Savart B and Coulomb A, checked
against an independent polyline kernel, curl(A) and compiled/NumPy agreement.
`ngsolve_winding_static.py` is an unqualified nonlinear current-response pilot.
It must finish before its independently extracted mover-force current
differences or material differential linkage can be used even as numerical
evidence. It does not negate copper force to obtain Kf, and reports only the
material contribution to differential inductance, not a total L from 2W/I^2.
The external return is an archived screening scenario, not recovered cable CAD.
See `results/closed-winding-current-progress-2026-10-20.json`.

`ngsolve_material_air_static.py` adds a vacuum mesh partition around all PMs
and material bodies, extending2mm beyond them. It keeps the exterior gauge
boundary remote and introduces no artificial field boundary at the partition.
Pinned geometry tests verify exact ferrite/metal volumes and both vacuum tags.
New1.2/0.9mm local/material mesh,40/60mm remote domain and degree10/12
quadrature jobs are separate unaccepted trials until their audits finish.
See `results/material-local-air-progress-2026-10-20.json`.

The independent nonlinear periodic FE and spectral implementations now agree
at one0.1%-of-PM-fundamental ripple in spatial phase0: loss differs by0.0585%,
within the unchanged reference gate. Both full-nonlinear absolute traces were
reassembled and checked, not replaced by tangent harmonic equations. This is
single-amplitude agreement, not a qualified amplitude envelope. Separate
nonlinear time/space/source/quadrature checks and1% ripple/both-phase trials
remain unaccepted. `audit_ngsolve_transient_trace.py` checks FE absolute traces;
`compare_periodic_nonlinear.py` requires completed audited implementations;
`audit_periodic_nonlinear_controls.py` rejects mixed refinement axes.
See `results/periodic-mnzn-independent-progress-2026-10-20.json`.

The0.1% phase0 nonlinear spectral time/depth/mode/angular controls and FE
time/lateral/depth controls have now completed and passed their original gates.
Every compared trajectory first passed its absolute-state equation audit.
A1% spectral trial failed8-period settlement at2.29e-5 versus the unchanged
1e-5 limit. Separate24-period retries retain the same physics and mesh/time
settings; neither failure nor the larger-amplitude envelope is accepted.

The uncached winding-current sweep timed out at1800s after archiving only the
zero-current state. A process sample located prescribed wire-field evaluation
inside automatic-differentiation tangent assembly. `quadrature_source.py`
stores the fixed unit-wire source at the exact declared integration points,
with bitwise-matching quadrature and analytical/source-cache checks. Energy,
gradient and the full material tangent match the uncached formulation in tests.
This is not a spatial field interpolator or a frozen material law; force and
off-rule field integration still use the analytical source. A separate cached
trial is unaccepted until its whole receipt and current-difference checks finish.
That cached trial has now finished all five equilibria in440s on two workers;
independent mover-force current differences and material-only linkage current
differences pass their step-refinement checks. These remain one-mesh pilot
outputs, not operating Kf or inductance ratings. In particular, the saved bottom
copper centreline coincides with the model ferrite interface. A filament there
does not resolve finite copper width/thickness or actual clearance; fixed-mesh
current-step convergence must not be mistaken for physical inductance
convergence. No source radius or material constant is fitted to fix this.
`wire_pm_linkage.py` also checks reciprocal free-space PM linkage against the
independent current-to-PM force kernel. Nonlinear pose/linkage and total winding
inductance qualification remain separate.
Four additional zero-current pose jobs translate only the PMs by +/-100um and
+/-50um. All four and `audit_winding_reciprocity.py` now complete: the full
PM-bias linkage position derivative agrees with the independent mover-force
current derivative within0.0554%, passing the unchanged2% consistency gate.
Pose-step and PM-volume-quadrature controls also pass. Copper, ferrite, return
routing and mesh stay fixed; off-axis or mixed-model pose changes are rejected.
This one-mesh reciprocity does not replace the pending spatial controls.

The first local-air equilibrium now passes the scalar-reference field gate:
maximum material-response discrepancy is3.92%, below the unchanged5% gate.
Mesh/domain/quadrature qualification remains separate. The exterior field can
also be reconstructed independently from integrated volume magnetization with
`material_source_field.py`; no field is evaluated inside its source material.
That baseline reconstruction differs from the scalar reference by at most1.33%
and passes its own source-volume quadrature control. Raw A-curl and both
reconstructed maps are archived, not corrected by subtracting a failed floor.
Neither single-case comparison substitutes for mesh/domain controls.

Those exterior-source controls have now completed. Reconstructed static
response fields change by at most0.0808% under mesh refinement,0.0307% under
domain expansion and0.000661% under quadrature refinement. PM forces also pass.
Each case separately passes the scalar-reference and source-volume checks.
This qualifies these exterior outputs for the centred prototype under the
unchanged2%/5% gates. The raw A-curl interpolation still fails4.6%/4.9%
mesh/domain response changes and remains unqualified; it is not relabeled by
the reconstruction. Interior fields/tensors and moving/current regimes remain
separate qualification work.

`wire_material_contacts.py` quantifies the nominal interface-source issue:
79 active ideal-wire segments, totaling0.365m, lie on the declared ferrite
boundary. This is not a measurement of actual copper surfaces. New winding jobs
return null for physical material differential inductance in this unsupported
case, retaining the finite-mesh current difference under an explicitly
unqualified diagnostic key. Tests verify that Kf diagnostics remain separate.

Explicit full constitutive gradient/tangent assembly and checked Newton-factor
reuse reproduce the original nonlinear FE smoke trajectory to about1e-10.
They did not demonstrate a speedup: historical automatic assembly took39.5s,
versus73.6/75.2s for the explicit/direct and explicit/PCG examples. Their
unfinished large retries were preserved and stopped, not promoted to results.
The default remains full automatic energy assembly with fresh Cholesky.

The3D material-motion tool can import an immutable completed mesh/equilibrium,
re-solve/check the new start pose, and update exact material-quadrature PM
source values at every midpoint. `--reuse-newton-factor` uses a vacuum
curl-curl/unchanged conducting-mass factor only as a preconditioner. The actual
full nonlinear Jacobian is updated and its linear residual checked each time;
no physical permeability is frozen. Its generalized material contrast is
bounded by mu_max, unlike a rotating first-iterate tangent. The full coarse
96-step retry, assembly-equivalence and independent-force audits completed.
It did not improve runtime. On the locally refined-air mesh the short-stroke
24/48-step time control also passes, but moving spatial/domain controls and
full-profile qualification remain required.

The saved copper now has finite200um-wide,35um-thick traces,500um via pads
and hollow300/350um-ID/OD barrels. The complete export has533 trace edges,
393 via positions and one connected solid. No root input or layer depth is
changed. Its finite extents reveal2.09mm^3 overlap with the previous nominal
magnetic envelope; this is reported, not hidden by a new gap. Geometry alone
does not qualify current distribution or inductance.

`finite_copper_current.py` uses compatible HDiv current and cellwise potential,
with exterior zero flux and internal conductor interfaces left open. Closed
annulus resistance and direct/block-solver equivalence tests pass. The first
full winding mesh reaches1.97M mixed DOFs and correctly stops at its800k cap
before assembly. The separate block-MINRES retry retains the physical mesh and
original equation/continuity/power gates; its pressure graph factor is only a
preconditioner, not a fitted resistor-graph current replacement.

A fresh linear-geometry solve with a central straight drive port now passes
the unchanged equation/current-moment/power gates. Its loop resistance is
4.79103 ohm at the saved75C temperature. An independent H1 potential solve
on the same mesh gives4.75738 ohm, within0.71%. This is a source-formulation
comparison, not independent geometry or hardware validation. The old port
overlapped widened return bends and drove local circulation. Curved-mesh
retries also failed the current-moment gate. Those failures remain archived.

`audit_finite_dc_controls.py` checks completed receipts, hashes, isolated mesh
or port changes, and resistance gates. `audit_finite_dc_sections.py` intersects
linear tetrahedra with explicit planes and clips the section geometrically.
Four straight-return sections reproduce the imposed loop current. The saved
trace/via probes in `audit_finite_dc_winding_sections.py` compare signed
currents against the independent winding resistor graph. All18 sampled
currents pass the5% reference gate, but three barrel sections miss the saved
area by2.36–2.81%, failing the2% local geometry gate. Whole-volume agreement
of0.366% therefore does not qualify this mesh. The0.15mm global refinement
now passes resistance convergence with a relative change of3.03e-7 and retains
0.71% primal agreement, but two local barrel-area failures remain unchanged.
`finite_copper_curvature.py` changes curvature safety2 to4 on the same CAD,
global size and DC physics to target this tessellation error. A saved-radius/
plating barrel test passes. The full curvature mesh has1.71M tetrahedra and
5.74M estimated mixed DOFs, so the3.5M cap correctly stopped it before assembly.
A geometry-only diagnostic now puts all18 sampled sections within2% of saved
areas, but no current solution exists on that mesh. A memory-control rerun
tests native face adjacency and released sparse-copy buffers on the original
mesh. It reproduces the mesh and DC result, but its336M-entry pressure factor
still exceeds the extrapolated memory budget, so the larger factor-based solve
was not started. A symmetric multilevel pressure-preconditioner control now
passes on the original mesh and the full5.74M-DOF curvature mesh, with original
equations/gates unchanged. The larger current solve took171.6s with3.48GB
maximum RSS and5.29GB peak footprint. All18 sampled winding area/current
checks pass; maximum barrel-area error is1.46%. Curvature resistance change
is0.0791%; independent primal agreement is0.4116%. These checks do not
establish all local interior fields or finite nonlinear magnetic coupling.
The separate0.5/0.4 straight-port control
passes with a resistance relative change of1.56e-6 and0.71% primal agreement;
the historical coarse local via-area failures remain failed. Neither finite-source magnetic coupling
nor physical self/differential inductance is qualified by these DC checks.

For archived completed jobs, run audits through `check_free_space.run` to
retain whole-job command receipts. Use new output paths for every attempt:

```sh
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/audit_finite_dc_controls.py \
  --first-work "$SOLVER_OPT/finite-copper-star2-v1-dc20-linear-20261020" \
  --second-work "$SOLVER_OPT/finite-copper-star2-v1-dc20-linear-primal-20261020" \
  --kind agreement --output "$SOLVER_OPT/new-dc-resistance-check.json"
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/audit_finite_dc_winding_sections.py \
  --work "$SOLVER_OPT/finite-copper-star2-v1-dc20-linear-20261020" \
  --output "$SOLVER_OPT/new-dc-winding-section-check.json" --threads 2
```

The second command currently fails the retained local via-area controls.
Evidence and exact hashes are in
`results/dc-finite-copper-progress-2026-10-20.json`.

`audit_finite_dc_pm_force.py` provides a separate bare PM/current interaction
control using streamed finite-volume current sources, analytical PM-face
Green kernels and the conductor Lorentz integral. It refines tetrahedral body
quadrature and reproduces current/power/volume observables. Ferrite, housing,
current self-field and inductance are excluded. Passing integrated force
checks cannot override failed local copper-area controls. The base audit
completed: independent PM/copper force balance is2.70e-13N and body-quadrature
force change is9.93e-10N. The finer-mesh force audit also completes and passes;
its per-loop-current force differs by1.81e-6 relative under global mesh
refinement. The curvature-mesh audit also completes, with independent force
balance4.43e-13N, quadrature change5.00e-10N and relative per-loop-current
force change8.64e-6 from the0.15mm global mesh. These are bare PM/current
interaction controls, not nonlinear ferrite/housing, self-field or inductance
qualification. They do not validate experimental housing motion/heating
capabilities or establish hardware ratings.

```sh
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/ngsolve_housing_motion.py \
  --source-work "$SOLVER_OPT/reduced-near06-bare-20261020" \
  --sigma 25000000 --speed 20 --span .024 --steps 96 \
  --mesh .0015 --far .06 --air-mesh .01 --threads 16 \
  --work "$SOLVER_OPT/new-coupled-motion"
```

### Low-speed charge-potential comparison

`finite_current_closure.py` now solves the saved prototype's actual finite
36x12x1mm nonmagnetic housing volume with NGSolve electric potential and
insulating walls. It compares closed and one-sided 0.5mm slotted geometries.
It uses only the analytical PM field. Neither induced magnetic reaction nor
the ferrite response is included in this particular diagnostic.

At 0.001m/s and 25MS/m, Rm is 0.00113. Mesh and independent quadrature
refinements pass the unchanged 2% gates. Zero/reverse-speed controls,
uniform-field charge cancellation, isolated-volume current, assembled
continuity residuals and mechanical/Joule power balance pass. A curl-free
linear-gradient source agrees with an independent rectangular streamfunction
Fourier-series loss within 0.0023%. `compare_finite_current.py` rotates the
existing independent SciPy resistor-grid oracle into the same physical
geometry. Its own refinement passes, and loss/force agree within 0.42% for
both closed and slotted housings. Required receipts and archived inputs are
checked before accepting either comparison.

At 20m/s, Rm would be about 22.6. This tool rejects Rm above 0.01. Do not scale
the low-speed loss or drag into an operating-speed prediction. The remaining
work needs coupled magnetic reaction and a moving-field/transient check.
Evidence: `results/finite-housing-lowrm-2026-10-20.json`.

```sh
"$SOLVER_OPT/ngsolve-venv/bin/python" scripts/solvers/finite_current_closure.py \
  --source-work "$SOLVER_OPT/completed-reduced-response" \
  --sigma 25000000 --speed .001 --bonus-order 8 \
  --work "$SOLVER_OPT/new-finite-housing-closure"
```

### Historical single-PM diagnostic

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

An independent 2D triangular FE implementation is now in
`ngsolve_periodic_ac.py`. It solves nonlinear PM bias with reaction vector
potential, then uses the full local differential-reluctivity tensor in a
separate complex coil-response solve with finite conducting wall. The analytic
PM field stays DC. `periodic_spectral_study.py` regenerates separate spectral
resolution controls, and `compare_periodic_ac.py` checks the FE controls before
cross-backend comparison. These tools require the optional pinned NGSolve
environment. They do not add an application dependency.

The first FE comparison passed diagonal responses and losses, but an extra
cross-phase check exposed numerical coupling from the mesh/integration setup.
Reflection-symmetric triangles alone did not remove it. Closing each triangle
rule under all six barycentric permutations preserves its degree/weight and
removes the pilot's artificial coupling without subtracting a failed term.
The unchanged 1e-8 cross-phase gate now passes throughout the corrected FE
mesh/source/domain refinement study, with maximum coupling 7.53e-15. Both
phase responses agree with independently refined spectral calculations; loss
errors are below 0.057% after the additional quadrature-order refinement. The
quadrature check also passes the unchanged 2% gate. The fine cold-start job hit its 180s cap and remains
unaccepted. Separate same-physics initial-guess jobs completed the fine and
expanded-air checks. Original failures and preliminary comparisons are retained, not
promoted to final evidence. See
`results/periodic-mnzn-independent-progress-2026-10-20.json` for current status.

The original failed FEMM MnZn comparisons below remain failed. A new FE versus
spectral agreement cannot explain or rewrite those missing raw Linux studies.

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

### Historical on-demand application reference prototype

The initial portable-tooling commit included the Rust reference library and
CLI validation, but not the later periodic-reference Svelte panel, IPC command
registration or stale-result UI changes. Commit `22e602b` supplies those files;
the Mac worktree repair restored their committed contents. The UI/browser
results below describe the original server workspace, not fresh verification
of this checkout. A subsequent fresh Mac rerun passed the Rust/frontend suites,
production build and 21 targeted browser regressions. See
`results/macos-application-regressions-2026-10-19.json` for logs and scope;
this does not qualify finite motor physics or the macOS WKWebView shell.

That application prototype had an explicit **Run periodic reference** action in the
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

The later Apple Silicon transfer did not include that raw directory. A fresh
native GetDP 4.0.0 control on 2026-10-19 used Gmsh 4.13.1 and the same explicit
0.2 mm interface target / 0.4 mm physical band settings. All six above/below
Magpylib maps pass the unchanged 5% gate, with worst error 2.622%. Exact closed
mover surfaces still give **0.462–0.465 N bare self-force**. The wider band fixes
map coverage but does not justify a nonlinear material retry or force acceptance.
Surface stability is not correctness. The fresh mesh is not byte-identical to
the missing Linux mesh, and both platform and GetDP version changed. Full raw
inputs, source snapshots, logs, receipts and audits remain outside git under
`$HOME/.local/opt/solver-prototypes-macos`. The compact index is
`results/five-pm-wideband-macos-force-unqualified-2026-10-19.json`.

A single finer 0.1 mm interface control held the physical band and all other
mesh controls fixed. It reached 3,934,366 DOFs but timed out at the 900-second
cap during `GenerateJac[S]`, before producing a usable field. Owned-worker
cleanup was verified. Its unchanged `running` summary is not progress evidence:
the inspector reports `incomplete-with-failed-child` from the timeout receipt.
No self-force convergence result or OOM diagnosis is inferred. Evidence is in
`results/five-pm-wideband-face01-macos-timeout-2026-10-19.json`.

Python helper checks:

```sh
.magpy-venv/bin/python -m unittest discover -s scripts/solvers -p 'test_*.py'
```
