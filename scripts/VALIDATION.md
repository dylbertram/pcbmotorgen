# Magnetic and branch-current regression tests

Run from the repository root.

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
