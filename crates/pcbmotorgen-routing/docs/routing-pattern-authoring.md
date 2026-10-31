# Routing-Pattern Plugin Authoring Guide

This document explains how to author a **coil routing generator** for pcbmotorgen
and load it into the app. Generators are _plugins_: they produce raw line
geometry and expose metadata + parameters through a strict, documented
interface. They are written either as a **Rust `cdylib` crate plugin** or a
**Python runner** script, and are validated on upload with helpful errors.

See `docs/adr/0009-routing-pattern-plugin-interface.md` for the architecture
decision; this is the practical authoring guide.

---

## 1. The contract in one paragraph

A routing pattern turns a **flat board context** (active-area length/width,
layer count, phase count, DFM trace/space limits, plus user parameters) into a
**`RoutingResult`** — a list of _segments_ (straight lines), _curves_ (arcs), and
_vias_, each carrying its own `layer` and `net`.

- The plugin supplies **only raw geometry**. It does **NOT** set trace width,
  via drill size, or annular ring — those are owned by the **`pcbmotorgen-dfm`
  crate** (`DesignRules`, downstream of routing since kata 0rgs) and consumed
  when the KiCad adapter (`pcbmotorgen-export`) converts the generic model to
  board items.
- The plugin does **NOT** do interference checking. The `pcbmotorgen-dfm`
  crate runs all clearance / via-pad DRC (`check_interference`) downstream,
  after the plugin returns — any routing is allowed in the generator; DFM is
  reported as diagnostics only.
- Any malformed shape (NaN, out-of-bounds, bad layer, degenerate segment/arc,
  bad net, empty result) is **rejected** at upload with a field-level error. It
  is never silently patched.

The host may wrap the validated result in a `RoutingReport`. That report adds
pole-pitch and phase-band width dimensions for the application and magnet-pattern
calculator; it does **not** change the strict plugin output shape.

---

## 2. The `RoutingResult` shape (millimetres; x = travel axis, y = across width)

```
RoutingResult {
  segments:  [ RouteSegment { start: {x,y}, end: {x,y}, layer, net, is_active } ],
  curves:    [ RouteCurve    { start: {x,y}, mid: {x,y}, end: {x,y}, layer, net, is_active } ],
  vias:      [ Via          { position: {x,y}, from_layer, to_layer, net } ],
  phase_bands: [ PhaseBand { layer, net, centerline_x_mm, start_x_mm, end_x_mm,
                             y_min_mm, y_max_mm, shape } ],   // optional (kata hzs2)
  io_pads:   [ IoPad        { position: {x,y}, size: {x,y}, drill_mm?, layers: [..],
                            kind: "smd"|"tht"|"board_edge", net, number? } ],   // optional
  io_traces: [ IoTrace       { start: {x,y}, end: {x,y}, layer, net, role: "fanout"|"tail" } ], // optional
}
```

- `layer` / `from_layer` / `to_layer` are indexes into the board copper stack
  (`0 .. num_layers-1`). **The pattern owns layer semantics** — a 2-layer braid
  emits segments on layers `0` and `1` and vias routing `0 → 1`.
- `net` is a phase label (`"A"`, `"B"`, `"C"` …). The writer prefixes `/`.
- `is_active` marks force-producing conductors vs end-turns (always allowed).
- `curves` are optional (arcs), matching KiCad's `(arc start mid end)`.
- `io_pads` / `io_traces` are optional and additive (serde-defaulted): declare
  connector/IC pads and terminal fanout traces only when your pattern routes
  IO to the controlling IC. In practice you usually should NOT: since kata
  xa0f the **host** generates the IO fanout itself, pattern-agnostically,
  when called through the opt-in `generate_routing_*_with_io` entry points
  (board-edge connector row strategy, `docs/API.md` §5.3.1/§13.1). Patterns
  stay motor-focused. Pad `size` comes from the DFM rules
  (`DesignRules::io_tht_pad_diameter_mm()` for THT stacks, `pcbmotorgen-dfm`
  crate) — the writers carry
  sizes through and never decide them. THT pads require `drill_mm`; surface
  pads (`smd` / `board_edge`) reject it. See `docs/API.md` §5.3.

---

## 3. Exposing metadata (name, author, version, description)

### Rust crate plugin

Implement the accessors on `RoutingPattern`:

