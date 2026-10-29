# Linear-drive move power model

Implementation scope for pcbmotorgen#7744. This document describes the first
backend slice, not completion evidence for the ticket.

## Supported model

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
