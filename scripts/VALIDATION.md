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
preserves the supplied project's config. It contains generated Star/wye
copper, not imported CAD: five magnets, three strands, 0.1 mm traces, 1 oz,
12 V, 1 A, 100 kHz. Do not substitute earlier feasibility-search settings.

```sh
RAYON_NUM_THREADS=4 cargo test -p pcbmotorgen closed_infinity_user_project_diagnostics --bin pcbmotorgen -- --ignored --nocapture
```

This reruns all 50 positions at mesh densities 10, 20 and 40, compares their
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
The Python check independently builds the alternating cuboid array with
Magpylib in SI units and integrates signed dL at nine mover positions.
Field and force mismatches fail with numerical tolerances. This checks the
field engine, force sign and integration for the exported samples. It does
not independently solve the electrical network or establish mesh convergence.

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