```rust
impl RoutingPattern for MyGenerator {
    fn id(&self) -> &str { "my-generator" }          // registry key
    fn display_name(&self) -> &str { "My Generator" }
    fn author(&self) -> &str { "You <you@example.com>" }
    fn version(&self) -> &str { "1.2.0" }
    fn description(&self) -> &str { "A nifty winding." }
    // Optional layer-range metadata (default None = unconstrained). Declare
    // it so the app can constrain its layer selector and reject unsupported
    // stacks at generate time instead of inside your `generate`.
    fn min_layers(&self) -> Option<u32> { Some(2) }          // e.g. needs two distinct copper layers
    fn max_layers(&self) -> Option<u32> { None }             // no upper bound
    fn layers_multiple_of(&self) -> Option<u32> { Some(2) }  // even-only stacks
    // ...
}
```

### Python runner

The runner prints a JSON **metadata block** when invoked with `--metadata`, and
exits 0:

```python
#!/usr/bin/env python3
import json, sys

PLUGIN = {
    "id": "my-generator",
    "display_name": "My Generator",
    "author": "You <you@example.com>",
    "version": "1.2.0",
    "description": "A nifty winding.",
    "min_layers": 2,                     # optional layer-range metadata
    "max_layers": None,                  # None/absent = unconstrained
    "layers_multiple_of": 2,             # even-only stacks
    "parameters": [                      # optional
        {"key": "num_strands", "label": "Strands", "description": "Braided paths per period",
         "param_type": "int", "default": 5, "min": 2, "max": 99, "step": 1,
         "multiple_of": 2},
    ],
}

if "--metadata" in sys.argv:
    json.dump(PLUGIN, sys.stdout)
    sys.exit(0)
```

The metadata block is **optional** — if the runner doesn't support `--metadata`,
the app falls back to the file stem as the id and leaves author/version blank.

### Winding end type

Generators can declare `end_type` in their metadata. For a fixed winding use
`{"kind": "fixed", "connection": "star"}`. The connection is `star`, `delta`,
or `closed`. For a parameter-controlled winding, declare its exact values:

```json
"end_type": {
  "kind": "parameter",
  "key": "connection",
  "default": 0,
  "options": [
    { "value": 2, "connection": "star" },
    { "value": 1, "connection": "delta" },
    { "value": 0, "connection": "closed" }
  ]
}
```

The default must match generation when the parameter is absent in a saved file.
It does not change the default for new projects. The host presents these choices
as routing sources and shows the declared connection read-only in Coil ends.
Legacy closed rings remain visible when selected in an existing file. Without
this metadata, Coil ends retains an editable winding selector, as it does for
uploaded copper. Rust generators override `RoutingPattern::metadata` and set
`PluginMetadata::end_type`; Python runners return the same JSON with `--metadata`.
Native plugins must rebuild against API version 3 because the metadata structure
has changed. Version 2 binaries fail the version check before their pattern is created.

---

## 4. Exposing parameters to the app

Patterns declare their **user-editable knobs** with `PatternParameter`:

| field         | type                 | meaning                                        |
| ------------- | -------------------- | ---------------------------------------------- |
| `key`         | String               | lookup key (goes into `RoutingContext.params`) |
| `label`       | String               | UI label                                       |
| `description` | String               | tooltip                                        |
| `param_type`  | `"int"` \| `"float"` | renders an integer or float control            |
| `default`     | f64                  | default value when unset                       |
| `min` / `max` | f64? (any type)      | inclusive range clamp (validated in routing) |
| `step`        | f64?                 | spinner step                                   |
| `multiple_of` | f64?                 | "value must be a multiple of this" constraint (validated in routing) |

### Rust

```rust
fn parameters(&self) -> Vec<PatternParameter> {
    vec![
        PatternParameter::int("num_strands", "Strands per period", 5.0, 2.0, 99.0)
            .with_description("Number of braided paths in each period.")
            .with_multiple_of(2.0),  // the braid needs an even strand count
    ]
}
```

`multiple_of` (optional, serde-defaulted) is enforced by the routing crate with
the same `1e-9` epsilon discipline as the min/max clamp; the app mirrors it
onto the input's step + invalid state so an off-multiple value cannot be
submitted.

At generate time the user's values arrive in `ctx.params.get("num_strands")`;
the pattern calls `ctx.param("num_strands", 5.0)` to read it with a fallback.
Any parameter representing a routing length or width is also in millimetres;
angles remain radians or degrees only where the parameter explicitly says so.

### Python

Declare `parameters` inside the `--metadata` block (shown above). Each dict maps
1:1 onto `PatternParameter`.

