# Linear-drive move power model

Implementation and historical evidence for pcbmotorgen#7744. Current behavior
is described in **Design-goal independence, v4** below. That section supersedes
the earlier design-limit gating and rejection interpretation. Earlier sections
remain as a record of what was implemented and tested, not current requirements.

## Supported model

### Generated three-phase spacing correction, 2026-10-30

Confirmed the generated two-layer star had the same 60-degree directed phase
axes as the imported Fader. Root cause: the infinity braid translated equally
oriented phase windings by `pole_pitch / 3`. This is one 60-degree phase belt,
not a 120-degree equal-polarity phase separation. The generator now uses
`2 * pole_pitch / 3` for three phases, with no terminal-polarity reversal or
fitted motor constant. For a 6 mm pole pitch, starts are 4 mm apart rather than
2 mm. Within-phase strand spacing stays `pole_pitch / (phases * strands)`.
The complete staggered end span is reserved before choosing connected complete
periods, so the corrected layout remains inside the configured board.
Other phase counts retain their previous placement; they are not newly qualified.

Generated phase-band positions now reach the routed static force commutation
law instead of being lost to its legacy analytic 60-degree fallback. When CAD
exchange omits the sidecar, three-phase routed MaxThrust uses an explicit
balanced 120-degree current law. Legacy independent-coil analytic fixtures are
unchanged. Exported/imported copies of the same new copper agree again.
This also supersedes old imported static-force results that used unbalanced
independent-coil currents. The supplied Fader copper itself is not regenerated
or modified and still has its original noncanonical phase layout. Its explicit
balanced-star move calculations are not silently converted to new geometry.

Regression coverage includes three strand counts, signed unit-terminal force
axes, zero-sum star currents, neutral/lead connectivity, strict routing bounds,
delta/closed lead construction and generator/CAD parity. The new generated
star force-map offsets are 70.4602°, -49.5403°, -169.5338°, with residuals below
0.005° from a common 120-degree sequence. Evidence:
`scripts/solvers/results/generated-star-commutation-2026-10-30.json`.

All six saved-design/control moves were regenerated with fresh loss models and
unchanged 2% energy/peak refinement and balance gates. The generated star v1,
1.6 mm PCB, 0.2 mm width/1 oz, original 90-degree reference now estimates
10.5056 W peak / 6.49745 J net for the full move, and 5.56903/5.57500 W peak
for short forward/return. Full source peak is 0.875468 A and required maximum
line voltage is 5.83679 V, with no modeled voltage finding. These are results
for **new generated copper**, not improved numbers for the unchanged imported
four-layer Fader. The regenerated Fader control retains its 0.8 mm scenario
37.6338 W peak at 90 degrees. Model version v6 records the implementation change.
Receipt: `scripts/solvers/results/practical-move-generator120-2026-10-30.json`.

Independent verification used reconstructed nodal currents, R and trace/via
dL with Magpylib cuboid fields at 20/40 conductor subdivisions. The first two
attempts exposed batch-size-dependent SciPy/Magpylib identity-rotation output;
their failed evidence remains in approved temp `generator120-oracle-20261030`
and `generator120-oracle-v2-20261030`. The final oracle evaluates the same
public functional cuboid field in bounded batches, tested against scalar
object results and repeated arrays larger than 33,000 points. No reference
force or tolerance was fitted to Rust output. Final 20/40 checks passed with
force-vector refinement 0.000896 N below the unchanged 2% gate. Accepted full
report: approved temp `generator120-oracle-final-20261030/summary.json`, SHA-256
`6ae643a40540b79bec65e44e7d29dea3b2fae626acd3adae1a40a54a3c13ceab`.
The earlier successful v3 report is retained as an intermediate checkpoint.
This is free-space prescribed-magnet validation, not material/hardware qualification.

The old generated driver-reference numbers were replaced only after the new
geometry's independent check. The geometry-specific equilibrium test now pins
the corrected 120-degree charge state and explicitly unbracketed legacy planar
rest fallback, rather than requiring the old 60-degree braid's rest point.
The known layered/imported travel-equilibrium limitation remains open.
A one-ULP backplane repeatability failure now uses the existing tested 1e-13
numerical-repeatability helper, with physical positive controls retained;
energy, force-reference and convergence tolerances were not changed.

Final affected Rust suites: 504 passed, 22 unit and one documentation test
ignored. Frontend full suite 554 passed/4 skipped, native-receipt mapping
17 passed separately; Svelte check/build pass; ten Python formula/audit tests
pass. Additional DFM/export suites passed 206 tests, with one optional user-file
and two documentation tests ignored. Supplied archive/DXF hashes remain unchanged. No push or supplied-file
rewrite, and no nonlinear or long external-solver campaign was performed.

### Commutation alignment and copper-width check, 2026-10-30

User clarified the requested copper is **0.2 mm trace width with 1 oz copper**.
The imported Fader already has 0.2 mm source width, and both inner/outer copper
are 1 oz, approximately 35 µm. CadBoard uses that imported width, not the
configuration's unrelated 0.127 mm minimum. No width or copper-weight change
was needed or simulated. The comparison retains the explicit 0.8 mm PCB scenario.

`scripts/solvers/audit_move_commutation.py` audits signed unit-terminal force
maps, without changing wiring or tuning geometry/force constants. On the
geometry-selected interior interval 14.5–50.5 mm, three electrical periods,
a DC+sine+cosine regression finds phase sine offsets A=69.9248°, B=9.9269°,
C=-50.0707°, amplitudes approximately 0.09704 N/A, and R² above 0.99997.
The directed axes are 60°, not 120°, apart under the saved terminal convention.
Thus the actual winding/mapping polarity and conventional balanced-star current
law are not a canonical match. A single reference angle cannot remove that.
Mathematically reversing B would produce 120° spacing with the opposite phase
sequence, but this is not a
verified hardware wiring correction and was **not** applied. Phase polarity,
mapping and physical star connections need review before changing any winding.

The positive-sequence fundamental of the existing signed map gives electrical
zero 2.2676493455876967 rad, or 129.9267°, versus the test scenario's 90°.
This is a geometry-derived fixed-reference diagnostic, not an actual controller
calibration or an optimal-current controller. The interval is selected from
full-overlap bounds and electrical period, not from desired power or force.
Using that reference, with every other Fader baseline input verified unchanged,
gives the following explicit imposed-motion scenarios:

| Move, 0.8 mm PCB | Peak W at 90° | Peak W at 129.93° | Net J at 90° | Net J at 129.93° |
| --- | ---: | ---: | ---: | ---: |
| Full forward | 37.6338 | 12.4062 | 10.3766 | 4.35611 |
| Short forward | 2.68357 | 3.32011 | 0.504599 | 0.557689 |
| Short return | 2.76087 | 3.41449 | 0.511402 | 0.569642 |

The full move source peak is 1.03385 A; move-average power 4.35611 W; drawn
equals net and returned energy is zero. Required line voltage peaks at 9.76837 V,
so this scenario has no modeled 12 V tracking conflict. This is not proof of
achieved motion, thermal suitability, controller implementation or winding
qualification. Short moves worsen at the new reference because the residual
noncanonical phase geometry makes coupling position-dependent. Do not present
the reference as a universal efficiency improvement.

All six diagnostic/control scenarios passed independent balances and unchanged
2% energy/peak refinement gates. Real-native export mapping now checks the
actual feasibility result rather than incorrectly assuming every full move
must have a voltage conflict. Python regressions recover known 120° axes,
detect 60° axes and distinguish a hypothetical polarity reversal from an
electrical-zero change. No supplied design/default settings were modified.

Evidence: `scripts/solvers/results/fader-commutation-audit-2026-10-30.json` and
`scripts/solvers/results/practical-move-alignment-2026-10-30.json`. Full receipts
are in approved temp `move-alignment-{baselines,models,results}-20261030`.
Reproduce the harmonic audit from the prior 0.8 mm full-forward receipt, then
run the existing baseline-export command with explicit
`PCB_MOTOR_FADER_PCB_THICKNESS_M=0.0008` and
`PCB_MOTOR_FADER_ELECTRICAL_ZERO_RAD=2.2676493455876967`, followed by the same
fresh-directory builder/native/refinement/export commands. The star2 controls
remain unchanged. Named loss-model exclusions and friction assumptions remain.

