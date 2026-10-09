---
name: rhino-mcp
description: MUST be used whenever driving the Rhino MCP (tools.rhino) to inspect or manipulate Rhino documents, import/verify 3D DXF geometry, capture viewports, or script Rhino through run_python/run_csharp/run_command. Covers slot lifecycle, the modal-dialog script-freeze trap, safe document clearing, DXF import, and geometry-verification workflows.
compatibility: opencode
metadata:
  domain: cad
  server: rhino
  versions: "8, 9 / BETA / WIP"
---

# Rhino MCP

Guidance for driving the Rhino MCP server (server name `rhino`). It manages real
Rhino instances ("slots") and lets an agent import files, inspect geometry,
script RhinoCommon, capture viewports, and run Grasshopper.

## When to use

- Importing/validating a DXF (or other CAD file) in Rhino and reporting elevations,
  spans, layer contents, entity counts, or compatibility.
- Any `tools.rhino.*` call, `run_python`, `run_csharp`, `run_command`, `open_doc`,
  `save_doc`, viewport capture, or Grasshopper (`g1_*`) work.

## Transport

The tools live under `tools.rhino` and are only callable inside Code Mode
(`execute`). Discover exact paths/signatures with `search({ query: "rhino ..." })`;
do not guess names. Every document/slot tool takes an optional `slot` argument.

## Slot lifecycle

1. `list_slots()` — see running slots. A user-started Rhino may appear with
   `adopted: true`; the router will not kill adopted slots.
2. `spawn_slot({ version: "8" })` — launch one if none is running. Omit `version`
   to use the router default. Returns a `slotId` (e.g. `aardvark`).
3. Pass that `slot` to **every** subsequent call. Without it, a tool targets the
   slot you last used and may auto-spawn a new Rhino.
4. `close_slot({ slot })` — graceful shutdown; refuses adopted (user-started) slots.
5. `close_doc({ slot })` — discards unsaved changes. **If it is the only open
   document, closing it also closes the Rhino window and the slot is pruned.**
   Useful as a recovery action, but it ends the slot.

## Golden rules (learned the hard way)

- **A modal dialog or an unsaved/large document freezes the script executors.**
  `run_python` and `run_csharp` then return an **empty** `payload` — even for
  `raise RuntimeError("probe")` — while `run_command` still answers `"Done."`.
  An empty payload is **not** success. Recover with `close_doc` (discard) or by
  dismissing the dialog, then confirm with a trivial `print("hello")`.
- **Prefer `run_command '_-Import "<abs path>" _Enter'` over `open_doc` for DXF.**
  `open_doc` can block past the 300 s HTTP timeout on large files and leave the
  slot wedged; the dashed `_-Import` path is dialog-free and fast. It reports
  `Model space objects read: N, skipped: M`.
- **`doc.Objects.Count` is stale after deletions** (it includes pending-delete
  objects). Iterate `for o in __rhino_doc__.Objects` to get the real set.
- **Clear with a Python loop, not `_SelAll _Delete`.** `_SelAll _Delete` misses
  locked/hidden/pending objects:
  ```python
  doc = __rhino_doc__
  for o in [x for x in doc.Objects]:
      doc.Objects.Delete(o.Id, True)
  doc.Views.Redraw()
  ```
- **Do not call `get_context` right after a big import.** A fresh import leaves
  every object selected, so `get_context` dumps a huge selection (thousands of
  entries). Use a targeted `run_python` census instead.
- **Use `__rhino_doc__`.** It is injected as the document handle. Do **not**
  use `scriptcontext.doc` or `rhinoscriptsyntax`; they are unreliable here.
- **One action per call.** `open_doc`, `get_viewport_image`, and large imports
  can time out independently; keep each step small and deterministic.

## Standard workflow

1. **Orient** — `list_slots`, then `get_context({ slot })` on an *empty* doc
   (or `run_python` printing `Rhino.RhinoApp.Version`).
2. **Clear** — Python delete loop (above) so measurements are not contaminated.
3. **Import** — `run_command` with `_-Import "<abs path>" _Enter`; capture the
   "objects read/skipped" lines as compatibility evidence.
4. **Inspect** — a `run_python` census (see reference file): entity kinds, layer
   names, Z values, X/Y/Z extents, and vertical-line (via) spans.
