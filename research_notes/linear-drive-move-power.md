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