### User-requested 0.8 mm Fader PCB scenario, 2026-10-30

An explicit test-only `PCB_MOTOR_FADER_PCB_THICKNESS_M=0.0008` override changes
the Fader scenario configuration, not its archive or app defaults. Every other
baseline input was checked equal to the 1.6 mm corrected-Z run. The two-layer
star control stays unchanged. Regenerated the loss declaration from the new
native R/L analysis; no old geometry-bound coefficients were reused.
Physical Fader layers are now -0.8, -0.5333333, -0.2666667, 0 mm. The same
63 mm/1 s and 1 mm/0.25 s quintic moves, pi/2 phase reference, 50 mN friction,
15 g mover, 75 C winding, 12 V/100 kHz and 47 µH per phase remain explicit.

| Fader move | 1.6 mm peak W | 0.8 mm peak W | 1.6 mm net J | 0.8 mm net J |
| --- | ---: | ---: | ---: | ---: |
| Full forward | 56.5753 | 37.6338 | 15.2938 | 10.3766 |
| Short forward | 3.85262 | 2.68357 | 0.717165 | 0.504599 |
| Short return | 3.96737 | 2.76087 | 0.727275 | 0.511402 |

The 0.8 mm full scenario has 3.13615 A sampled positive source peak and
10.3766 W move-average power. The short forward/return averages are
2.01840/2.04561 W and source peaks 0.223631/0.230073 A. All three have zero
returned energy, so drawn equals net. Full peak falls 33.5% and net energy
32.2%. Phase R falls only about 0.6%, from approximately 4.86 to 4.83 Ω;
the main benefit is stronger coupling to the now-closer lower layers.
The full move still requires up to 19.011 V line voltage, above the 12 V link.
It remains imposed demand, not achieved motion or a board/current rating.
Short cases have no voltage tracking finding. This does not validate the
pi/2 phase alignment or the friction estimate, nor resolve omitted losses.

The three Fader cases and unchanged star controls passed the same independent
energy balances and 2% time/force-map energy/peak convergence checks. Seventeen
native-receipt report/export tests and six Python formula/summary tests passed.
Receipt `scripts/solvers/results/practical-move-pcb08-2026-10-30.json` records
the thickness and explicit override. Full receipts are in approved temp
`move-pcb08-{baselines,models,results}-20261030`. Reproduce using the earlier
export/build/evaluate commands with this explicit Fader-only environment override
on the baseline-export command and fresh output directories. Supplied files
remain unchanged; this scenario does not switch the user's active saved design.

### Simulation height audit after the PCB correction

Audited the active desktop simulation entry points, not just move power:

| Path | Height source and audit result |
| --- | --- |
| Static force sweep | CadBoard physical layer hints, then routed current-weighted Lorentz samples. Scaled source Z and already-placed Z give equal force. |
| Driver resistance/inductance | Same hints for trace heights, via lengths and Neumann integrals. Scaled and already-placed source results agree for R and effective L. |
| Copper heat preview | Same CadBoard hints. Added a public-command regression checking every trace/via sample against the DC snapshot layer heights, plus software-thickness edits. |
| DC geometry, live coupled DC and coil B field | Host rebuilds via prepare_dc_winding_geometry before worker requests; workers consume physical geometry_hints, not raw CAD Z. No external solver launched. In-app imported source preparation remains explicitly unsupported. |
| PM-only B-field grids and 3D PM field | Sample requested physical XYZ with PCB top at zero and magnet height from air gap. No CAD-layer-height dependency. |
| Housing motion and stack calculations | Housing separation uses configured PCB thickness and air gap. Imported placement validation uses CadBoard hints. |
| 3D copper and heat mapping | Proportional physical layer placement from configured thickness, added in 1b30eb8. |
| Travel envelope/equilibrium | **Outstanding limitation.** physics::travel_envelope generates coils without CAD input; equilibrium/charge.rs builds legacy conductor samples in one Z=0 plane. It is not an actual layered/imported Fader equilibrium calculation. Do not treat its rest positions as qualified by the corrected force/move results. |

The heat visualization implementation fingerprint now includes cad_source.rs,
so layer-placement implementation changes alter provenance. The coordinate text
now discloses imported-Z scaling. This audit does not fix the separate legacy
travel-envelope geometry model or qualify old external solver caches.

### PCB layer placement correction, user clarification 2026-10-29

The configured PCB thickness is authoritative. Raw imported DXF Z values encode
relative layer spacing, not the physical board thickness. This supersedes the
earlier interpretation in this document that the Fader's -4.8/-3.2/-1.6/0 mm
source heights must be used directly by physics. For every motor CAD board the
placement is now `(source_z - max_z) / (max_z - min_z) * pcb_thickness`.
A single layer is at zero. Layer indices, relative spacing, XY copper and
terminal connectivity are unchanged. The supplied archive/DXF bytes are not
edited. The Fader's 1.6 mm PCB therefore uses -1.600, -1.0666667, -0.5333333,
0 mm copper heights. Changing the software PCB thickness changes this placement.

The same CadBoard placement feeds force, winding resistance/inductance, via
lengths, heat visualization, DC geometry snapshots and move power. The 3D viewer
and power report use the same proportional placement. Raw input geometry remains
in exported inputs; native move notes record the physical heights. Move model
version is now `linear-move-demand-v5`. Older raw-Z results are historical and
must not be reused as current Fader evidence. Changed DC geometry requires fresh
hash-bound qualification; no external qualification campaign was run here.

Regenerated all six cases using the same trajectories, pi/2 phase reference,
50 mN friction, 15 g mass, copper/PWM/driver/inductor assumptions and convergence
gates. Receipt: `scripts/solvers/results/practical-move-zfix-2026-10-29.json`.
The Fader full move now estimates 56.5753 W peak, 4.71461 A source peak,
15.2938 W average and 15.2938 J drawn/net, with zero returned energy. Previous
raw-Z values were 158.2377 W and 41.6086 J. Full-move winding heating at the new
peak is 53.4919 W. A physical 12 V voltage tracking conflict remains, so these
are imposed-motion estimates, not achieved hardware demand. Phase alignment and
friction assumptions still need review; this correction alone does not close
the reopened practical-accuracy issue.

All six cases passed independent balances and the unchanged 2% spatial/time
energy and peak gates. The native-receipt UI/report/CSV/snapshot mappings pass.
Full Rust: 139 desktop + 241 simulation + 7 integration passed, 22 ignored.
Frontend: 555 passed, 3 skipped; Svelte check and build pass. Seven Chromium
power/3D-display tests pass. Regression cases cover unequal spacing, shifted or
reversed source Z, one layer, source immutability, thickness edits and shared
physics/DC placement. Full receipts: approved temp `move-zfix-{baselines,models,results}-20261029`.

### Geometry-bound engineering estimate, 2026-10-29

**Acceptance audit update:** the superseding receipt is
`scripts/solvers/results/practical-move-audit-v2-2026-10-29.json`. The earlier
geometry-bound receipt incorrectly described the two-layer design's saved 15 g
carriage mass as a user-approved Fader assembly. Its numeric value was not
changed. The corrected two-layer case explicitly treats that saved mass as a
scenario assumption with unverified assembly coverage. The 15 g full-assembly
approval applies to the Fader only. The corrected runs preserve all design data.

The full-forward trajectories cover 63 mm in 1 s and the shorter trajectories
cover 1 mm in 0.25 s. Their zero-end-velocity quintic profiles reach 0.118125 and
0.0075 m/s respectively: the Fader's configured 0.5 m/s is a design target,
not the peak speed of these particular moves. At 193 positions and 0.25 ms the
estimated peak W / peak A / average W / drawn J / returned J / net J are:

| Design and move | Peak W | Peak A | Average W | Drawn J | Returned J | Net J |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fader full forward | 158.238 | 13.186 | 41.609 | 41.609 | 0 | 41.609 |
| Fader short forward | 10.110 | 0.843 | 7.433 | 1.858 | 0 | 1.858 |
| Fader short return | 10.427 | 0.869 | 7.544 | 1.886 | 0 | 1.886 |
| Two-layer full forward | 115.102 | 9.592 | 31.812 | 31.812 | 0 | 31.812 |
| Two-layer short forward | 9.279 | 0.773 | 7.395 | 1.849 | 0 | 1.849 |
| Two-layer short return | 9.496 | 0.791 | 7.473 | 1.868 | 0 | 1.868 |

Zero returned energy is a result for these dissipative cases, not an assumption
that regeneration is impossible. The separate braking balance tests exercise
positive returned energy and explicit sink handling. The summary includes
scenario profiles, geometry bindings and hashes for the native inputs, models,
results and winding sensitivity receipts; it checks snapshot/model equality,
energy balance and the unchanged convergence gates before writing. Full trace
receipts were kept externally. The 10%/100% winding AC probes are hypothetical
stress cases, not bounds: peak Fader power rises to 173.327/309.132 W and
two-layer to 125.984/223.924 W, showing the impact of excluded winding physics.

To reproduce, from the repository root choose a new empty parent directory in
`OUT` (each child must not exist), and put the two hash-matched supplied archives
in `DESIGNS`. The commands use the checked-in test fixtures and do not write the
supplied archives:

```sh
PCB_MOTOR_SUPPLIED_DESIGN_DIR="$DESIGNS" PCB_MOTOR_SCREENING_OUTPUT="$OUT/baselines" cargo test -p pcbmotorgen export_saved_design_screening_inputs -- --ignored --nocapture
(cd app/desktop && PCB_MOTOR_SCREENING_BASELINES="$OUT/baselines" PCB_MOTOR_ESTIMATE_OUTPUT="$OUT/models" pnpm exec vitest run src/lib/practicalMoveEstimate.test.ts)
PCB_MOTOR_ENGINEERING_ESTIMATE=1 PCB_MOTOR_SCREENING_BASELINES="$OUT/baselines" PCB_MOTOR_SCREENING_MODELS="$OUT/models" PCB_MOTOR_SCREENING_OUTPUT="$OUT/results" cargo test -p pcbmotorgen evaluate_saved_design_screening_assumptions -- --ignored --nocapture
PCB_MOTOR_SCREENING_RESULTS="$OUT/results" PCB_MOTOR_SCREENING_OUTPUT="$OUT/winding" cargo test -p pcbmotorgen winding_ac_uncertainty_sensitivity -- --ignored --nocapture
(cd app/desktop && PCB_MOTOR_SCREENING_RESULTS="$OUT/results" pnpm exec vitest run src/lib/powerRequirements.test.ts)
python3 scripts/solvers/summarize_move_screening.py "$OUT/baselines" "$OUT/models" "$OUT/results" "$OUT/summary.json" --engineering-estimate --builder app/desktop/src/lib/practicalMoveEstimate.ts --winding-sensitivity "$OUT/winding"
```

Use absolute paths for `OUT` and `DESIGNS`. Archive hashes are enforced by the
export fixture. The timing and force-grid gates validate numerical convergence,
not model accuracy. The generated 20 A / 1 m/s loss applicability domain is a
scenario validity interval, not a motor or driver rating or a design-goal gate;
outside it the declared loss model does not extrapolate.

The move editor can explicitly construct an approximate DRV8311 12 V / 100 kHz
scenario from the current native three-phase analysis. It uses the referenced
driver and Bourns 47 µH data and the RL, phase-pair and isolated-slab estimates
described below. The inductor Q-derived term is combined excess AC loss, not
separately measured core loss. Winding proximity and via AC distribution,
inductor bias/harmonics and board-level auxiliary loads remain excluded. Complete
hardware totals remain Unknown. The stiff DC-link boundary explicitly accepts
regeneration; upstream supply and capacitor transients are not modeled. Dynamic
housing/backplane move losses remain unsupported.

The model snapshot binds the estimate to hot phase resistances, effective
inductance, copper thickness and electrical period; changing these rejects stale
coefficients. The UI does not replace an existing declaration. The full Fader
uses its unchanged 15 g assembly, 63 mm travel, 0.5 m/s target, 12 V, 100 kHz,
47 µH per phase and saved copper/connectivity/depths. Both full moves report a
physical voltage tracking conflict separately from imposed-motion demand.

`scripts/solvers/results/practical-move-ui-bound-estimate-2026-10-29.json`
hashes the unchanged archives, model declarations, inputs and native receipts
for both designs and six moves. At 193 positions and 0.25 ms, full-forward
Fader is 158.238 W peak, 13.186 A peak and 41.609 J net; the two-layer star is
approximately 115.102 W and 31.812 J net. They are estimates with exclusions,
not achieved motion or guaranteed maxima. Each move passed the existing 2%
force-map and time-step energy/peak convergence checks and independent energy
balances. The UI report, CSV, snapshot and trace mappings were checked against
the regenerated native receipts. Earlier ripple/driver and hypothetical +10%
and +100% winding-AC resistance probes illustrate sensitivity, not confidence
intervals or measurements. Full receipts remain outside the checkout.

Verification: 386 Rust tests passed (22 ignored), 553 frontend tests passed
(2 skipped), five independent Python formula tests passed, Svelte check and
build passed, and six Chromium power tests passed. All four supplied files
retained their recorded SHA-256 hashes. These checks establish numerical and
export consistency, not physical accuracy or hardware qualification.

### Carriage setup clarification, 2026-10-29

The user accepts 15 g as a reasonable full moving-assembly estimate for the
Fader, including its moving bushings and enclosure. It is an engineering input,
not a measured mass, and no longer needs to be treated as an unresolved coverage
blocker for this scenario. Friction means bushing-to-rail sliding resistance.
Reasonable estimates are acceptable before planned board/prototype tests;
perfect material/friction measurements are not prerequisites for useful design
simulation. This supersedes the earlier Fader mass-coverage caveats below,
without qualifying unrelated designs or filling in driver/inductor losses.

Design setup now exposes carriage mass and friction under Drive. New designs
default to the combined magnet mass, using a list of known weights seeded with
the user's 5×5×3 mm N52 = 0.57 g reference. Other NdFeB sizes use an explicitly
approximate volume × 7.6 g/cm³ estimate consistent with that reference. The
display lists current dimensions/count, each magnet's mass and combined mass.
The full-assembly override includes magnets once plus all other moving parts,
not stationary rails. Existing saved masses remain overrides, including 15 g;
they are never replaced on load by the new magnet-only default. Automatic mode
updates with magnet dimensions/count and survives save/load.

The optional move remains separately explicit. “Use design mass and friction”
copies these estimates and their inclusion statement into the move draft, which
must then be applied. It does not invent a trajectory, source sink capability or
loss coefficients, and does not silently overwrite an existing applied move.
Reports separately show design estimates and the mass/friction actually used by
an explicit move.

Verification: 550 frontend unit tests pass with one existing skip, Svelte check
has zero errors/warnings, production build passes with its existing large-chunk
warning, and thirteen affected Chromium tests pass, including mobile layout.
The Rust suite passes 137 desktop, 239 simulation unit and seven integration
tests, with 18 explicit ignores. Native persistence tests cover legacy-mass
preservation and both saved mass modes. Browser screenshots are UI
evidence, not native WKWebView or physics validation.

### Simulation assumptions

- One three-phase star winding, sinusoidal FOC with id = 0. Phase current means
  peak sinusoidal amplitude, not RMS, line-to-line current or source current.
- A prescribed quintic position trajectory over an explicit duration. Start and
  end velocity are specified; endpoint acceleration is zero. Both travel bounds,
  maximum speed, acceleration and deceleration are declared by the caller.
  The model does not integrate achieved motion or simulate current-limit response.
  Moves are monotonic. A reversal is evaluated as separate forward and reverse
  moves, not a smoothed Coulomb-friction sign change inside one interval.
- Total moving mass is an explicit input with an inclusion statement. Friction
  is Coulomb force, damping is viscous, and external load is a signed force that
  the motor must overcome. Zero values must be supplied explicitly.
- Position-dependent Kf is a bounded, linearly interpolated table in the
  first-magnet-center coordinate used by ForceEvaluator. No extrapolation or
  fitted mean constant is permitted in the production adapter. Ke = 2 Kf / 3
  is the reciprocal phase-peak convention of this sinusoidal model.
