# DXF elevation & via-span verification (pcbmotorgen)

Recipe for validating a generated 4-layer / 1.6 mm DXF in Rhino. Use with the
`rhino-mcp` skill.

## 1. Generate the DXF through the real app path

The Tauri app crate (`app/desktop/src-tauri`) is a **binary**, so it cannot be
imported as a library. Reproduce its `export_coils_dxf` path with a throwaway
cargo crate outside the repo (no repo changes):

`Cargo.toml`:
```toml
[package]
name = "dxf_harness"
version = "0.0.0"
edition = "2021"
[dependencies]
pcbmotorgen-routing = { path = ".../crates/pcbmotorgen-routing" }
pcbmotorgen-export  = { path = ".../crates/pcbmotorgen-export" }
```

`main.rs` mirrors `LinearMotorConfig::default()` → `generate_coils_for_context`
→ `phase_coils_to_cad_geometry` → `cad_geometry_to_3d_dxf`:
```rust
use pcbmotorgen_export::cad_dxf::{
    cad_geometry_to_3d_dxf, phase_coils_to_cad_geometry,
};
use pcbmotorgen_routing::{generate_coils_from_context, RoutingContext};
use std::collections::HashMap;

let ctx = RoutingContext {
    active_area_length_mm: 195.0, board_width_mm: 20.0,
    num_layers: 4, phases: 3,
    min_trace_mm: 5.0 * 0.0254, min_space_mm: 5.0 * 0.0254, // mils_to_m(5)*1e3
    expects_continuous: false, params: HashMap::new(),
    magnet_pitch_mm: Some(12.0), magnet_array_span_mm: Some(120.0),
    phase_clearance_mm: None,
};
let coils = generate_coils_from_context(&ctx, "infinity-braid");
let geometry = phase_coils_to_cad_geometry(&coils, 4, 1.6, ctx.min_trace_mm).unwrap();
let dxf = cad_geometry_to_3d_dxf(&geometry).unwrap();
std::fs::write("default_4layer.dxf", dxf).unwrap();
```
Build with `CARGO_TARGET_DIR=<repo>/target` to reuse the workspace artifacts.

## 2. Expected values

`layer_z_mm = pcb_thickness * (i/(n-1) - 1)` for `i in 0..n`, bottom-to-top:

| layers | layer_z_mm (mm) | adjacent gap |
|---|---|---|
| 4 / 1.6 mm | `[-1.6, -1.0667, -0.5333, 0.0]` | `1.6/3 = 0.5333` |

- **Top plane is Z=0**, bottom is Z=-1.6. Indices are bottom-up; `layer 0 → B.Cu`,
  `layer n-1 → F.Cu` (KiCad mapping).
- Vias must join **only actual adjacent layers** and length must equal the
  adjacent-plane gap. On a 4-layer board a via that spans 1.6 mm (0→3) is a bug;
  0.5333 mm (0→1) is correct.
- X origin stays at the trace start (0); export and re-import must share the
  same X frame so the mover-travel/magnet overlay aligns.

## 3. Import and census in Rhino

```
run_command: '_-Import "<abs>/default_4layer.dxf" _Enter'
```
Expect `Model space objects read: <n>, skipped: 0`. Then run the geometry census
from the skill. For the default infinity-braid expect:

```
L0_A..C  Z=[-1.6]             vertical=0
L1_A..C  Z=[-1.066667]        vertical=0
Via_L0_L1_A..C Z=[-1.6,-1.0667] vertical=<count>
X range [0.000000, 191.200000] span 191.200000
```

**Gotcha:** the infinity-braid is inherently two-layer (B.Cu + In1.Cu), so its
copper sits on the **bottom two** planes. Rhino shows Z=-1.6 and Z=-1.0667; the
Z=0 and Z=-0.5333 planes carry no entities even though the 4-plane stack is
defined. "Top copper at Z=0" holds for the *stack frame*, not the braid's
entities — confirm which reading the acceptance criterion means before failing a
ticket on it.

## 4. Re-import stability

Clear (Python loop), re-import, re-census. X min/max and via spans must be
identical to the first import.

## 5. Disconnected-via fixture

Craft a DXF of vertical `LINE`s on `Via_L<a>_L<b>_<net>` layers with **no**
matching trace endpoints; via endpoints define the Z planes. Importing it
through the app importer (`pcbmotorgen_export::cad_dxf::import_3d_dxf` with the
UI's `CadImportOptions`) produces one
`Via at (x, y) mm has no matching trace endpoint on layer N.` warning per
endpoint. The UI collapses these with `groupCadImportWarnings` (keyed
`unconnected-via-layer-<N>`), so hundreds of warnings become a few collapsible
per-layer groups (examples capped at 5).

## 6. Regression tests to run alongside

```bash
cargo test -p pcbmotorgen-export --lib cad_dxf
cargo test -p pcbmotorgen round_trip_save_load_preserves_state
cd app/desktop && pnpm vitest run \
  src/lib/cadPreview.test.ts \
  src/lib/stores/config.layers.test.ts \
  src/lib/stores/project.test.ts
```
