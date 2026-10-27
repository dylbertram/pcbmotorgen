# DC evidence handoff for future rotary and imported-material support

## User-approved deferral

On 2026-10-22 the user deferred imported magnet, ferrite and housing geometry
until those inputs are supported in the app. Remaining tests specific to rotary,
rather than linear, motor designs are deferred until rotary app expansion.
Deferral changes scheduling and applicability, not numerical acceptance.

- [Rotary app expansion, pcbmotorgen#rxjp](https://kata.bertramdesigns.com/kata?issue=01M5H5P1YG5DA0KRFNJ5Q8RXJP#direct=1)
- [Deferred qualification pickup, pcbmotorgen#dtcv](https://kata.bertramdesigns.com/kata?issue=01M5H5SR5B09EGCWQ0MRJXDTCV#direct=1), child of the expansion ticket
- [Existing simulation work, pcbmotorgen#ytgr](https://kata.bertramdesigns.com/kata?issue=01M579582KSBCG2Q4CN30WYTGR#direct=1)

The imported four-layer winding is a copper-source test, not proof of rotary
topology. Circular trace primitives do not establish an angular motor model.
Generic linear-source drive-length, field accuracy and supported-geometry checks
are not automatically deferred as rotary work. They remain unverified where
needed for the linear app. Existing linear housing screening remains unchanged.

## Evidence locations and preservation

- Authoritative approvals, manifests, hashes, reports and failures:
  `scripts/solvers/results/dc-current-coupling-progress-2026-10-21.json`.
- Algorithms, limitations and command interfaces: `scripts/solvers/README.md`.
- Local archives: `$HOME/.local/opt/solver-prototypes-macos/`, especially
  `dc-imported-star4-*`. These paths are not portable installed-solver evidence.
- Branch: `simulation/add-femm-and-improve`. Implementation/evidence milestones
  include `d7b44c4`, `61adad9`, `20f5255`, `88744b5`, `2a996e8`, `dc4b926`,
  `86a16ef`, `f0b9537`, `65bedd4`, `1ac673e` and `c871221`.
- Original `.pmmotor`/DXF files, historical failures and Mutagen are untouched.
  No push or delivery bundle was created for this work.

Recheck actual input/mesh/solution hashes, archived implementations and completed
whole-job receipts before reuse. A stale `running` summary, matching element
counts, or an old watcher checkpoint is not acceptance or process liveness.

## Recorded generated-case capability that remains verified

`star_2-layer.pmmotor` version 1 uses generated routing, not imported CAD. The
recorded derived study has explicit approval for 35 µm copper-to-ferrite surface
clearance without an explicit soldermask region. Ferrite and housing moved
downward together by 52.5 µm; copper/PM positions and the 100 µm internal gap stayed
fixed. The original 2.0904250706 mm³ overlap is preserved in the historical input;
the derived BRep has zero overlap. This approval does not transfer to new designs.

All 501 eligible source sections and exact 1,707,719-cell affine RT0 export pass.
The sampled coupled matrix covers 0, ±0.1 and ±0.5 loop A, nominal/±100 µm lateral
poses, zero/linear limits, total and incremental balance, mesh/domain/quadrature/
source controls and independent magnetic formulations. The aggregate audit covers
37 magnetic jobs, 185 saved states and 44 control pairs, SHA256
`6cfab100944bc80d3312da9bd6b3f5e66b2afa3c623f56e8d643b214a1dedb9f`.
It establishes that sampled case, not interpolation, arbitrary CAD or torque.

The restricted experimental app admits exact verified requests and solves fresh
fields, never replays archived forces. A managed real saved-design solve took
94.8 s; changed-depth rejection and real numerical-child cancellation passed.
The previous full browser run passed 338/338. Those are revision-specific results,
not a new native WKWebView or portable installed-solver reproduction claim.

## Imported copper-source evidence available for reuse

The original `star_4-layer.pmmotor` version 0 SHA256 is
`6a550dcb4327a6e846582fb883c4958a0d275cba85b33271337deee405794e81`.
The offline actual-geometry snapshot SHA256 is
`2bb1eb84ffbc67a47ff7dc83a0bd986ddf315e29431fa8c06e45d1ef48b99e7a`.

The model preserves 1055 straight segments, three native circular arcs, 789
physical via spans at 396 XY positions, 393 blind gaps and three through-vias
with unlanded stubs. Traces are 127 µm wide and copper 35 µm thick. Saved depths
0, −1.6, −3.2 and −4.8 mm were not stretched to the saved 0.8 mm nominal board
setting. CAD audits pass all 393 gap windows, 789 bores and six stub sections.
The declared A-positive/C-negative screening return is not recovered cable CAD.
No imported magnetic material is coupled in this study.

Saved electrical solutions are 1 V bases, not 1 A fields. The selected spatial
source has effective loop current 0.06646553475981938 A. The earlier generated
source's separate basis current is 0.2088885882614788 A. Preserve each source's
own normalization and saved resistivity/temperature; do not cross-use them.

| Check | Verified scope/result |
| --- | --- |
| Curvature4 and spatial 0.3 mm DC sources | Original equation/current/power gates pass; spatial source has 18,239,956 mixed DOFs |
| Local sections | All 1004 active and 507 passive/arc/stub current and area checks pass; four return sections pass |
| Independent electrical formulation | Spatial mixed R = 15.0453916246 Ω; H1 R = 14.9849328049 Ω; disagreement 0.403464% under 5% gate |
| Curvature/spatial controls | Curvature R change 0.06145%; spatial R change 4.91466e-7 relative; all 1004 local spatial-current comparisons pass 2% |
| Exact spatial RT0 export | All 5,449,004 affine cells and radial terms retained; power reload error 1.93e-14; 64-cell identity error 5.27e-15 |
| Exterior integration pilot | Two explicit points 1/2 mm below entire source; analytical integration vs tetrahedron quadrature orders 2/4/6 pass 2% refinement and 5% agreement, 1e-12 T floor |
| Exterior spatial comparison | Exact matching points, raw 1 V/per-A field changes ≤1.067e-5/1.029e-5 relative; no fitted scale |
| Selected-source drive-profile gauge | Fresh solve, same 1 V line integral; full raw-current difference 4.609e-12, loop-current difference 8.438e-15; 678.8 s and 12.974 GB peak footprint |

The exterior pilots share prescribed current, not magnetic unknowns. They are
integration checks at two points, not independent coupled solves, all-near-field
or material-band qualification. Per-A normalization divides only by the measured
saved-basis current. It does not fit a correction constant.

Key spatial archives:

- Current: `dc-imported-star4-curvature4-mesh-control-v1-20261021`.
- Local reports: `dc-imported-star4-spatial03-all-active-v1-20261022.json`,
  `...-all-passive-v1-20261022.json`, `...-return-v1-20261022.json`.
- H1/reference: `dc-imported-star4-spatial03-primal-v1-20261022` and
  `dc-imported-star4-spatial03-primal-agreement-v1-20261022.json`.
- Exact export: `dc-imported-star4-spatial03-rt0-v1-20261022`. Summary SHA256
  `170bcd3c96f43b4c1af15090ae6983c49a25ff25d948ba00782ae01a4d4d56b7`;
  archive SHA256 `f2c1e35389611119adc5b7a0ace3f12350cf29d0d291d54ab97c89e1fa6631b8`.
- Exterior pilot/control: `dc-imported-star4-spatial03-exterior-field-v1-20261022`
  and `dc-imported-star4-spatial03-exterior-field-refinement-v1-20261022.json`.
- Drive profile: `dc-imported-star4-spatial03-drive-gauge-v1-20261022`.

Latest helper suite: 403 passed, zero skips, 29.597 s,
`dc-exterior-refinement-all-helpers-v1-20261022.log`. The earlier 401-test run with
one missing-pyamg skip remains preserved; corrected runs include pinned pyamg.
No application/browser suite was rerun for this documentation-only handoff.

## Failures and unfinished checks must remain visible

The coarse source passed current comparisons but failed 59 barrel-area checks.
Refinement resolves those geometric failures; original failed reports remain
failed. Preserve earlier 1800 s mesh timeouts, the 12-million-DOF preassembly cap,
the direct H1 power-balance failure and historical quadrature/solver failures.

The independent drive-LENGTH trial at port fraction 0.4 was interrupted after
264.53 s in native meshing, with no saved mesh or field. It remains unverified.
The successful drive-PROFILE test is not a replacement. This generic source check
does not become rotary-specific merely because an imported winding was used.

The older watcher also stopped at 22:05 UTC; the cause is unknown. Later shell
watchers and one-shot scheduler checks caught completions, but no uninterrupted
overnight monitoring claim is justified. At 06:41 UTC no workers or owned-group
descendants remained. The compute allocation ends at 2026-10-22 06:53:31 UTC;
this handoff does not renew it. The machine has native 24 GiB RAM; Docker's 20 GB
allowance is unrelated. The 18 GiB footprint guard is sampled protection, not a
kernel allocation guarantee. Long trials need a new adequate allocation.

## Deferred work and conditions for pickup

### Imported PM/ferrite/housing geometry

Resume after app support defines the actual import/schema/request path. Obtain
explicit materials, remanence/orientations, placements and supported tolerances.
Audit physical CAD overlap, distances, topology and FE material tagging. Present
corrections for approval; never assign material priority, repair inputs silently,
or inherit the generated-case 35 µm placement decision.

### Rotary-only qualification

Resume when the app represents rotor/stator topology, rotation axis and angular
pose. Verify actual rotary winding/return connectivity, current and power/local
controls; current magnitude/polarity/angular-pose and commutation cases; torque
and force balance; zero-current and linear-material limits; mesh/domain/quadrature/
source controls ≤2%; independent torque/force agreement ≤5% with declared floors.
Straight translation or a circular trace is not a rotary reference. Do not infer
torque, angle interpolation or actual reversal from the existing Cartesian
force/mirror-trajectory evidence.

### Common qualification before exposure

Finish relevant drive-length and broader finite-source near/material-region
controls for each admitted geometry. Preserve exact affine RT0 cells and source
normalization. Qualify appropriate nonlinear coupled and independent formulations
on explicit supported physical inputs. Recalculate app requests from actual
geometry, reject unsupported cases, and rerun affected numerical/backend/IPC/UI/
browser and cancellation/failure/stale-result tests before registration.

Differential inductance, real reversal/dynamics, temperature and hardware ratings
remain separate. Generic linear geometry generalization and any source controls
needed by the linear app remain under `pcbmotorgen#ytgr`, not marked complete
by this deferral. Existing imported circular/material DC app cases remain
explicitly unsupported until independently admitted.