- Balanced hot phase resistance and constant synchronous phase inductance,
  including declared external inductors. The production adapter must reject
  unsupported phase imbalance, connection, commutation, saliency, or conductive
  stack models rather than silently using their mean or omitting their drag.
- PWM-cycle-averaged voltage and power. No switching ripple is included in
  current, RMS, copper loss or scenario peaks. Finite time samples are not
  guaranteed maxima, current-trip predictions or thermal qualification.

## Electrical accounting

For signed q-axis phase amplitude I, velocity v and electrical angular speed w:

    F = Kf(x) I
    vq = R I + L dI/dt + Ke(x) v
    vd = -w L I
    Pmotor = F v + 1.5 R I² + d(0.75 L I²)/dt

The model records mechanical work, Coulomb/damping dissipation, external-load
work, kinetic energy and magnetic energy independently. Voltage feasibility uses
sqrt(3) times the required phase-vector magnitude, plus the declared driver
conduction-path voltage allowance, against the available line-voltage envelope.
Current feasibility uses the declared phase-amplitude limit, not an invented
OCP duration. Failure means the prescribed motion is not demonstrated achievable.
It does not produce an achieved-motion trace.

Driver conduction loss is 0.75 I² Rpath, where Rpath is the datasheet high-side
plus low-side resistance and equal high/low on-resistance is assumed. A declared
additional constant loss in watts may account for switching, dead-time and
control consumption over this one interval. This is a scenario assumption, not
a validated loss law or conservative bound. Without that declaration total
source power/current/energy remain unavailable; partial inverter demand remains
available and labelled partial.

The initial source model is an explicitly selected stiff source directly at the
DC link. Its voltage is constant, so capacitor energy change is zero. A caller
must declare whether that source accepts regeneration. Negative demand with a
non-sinking source is rejected; the model does not invent a clamp, brake resistor,
overvoltage response or capacitor transient. The separate capacitor-energy
function computes 0.5 C (Vend² - Vstart²) only. It cannot reconstruct source
peak power or a source waveform from endpoint voltages.

Psource = Vsource Isource, positive for draw and negative for return. Drawn and
returned energy are positive magnitudes; net = drawn - returned. All integrals
and phase RMS values cover exactly [0, duration]. Piecewise-linear integration
splits zero crossings for drawn/returned energy. Startup before t=0, shutdown
after the final sample, idle, hold, repeated operation, and switching transients
are excluded. Nonzero endpoint magnetic energy is recorded, not hidden.

## Numerical validation and remaining gates

Backend unit tests use analytic limiting cases, not substitutes for active saved
design evidence. Energy-balance residuals are exported rather than corrected.
Convergence checks compare time steps and peak power separately. The model's
current derivative uses second-order finite differences, so the caller must
check derivative and peak sensitivity when refining its time step and force map.

Before wiring this into engineering exports:

1. Prepare actual routed copper, layer depths, terminals and temperature-dependent
   resistance through existing authoritative backend paths. Generate the force
   table for the active design and declared sinusoidal law, never accept a
   frontend-supplied Kf as authoritative. Check the law against actual per-phase
   excitation, not merely a positive mean thrust.
2. Persist an optional move and source/loss declarations. Legacy files have no
   move, not default operating requirements. Connect native jobs with input
   identity, cancellation, pending/error and stale-result suppression.
3. Extend UI, report, requirements CSV, model snapshot and trace CSV from the same
   native result. Browser fixtures must not enter engineering exports.
4. Validate a supported saved design and a materially different one, then the
   actual Fader-traces-workspace.pmmotor attachment. That attachment is absent
   from this checkout. Its 63 mm travel, 0.5 m/s target, 12 V, 100 kHz PWM and
   47 µH per phase are not enough to infer mass, loads, profile or driver losses.
5. Record saved-design energy tolerances, time/space convergence and peak
   sensitivity. A partial or all-Unknown report cannot close #7744. Numerical
   validation does not establish measured performance, a worst-case supply
   bound, permitted peak duration or safe hardware operation.

## First-slice test evidence, 2026-10-28

`cargo test -p pcbmotorgen-simulation` passed 221 unit tests and 7 integration
tests, with 2 pre-existing ignored tests. Twenty new tests cover the move-power
kernel. No app integration or saved-design acceptance is implied by this run.
The first targeted run exposed an over-tight fixed residual tolerance in the
convergence test. It was replaced with the stated second-order residual gate,
not by forcing the residual to zero or changing calculated power.

The analytic refinement case is an 80 mm quintic move over 1 s, 0.5 kg,
0.02 N Coulomb friction, Kf = 2 N/A, R = 0.5 ohm per phase, L = 10 mH per
phase, and Rpath = 0.2 ohm. Additional driver losses are explicitly zero and
the source explicitly accepts return, so these are idealized scenario results,
not total hardware demand or active-design evidence.

| Time step, s | Electrical balance residual, J |
| --- | --- |
| 0.01 | 5.292000e-8 |
| 0.005 | 1.336500e-8 |
| 0.0025 | 3.358125e-9 |
| 0.000625 | 2.106739e-10 |

The mechanical residual stays below 2e-17 J in this case. The regression gate
for each independent balance residual is 6e-4 times dt squared, in joules
with dt in seconds. The combined source balance gate is twice that tolerance.
Other analytic cases use explicit absolute tolerances in the test source.

Relative to the 0.000625 s reference, net-energy error falls from 5.139747e-8 J
at 0.01 s to 3.142346e-9 J at 0.0025 s. Sampled positive peak-power error falls
from 1.418470e-5 W to 6.573318e-7 W; the reference peak is 0.03449528 W.
The test requires energy error reduction greater than 8, peak error reduction
greater than 4, and refined relative peak error below 0.1 percent. These are
kernel-case numerical gates, not tolerances transferred to an untested design.

## Native integration, 2026-10-29

The first slice was committed locally as `2b84071`. The attachments are now in
the project root. Earlier statements that the attachment was missing describe
the initial checkout, not the current state.

### Phase-domain model and delivery

Model `linear-move-sinusoidal-v2` supersedes the scalar/balanced-resistance
restriction above for native routed designs. It uses three individual hot
resistances and the full symmetric self/mutual inductance matrix, plus external
series inductance on its diagonal. A non-passive matrix is rejected rather than
repaired. The native force map contains actual signed terminal N/A coefficients
from the existing network-current-weighted Lorentz integration at the saved
conductor depths. No mean sweep Kf or fitted replacement geometry is used.

For declared balanced sine basis q(x), motor force coefficients k(x), and
required force F, the imposed phase commands are:

    I_amplitude = F / dot(k(x), q(x))
    i_phase = I_amplitude q(x)
    v_phase = R_phase i_phase + L_matrix di_phase/dt + k(x) velocity
    Pterminal = dot(v_phase, i_phase)
    Umagnetic = 0.5 dot(i_phase, L_matrix i_phase)

Force coefficients and back EMF obey terminal reciprocity directly; no scalar
Ke convention is imposed on an unbalanced or non-sinusoidal force distribution.
The explicit balanced-star move controller is separate from the existing static
preview's commutation law. The declared electrical zero is not automatically
fitted, rectified or calibrated to force a passing move. Singular/nonpositive
coupling rejects the request. Floating-neutral SVPWM feasibility uses the
instantaneous max-minus-min command voltage, including conduction allowance.

Only linear, declared star windings with three connected networks are supported.
For legacy imported files with no connection enum, explicit terminal picks at a
shared physical neutral establish star connectivity. A filename and unrelated
generated-routing settings do not. Stack/housing requests are rejected because
their dynamic inductance, drag and eddy losses are not integrated. In particular,
`star_2-layer.pmmotor` version 2 is not silently reduced to its bare version 1.
Partial copper overlap is evaluated with the actual finite magnet/copper field.
The full-overlap interval is recorded, never treated as a measured mechanical
end stop or used to alter the requested 63 mm travel.