### Deriving vs declaring

Parameters that are **derived from the board** must be computed **inside** the
pattern and must **NOT** be exposed as parameters. Example: the infinity braid's
amplitude `A = board_width / 2` and total length `D = active_area` (the routing domain equals the active area)
come from the context. Only genuinely independent user knobs (strand count,
period count, angles…) should be declared. Out-of-range user values are rejected
by the routing crate: `float` below `min` gives _"…is below the minimum … for
pattern "…""_.

### Phase-band width and pole-pitch handoff

Do not add `band_width_mm` or `pole_pitch_mm` as duplicated user parameters. The
host computes these dimensions from the board context and returned active
geometry so they cannot drift away from the active area or magnet layout.

The two equations used by the sidecar are:

```text
w_s = (N * w_t + (N - 1) * s) / sin(theta)
max(w_s) = tau_p / phases - g_phase
```

`theta` is measured from the x/travel axis, `tau_p` is centre-to-centre
North/South pole pitch, and `g_phase` is the core's minimum spacing rule. A
`PhaseBandWidth` record includes the exact `N`, `w_t`, `s`, `theta`, calculated
`band_width_mm`, maximum, and margin. A negative margin is returned as a DFM
diagnostic; the host never modifies plugin coordinates.

Patterns own pole-region semantics as well as trace geometry. Return one
`pole_regions` record per phase and pole pitch when the pattern has a pole
layout. Each record contains `phase`, zero-based `pole_index`, and millimetre
`start`/`end` points. The host must not reconstruct these boundaries from
segments. For the infinity braid, each shared boundary is the midpoint between
the rightmost point-3 of one diamond period and the leftmost point-1 of the
next period. Point 0 (the top vertex) is not used as the pole boundary.
The infinity pattern extrapolates the first and last boundaries from the
interior median spacing so edge regions remain equal in width for visualization.

### Declaring phase bands (kata hzs2)

Patterns that have a clear phase-band layout SHOULD declare it on the result
(`RoutingResult.phase_bands`): one `PhaseBand` record per `(layer, net)` band
with

- `centerline_x_mm` — the centerline of the band's first repeating instance
  (the **phase reference position**). Adjacent phase bands must sit one
  phase-band pitch apart in the centerlines; simulation commutation derives
  the per-phase electrical offsets from these centerline distances
  (offset = π·Δx/τ_p), so the declaration must match the laid-out geometry.
- `start_x_mm` / `end_x_mm` — the band's along-travel extent as laid out
  (for a repeating layout: the full span of all repeats).
- `y_min_mm` / `y_max_mm` — the band's across-travel extent.
- `shape` — `linear` (straight legs at a fixed angle) or `braided` (strands
  crossing over the extent).

Declaring is optional: when a pattern declares no bands, the host derives
them in the dimension sidecar from the ideal phase-band pitch `τ_p/phases`
and marks them `derived`. Declared bands pass the same strict validator as
the geometry (finite, in-bounds, non-degenerate extents, valid layer/net)
and are never sanitised. For the bundled infinity braid the declaration is
consistent with its `pole_regions` emission: the centerline is the first
pole region's center, the extent spans all of the phase's pole regions, and
the diamonds cover the full board width.

For the bundled infinity braid, `period_pitch_mm` is exactly the context's
`magnet_pitch_mm` whenever magnet data is supplied. Its phase/strand via grid
uses `magnet_pitch_mm / (phases × strands)` for both the final within-phase
step and the boundary from one phase to the next. A custom pattern can expose
a `num_strands` or `trace_count` parameter so
the generic report can use that value as `N`; otherwise it reports one trace.
(Whole-coil winding counts such as `turns` are deliberately NOT consulted —
they are not per-bundle strand counts.)

---

## 5. The strict-shape validator (what gets rejected)

`Validator::validate` rejects (on upload, before anything is written) results
containing:

- **Non-finite** coordinates (NaN/Inf).
- **Out-of-bounds** x/y outside `active_area` × `board_width` (the routing domain equals the active area).
- **Bad layer** index `≥ num_layers`; a via with `from_layer == to_layer`.
- **Degenerate** zero-length segments or collapsed arcs.
- **Bad net** (empty or non-ASCII label).
- **Empty** result (no segments/curves/vias).
- **Continuity** break when `expects_continuous()` is `true`.