5. **Capture** — `get_viewport_image` with `view`/`displayMode` and a
   `boxMin`/`boxMax` frame; the result carries a JSON metadata block (camera,
   framed bounding box, visible object count) plus the JPEG. Prefer framing a
   small region; the base64 image is large and large tool outputs are written to
   `~/.local/share/opencode/tool-output/`.
6. **Report/clean up** — leave the user's slot alone unless asked; `close_slot`
   only managed slots.

## Geometry census (the core pattern)

```python
import Rhino
from collections import defaultdict

doc = __rhino_doc__
n = 0
zs, xs, ys = set(), [], []
layer_zs = defaultdict(set)
vertical = defaultdict(int)   # vertical LINEs == vias
total = defaultdict(int)

for o in doc.Objects:
    g = o.Geometry
    layer = doc.Layers[o.Attributes.LayerIndex].FullPath
    total[layer] += 1
    if isinstance(g, Rhino.Geometry.LineCurve):
        n += 1
        a, b = g.Line.From, g.Line.To
        for p in (a, b):
            zs.add(round(p.Z, 6)); xs.append(p.X); ys.append(p.Y)
            layer_zs[layer].add(round(p.Z, 6))
        if abs(a.X-b.X) < 1e-9 and abs(a.Y-b.Y) < 1e-9 and abs(a.Z-b.Z) > 1e-9:
            vertical[layer] += 1

print("linecurves=%d objects=%d" % (n, doc.Objects.Count))
print("uniqueZ=%s" % sorted(zs))
print("Xrange=[%.6f,%.6f] span=%.6f" % (min(xs), max(xs), max(xs)-min(xs)))
for l in sorted(layer_zs):
    print("  %-16s Z=%s vertical=%d total=%d" %
          (l, sorted(layer_zs[l]), vertical.get(l, 0), total[l]))
```

Read planar trace Z from `LineCurve.Line.From/To`; a vertical line (equal X/Y,
differing Z) is a layer-to-layer via — its Z span is the via length.

## Viewport capture

```
get_viewport_image({
  view: "perspective" | "front" | "top" | ...,
  displayMode: "Wireframe" | "Shaded" | "Ghosted" | ...,
  boxMin: { x, y, z }, boxMax: { x, y, z },   # frames this bbox for you
  width: 900, height: 420,
  slot
})
```
`set_camera` can also set `location`/`target`/`projection`. The image metadata
reports the resulting scene bounding box and on-screen object count — use it to
detect an empty/off-screen capture without re-shooting.

## DXF notes

- pcbmotorgen exports R12 ASCII 3D DXF with `$INSUNITS=4` (mm); Rhino honours it
  and imports coordinates unchanged (no scaling).
- Planar copper centerlines are `LINE` on `L<idx>_<net>`; inter-layer vias are
  vertical `LINE`s on `Via_L<from>_L<to>_<net>`. `ARC`/`CIRCLE`/`LWPOLYLINE` may
  also appear from other producers.
- A param/units dialog should not appear when importing with the dashed
  `_-Import` form; if the slot wedges, apply the freeze-recovery rule above.

## Grasshopper

`g1_start`, `g1_search_components`, `g1_apply_graph`, `g1_place_slider`,
`g1_connect_many`, `g1_solve_graph`, `g1_get_canvas_graph`, `g1_clear_canvas`
drives the GH1 canvas. `g1_clear_canvas` requires `confirm: true`. Use
`g1_get_canvas_graph` to snapshot components/wires/data after a solve.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `run_python`/`run_csharp` return empty `payload` | Modal dialog or unsaved/large document blocking Rhino | `close_doc` (discard) or dismiss; verify with `print("hello")` |
| `open_doc` times out (~300 s) | Large import / blocking dialog | Use `_-Import` via `run_command` |
| `doc.Objects.Count` far larger than expected | Pending-delete objects counted | Iterate `doc.Objects` |
| `_SelAll _Delete` leaves objects | Locked/hidden objects not selected | Python delete loop |
| `get_context` output is enormous | Fresh import selected everything | Use targeted `run_python` |
| `spawn_slot` returns `JsonReaderException` | Router startup transient / launcher message | Retry; if persistent, recover the existing slot instead |
| Slot missing after `close_doc` | Closing the only doc closed Rhino | `spawn_slot` a new one |

See `reference/dxf-elevation-verification.md` for the pcbmotorgen default-DXF
elevation/via-span verification recipe.