The desktop command accepts exact inputs, echoes them with SHA-256 identity and
simulation provenance, and permits one owned calculation. Cancellation is
cooperative between solver stages; ownership is retained until exit. The client
invalidates publication immediately on edits, pending reruns, failure, cancel or
disposal, and checks request identity and the complete input payload again.
Browser mode has no substitute move solver or engineering trace export.

An optional `power_move` persists the explicit request. Missing legacy fields
remain None/null. The current UI uses an advanced JSON editor with incomplete
null placeholders, explicit apply/run/clear actions, native cancellation, model
limitations and a requested-motion rejection message. It does not guess a move
from the static target. Reports, requirements CSV, snapshot v2 and time-series
CSV share the same current native result and identity checks. CSV records phase
names, units, source boundary, required commands, provenance, interval stage,
averaging treatment and partial-model scope. No achieved trajectory, startup,
idle, settling or repeated-operation trace is synthesized.
Unsupported JSON fields are rejected by both the editor and native request
parser rather than silently dropping a requirement such as a peak-duration law.

### Read-only saved-design evidence

The supplied files remain byte-for-byte unchanged and untracked. SHA-256:

- `Fader-traces-workspace.pmmotor`: `567d97900475c92598f9ad6f7df9e7aeaf374dfc542fa25fa7e04b90dbfb287b`
- `star_2-layer.pmmotor`: `0ed215f6ff403b927dbeac1ea3d4d9587489a1f1c0680e4ce3a2a48658475d82`
- `star_4-layer.pmmotor`: `6a550dcb4327a6e846582fb883c4958a0d275cba85b33271337deee405794e81`
- `star-wye_4-layer.dxf`: `4769c3da7030241c9a4b58c009cd120e18aa53e35156542733669c12c1772ca0`

The bounded regression explicitly selects version 1 of each motor file. The
Fader retains all 1055 segments, 3 curves, 789 vias, its selected terminals,
0.2 mm trace width, saved depths [-4.8, -3.2, -1.6, 0] mm, 12 V supply,
100 kHz PWM and 47 microhenry per-phase external inductors. The generated
two-layer star version 1 is a materially different copper source. The four-layer
0.127 mm imported version also ran at the initial grid; it was not substituted
for the Fader.

The test scenario is deliberately not a new saved operating requirement:
63 mm imposed move from 2.5 to 65.5 mm first-magnet-center position over 1 s,
zero endpoint velocity/acceleration, speed cap from the saved target,
acceleration cap from the saved configuration, explicitly symmetric deceleration
cap, saved 0.05 N kinetic friction, explicitly zero damping/external load,
configured 15 g used only as an unconfirmed numerical scenario, declared
balanced-star reference pi/2, saved phase-amplitude limit of 1 A, and a declared
stiff source accepting return. Cap/mass breakdown and actual supply sink behavior
are not inferred. Additional switching/dead-time/control loss is Unknown.
The Fader's 0.5 m/s remains a target cap, not a claimed achieved speed or a
voltage-limited replacement target.

Both full-travel requests fail the current and voltage checks. The following
are **required demand for rejected motion**, not consumed energy or achievable
source power:

| Design/version | Force points | dt, s | Required copper energy, J | Required partial DC-link sampled peak, W |
| --- | --- | --- | --- | --- |
| Fader / 1 | 65 | 0.001 | 40.7129907251 | initial grid |
| Fader / 1 | 97 | 0.001 | 39.7920619315 | 155.862626133 |
| Fader / 1 | 129 | 0.001 | 39.4736103343 | 155.277586432 |
| Fader / 1 | 129 | 0.0005 | 39.4733617018 | 155.277595309 |
| Generated two-layer star / 1 | 65 | 0.001 | 28.4888342894 | initial grid |
| Generated two-layer star / 1 | 97 | 0.001 | 27.8811269403 | 112.125602271 |
| Generated two-layer star / 1 | 129 | 0.001 | 27.6732622584 | 111.926027590 |
| Generated two-layer star / 1 | 129 | 0.0005 | 27.6730872592 | 111.926027745 |

Spatial refinement at fixed dt compares 97 versus 129 force positions. Required
copper-energy changes are 0.8067% for the Fader and 0.7511% for generated star;
partial-peak changes are 0.3768% and 0.1783%. Both pass the declared 2% local
refinement gates. Separate time refinement at the fixed 129-point map changes
copper energy by about 0.00063%; the partial peak changes below 0.00001%.
The initial 65-to-97 spatial change exceeded 2% and is retained as coarse-grid
evidence, not relabelled as converged.

Finest-grid independent electrical balance residuals are 2.0822e-10 J and
5.7523e-12 J; mechanical residuals are below 2e-18 J. Gates are electrical
residual below 1e-6 times copper energy, and mechanical residual below 1e-9 J.
These are local model-convergence checks, not independent absolute magnetic
force qualification or worst-case peak bounds.

A separate 1 mm reverse request from 12.5 to 11.5 mm over 0.25 s, using the
129-point map and 0.0005 s time step, passes the Fader's sampled current/voltage
envelope and fails the two-layer version's envelope. Both reconcile their energy
balances. This is a separate monotonic reverse move, not a simulated reversal
transient, OCP response, or achieved-motion measurement.

For that Fader reverse move only, a separate explicitly idealized constant-zero
additional-driver-loss scenario gives partial modeled source peak 7.10315 W,
peak source current 0.591929 A, average 5.87867 W and net/drawn energy 1.469667 J,
with zero returned energy over the exact 0.25 s interval. Its independent source
balance and peak-current/power convention pass. These numbers are **not total
hardware demand or a conservative bound**. The unknown-loss version withholds
even those partial source totals.

Reproduce these bounded checks, without editing the files:

```sh
PCB_MOTOR_PROJECT_PATH="$PWD/Fader-traces-workspace.pmmotor" \
PCB_MOTOR_MOVE_REFINEMENT=1 cargo test -p pcbmotorgen \
  commands::move_power::tests::supplied_saved_design_move_scenario -- --ignored --nocapture
```

Repeat with `star_2-layer.pmmotor` for explicitly selected version 1. Each run
checks the supplied file bytes again before returning. Final local logs are in
the approved OpenCode temporary directory as
`move-power-20261029-Fader-traces-workspace-final.log` and
`move-power-20261029-star_2-layer-final.log`.

### Current gate and verification

The native result records `source_model_scope = partial_declared_scenario`.
Total supply peak/average/energy stay Unknown in UI and exports even when a
constant driver loss is declared, because ripple/AC copper/external-inductor
loss models are absent. Partial modeled source W/A/J are separate, labelled
scenario results. They are not the ticket's total-power or maximum requirement.

Current verification passes: 131 desktop Rust tests with 14 explicit ignored,
227 simulation unit plus 7 integration tests with 2 pre-existing ignored,
537 frontend tests with 1 pre-existing skipped, and 10 Chromium report/control
tests at two viewports. The two supplied-design refinement tests were run
explicitly in addition to the ordinary suite. Svelte/type check has zero errors
or warnings; the production frontend build passes with its existing chunk-size
warning. Browser native-transport fixtures test UI/identity/export behavior only,
not native WKWebView observation or engineering physics evidence.

#7744 remains open. Remaining acceptance needs complete supported loss accounting
or properly bounded totals, confirmed operating/mass/source inputs, and numerical
validation of that complete model for supported saved designs. Hardware thermal,
current-duration, controller-bandwidth and worst-case guarantees remain unknown.
No physical design was modified, no external-solver campaign was launched, and
no original housing was removed to force a passing request.

## Declared loss-model extension

### Practical-estimate investigation, 2026-10-29

#### Referenced partial screening case

`scripts/solvers/practical_move_assumptions.py` now constructs an explicit,
limited 12 V/100 kHz DRV8311 scenario from a native baseline's actual phase
resistances, phase names and effective inductance. It is a screening model,
not a new saved-design setting. It preserves supplied geometry and drive inputs.