Useful error messages are returned to the UI, e.g.
`segments[3].end.y: y = -10.000 mm outside the board width [0, 20.000 mm]`.

---

## 6. Authoring a Rust `cdylib` plugin

A native plugin is a `cdylib` compiled against the **same** `pcbmotorgen-routing`
crate version. See `crates/routing-plugin-example` for a complete, working
reference. The C-ABI surface is:

```rust
#[no_mangle]
pub static pcbmotorgen_ROUTING_PLUGIN_API: u32 = 3;  // end-type metadata; millimetre contract

#[no_mangle]
pub unsafe extern "C" fn pcbmotorgen_routing_plugin_create() -> *mut std::ffi::c_void {
    let inner: Box<dyn RoutingPattern> = Box::new(MyGenerator);
    let outer: Box<Box<dyn RoutingPattern>> = Box::new(inner); // double-box preserves the vtable
    Box::into_raw(outer) as *mut std::ffi::c_void
}

#[no_mangle]
pub unsafe extern "C" fn pcbmotorgen_routing_plugin_destroy(v: *mut std::ffi::c_void) {
    if !v.is_null() { drop(Box::from_raw(v as *mut Box<dyn RoutingPattern>)); }
}
```

Both host and plugin must link the same `pcbmotorgen-routing` crate so the
trait-object vtable layout matches. Build with `crate-type = ["cdylib"]`
(`librouting_plugin_example.dylib` on macOS, `.so` on Linux, `.dll` on Windows).

> **Warning:** loading a native library executes its code. Only load plugins you
> trust. The app loads the file the user explicitly picked via **Browse…**.

---

## 7. Authoring a Python runner

A Python runner is a standalone `.py` script with two modes:

1. **Default mode** — reads the `RoutingContext` JSON on **stdin**, prints one
   strict `RoutingResult` JSON to **stdout**, and prints _nothing else_ to
   stdout. Non-zero exit or extra stdout text is treated as a malformed output.
2. **`--metadata` mode** — prints a `PluginMetadata` (name/author/version +
   parameters) and exits 0. Optional.

See `scripts/pattern_runners/example_runner.py` (a fully valid minimal runner)
and `docs/reference/pcbBraid` (the reference braid algorithm to port).

The Rust loader executes `python3 <script>`, feeds the context on stdin, parses
stdout as `RoutingResult`, then runs the result through the **same** strict
validator as native plugins — a Python pattern cannot bypass any shape rule.
The loader does not accept a `RoutingReport` envelope from Python; dimension
metadata is calculated by the host after validation.

---

## 8. Loading into the app

In the **Routing pattern** panel:

1. Choose **Native crate plugin** or **Python runner**.
2. Click **Browse…** to pick the `.dylib`/`.so`/`.dll`/`.py` file.
3. Optionally set a **Pattern name** (registry id).
4. Click **Load generator**. The plugin is probed against the current config;
   if it passes, it is **persisted** into the app's data directory
   (`app_data/plugins/`) and added to the installed list. If it fails, the
   rejection error is shown.

Installed generators are re-loaded automatically on the next app start
(`load_installed_plugins`), and can be removed from the **Installed generators**
list.

### Directory layout (macOS example)

```
~/Library/Application Support/<app-identifier>/plugins/
    plugins.json            # installed-plugin manifest
    my-generator.py         # stored python runner
    my_braid.dylib          # stored native plugin
```

---

## 9. Quick checklist

- [ ] Return valid geometry within the board bounds, layers `< num_layers`.
- [ ] No NaN / zero-length segments / self-looped vias.
- [ ] Net labels are non-empty ASCII phase names.
- [ ] Derive board-sized quantities from the context; expose only true knobs
      as `parameters`.
- [ ] Declare layer-range metadata (`min_layers` / `max_layers` /
      `layers_multiple_of`) when your pattern needs a specific stack; declare
      `multiple_of` on parameters whose values must be multiples.
- [ ] Implement metadata (author, version, description) — Rust accessors or the
      Python `--metadata` block.
- [ ] Keep output to raw geometry only — never set widths / via sizes / DRC
      (the downstream `pcbmotorgen-dfm` crate owns `DesignRules` and runs
      interference checks).
- [ ] Keep Python output to strict `RoutingResult` JSON — do not emit the
      host-side `RoutingReport` envelope.
- [ ] Emit `io_pads` / `io_traces` only when your pattern actually routes IO;
      they are optional, and IO traces must never be force-producing
      conductors (that is what `segments[].is_active` is for).
