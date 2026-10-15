# pcbmotorgen-routing API

**Status:** Active (wire contract `format_version = 2`)
**Owner:** `crates/pcbmotorgen-routing` (model, validator, loaders, report —
the full routing-pattern plugin contract; DFM lives downstream in
`pcbmotorgen-dfm`)
**Canonical reference:** this document consolidates the package README, the
original routing-pattern specification (`SPEC.md`), the field-level handoff
contract, and the authoring guide. Companion deep-dives remain at
[`routing-pattern-handoff.md`](./routing-pattern-handoff.md),
[`routing-pattern-authoring.md`](./routing-pattern-authoring.md), and
[`routing-readme-guide.md`](./routing-readme-guide.md).

---

## 1. Overview and scope

`pcbmotorgen-routing` is the leaf Rust crate that turns a motor-board context
into validated PCB stator routing geometry. It is intentionally independent of
the application's `LinearMotorConfig` and of the physics, magnet, and KiCad
crates, so it can be developed and tested alone.

The crate owns:

- the strict `RoutingPattern` plugin interface;
- the canonical `RoutingResult` geometry model (`segments`, `curves`, `vias`,
  `pole_regions`);
- the strict-shape `Validator` and structured field-level errors;
- the registry and dynamic loaders (Rust `cdylib` plugins + Python runners);
- the bundled two-layer `infinity-braid` reference pattern; and
- the pole-pitch and active-conductor-band (`phase_band_widths`) calculations needed to
  hand traces off to a magnet-array calculator.

The crate does **not** own:

- KiCad layer-name mapping (`layer_idx → B_Cu / In*_Cu / F_Cu`) — that stays in
  the KiCad writer (`pcbmotorgen-export`);
- DFM (design-for-manufacturing): trace width / clearance / via sizing
  (`DesignRules`) and DRC interference diagnostics (`check_interference`)
  live downstream in `pcbmotorgen-dfm` (kata 0rgs). The context's
  `min_trace_mm` / `min_space_mm` / `phase_clearance_mm` fields stay part of
  this wire contract — patterns consume them for layout and phase-band math;
  the DFM crate reads the mirrored `DesignRules` snapshot instead (§4, §7, §9);
- copper widths / via sizes supplied by the application core — the app mirrors
  them into `DesignRules` (`pcbmotorgen-dfm`) and the writer merely consumes
  them;
- the physics / force model (`pcbmotorgen-simulation`);
- any external interchange format such as circuit-json, or PCB file formats
  (KiCad / DXF / Gerber).

### Module map

| Module | Purpose |
| --- | --- |
| `model` | Canonical `RoutingResult` (segments, curves, vias, pole regions). |
| `context` | Flat `RoutingContext` snapshot fed to every pattern. |
| `pattern` | The `RoutingPattern` trait, `PatternParameter`, `PluginMetadata`. |
| `validator` | The single strict-shape gate every result must pass. |
| `dimensions` | Pole pitch, phase-band budget, and phase-band width calculations. |
| `report` | `RoutingReport` — validated geometry plus its dimension sidecar. |
| `coil` | `PhaseCoil` presentation model (grouped by layer + net). |
| `registry` | `RoutingRegistry` patterns register into. |
| `loaders` | Dynamic loading of patterns (Rust `cdylib` + Python runners). |
| `patterns` | Bundled reference patterns (the `infinity` braid). |
| `generate` | App-facing facade: registry, loading, context → result/coils, and the opt-in host IO fanout step (`io_fanout`, §13.1). |
| `error` | `RoutingError` / `RoutingErrorKind` structured field-level errors. |

> **DFM modules moved out (kata 0rgs):** the former `design` (`DesignRules`)
> and `interference` (`check_interference`) modules now live in the
> downstream `pcbmotorgen-dfm` crate (`crates/pcbmotorgen-dfm`), which depends
> on this crate. See §7 and §9.

## 2. Units and coordinate conventions

| Quantity | Convention |
| --- | --- |
| Units | **Millimetres (mm)** for all lengths. Base unit throughout the wire format and all dimensions. |
| X axis | Travel axis (stator length). |
| Y axis | Across board width (perpendicular to travel). |
| Z axis | Not part of the wire format; depth is encoded by the `layer` index. |
| `layer` | Zero-based index into the copper stack `[0, num_layers)`. **The pattern owns layer semantics.** |
| `net` | Phase/net label, e.g. `"A"`, `"B"`, `"C"`; ASCII and non-empty. The KiCad writer prefixes `/`. |
| Angles | Radians when reported in the dimension sidecar (`angle_rad`); a pattern parameter may declare degrees only when its label says so explicitly. |

Never show a bare example number without its unit: write `12 mm`, not `12`.

## 3. Architecture: one interface, three delivery mechanisms

Every routing pattern — bundled, Rust `cdylib` crate plugin, or Python runner —
produces its geometry through **one canonical interface** and is validated
identically.

| Source | Mechanism |
| --- | --- |
| Bundled pattern | `RoutingPattern` trait, same process (`patterns/infinity`). |
| Rust crate plugin | `cdylib` with a stable C ABI (`pcbmotorgen_routing_plugin_create`), loaded via `libloading`. |
| Python runner | Subprocess: receives the flattened `RoutingContext` JSON on stdin, emits the strict `RoutingResult` JSON on stdout (nothing else), then passes the same validator. |

```
                       ┌────────────────────────────────────────────┐
   RoutingContext ───▶ │  RoutingPattern.generate(ctx)             │
  (flat snapshot)      │  (bundled | cdylib | python runner)        │──▶ RoutingResult
                       │                                            │
                       └──────────────────┬─────────────────────────┘
                                          │ Validator::validate (reject, never sanitise)
                                          ▼
                                   validated RoutingResult
                                          │
                     ┌────────────────────┼─────────────────────────┐
                     ▼                    ▼                         ▼
              RoutingReport      PhaseCoil (preview /      KiCad + DXF writers
              (+ dimensions)     simulation model)         (pcbmotorgen-export)
```

## 4. Input contract: `RoutingContext`

A flat snapshot handed to every pattern at generate-time. Patterns must not
depend on the concrete core `LinearMotorConfig`; this snapshot is the entire
world. The parent application converts its SI/metre config at the routing
boundary.