- TI SLVSFN2B section 7.5 gives typical 0.21 Ω high-side plus low-side path at
  25 °C; SLEW=01 gives 75 V/µs (20–80%); DEADTIME=001 gives 200 ns. The saved
  driver path value is used unchanged. The SLEW and DEADTIME choices are
  assumptions, not recovered board settings. The assumed diode drop is 0.7 V,
  not a TI-specified value. Typical 12 V operating current is interpolated
  between 10 mA at 25 kHz and 12 mA at 200 kHz. External control/regulator
  consumption remains unspecified. TI section 12.3.1 FOC switching/dead-time
  equations use electrical-cycle RMS. Their coefficients are mapped to
  `sum(abs(phase current))` by equating their averages for ideal balanced
  sinusoidal currents, not by claiming an instantaneous switching simulation.
- Ripple uses the exact 50%-duty two-phase RL peak-to-peak formula at the
  native effective inductance and worst hot phase R, plus assumed external
  inductor DCR and half the driver conduction-path resistance. The covariance
  approximates a symmetric triangular ripple shared by a uniformly selected
  phase pair. It is not an SVPWM solution, measured ripple, or universal bound.
  An independent exponential half-cycle march verifies the RL formula, and
  numerical triangle integration verifies the balanced covariance.
- Bourns SRP1265WA-470M is a **representative scenario part**, not a board
  modification: 47 µH, 74.1 mΩ typical DCR, 89 mΩ maximum DCR, Q typical 20
  at 100 kHz / 1 V, all at 25 °C. Its typical 5.2 A Irms and 6 A Isat are not
  hardware guarantees. Estimate DCR at the assumed winding temperature using
  copper's 0.00393/°C coefficient. Q gives total small-signal AC resistance
  `2πfL/Q`, not core resistance alone. Subtract 25 °C DCR once and apply the
  remainder to the triangle's fundamental mean-square current. The result is
  entered in the existing constant-inductor-loss field, but is explicitly a
  combined AC-excess proxy, not separately measured core loss. Bias, temperature,
  nonlinearity and harmonics are not characterized. The generated two-layer
  design has no external inductor and remains unchanged.
- An isolated-slab skin-effect formula uses 35 µm copper and the actual hot DC
  phase resistance as a proxy. It applies the maximum-domain electrical
  frequency for fundamental and 100 kHz for ripple. A complex-impedance
  calculation independently checks the formula. This approximation does not
  model conductor proximity, via-specific current distribution or harmonics.
  Those limitations, external board electronics, and inductor bias/harmonic
  limitations remain **named omissions**, so `source_model_scope` stays
  `partial_declared_scenario` and complete supply totals remain Unknown.

References: TI sections [7.5](https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-XXXXXXXX-SF0T-XXXX-XXXX-000000179401)
and [12.3.1](https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-C826F7E8-19E5-47C8-9C09-E13912428538),
[Bourns SRP1265WA](https://www.bourns.com/docs/product-datasheets/srp1265wa.pdf),
and [Coilcraft on Q](https://www.coilcraft.com/en-us/resources/application-notes/key-parameters-for-selecting-rf-inductors/).

Read-only Fader version 1 and generated two-layer star version 1 were evaluated
at 129/193 force positions at 0.0005 s, then 193 positions at 0.00025 s.
Full forward is 63 mm in 1 s; short moves are ±1 mm in 0.25 s. Both use a
stiff 12 V DC link explicitly accepting regeneration, zero endpoint velocity,
15 g mass and 0.05 N bushing/rail friction, with zero external load/damping
as explicit test assumptions. This does not assert the actual supply can sink
energy. The Fader's saved 0.5 m/s setting remains unchanged and is not used as
a cap. Both full moves have physical voltage-tracking findings; calculated
demand is retained, not claimed as achievable.

| Case | Partial sampled peak W | Partial peak A | Partial average W | Drawn / returned / net J |
| --- | ---: | ---: | ---: | ---: |
| Fader full forward | 158.238 | 13.1865 | 41.6086 | 41.6086 / 0 / 41.6086 |
| Fader short forward | 10.1104 | 0.8425 | 7.4334 | 1.85835 / 0 / 1.85835 |
| Fader short return | 10.4274 | 0.8690 | 7.5442 | 1.88605 / 0 / 1.88605 |
| Two-layer full forward | 115.102 | 9.5919 | 31.8123 | 31.8123 / 0 / 31.8123 |
| Two-layer short forward | 9.2792 | 0.7733 | 7.3955 | 1.84887 / 0 / 1.84887 |
| Two-layer short return | 9.4955 | 0.7913 | 7.4731 | 1.86828 / 0 / 1.86828 |

The two full cases are imposed demand above the DC-link voltage, not delivered
power or achieved motion. The short-move absence of a voltage finding does not
prove tracking or current/thermal safety. Zero returned energy here is a result
of these lossy trajectories, not a general braking claim.

All six cases pass the unchanged 2% energy/peak gates for each spatial and
time refinement, independent electrical/source balance below 1e-6 of accounted
losses, and mechanical balance below 1e-8 J. The largest spatial changes are
0.6002% net energy and 0.8314% peak; the largest time changes are 0.0003% net
energy and 0.0044% peak. These are convergence checks for the stated model,
not error bounds on its approximations.

An intentionally broad assumption sensitivity scales ripple amplitude and
switching/dead-time coefficients by 0.5 and 2; the Q proxy scales with ripple
amplitude squared. Full-move partial net energy spans 41.2315–42.5086 J for
Fader and 29.7412–39.3822 J for two-layer. These are sensitivity probes, not
calibrated confidence intervals or guaranteed extrema; in particular the
uninducted two-layer estimate is sensitive to ripple assumptions.

Hash-bound compact receipts, including sensitivity hashes, are in
`scripts/solvers/results/practical-move-screening-v3-2026-10-29.json`.
Full baseline, model and native receipts are in the approved temporary folder's
`move-screening-baselines-20261029`, `move-screening-models-v2-20261029`,
`move-screening-results-v2-20261029`, and `move-screening-sensitivity-v2-20261029`
directories. The earlier `practical-move-screening-2026-10-29.json` and v1
temporary receipts preserve the first approximation before the slab addition.
The optional native receipt report test checks all six cases against UI report,
CSV, snapshot and time-series mapping, while confirming complete totals remain
Unknown. No browser physics or hardware results are implied.

During the full Rust verification the imported-copper goal-invariance test
failed once on a one-ULP mutual-inductance difference. Its filament accumulation
uses a Rayon parallel sum with nondeterministic reduction order. The invariance
helper now compares numerical arrays at 1e-13 relative with a 1e-12 scale
floor, while still requiring matching structure and nonnumeric fields. A new
control accepts 1e-14 relative roundoff and rejects a 1e-10 relative change.
This is a numerical-repeatability tolerance, not a motor-performance target;
the source/energy and 2% refinement gates above were not changed. The full
Rust suite passed on rerun.

The practical-goal completion criterion is **not yet met**: the included loss
approximations are useful partial screening, but omitted winding proximity,
inductor nonlinearity/harmonics and external electronics remain unquantified.
Do not relabel the above partial numbers as complete W/A/J estimates.

The existing declared-loss interface has a constant, balanced three-phase ripple
covariance and constant per-inductor core watts over the move. These are model
assumptions, not quantities furnished by a 47 µH inductance rating. A practical
scenario must derive and document the selected PWM, current/voltage range,
ripple statistics and core-loss estimate and test sensitivity. It must not
relabel the existing numerical fixture as component data.

TI DRV8311 datasheet SLVSFN2B sections 7.5 and 12.3.1 give a useful starting
point: typical HS+LS resistance 0.210 Ω at 25 °C and 0.330 Ω at 150 °C,
VM operating current 10 mA at 25 kHz and 12 mA at 200 kHz (12 V, 25 °C),
and separate FOC conduction, switching and dead-time equations. At SLEW 01,
the typical 20–80% slew rate is 75 V/µs; DEADTIME 001 is typically 200 ns.
These are conditional typical values, not evidence that the saved board uses
those settings. The datasheet FOC equations use electrical-cycle RMS; mapping
them into an instantaneous whole-inverter loss law requires an explicit
waveform assumption and independent check. Operating current may include gate
drive power, so its boundary must be reconciled before adding switching terms.
Sources: https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-XXXXXXXX-SF0T-XXXX-XXXX-000000179401
and https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-C826F7E8-19E5-47C8-9C09-E13912428538.

One commercially listed 47 µH candidate, Coilcraft MSS6132T-473MLC, is listed
by DigiKey with 0.300 Ω maximum DCR at its specified reference conditions
and 1.3 A current rating: https://www.digikey.com/en/products/detail/coilcraft/MSS6132T-473MLC/21381941.
This is a possible comparison component, not a selected part, core-loss model,
proof of saturation margin or a change to the saved design. Manufacturer
core-loss information and its applicable waveform still need confirmation.

The optional `supplied_saved_design_declared_loss_model` diagnostic previously
required `feasible` on its base and refined cases, contradicting v4 goal and
physical-tracking separation. Those assertions were removed; the numerical
source, conservation and unchanged 2% refinement checks remain. Executed with
the unchanged Fader version 1 and refinement enabled: it passed at 129/193
positions and 0.0005/0.00025 s; spatial changes in net energy and sampled peak
were 0.632% and 0.626%, and the subsequent time changes were approximately
1e-9 relative. These are **synthetic loss-fixture** results, not the requested
practical estimate or a completed saved-design acceptance. Fader SHA-256 remained
`567d97900475c92598f9ad6f7df9e7aeaf374dfc542fa25fa7e04b90dbfb287b`.

Remaining: derive, implement and independently check a supported practical
loss scenario with honest limits; run full and short forward/return cases for
both unchanged saved designs, establish exports and sensitivity evidence, and
update ticket acceptance. No external-solver campaign or hardware qualification
is implied by this investigation.

Model `linear-move-sinusoidal-v3` accounts for declared cycle-average losses without inventing a
PWM waveform or driver efficiency. It requires explicit phase ordering,
references, a fixed voltage/PWM/temperature/driver operating point and current
and speed applicability limits. It rejects extrapolation outside that domain.

Winding fundamental AC resistance increments, winding ripple AC increments,
external series resistance and external-inductor core watts are separate inputs.
Hot winding DC resistance remains authoritative from the actual copper network.
No winding resistance or motor constant may be replaced by these declarations.

Declared zero-mean phase-ripple covariance and peak-deviation bounds describe
cycle-average statistics, not synthetic switching samples. The covariance must
be positive semidefinite, symmetric and balanced at a floating star neutral.
Its diagonal adds to each phase's mean-current squared for RMS heating. A
constant covariance adds constant magnetic stored energy, not a second energy
flow or startup stage. Zero-ripple or explicitly idealized cases stay partial.

Switching and dead-time each use a declared whole-inverter energy-per-PWM-cycle
law: constant plus a coefficient times the sum of absolute mean phase currents
plus a coefficient times the sum of mean-square phase currents. The latter
includes declared ripple variance. These are calibrated/declared average laws,
not derivations of switching-event currents from RMS data. Controller and other
DC-link watts are explicit. Legacy lumped driver watts and this component model
cannot both be applied.

Only a non-idealized, in-domain declaration with all terms and no stated
omissions may supply totals for that declared model. Such totals remain modeled
scenario quantities, not measured hardware totals or guaranteed maxima. Missing
declarations, idealized choices and stated omissions retain Unknown total rows.
The source remains an explicitly stiff DC link; no upstream or capacitor
transient capability is implied. Actual mass coverage, losses and source
behavior still need confirmation before saved-design total-power acceptance.

### v3 verification, 2026-10-29

The native public command was exercised on unchanged Fader version 1 with a
1 mm reverse move from 12.5 to 11.5 mm over 0.25 s. Configured mass/friction were
retained; mass coverage is still explicitly unconfirmed. Travel, speed cap,
12 V source, 100 kHz PWM and 47 µH external inductance per phase were unchanged.
The test supplies explicitly numerical loss coefficients and ripple statistics,
NOT measured or datasheet-qualified DRV8311, inductor or winding AC properties.
It explicitly assumes the stiff DC link accepts regeneration. No physical
design, configured motor constants or imported copper was substituted.

At 129 force positions and 0.0005 s timestep the conditional fixture produced
7.2681532938 W sampled peak, 0.6056794411 A sampled source peak,
6.0289761543 W average and 1.5072440386 J drawn/net energy, with zero returned
energy. Mean phase peak was 0.9318889867 A; the declared-ripple envelope was
0.9518889867 A. Accounted loss energy was 1.5071857854 J and the independently
recomputed source-energy residual was 2.0596e-10 J. Input SHA-256:
`670521de6ddcb64dd7952b4e17925aeb8b536453746d731e9d98677fbbef952f`.

Separate refinements passed the predeclared 2% energy/peak gates:

- 193 force positions at fixed 0.0005 s: 1.4977757816 J and 7.2229036308 W;
  relative changes 0.6321545% energy and 0.6264747% peak.
- Fixed 193 positions at 0.00025 s: 1.4977757795 J and 7.2229036373 W;
  relative changes approximately 1.41e-9 energy and 9.01e-10 peak.
- Final source residual 5.1475e-11 J, below the gate of
  `1e-6 * accounted_loss_energy_j`. No numerical residual correction was used.

Reproduction (from repository root):

```sh
PCB_MOTOR_PROJECT_PATH="$PWD/Fader-traces-workspace.pmmotor" PCB_MOTOR_DECLARED_LOSS_REFINEMENT=1 cargo test -p pcbmotorgen commands::move_power::tests::supplied_saved_design_declared_loss_model -- --ignored --nocapture
```

Full Rust verification passed 132 desktop tests (15 explicit ignores), 237
simulation unit tests (two pre-existing ignores) and seven integration tests.
Frontend verification passed 545 tests (one pre-existing skip), zero
svelte-check errors/warnings, and production build (existing chunk-size warning).
Ten Chromium regressions passed across 1280/1600 px viewports; artifacts are in
`app/desktop/e2e-results/loss-v3-final-20261029/`. Browser tests use synthetic
transport DTOs only, not numerical solver evidence. They cover complete-model
totals and exports, incomplete templates, coefficient-edit invalidation,
Unknown demo/partial totals and cancelled late-response suppression. The
generated desktop `move-power.png` was inspected. This is not observed native
WKWebView acceptance. Svelte autofixer reported no issues; its effect suggestions
refer to the existing imperative job-ownership lifecycle, not derived physics.

Report/snapshot/time-series exports retain the loss laws, domain, references,
phase ordering, RMS/peak distinctions and component ledger. Snapshot format is
now v3. Legacy saved moves need no new declaration. The editor adds incomplete
null fields rather than guessed zero-loss values. Native checks reject invalid
covariance, domain mismatch, coefficient overflow and legacy/component driver
double counting; analytic tests cover hold, braking, ripple and timestep refinement.

All four supplied root file hashes still match the values recorded above.
Ticket #7744 remains open: actual loss/ripple parameters, moving-mass coverage
and source sink behavior must be confirmed for actual saved-design total-power
acceptance. Placeholder coefficients do not satisfy that gate. The previously
tested 63 mm requests remain electrically infeasible. Unsupported dynamic
backplane/housing losses still reject; no external-solver campaign, hardware
maximum, permitted peak-duration, controller or thermal qualification is claimed.

### Additional saved-design rejection evidence

The same 1 mm/0.25 s declared-loss request was next tried against the two other
supplied version-1 designs. Both calls to the existing success-only
`supplied_saved_design_declared_loss_model` test failed its feasibility assertion:

- `star_2-layer.pmmotor`: current-limit failure, mean phase peak
  1.0622824503 A and declared-ripple envelope 1.0822824503 A against 1 A.
  Input SHA-256 before the mass-label clarification was
  `bab26c905bc954a73669a94976c39057df2953d44cf5b13249c03fb74f366756`.
- `star_4-layer.pmmotor`: voltage-limit failure, required line peak
  12.7698317899 V. Input SHA-256 before the label clarification was
  `48f0040cca2da708d2dad71fd6fd17dc2bbe3b8446fd277666736954a26bbfec`.

These failed success probes are not successful total-power scenarios. No design,
current limit, move duration or load was changed to make them pass. The existing
success-only assertion remains unchanged. A separate rejection regression now
pins the archive hashes and explicitly selects version 1, checks these expected
limits and requires `source = null` at each resolution. It checks energy balance
for required excitation, not achieved source demand, and compares accounted
losses, phase envelope and required line-voltage peak under separate 129→193
spatial and 0.0005→0.00025 s time refinements. All comparisons pass 2% gates.

Final required-excitation diagnostics at 193 positions/0.00025 s:

- Two-layer: 1.0788584841 A declared envelope, 4.8899911371 V required line
  peak, 1.0214920739 J accounted losses, source residual 1.5457e-12 J.
  Input SHA-256 `461f708773dd539f78e59b52c18d5aa6b19a0c2a9b850d461749cc67490cdc1a`.
- Four-layer: 0.9489543302 A declared envelope, 12.7296176980 V required line
  peak, 2.2902780384 J accounted losses, source residual 2.7620e-12 J.
  Input SHA-256 `0757561657eacea742e8688b9ec4b82fe163726400a209a2b1ebdb744b529be8`.

The regression separately selects two-layer version 2 and confirms that its
actual saved backplane/housing survives request construction and causes explicit
unsupported-dynamic-loss rejection. It never falls back to version 1.

```sh
PCB_MOTOR_SUPPLIED_DESIGN_DIR="$PWD" cargo test -p pcbmotorgen supplied_loss_model_rejects_current_voltage_and_unsupported_stack_without_repair -- --ignored --nocapture
```

The shared request helper now describes mass as the configured carriage mass
with unconfirmed complete-assembly/cap coverage, rather than hard-coding 15 g
in the text. The numeric value still comes from the saved design. Re-running
Fader and both refinements produces identical numerical results to the previous
section; its clarified-label base input SHA-256 is now
`0049a7a0fb3b31fa6e05221656bbaf68fdf9695828b69e9cc94f8e12d6848979`.

### Driver source audit and inputs still required

Checked TI's DRV8311 production datasheet SLVSFN2B, revision B, February 2022,
using its HTML sections on 2026-10-29:

- [7.5 Electrical characteristics](https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-XXXXXXXX-SF0T-XXXX-XXXX-000000179401)
  specifies 210 mΩ typical HS+LS resistance at VM ≥ 6 V, 1 A and junction
  temperature 25°C; 330 mΩ typical at 150°C. The saved 0.21 Ω is therefore a
  configured typical cold value, not a hot-driver or worst-case resistance.
  Saved winding temperature 75°C does not establish driver junction temperature.
  No resistance value was changed or interpolated from these endpoints.
- The same section specifies VM operating current at 12 V and 25/200 kHz,
  for example 10/12 mA typical at 25°C. These are not a qualified 100 kHz
  controller-only coefficient. Standby/operating current, charge-pump/gate
  consumption and externally supplied logic/regulator loads need a clear
  boundary before combining them with switching and controller terms. Do not
  add the entire operating-current draw to overlapping calibrated loss laws.
- [12.3.1 Power dissipation](https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-C826F7E8-19E5-47C8-9C09-E13912428538)
  provides FOC estimates for conduction, switching and diode dead-time losses.
  It requires rise/fall time, diode forward voltage, dead time and current
  conventions. Section 7.5 specifies slew/dead time under selected settings;
  the saved file identifies only DRV8311, not the H/S/P variant, PWM mode,
  SLEW/DEADTIME settings or driver temperature. Do not choose a setting or map
  a whole-electrical-cycle RMS estimate to an instantaneous current law silently.
- [11.1 Bulk capacitance](https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-73020C97-0258-497F-8442-8933E816B34B)
  explicitly depends on supply capability, wiring inductance, allowable voltage
  ripple and braking method. A chip capable of synchronous conduction does not
  prove that the upstream 12 V supply can sink regenerative energy.

The supplied Fader has 15 g configured carriage mass, 0.05 N friction and
47 µH external inductance per phase, but no moving-part coverage statement,
inductor manufacturer/part number, DCR/core-loss data, qualified ripple moments,
winding AC-loss increments or source sink declaration. Inductance alone cannot
identify an inductor's losses. Magnet dimensions alone cannot establish total
moving mass. These missing inputs require design-owner data or an explicitly
approved, referenced modeling assumption; they cannot be recovered from this
datasheet. No production loss preset or saved-design total was fabricated.

Follow-up changes touch tests and this evidence note only. Verification reruns
the six automatic native move-command tests and explicitly executes the new
saved-design rejection regression and the unchanged Fader success/refinement
gates. Previous frontend/build/Chromium evidence applies to unchanged production
code; those suites were not rerun for this test-only follow-up. Original root
hashes were checked again and match. The blocking inputs above remain open.

## Design-goal independence, v4

User clarification on 2026-10-29: the goal is accurate simulation results,
not checking the design goals. Exceeding goals is acceptable and irrelevant
to the simulation. The previous treatment of current/speed/acceleration goals
and voltage margins as publication gates was wrong.

Model `linear-move-demand-v4` calculates the imposed trajectory's required
force, current, voltage, power and energy without clamping to or rejecting
against those goals. The configured static-preview current setpoint and driver
peak rating no longer cap the move allocation. Legacy request current/speed/
acceleration-limit fields remain readable but are ignored; new JSON templates
omit them and native deserialization permits their absence. Move-specific
physical validation no longer requires force-target relationships or positive
acceleration/current/temperature-rise goals; ordinary design validation is
unchanged. No physical geometry or material parameters are substituted.

Design targets and model validity are distinct. Invalid covariance, unsupported
housing/stack physics, loss-domain extrapolation, nonfinite inputs, unresolved
internal reversal and source-return incompatibility still cannot produce
unsupported results. A supplied loss law's applicability domain is a statement
of where its equations are valid, not a desired performance goal.

The physical DC-link voltage still enters power/current accounting. Required
phase-command voltage above that actual bus is recorded as a physical tracking
finding, without the configurable headroom factor. It does not suppress required
W/A/J. Such demand describes the imposed motion, not actual hardware delivery or
achieved tracking. The legacy `feasible` field now means only physical tracking
compatibility and never design-goal compliance. UI/report show "Physical
tracking findings" instead of treating goals as a pass/fail gate. Snapshot
format is v4 and the trace column is `physical_tracking_compatible`.

Native public-command regressions on both supplied star designs independently
change the configured current setpoint to zero, contradictory force goals,
zero acceleration goal, target speed, driver peak rating, request limits and
voltage margin. The complete per-sample traces and source W/A/J are exactly
identical before and after those goal edits. No geometry, loss law, physical
source voltage or trajectory changes in these comparisons.

At 193 force positions and 0.00025 s, the numerical-coefficient fixtures now
publish required demand for both designs:

- Two-layer v1: 4.8824137794 W sampled peak, 0.4068678150 A sampled source
  peak, 4.0861682867 W average, 1.0215420717 J drawn/net, no returned energy.
- Four-layer v1: 11.0535335716 W sampled peak, 0.9211277976 A sampled source
  peak, 9.1613121707 W average, 2.2903280427 J drawn/net, no returned energy.
  The 12.7296176980 V required line peak exceeds the actual 12 V bus; the
  calculated demand remains available with that separate physical finding.

These are still numerical loss-law fixtures, not accurate production-loss
estimates or hardware measurements. Missing real loss data remains an accuracy
limitation; exceeding a design goal does not. Fader outputs and its separate
2% spatial/time refinement gates remain numerically unchanged. Two-layer v2
still rejects missing dynamic housing/stack physics, not a design goal.

Reproduction:

```sh
PCB_MOTOR_SUPPLIED_DESIGN_DIR="$PWD" cargo test -p pcbmotorgen supplied_loss_model_demand_is_independent_of_design_goals -- --ignored --nocapture
```

Verification: 132 desktop Rust tests, 237 simulation unit tests and seven
integration tests pass, with 18 explicit ignored tests across those crates.
The two saved-design goal-invariance/refinement runs and Fader refinement test
were explicitly executed and pass. Frontend passes 546 tests with one existing
skip, check reports zero errors/warnings, build passes with its existing chunk
warning, and 10 Chromium regressions pass. New report/browser assertions retain
totals despite physical tracking findings and preserve stale/cancel/demo guards.
Artifacts: `app/desktop/e2e-results/demand-independent-goals-final-20261029/`.
Svelte autofixer reports no issues. Original supplied files remain unchanged.