```json
{
  "active_area_length_mm": 195.0,
  "board_width_mm": 20.0,
  "num_layers": 4,
  "phases": 3,
  "min_trace_mm": 0.127,
  "min_space_mm": 0.127,
  "expects_continuous": false,
  "params": { "num_strands": 5 },
  "magnet_pitch_mm": 12.0,
  "magnet_array_span_mm": 120.0
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `active_area_length_mm` | `f64` | Copper active-area length along travel [mm]. |
| `board_width_mm` | `f64` | PCB dimension perpendicular to travel [mm]. |
| `num_layers` | `u32` | Copper layers in the stack. |
| `phases` | `u32` | Electrical phase count. |
| `min_trace_mm` | `f64` | Minimum manufacturable trace width [mm]. |
| `min_space_mm` | `f64` | Minimum trace-to-trace clearance [mm]. |
| `expects_continuous` | `bool` | Whether the pattern declares end→start continuity per (layer, net), driving the validator continuity check. |
| `params` | `{string → number}` | Pattern-specific user-editable parameters. |
| `magnet_pitch_mm` | `f64?` | Pole pitch, centre-to-centre North/South distance (`tau_p`), when the mover layout is known [mm]. |
| `magnet_array_span_mm` | `f64?` | Full mover magnet-array span, when known [mm]. |

Convenience accessors on the Rust type: `ctx.param(key, default)` reads a
parameter with a fallback; `ctx.magnet_pitch()` resolves the pole pitch (only
when `> 0`); `ctx.magnet_array_span()` resolves the mover span.

`min_trace_mm` / `min_space_mm` / `phase_clearance_mm` are wire-contract
fields consumed by patterns (layout + phase-band math, §10.1). They are not
the DFM authority: sizing and DRC clearance decisions live downstream in
`pcbmotorgen-dfm`, which reads the `DesignRules` snapshot the app bridges
from the same config values (§7, §9).

## 5. Output contract: `RoutingResult`

The canonical geometry document. Every element carries its own `layer` and
`net`; the pattern owns layer semantics. A plugin emits **only raw geometry** —
no trace widths, via sizes, or KiCad layer names.

```json
{
  "format_version": 2,
  "segments": [
    {
      "start": { "x": 0.0, "y": 0.0 },
      "end": { "x": 0.0, "y": 20.0 },
      "layer": 0,
      "net": "A",
      "is_active": true
    }
  ],
  "curves": [
    {
      "start": { "x": 1.0, "y": 20.0 },
      "mid": { "x": 1.6, "y": 20.8 },
      "end": { "x": 2.2, "y": 20.0 },
      "layer": 0,
      "net": "A",
      "is_active": false
    }
  ],
  "vias": [
    {
      "position": { "x": 1.0, "y": 10.0 },
      "from_layer": 0,
      "to_layer": 1,
      "net": "A"
    }
  ],
  "pole_regions": [
    {
      "phase": "A",
      "pole_index": 0,
      "start": { "x": 0.0, "y": 10.0 },
      "end": { "x": 12.0, "y": 10.0 }
    }
  ],
  "leg_grid": { "slot_count": 975, "strands_per_leg": 5 },
  "phase_bands": [
    {
      "layer": 0,
      "net": "A",
      "centerline_x_mm": 7.6,
      "start_x_mm": 1.6,
      "end_x_mm": 781.6,
      "y_min_mm": 0.0,
      "y_max_mm": 20.0,
      "shape": "braided"
  "io_pads": [
    {
      "position": { "x": 48.0, "y": 2.0 },
      "size": { "x": 0.6, "y": 0.6 },
      "drill_mm": null,
      "layers": [1],
      "kind": "smd",
      "net": "A",
      "number": "1"
    }
  ],
  "io_traces": [
    {
      "start": { "x": 0.0, "y": 10.0 },
      "end": { "x": 47.0, "y": 2.0 },
      "layer": 1,
      "net": "A",
      "role": "fanout"
    }
  ]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `format_version` | `u32` | Wire-contract version. Absent ⇒ `2` (serde default; see §15). |
| `segments[]` | segment | Straight traces: `start`/`end` points `{x, y}`, `layer`, `net`, `is_active`. |
| `curves[]` | curve | Rounded corners / arcs — quadratic Bézier `start → mid → end`; `mid` is the control point on the arc (matches KiCad `(arc start mid end)`). |
| `vias[]` | via | Inter-layer connections: `position`, `from_layer`, `to_layer`, `net`. |
| `pole_regions[]` | region | Pattern-defined phase/pole-pitch boundaries: `phase`, zero-based `pole_index`, millimetre `start`/`end` points. Optional. |
| `leg_grid` | `object?` | Optional pattern-declared leg grid (see §10.2). |
| `phase_bands[]` | band | Optional pattern-declared phase-band geometry, one record per `(layer, net)` band (see §5.2). Additive; omit when the pattern has no band layout to declare. |
| `io_pads[]` | pad | Connector/IC pads for IO routing: `position`, pad-stack `size` (`{x, y}` mm; `x == y` ⇒ circular), `drill_mm` (THT only), `layers` (empty ⇒ exporter default set for the kind), `kind` (`smd` / `tht` / `board_edge`), `net`, optional `number` (pad/pin label). Optional. |
| `io_traces[]` | trace | Terminal fanout traces, typed distinctly from active conductors: `start`/`end`, `layer`, `net`, `role` (`fanout` / `tail`). Optional. |

`is_active` distinguishes **force-producing conductors** (`true`) from
**end-turn connectors** (`false`).

### 5.1 Pole regions

`pole_regions[]` is the authoritative region interface for magnet/pole
placement. It is deliberately emitted by the pattern rather than inferred by the
host. Each record has a phase label, a zero-based `pole_index`, and millimetre
`start`/`end` points. The host must never reconstruct these boundaries from
segments.

For the bundled infinity braid, the shared boundary between adjacent regions is
the midpoint between the rightmost point-3 of one diamond period and the
leftmost point-1 of the next; that point is both the preceding region's end and
the following region's start. Point 0 (the top vertex) is not used as the pole
boundary. The first and last regions are centered/extrapolated from the
neighboring median spacing so they have the same width as the interior regions
rather than being clipped to the first or last generated point.

### 5.2 Phase bands (declared geometry, kata hzs2)

`phase_bands[]` is the first-class position + shape contract for phase bands —
the position/shape counterpart of the host-calculated `phase_band_widths[]`
budget records (§10.1): the pattern declares **where** each band sits, the
host derives how **wide** the conductor bundle is. One record per
`(layer, net)` band, in millimetres:

```rust
pub struct PhaseBand {
    pub layer: Layer,            // copper layer carrying the band
    pub net: Net,                // phase/net label
    pub centerline_x_mm: f64,    // centerline x of the band's first repeat
    pub start_x_mm: f64,         // along-travel extent start, as laid out
    pub end_x_mm: f64,           // along-travel extent end (> start)
    pub y_min_mm: f64,           // across-travel extent lower bound
    pub y_max_mm: f64,           // across-travel extent upper bound
    pub shape: PhaseBandShape,   // "linear" | "braided"
}
```

- `centerline_x_mm` is the **phase reference position**: the centerline of the
  band's first repeating instance (for a single-instance band, the band's own
  centerline). Simulation commutation derives the per-phase electrical
  offsets from the centerline distances between phases (glossary
  "Commutation": offset = π·Δx/τ_p), so adjacent phase bands must sit one
  phase-band pitch apart in the centerlines, matching the laid-out geometry.
- `start_x_mm`/`end_x_mm` span the band **as the pattern lays it out** — for a
  repeating layout that is the full span of all repeats.
- `shape` says how the band occupies its y-extent: `linear` (straight legs at
  a fixed angle, e.g. a serpentine) or `braided` (strands crossing over the
  extent, e.g. the infinity braid's diamonds).

Declaring is optional. When a pattern declares no bands, the host derives
them in the `RoutingDimensions` sidecar from the ideal phase-band pitch
`τ_band = τ_p/phases` and marks them `derived` (§10.4). Declared bands are
validated like every other geometry (finite, in-bounds, non-degenerate
extents, valid layer/net) and are never sanitised.
### 5.3 IO elements: connector/IC pads and terminal fanout traces (additive)

`io_pads[]` and `io_traces[]` are the additive interface for input/output
routing to the controlling IC. Both fields are serde-defaulted, so legacy
payloads and non-IO patterns deserialize unchanged and `FORMAT_VERSION` is
unaffected (see §15). Two producers exist:

- **Patterns** may declare IO elements directly (the schema supports it);
  patterns stay motor-focused and are not expected to.
- **The host** (kata xa0f) generates IO routing after pattern generation and
  before validation, via the opt-in `generate_routing_*_with_io` entry
  points (§13.1). This is pattern-agnostic: it works for bundled, native
  plugin, and Python runner patterns alike.

- `IoPad` carries the full pad-stack definition the writer needs: centre
  `position`, copper `size` (`{x, y}` in mm — equal extents mean a circular
  pad), optional plated `drill_mm`, the copper `layers` it occupies
  (zero-based board-stack indices; empty means the exporter's default set for
  the kind — all copper layers for `tht`, the top layer for surface pads),
  the `kind` (`smd` / `tht` / `board_edge`, mapping onto KiCad's
  `PT_SMD` / `PT_PTH` / `PT_EDGE_CONNECTOR`), the phase `net`, and an
  optional pad `number` (carried through to KiCad as the pad number).
- `IoTrace` is deliberately a distinct element family from `segments[]` so
  DFM checks can treat IO routing differently — it is never a
  force-producing conductor. `role` distinguishes a `fanout` (coil terminal →
  pad) from a `tail` (pad → board-edge exit).

The strict-shape validator (§8) checks IO elements like every other element:
domain bounds (the routing domain equals the active area — the epsilon lets
board-edge pads sitting exactly on a boundary pass), positive finite pad
sizes, `tht` pads require a positive `drill_mm` while `smd` / `board_edge`
pads reject one, and layer/net rules. Generated IO is held to the same
rejected-not-sanitised standard: the generator emits valid geometry by
construction, and anything that does not pass is a generation error.

Sizing authority: pad dimensions remain governed by `DesignRules`
(downstream in `pcbmotorgen-dfm`, kata 0rgs) — callers read sizes from there
(e.g. `DesignRules::io_tht_pad_diameter_mm()` for a THT pad stack) and bridge
them into the generation options; the generator reads sizes and never
decides them. The writers only carry the declared sizes through.

#### 5.3.1 Host placement strategy (default, kata xa0f)

`generate_io_fanout` implements one deterministic default strategy — a
**board-edge connector row**:

1. **Terminals.** Elements are grouped by `(layer, net)` (the same grouping
   as the `PhaseCoil` adapter); each group contributes its first element's
   start and last element's end as its two electrical terminals.
2. **Rows.** Each terminal fans out to the **nearest across-travel board
   edge** (`y ≤ board_width/2` → the `y = 0` row, else the
   `y = board_width` row; the tie goes to `y = 0`). `IoFanoutEdge::AcrossMin`
   / `AcrossMax` force a single row instead.
3. **Pad slots.** Within a row, pads are evenly spaced along the travel axis
   (end pads one pad diameter inboard of the x extremes), assigned to
   terminals in x order — a monotone assignment, so fanout traces within a
   row never cross each other. Pads are numbered `1..N` in emission order
   (min row first, left to right).
4. **Pad stack.** `IoFanoutOptions::tht` (the canonical sizing path —
   `DesignRules::io_fanout_options()`) emits `tht` pads one pad radius
   inboard of the edge so the drill stays on the board, declaring **all**
   copper layers (a through-hole pad spans the stack, so the fanout connects
   from any layer). `IoFanoutOptions::board_edge` emits castellated
   `board_edge` pads centred exactly on the outline, declaring exactly the
   fanout's layer. An IC-footprint strategy (pads in the active area, with
   `tail` traces to the edge) remains possible through the schema but is not
   generated by this step.
5. **Nets.** Pass-through: a pad/trace inherits the net (phase label) of the
   coil terminal it connects. A phase with several coil groups gets several
   same-net connector pins.
6. **Layers / crossings.** Fanouts stay on a single layer (the terminal's
   layer) — **no vias are generated**: the nearest-edge row makes every
   fanout a short straight trace, so a layer change is never genuinely
   required. `IoTraceRole::Tail` is not used by the default strategy (the
   pads already sit at the exit).
7. **Determinism.** The step is a pure function of
   `(result, context, options)`; a terminal that coincides with its pad slot
   is resolved by a deterministic in-bounds nudge so no zero-length trace is
   ever emitted (the validator rejects those).

## 6. The `RoutingPattern` trait

```rust
pub trait RoutingPattern: Send + Sync {
    fn id(&self) -> &str;          // stable registry key, e.g. "infinity-braid"
    fn display_name(&self) -> &str;
    fn author(&self) -> &str { "" }
    fn version(&self) -> &str { "" }
    fn description(&self) -> &str { "" }
    fn parameters(&self) -> Vec<PatternParameter> { Vec::new() }
    fn min_layers(&self) -> Option<u32> { None }           // layer-range metadata
    fn max_layers(&self) -> Option<u32> { None }
    fn layers_multiple_of(&self) -> Option<u32> { None }   // e.g. Some(2) = even-only stacks
    fn expects_continuous(&self) -> bool { false }
    fn generate(&self, ctx: &RoutingContext) -> Result<RoutingResult, RoutingError>;
}
```

`author` / `version` / `description` default to empty; `parameters()` defaults to
none; the layer-range accessors default to `None` (unconstrained);
`expects_continuous()` defaults to `false`. `metadata()` composes all of the
above into a `PluginMetadata`.

**Layer-range metadata.** `min_layers()` / `max_layers()` declare the copper
stack sizes a pattern supports, and `layers_multiple_of()` adds a
multiple-of constraint (e.g. `Some(2)` = even-only stacks). All three default
to `None` = unconstrained, so existing patterns are unaffected (additive).
The host validates the context against them at generate-time
(`generate_routing_report` rejects a context whose `num_layers` violates the
declared range with a helpful error, e.g. `pattern "my-braid" requires at
least 2 copper layer(s), got 1`) and exposes them through the plugin catalog
(`available_pattern_metadata`) so the app can constrain its layer selector.
The bundled infinity braid declares `min_layers = Some(2)` (its top/bottom
braid needs two distinct copper layers).

### 6.1 Parameters

A pattern declares its user-editable knobs with `PatternParameter`:

| Field | Type | Meaning |
| --- | --- | --- |
| `key` | `String` | Lookup key (goes into `RoutingContext.params`). |
| `label` | `String` | UI label. |
| `description` | `String` | Tooltip. |
| `param_type` | `Int` \| `Float` | Renders an integer or float control. |
| `default` | `f64` | Default when unset. |
| `min` / `max` | `f64?` | Inclusive range clamp, validated by the routing crate. |
| `step` | `f64?` | Spinner step. |
| `multiple_of` | `f64?` | "Value must be a multiple of this" constraint (e.g. `2.0` = even-only strand counts), validated by the routing crate. |

Constructors: `PatternParameter::int(key, label, default, min, max)` and
`PatternParameter::float(key, label, default)`, plus `.with_description(...)`
and `.with_multiple_of(m)`.

`multiple_of` is enforced by `validate_routing_params` with the same `1e-9`
epsilon discipline as the min/max checks: a value within `1e-9` of a valid
multiple passes (float noise), everything else is rejected before generation,
e.g. `Strands = 3 is not a multiple of 2 for pattern "my-braid"`. The app
mirrors the constraint onto the input's step + invalid state so an incorrect
value cannot be submitted; the routing crate remains the authority.

At generate-time the user's values arrive in `ctx.params.get(key)`; the pattern
reads them with `ctx.param("num_strands", 5.0)`. A parameter representing a
routing length or width is also in millimetres; angles remain radians or degrees
only where the parameter explicitly says so.

**Deriving vs declaring.** Parameters that are derived from the board must be
computed **inside** the pattern and must **NOT** be exposed as parameters.
Example: the infinity braid's amplitude `A = board_width / 2` and total length
`D = active_area` (the routing domain equals the active area — there is no end padding) come from the context. Only genuinely independent
user knobs (strand count, period count, angles…) should be declared.
Out-of-range user values are rejected before generation with a helpful error,
e.g. `Strands per period = 1 is below the minimum 2 for pattern "infinity-braid"`.

**Do not** duplicate `band_width_mm` or `pole_pitch_mm` as user parameters: the
host computes these dimensions from the board context and returned active
geometry so they cannot drift away from the active area or magnet layout.

### 6.2 Metadata

Rust patterns implement the trait accessors. A Python runner optionally prints
a `PluginMetadata` JSON block when invoked with `--metadata` and exits 0; if the
runner does not support it, the app falls back to the file stem as the id and
leaves author/version blank.

```python
PLUGIN = {
    "id": "my-generator",
    "display_name": "My Generator",
    "author": "You <you@example.com>",
    "version": "1.2.0",
    "description": "A nifty winding.",
    "min_layers": 2,                      # optional layer-range metadata
    "max_layers": None,                   # None/absent = unconstrained
    "layers_multiple_of": 2,              # even-only stacks
    "parameters": [                       # optional
        {"key": "num_strands", "label": "Strands", "description": "Braided paths per period",
         "param_type": "int", "default": 5, "min": 2, "max": 99, "step": 1,
         "multiple_of": 2},
    ],
}
```

Each dict in `parameters` maps 1:1 onto `PatternParameter`; the top-level
`min_layers` / `max_layers` / `layers_multiple_of` keys map onto the trait's
layer-range accessors and flow into `PluginMetadata`.

## 7. Design rules (DFM)

**Moved downstream (kata 0rgs):** `DesignRules` — the trace width / clearance
/ via sizing authority — now lives in the `pcbmotorgen-dfm` crate
(`crates/pcbmotorgen-dfm`, module `rules`). Dependency direction:
`pcbmotorgen-dfm → pcbmotorgen-routing`; the routing crate keeps **no** DFM
types. The strict-shape validator (§8) is wire-contract validation and stays
here.

| Field | Default | Meaning |
| --- | --- | --- |
| `min_trace_mm` | `0.127` (5 mil) | Minimum manufacturable trace width [mm]. |
| `min_space_mm` | `0.127` (5 mil) | Minimum trace-to-trace clearance [mm]. |
| `min_via_drill_mm` | `0.2` | Minimum via drill diameter [mm]. |
| `min_via_annular_ring_mm` | `0.1` | Minimum via annular ring width [mm]. |

Derived helpers on `DesignRules`: `via_pad_diameter_mm() =
min_via_drill_mm + 2 · min_via_annular_ring_mm` (default `0.4` mm),
`via_pad_radius_mm()`, and `io_tht_pad_diameter_mm()` (= the via pad
diameter; the THT IO pad sizing authority, §5.3).

Division of responsibilities after the split:

- Patterns generate **any** geometry; the routing crate validates the wire
  shape (§8) and never applies manufacturability rules.
- The application bridges its config (`min_trace_m`, `min_space_m`,
  `min_via_drill_m`, `min_via_annular_ring_m`) into a `DesignRules` snapshot
  and mirrors the same values into the `RoutingContext` fields listed in §4 —
  the context fields stay contract; `pcbmotorgen-dfm` reads the snapshot for
  sizing and DRC decisions.
- Downstream consumers (the KiCad writer, the DXF exporter) read sizes from
  `DesignRules` — they never decide them.

## 8. Strict-shape validation

`Validator::validate(&RoutingResult, &RoutingContext, expect_continuous)` is the
single gate every result from any source must pass before it can be written,
previewed, or simulated. It returns `Ok(())` or the first `RoutingError`.

A non-conforming document is **rejected with a structured field-level error,
never sanitised.** Rules:

- **Version** — `format_version` must equal `2`; a version-1 metre payload is
  rejected.
- **Non-empty** — the result must contain at least one segment, curve, or via.
- **Finite** — every coordinate must be finite (`NaN`/`Inf` rejected).
- **Bounds** — x within `[0, active_area_length_mm]` (the routing domain equals the active area) and y within
  `[0, board_width_mm]` (inclusive, with a `1e-6` epsilon so exact-boundary
  coordinates pass). Inactive segments (`is_active: false` — end turns and
  terminal leads) are exempt from the y bound so leads can leave the board
  width; they must still be finite and inside the x range.
- **Layer range** — `layer` / `from_layer` / `to_layer` inside `[0, num_layers)`.
- **Vias** — `from_layer` must differ from `to_layer`.
- **Non-degenerate** — segments have non-zero length; arcs have start/mid/end
  that do not collapse to a point; pole regions have non-zero length;
  declared phase bands have non-degenerate along-travel and y extents.
- **Declared phase bands** — finite, in-bounds (x within the routing area, y
  within the board width), valid layer index and ASCII net label.
- **Net labels** — non-empty and ASCII; duplicates allowed only for parallel
  conductors.
- **Continuity** — when `expect_continuous` is set, consecutive elements sharing
  a (layer, net) chain must connect end→start within a tolerance of
  `max(2 · min_trace_mm, 1e-6)`.

### 8.1 Errors

`RoutingError { index, field, kind, message }`:

| Field | Meaning |
| --- | --- |
| `index` | 1-based index of the offending element (0 = whole-result error). |
| `field` | Offending field path, e.g. `"segments[3].end.y"`. |
| `kind` | `RoutingErrorKind`: `Malformed`, `OutOfBounds`, `BadLayer`, `Degenerate`, `BadNet`, `Missing`, `Generation`. |
| `message` | Human-helpful text surfaced in the UI. |

Example surfaced to the user:

```
segments[3].end.y (element #4): y = -10.000 mm outside the board width [0, 20.000 mm]
```

On the first error the upload/generate fails fast with the single structured
error.

## 9. Interference / DRC diagnostics

**Moved downstream (kata 0rgs):** `check_interference(&DesignRules,
&RoutingResult) -> Vec<InterferenceViolation>` now lives in the
`pcbmotorgen-dfm` crate (`crates/pcbmotorgen-dfm`, module `interference`).
The signature is unchanged and the routing crate re-exports nothing.

It reports design-rule violations against the configured widths:

- **Segments** — same-layer, different-net traces closer than
  `min_trace_mm + min_space_mm` (edge-to-edge clearance).
- **IO fanout traces** (kata xa0f) — join the same clearance rule, against
  segments and other IO traces; they are ordinary copper for DRC purposes.
- **Via pads** — via pad (`drill + 2 × annular ring`) on its from/to layers
  closer than `via_pad_radius + trace_width/2 + min_space` to a different-net
  trace (segments or IO traces).
- **IO pads** (kata xa0f) — on each explicitly declared copper layer, closer
  than `pad_radius + trace_width/2 + min_space` to different-net copper, or
  closer than `pad_radius_a + pad_radius_b + min_space` to a different-net IO
  pad sharing a declared layer (the effective pad radius is the half diagonal
  of the pad copper). Pads without declared layers are skipped — the
  exporter's implicit default layer set is unknown downstream; the host IO
  generator always declares its layers explicitly.

Violations are surfaced as `InterferenceViolation { layer, net_a, net_b, kind,
gap_mm, message }` and are **diagnostics only** — they are reported, never used
to silently alter geometry. The check is bounded (200k pair comparisons) to
avoid runaway behavior on pathological inputs. Callers run it downstream of
generation (the app's `check_coil_interference` command), never inside the
generator — any routing is allowed; DFM is reported later.

## 10. Enriched handoff: `RoutingReport` and `RoutingDimensions`

The strict plugin payload remains geometry-only. After generation and
validation, the host may wrap the exact `RoutingResult` in a `RoutingReport`:

```rust
#[derive(Serialize, Deserialize)]
pub struct RoutingReport {
    pub result: RoutingResult,        // the validated canonical geometry
    pub dimensions: RoutingDimensions, // pole pitch + phase-band width sidecar
}
```

The `generate_coils` IPC response exposes the same measurements as
`routing_dimensions`; the Tauri adapter converts those values back to its
existing SI/meter frontend DTO names for compatibility.

```json
{
  "result": {
    "format_version": 2,
    "segments": [ { "start": { "x": 0.0, "y": 0.0 }, "end": { "x": 0.0, "y": 20.0 }, "layer": 0, "net": "A", "is_active": true } ],
    "curves": [],
    "vias": [],
    "pole_regions": [ { "phase": "A", "pole_index": 0, "start": { "x": 0.0, "y": 10.0 }, "end": { "x": 12.0, "y": 10.0 } } ],
    "leg_grid": { "slot_count": 975, "strands_per_leg": 5 },
    "phase_bands": [
      {
        "layer": 0, "net": "A",
        "centerline_x_mm": 7.6, "start_x_mm": 1.6, "end_x_mm": 781.6,
        "y_min_mm": 0.0, "y_max_mm": 20.0, "shape": "braided"
      }
    ]
  },
  "dimensions": {
    "active_area_length_mm": 800.0,
    "total_routing_length_mm": 800.0,
    "board_width_mm": 20.0,
    "phases": 3,
    "magnet_array_span_mm": 120.0,
    "pole_pitch_mm": 12.0,
    "period_pitch_mm": 12.0,
    "period_count": 65,
    "phase_band_pitch_mm": 4.0,
    "phase_clearance_mm": 0.127,
    "max_phase_band_width_mm": 3.873,
    "slot_count": 975,
    "slot_pitch_mm": 0.8205128205128205,
    "interleave_step_mm": 0.8,
    "phase_band_widths": [
      {
        "layer": 0,
        "net": "A",
        "trace_count": 5,
        "trace_width_mm": 0.127,
        "trace_spacing_mm": 0.127,
        "angle_rad": 1.030377,
        "band_width_mm": 1.333,
        "slot_width_mm": 0.148,
        "max_band_width_mm": 3.873,
        "margin_mm": 2.540
      }
    ],
    "pole_regions": [],
    "phase_bands": [
      {
        "layer": 0, "net": "A",
        "centerline_x_mm": 7.6, "start_x_mm": 1.6, "end_x_mm": 781.6,
        "y_min_mm": 0.0, "y_max_mm": 20.0, "shape": "braided",
        "derived": false
      }
    ]
  }
}
```

| Dimension field | Type | Meaning |
| --- | --- | --- |
| `active_area_length_mm` | `f64` | Active copper length from the context [mm]. |
| `total_routing_length_mm` | `f64` | Active length — the routing domain equals the active area [mm]. |
| `board_width_mm` | `f64` | Across-board width used for the braid angle [mm]. |
| `phases` | `u32` | Phase count used for the phase-band calculation. |
| `magnet_array_span_mm` | `f64?` | Full mover magnet-array span [mm], when supplied. |
| `pole_pitch_mm` | `f64?` | Centre-to-centre adjacent North/South pole pitch (`tau_p`) [mm]. |
| `period_pitch_mm` | `f64?` | Pattern repeat pitch [mm]; exact pole pitch for the magnet-aware infinity braid. |
| `period_count` | `u32?` | Complete repeat periods emitted, when known. |
| `phase_band_pitch_mm` | `f64?` | Ideal phase-band pitch, `pole_pitch / phases` [mm]. Distinct from the true slot pitch `slot_pitch_mm`. |
| `phase_clearance_mm` | `f64` | Explicit inter-phase clearance `g_phase` from `RoutingContext.phase_clearance_mm`; when the context leaves it unset, the context's `min_space_mm` is used as a documented fallback [mm]. |
| `max_phase_band_width_mm` | `f64?` | `pole_pitch / phases - phase_clearance` [mm]. |
| `slot_count` | `u32?` | Total active leg slots declared by the pattern's leg grid (`N_slots`), when it declares one. |
| `slot_pitch_mm` | `f64?` | True slot pitch `tau_s = L_stator / N_slots` from the declared leg grid [mm]. |
| `interleave_step_mm` | `f64?` | Effective leg pitch of braided slotless patterns, `tau_p / (phases × strands)` from the declared leg grid [mm]. |
| `phase_band_widths` | array | Per-active-`(layer, net)` bottom-up width records. |
| `pole_regions` | array | Pattern-defined start/end boundaries, copied from the result. |
| `phase_bands` | array | Resolved per-`(layer, net)` phase-band geometry (§5.2): the pattern's declared bands (`derived: false`) or host-derived bands from the ideal phase-band pitch (`derived: true`). Empty when there is no declaration and no pole pitch. |

Each `phase_band_widths[]` record includes `trace_count` (`N`), `trace_width_mm`
(`w_t`), `trace_spacing_mm` (`s`), `angle_rad` (`theta`), the calculated
`band_width_mm`, the glossary-exact single-leg `slot_width_mm`, the top-down
`max_band_width_mm`, and `margin_mm`.
Convenience helpers on `RoutingDimensions`: `all_phase_bands_fit()` and
`pole_to_pole_pitch_mm()`.

### 10.1 Phase-band width equations

For each active `(layer, net)` group, the bottom-up width is:

```text
w_s = (N * w_t + (N - 1) * s) / sin(theta)
```

- `N` = `trace_count` — for the bundled infinity braid the `num_strands`
  parameter; for generic patterns the first present parameter among
  `num_strands` and `trace_count`; otherwise `1`. Whole-coil counts
  (`turns`, `windings_per_phase`) are deliberately **not** consulted: they
  count coil windings, not parallel strands in one bundle, and previously fed
  this equation with silently wrong numbers.
- `w_t` = `trace_width_mm` = `min_trace_mm` from the context.
- `s` = `trace_spacing_mm` = `min_space_mm` from the context.
- `theta` = `angle_rad`, measured from the x/travel axis. An angle parallel to
  the travel axis is rejected because the projection is undefined; geometry is
  never silently changed.

The top-down limit is:

```text
max(w_s) = tau_p / phases - g_phase
```

where `tau_p` is the **centre-to-centre** North/South pole pitch (`pole_pitch_mm`,
not the magnet's physical width) and `g_phase` is `phase_clearance_mm`.
`g_phase` is an **explicit input**: `RoutingContext.phase_clearance_mm` carries
it, and when a context leaves it `None` the context's `min_space_mm`
(trace-to-trace clearance) is used as a documented compatibility fallback.
That fallback keeps legacy contexts working, but it is a real reuse of the
trace clearance rule — set `phase_clearance_mm` explicitly when the
phase-to-phase gap differs from the trace-to-trace clearance.
`phase_band_pitch_mm` is the ideal phase-band pitch `tau_p / phases`; it is
separate from the conductor band width in each `phase_band_widths[]` record.

A negative `margin_mm` is a **diagnostic** that the requested bundle does not
fit — the host never shortens, moves, or sanitises the pattern's coordinates to
hide it. If a context has no magnet pitch, the bottom-up records are still
available and the top-down fields are `null`.

### 10.2 True per-slot metrics (declared leg grid)

A **slot houses one active leg** — never a whole coil bundle (glossary
"Slot"). Alongside the phase-band metrics, a pattern may declare its leg grid
on the result (`RoutingResult.leg_grid: Option<LegGrid>`, additive with
`#[serde(default)]`):

```rust
pub struct LegGrid {
    pub slot_count: u32,                 // N_slots
    pub strands_per_leg: Option<u32>,    // the braid's num_strands
}
```

When the grid is declared, `RoutingDimensions` gains:

- `slot_count` — the declared `N_slots`;
- `slot_pitch_mm` — the true slot pitch `tau_s = L_stator / N_slots`, with
  `L_stator` the context's active-area length (the stator track populated by
  active legs);
- `interleave_step_mm` — the effective leg pitch of braided **slotless**
  patterns, `tau_p / (phases × strands_per_leg)`. Braided patterns have no
  physical slots; this is the equivalent leg-pitch model of their interleaved
  trace layout. Note that `tau_s = tau_p / phases` (the ideal phase-band
  pitch) only holds for uniform 1-slot-per-pole-per-phase windings.

Without a declared grid all three fields stay `null` and the phase-band
metrics work exactly as before. A malformed declaration (zero slot or strand
count) degrades to `null` rather than failing generation. The bundled
infinity braid declares its actual leg grid: `slot_count = periods × phases ×
strands` (65 × 3 × 5 = 975 for the 800 mm / 12 mm-pole-pitch reference
fixture, which hosts 65 complete 12 mm periods) and
`strands_per_leg = num_strands`; each braid strand remains a single-trace leg,
so its per-record `slot_width_mm` is the single-leg width.

Per-record slot width (glossary "Slot Width") — the along-travel width of the
track space housing one active leg:

```text
slot_width = (k * w_t + (k - 1) * s) / sin(theta)      (k = parallel strands in ONE leg)
```

`phase_band_widths[].slot_width_mm` always reports the single-trace leg width
(`k = 1`, i.e. `w_t / sin(theta)`). Callers whose legs bundle `k` parallel
strands compute the bundled-leg width with the helper directly. The slot
width is a different quantity from `band_width_mm` (the full `N`-strand
bundle), from `slot_pitch_mm`, and from the electrical period `P_e`.

**Worked examples** (these exactly match the Rust unit tests):

```rust
// Single-leg slot width: w_t = 0.2 mm, theta = 45°
assert_eq!(slot_width_from_leg_geometry_mm(1, 0.2, 0.15, 45_f64.to_radians())?, 0.28284271);
// (1 * 0.2) / sin(45°) = 0.2 / 0.7071 ≈ 0.2828 mm

// Bundled leg (k = 4 parallel strands in one leg): w_t = 0.2, s = 0.15, theta = 45°
assert_eq!(slot_width_from_leg_geometry_mm(4, 0.2, 0.15, 45_f64.to_radians())?, 1.76776695);

// Bottom-up phase-band width: 4 parallel traces, w_t = 0.2 mm, s = 0.15 mm, theta = 45°
assert_eq!(phase_band_width_from_trace_geometry_mm(4, 0.2, 0.15, 45_f64.to_radians())?, 1.76776695);
// (4 * 0.2 + 3 * 0.15) / sin(45°) = 1.25 / 0.7071 ≈ 1.7678 mm

// Top-down: tau_p = 12 mm, 3 phases, g_phase = 0
assert_eq!(max_phase_band_width_from_pole_pitch_mm(12.0, 3, 0.0)?, 4.0);

// True slot pitch: L_stator = 800 mm (reference fixture active area), 975 slots
assert_eq!(slot_pitch_from_leg_grid_mm(800.0, 975)?, 800.0 / 975.0);
```

Public helpers: `pcbmotorgen_routing::phase_band_width_from_trace_geometry_mm(...)`,
`pcbmotorgen_routing::max_phase_band_width_from_pole_pitch_mm(...)`,
`pcbmotorgen_routing::slot_width_from_leg_geometry_mm(k, w_t, s, theta_rad)`, and
`pcbmotorgen_routing::slot_pitch_from_leg_grid_mm(l_stator_mm, n_slots)`, all returning
`Result<f64, String>` with the input validation described above.

### 10.3 Infinity-braid alignment

When `RoutingContext.magnet_pitch_mm` is present, the bundled infinity braid:

1. reserves a uniform phase/strand via step of
   `magnet_pitch_mm / (phases × strands)`;
2. uses the largest number of complete diamond periods that fit after that
   interleave is reserved (`floor((total + step) / pole_pitch) - 1`, minimum 1);
3. sets the diamond period to **exactly** `magnet_pitch_mm` (never a rounded
   approximation) and never leaves a wide via gap between adjacent period grids;
4. reports that value as both `pole_pitch_mm` and `period_pitch_mm`.

The remaining end length is used by the braid's interleave offsets. If the
routable length is shorter than one pole pitch, generation fails with an
actionable error rather than emitting a magnet-misaligned pattern. Without a
magnet layout, the reference pattern retains its fallback `n_periods` probe
behavior and does not claim magnet alignment (its repeat pitch is reported, but
there is no pole pitch to compare it with).

The braid also declares its leg grid on the result (see §10.2):
`slot_count = periods × phases × strands` and `strands_per_leg = num_strands`,
from which the host reports the true slot pitch and the
`tau_p / (phases × strands)` interleave step.

And it declares its phase bands on the result (see §5.2 and §10.4): one
record per `(layer, net)`, with the first-repeat centerline taken from the
phase's first pole region (adjacent phase centerlines sit exactly
`τ_p/phases` apart), the full span of the phase's pole regions as the
along-travel extent, the full board width as the y-extent, and the `braided`
shape — consistent with the `pole_regions` emission by construction.

### 10.4 Resolved phase-band geometry (declared vs derived, kata hzs2)

`RoutingDimensions.phase_bands` carries one `ResolvedPhaseBand` record per
`(layer, net)` band — the position/shape counterpart of the
`phase_band_widths[]` budget records:

```rust
pub struct ResolvedPhaseBand {
    #[serde(flatten)]
    pub band: PhaseBand,   // the §5.2 declaration fields, flattened on the wire
    pub derived: bool,     // true = host-derived fallback, false = declared
}
```

Resolution rules:

1. **Declared wins.** A non-empty `RoutingResult.phase_bands` is copied
   verbatim into the sidecar with `derived: false`.
2. **Host fallback.** When the pattern declares no bands and a pole pitch is
   known, the host derives one band per active `(layer, net)` group from the
   ideal phase-band pitch `τ_band = τ_p/phases` (glossary "Phase Band"): the
   group's net takes phase slot `p` — its index among the distinct active
   nets — with extent `[p·τ_band, (p+1)·τ_band]`, centerline
   `p·τ_band + τ_band/2`, the full board width as y-extent, a linear shape,
   and `derived: true`. These are a model of the ideal layout, not measured
   geometry.
3. **No pole pitch, no declaration** ⇒ empty sidecar (nothing to derive
   from); declared bands still pass through.

Consumers (simulation commutation and equilibrium, and the open travel-
endpoints work) read the declared positions when present; the analytic
derivations from `pole_pitch`/`phases` remain the fallback. The bundled
infinity braid declares its real bands (see §10.3), so a braid payload never
contains derived records.

## 11. Presentation projection: `PhaseCoil` / `CoilPathIpc`

`routing_result_to_phase_coils(&RoutingResult, pattern_id)` groups validated
elements by `(layer, net)` into `PhaseCoil` objects: `segments` +
`corner_arcs` + `center_via_positions`; each arc carries `is_active`. Each
`PhaseCoil` carries `phase_idx`, `layer_idx`, `phase_name`, `pattern_id`, and an
optional `layer_pair`. Convenience accessors include `polyline()`,
`bounding_box()`, `is_continuous()`, `total_length_mm()`,
`active_length_mm()`, `end_turn_length_mm()`, and
`active_conductor_x_positions()`.

The frontend DTO (`CoilPathIpc`, mirrored by `app/desktop/src/lib/types/coils.ts`)
ships the same three primitive families to the preview:

| Wire field | Rendered as (SVG preview) |
| --- | --- |
| `segments` | `<line>` — thick solid for active, thin dashed for end-turns. |
| `corner_arcs` | `<path d="M s Q m e">` — dashed unless `is_active`. |
| `via_positions` | `<circle>` at via centers. |
| `routing_dimensions` | Pole pitch, phase-band budget, and phase-band width sidecar. |

The routing crate's units remain millimetres. The application IPC adapter
converts the sidecar and geometry to its existing SI/meter frontend contract at
that boundary; the preview applies its own world→pixel fit including a
per-layer schematic `yOffset` (1 mm per layer) purely for readability — the
wire format itself carries no artificial offsets.

## 12. Registry and dynamic loading

### 12.1 Registry

`RoutingRegistry` resolves a pattern `id` → concrete `RoutingPattern`:

| Method | Purpose |
| --- | --- |
| `register(pattern)` / `register_boxed(boxed)` | Add or replace a pattern by id. |
| `remove(id)` | Remove a pattern; returns whether one was removed. |
| `get(id)` | Look up a pattern. |
| `contains(id)` | Check registration. |
| `ids()` | All registered ids, sorted. |
| `catalog()` | `(id, display_name)` pairs for the UI selector. |

The app registers bundled patterns at startup (`bundled_registry()`) and
runtime-loaded plugins through `register_runtime_pattern` / `unregister_runtime_pattern`.
`available_pattern_ids()` lists what can run.

### 12.2 Native Rust `cdylib` plugin

A native plugin is a `cdylib` compiled against the **same**
`pcbmotorgen-routing` crate version (so the trait-object vtable layout matches).
The C-ABI surface (verified on load, before registration):

```rust
#[no_mangle]
pub static pcbmotorgen_ROUTING_PLUGIN_API: u32 = 2;  // millimetre contract

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

Build with `crate-type = ["cdylib"]` (`*.dylib` on macOS, `*.so` on Linux,
`*.dll` on Windows). The host verifies `pcbmotorgen_ROUTING_PLUGIN_API == 2`
before registering; the plugin is then **probed** by generating against the
current config and rejected on upload if the shape fails validation.

> **Warning:** loading a native library executes its code. Only load plugins you
> trust. The app loads the file the user explicitly picked via **Browse…**.

### 12.3 Python runner

A Python runner is a standalone `.py` script with two modes:

1. **Default mode** — reads the `RoutingContext` JSON on **stdin**, prints one
   strict `RoutingResult` JSON to **stdout**, and prints _nothing else_ to
   stdout. Non-zero exit or extra stdout text is treated as a malformed output.
2. **`--metadata` mode** — prints a `PluginMetadata` (name/author/version +
   parameters) and exits 0. Optional; if missing the app falls back to the file
   stem as id.

The Rust loader executes `python3 <script>`, feeds the context on stdin, parses
stdout as `RoutingResult`, then runs the result through the **same** strict
validator as native plugins — a Python pattern cannot bypass any shape rule.
The loader does **not** accept a `RoutingReport` envelope from Python; dimension
metadata is calculated by the host after validation.

The complete, working reference runner is
`crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py`. The
reference braid algorithm to port lives in `.ref/pcbBraid` (after Verbeek &
Dehez).

### 12.4 Upload and persistence workflow

In the **Routing pattern** panel:

1. Choose **Native crate plugin** or **Python runner**.
2. Click **Browse…** to pick the `.dylib` / `.so` / `.dll` / `.py` file.
3. Optionally set a **Pattern name** (registry id) for Python runners.
4. Click **Load generator**. The plugin is probed against the current config; if
   it passes, it is **persisted** into the app's data directory
   (`app_data/plugins/`) and added to the installed list. If it fails, the
   rejection error is shown.

Installed generators are re-loaded automatically on the next app start and can
be removed from the **Installed generators** list. Directory layout (macOS
example):

```
~/Library/Application Support/<app-identifier>/plugins/
    plugins.json            # installed-plugin manifest
    my-generator.py         # stored python runner
    my_braid.dylib          # stored native plugin
```

## 13. App-facing facade (public functions)

All public exports are re-exported at the crate root (`use pcbmotorgen_routing::…`).

```rust
// Generation
pub fn generate_routing_report(ctx: &RoutingContext, id: &str) -> Result<RoutingReport, String>;
pub fn generate_routing_result(ctx: &RoutingContext, id: &str) -> Result<RoutingResult, String>;
pub fn generate_coils_from_context(ctx: &RoutingContext, id: &str) -> Vec<PhaseCoil>;

// Generation with host-side IO fanout (kata xa0f, §13.1)
pub fn generate_routing_report_with_io(
    ctx: &RoutingContext, id: &str, io: &IoFanoutOptions,
) -> Result<RoutingReport, String>;
pub fn generate_routing_result_with_io(
    ctx: &RoutingContext, id: &str, io: &IoFanoutOptions,
) -> Result<RoutingResult, String>;
pub fn generate_io_fanout(
    result: &mut RoutingResult, ctx: &RoutingContext, io: &IoFanoutOptions,
) -> Result<(), String>;

// Registry
pub fn available_pattern_ids() -> Vec<(String, String)>;   // (id, display_name) catalog pairs
pub fn available_pattern_metadata() -> Vec<PluginMetadata>; // catalog incl. layer-range metadata
pub fn bundled_registry() -> RoutingRegistry;
pub fn register_runtime_pattern(pattern: Box<dyn RoutingPattern>) -> Result<(), String>;
pub fn unregister_runtime_pattern(id: &str);               // no-op for bundled patterns

// Metadata / parameters
pub fn pattern_metadata(id: &str) -> Option<PluginMetadata>;
pub fn pattern_parameters(id: &str) -> Vec<PatternParameter>;
pub fn validate_routing_params(id: &str, params: &HashMap<String, f64>) -> Result<(), String>;

// Loading
pub fn register_native_plugin(path: &Path, probe: &RoutingContext) -> Result<String, String>;
pub fn register_python_runner(path: &Path, probe: &RoutingContext, custom_id: Option<&str>) -> Result<String, String>;

// Presentation
pub fn routing_result_to_phase_coils(result: &RoutingResult, pattern_id: &str) -> Vec<PhaseCoil>;

// Dimension helpers
pub fn phase_band_width_from_trace_geometry_mm(u32, f64, f64, f64) -> Result<f64, String>;
pub fn max_phase_band_width_from_pole_pitch_mm(f64, u32, f64) -> Result<f64, String>;

// DRC — moved downstream to pcbmotorgen-dfm (§9): check_interference
```

Generation flow: `generate_routing_report` validates user parameters against the
pattern's declared schema (including `multiple_of`), validates the context's
`num_layers` against the pattern's declared layer-range metadata, calls
`pattern.generate(ctx)`, runs the result
through the validator, then computes the dimension sidecar from the exact same
context (`RoutingDimensions::for_infinity` for `"infinity-braid"`,
`RoutingDimensions::from_result` for generic patterns). `generate_coils_from_context`
adapts a validated result into the `PhaseCoil` presentation used by the preview
and the force model.

### 13.1 Host-side IO fanout generation (kata xa0f)

`generate_routing_report_with_io` / `generate_routing_result_with_io` are the
opt-in IO toggle: they run the identical pipeline but insert one host step
between `pattern.generate(ctx)` and the validator —

```text
pattern.generate(ctx) → generate_io_fanout(result, ctx, &IoFanoutOptions) → Validator::validate
```

- The step is **pattern-agnostic** (bundled, native, and Python runner
  patterns all get it) and appends `io_pads[]` / `io_traces[]` connecting
  every coil terminal to a board-edge connector row (§5.3.1).
- The plain `generate_routing_report` / `generate_routing_result` entry
  points **never** emit IO: existing callers, payloads, and exports stay
  byte-identical without any code change. This opt-in entry-point design was
  chosen over a `RoutingContext` field because the context is the pattern's
  input contract (the app constructs it with a full struct literal) — host
  toggles do not belong in it.
- A generated result that fails validation is a generation error
  (`pattern "<id>" produced a malformed shape…`), never sanitised; the IO
  step's own errors surface as `pattern "<id>" IO fanout generation failed:
  …`.
- Sizing: `IoFanoutOptions` carries the pad diameter / drill; the canonical
  values come from the DFM authority via `DesignRules::io_fanout_options()`
  (in `pcbmotorgen-dfm`). Export consumes the result unchanged through
  `io_elements_to_board_items` / `write_io_elements` (KiCad `Footprint` /
  `Pad` + tracks, DXF pad circles / trace lines).

## 14. Commands, tests, and guarantees

Run these from the repository root:

```bash
# Focused routing tests: strict validator, dimension equations, runner parsing
cargo test -p pcbmotorgen-routing

# Compile the routing package without running tests
cargo build -p pcbmotorgen-routing
cargo check -p pcbmotorgen-routing

# Check the routing consumers (KiCad/DXF adapter + simulation)
cargo check -p pcbmotorgen-export -p pcbmotorgen-simulation

# Full workspace verification
cargo test --workspace
cargo build --workspace

# Frontend contract/tests for the generate_coils adapter (from app/desktop)
cd app/desktop
pnpm test
pnpm run build
```

Python runner smoke test (from the repository root):

```bash
python3 crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py --metadata
python3 crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py \
  < <(printf '%s\n' '{"active_area_length_mm":120.0,"board_width_mm":20.0,"phases":3,"num_layers":2,"min_trace_mm":0.127,"min_space_mm":0.127,"expects_continuous":false,"params":{}}')
```

The package has no Python dependency for normal Rust builds; Python is only
needed when a user installs a Python runner.

`cargo test -p pcbmotorgen-routing` covers:

- NaN/Infinity, bounds, layer, degenerate-shape, net, and continuity rejection;
- exact bottom-up and top-down phase-band width equations;
- exact per-slot width and slot-pitch equations plus leg-grid-derived slot metrics;
- phase-band declaration round-trip, host fallback derivation (marked
  `derived`), and braid-declared bands matching its pole regions (kata hzs2);
- host IO fanout generation (kata xa0f): terminal→pad mapping, net
  assignment, deterministic placement, nearest-edge rows, degenerate-guard,
  opt-in behavior (plain entry points stay IO-free), and
  validator-accepts-generated-IO end to end on the bundled braid;
- exact pole-pitch alignment for the bundled infinity braid;
- per-layer/per-net dimension reporting; and
- Python runner parsing and malformed-output rejection.

The validator is the single gate before geometry is previewed, simulated, or
written. A malformed result is rejected with `index`, `field`, `kind`, and a
human-readable message; it is never repaired in place.

## 15. Version policy

- The current contract version is `FORMAT_VERSION = 2`
  (`crates/pcbmotorgen-routing/src/model.rs`).
- `RoutingResult.format_version` is **serde-defaulted** to the current version:
  payloads and Python runners that omit the field are interpreted as version 2
  only when they already use millimetres.
- **Additive change** (new optional field, new element type, or a host-side
  `RoutingReport` dimension sidecar): allowed without a version bump; consumers
  must tolerate the missing field (serde `default`). The sidecar is not part of
  the strict plugin JSON.
- **Breaking change** (field removed/reinterpreted, units or coordinate
  conventions changed, validation semantics changed, or a native-plugin ABI
  change): MUST bump `format_version` (and the `pcbmotorgen_ROUTING_PLUGIN_API`
  constant) and update this document. Version 2 is the millimetre contract;
  version-1 metre payloads must not be mixed into version 2.
- **v-next first-class phase-band geometry (kata hzs2):** patterns may
  declare phase bands on the result (`RoutingResult.phase_bands:
  Vec<PhaseBand>`, additive with `#[serde(default)]`) — per-`(layer, net)`
  centerline x, along-travel extent, y-extent/shape, and net label (§5.2).
  `RoutingDimensions` gains `phase_bands: Vec<ResolvedPhaseBand>` (additive,
  serde default empty): declared bands copied through, or host-derived bands
  from the ideal phase-band pitch `τ_p/phases` marked `derived: true` (§10.4).
  No version bump: legacy payloads without the fields deserialize unchanged.
- **v-next terminology alignment:** slot-width dimension fields were renamed to
  phase-band terminology (`band_width_mm`, `max_band_width_mm`,
  `phase_band_pitch_mm`, `phase_band_widths`). The old key names are no longer
  accepted on deserialize (clean break, pre-1.0); `RoutingContext` carries
  `magnet_array_span_mm` only.
- **v-next IO routing definitions (kata htcq):** `RoutingResult` gains the
  additive, serde-defaulted fields `io_pads: Vec<IoPad>` and
  `io_traces: Vec<IoTrace>` (see §5.3) — connector/IC pad stacks and terminal
  fanout traces typed distinctly from active conductors. No version bump:
  payloads without the fields deserialize unchanged, and emission of IO
  elements is optional for patterns. The export crate emits them
  (KiCad `FootprintInstance`/`Pad` + fanout tracks; DXF `IO_Pad` circles /
  rectangle outlines + normal track LINEs) and proves byte-identical legacy
  exports with golden tests.
- **v-next host IO fanout generation (kata xa0f):** the host can now
  **generate** the IO routing itself — an opt-in host step
  (`generate_routing_*_with_io`, §13.1) that appends `io_pads[]` /
  `io_traces[]` after pattern generation and before validation, using the
  board-edge connector row strategy (§5.3.1). No API/ABI version bump and no
  schema change: the entry-point toggle means payloads from the existing
  functions are byte-identical to the pre-xa0f behavior.
- **v-next true per-slot metrics (kata mqw4):** patterns may declare a leg
  grid on the result (`RoutingResult.leg_grid: Option<LegGrid>`, additive);
  `RoutingDimensions` gains `slot_count`, `slot_pitch_mm` (true
  `tau_s = L_stator / N_slots`), and `interleave_step_mm`
  (`tau_p / (phases × strands)` for braided slotless patterns), and each
  `phase_band_widths[]` record gains the single-leg `slot_width_mm`
  (`w_t / sin(theta)`). Two legacy serde aliases were retired because those
  key names became the new true-slot fields: a dimensions-level
  `slot_pitch_mm` key now populates the true slot pitch (not
  `phase_band_pitch_mm`), and a per-band `slot_width_mm` key now populates
  the single-leg width while `band_width_mm` became required (payloads
  relying on the old per-band alias are rejected instead of silently
  reinterpreted). `RoutingContext.phase_clearance_mm` (`Option<f64>`) makes
  the inter-phase clearance `g_phase` an explicit input; when `None` it falls
  back to `min_space_mm` by documented contract. The `trace_count` hint no
  longer accepts whole-coil counts (`turns`, `windings_per_phase`).
- **v-next DFM crate extraction (kata 0rgs):** `DesignRules` and
  `check_interference` moved out of this crate into the new downstream
  `pcbmotorgen-dfm` crate (`pcbmotorgen-dfm → pcbmotorgen-routing`). No
  wire-format change: `RoutingResult` / `RoutingContext` shapes are
  unchanged and `DesignRules`' serde shape is byte-compatible. The context's
  `min_trace_mm` / `min_space_mm` / `phase_clearance_mm` fields stay part of
  this contract (§4) — they are pattern inputs, not DFM; the DFM crate reads
  the mirrored `DesignRules` snapshot downstream (§7, §9).
- **v-next pattern layer-range + param multiple-of metadata (kata we8r):**
  additive-only, no API-version bump. The `RoutingPattern` trait gains three
  defaulted methods (`min_layers`, `max_layers`, `layers_multiple_of` — all
  `None` = unconstrained) that flow into `PluginMetadata` (serde-defaulted
  fields, so older metadata payloads still deserialize), and
  `PatternParameter` gains a serde-defaulted `multiple_of: Option<f64>`
  constraint enforced by `validate_routing_params`. The host rejects
  generate-time contexts whose `num_layers` violates the pattern's declared
  layer range. Because the methods are defaulted and the wire shapes are
  serde-defaulted, a previously compiled plugin still loads and runs against
  the updated host; newly compiled plugins can opt into the metadata.
  `available_pattern_metadata()` is a new facade function (the existing
  `available_pattern_ids()` is unchanged).

## 16. Maintaining these documents

This section (consolidated from the README authoring guide) applies to any
maintainer changing the Rust model, the handoff, or this API reference.

### What the package README must contain

1. **Scope and ownership** — what the crate produces and owns, and explicitly
   what it does **not** own (KiCad layer mapping, copper widths supplied by the
   core, the physics model).
2. **Units and axes** — millimetres; x = travel; y = across width; zero-based
   copper-stack layer indexes.
3. **Canonical output vs enriched application output** — plugins emit strict
   `RoutingResult` geometry only; the host validates; `RoutingReport` /
   `routing_dimensions` carry calculated pole pitch and phase-band widths. Never tell
   plugin authors to emit a report envelope from Python.
4. **Design equations with a worked example** — equation, symbol meanings with
   units, angle direction, and one hand-checkable number. Keep both phase-band
   width views together (`w_s = (N·w_t + (N-1)·s)/sin(theta)` and
   `max(w_s) = tau_p/m - g_phase`).
5. **Commands** — copy/paste focused and workspace commands.
6. **Extension links** — to this API reference, the authoring guide, the handoff
   contract, the reference runner, and the native plugin pattern.

### Safe update procedure

1. Change the Rust model or public API first.
2. Add or update unit tests for the new field/equation.
3. Update this API reference with the exact wire shape.
4. Update `docs/routing-pattern-authoring.md` if plugin authors are affected.
5. Update the package README with the user-facing explanation and commands.
6. Search for stale names or units:

   ```bash
   rg "coil_topology|single-layer|phase_band_width|pole_pitch|RoutingResult" \
     README.md docs crates app/desktop
   ```

7. Run the focused routing tests, then the workspace check/build.

Avoid promising behaviour that is not tested. In particular, do not describe a
pattern as magnet-aligned unless its reported `period_pitch_mm` is exactly the
context's `pole_pitch_mm` within the test tolerance.

### Plugin README template

When publishing a new pattern, copy this outline into its README:

```markdown
# my-pattern

## Purpose
What motor topology does this pattern generate? Single- or multi-layer?

## Contract
- Units: millimetres; x = travel; y = board width.
- Entry point: `generate(ctx)` or the Rust `RoutingPattern` implementation.
- Output: strict `RoutingResult` with segments, curves, and vias.
- Layer/net ownership: explain every layer and net emitted.

## Parameters
| key | type | default | range | meaning |
| --- | --- | --- | --- | --- |
List only independent user knobs; explain which dimensions are derived from the
context rather than copied into parameters.

## Motor dimensions
State how pole pitch, phase-band pitch, phase-band width, trace angle, and any pattern
period are calculated, with equations and units.

## Phase bands
State whether the pattern declares `phase_bands` (kata hzs2) and what each
record means: per `(layer, net)` first-repeat `centerline_x_mm` (the phase
reference position; adjacent phase bands one phase-band pitch apart),
`start_x_mm`/`end_x_mm` as laid out, `y_min_mm`/`y_max_mm`, and `shape`
(`linear` or `braided`). If the pattern does not declare bands, say so and
note that the host derives them from the ideal phase-band pitch and marks
them `derived`.

## Build and install
# Python runner
python3 my_pattern.py --metadata
# Rust plugin
cargo build --release

## Example
Show a context JSON and the important output counts/dimension fields.

## Validation and tests
Document the command that exercises malformed output, bounds, layers, and DFM
limits. State that the host validator rejects output rather than sanitising it.

## Version, author, and license
Keep these identical to the runner `--metadata` block or Rust trait accessors.
```

The example should show the **strict geometry JSON**, not a host-side
`RoutingReport` wrapper; explain any `routing_dimensions` values as consumer
metadata calculated after validation.

### Documentation review checklist

- [ ] Scope and ownership are accurate.
- [ ] Units, axes, layer indexes, and net semantics are explicit.
- [ ] Strict plugin JSON is not confused with `RoutingReport`.
- [ ] Phase-band width and pole-pitch equations include symbol definitions.
- [ ] A worked example matches the Rust tests.
- [ ] Focused and workspace commands are copy/pasteable.
- [ ] Rust and Python extension paths are linked.
- [ ] No removed legacy topology or single-layer assumption remains.

## 17. Field references

- Rust model: `crates/pcbmotorgen-routing/src/model.rs` (`FORMAT_VERSION`, `Point`, `Layer`, `Net`, `RouteSegment`, `RouteCurve`, `Via`, `PoleRegion`, `RoutingResult`)
- Context: `crates/pcbmotorgen-routing/src/context.rs`
- Pattern trait / parameters / metadata: `crates/pcbmotorgen-routing/src/pattern.rs`
- Validator: `crates/pcbmotorgen-routing/src/validator.rs`
- Errors: `crates/pcbmotorgen-routing/src/error.rs`
- Design rules: `crates/pcbmotorgen-dfm/src/rules.rs` (moved from this crate, kata 0rgs)
- Dimensions: `crates/pcbmotorgen-routing/src/dimensions.rs`
- Interference: `crates/pcbmotorgen-dfm/src/interference.rs` (moved from this crate, kata 0rgs)
- Report: `crates/pcbmotorgen-routing/src/report.rs`
- Coil presentation: `crates/pcbmotorgen-routing/src/coil.rs`
- Registry: `crates/pcbmotorgen-routing/src/registry.rs`
- Loaders (native C ABI + Python): `crates/pcbmotorgen-routing/src/loaders/`
- Facade: `crates/pcbmotorgen-routing/src/generate/`
- Bundled pattern: `crates/pcbmotorgen-routing/src/patterns/infinity/`
- Reference algorithm: `crates/pcbmotorgen-routing/.ref/pcbBraid`
- Python runner example: `crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py`
- IPC DTO: `app/desktop/src-tauri/src/ipc/coils.rs` + `app/desktop/src/lib/types/coils.ts`
- Companion docs: `docs/routing-pattern-authoring.md`, `docs/routing-pattern-handoff.md`, `docs/routing-readme-guide.md`