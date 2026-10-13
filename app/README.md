# Settings

Open **pcbmotorgen > Settings…** with the menu bar or **Cmd/Ctrl+,**.
Choose Light, Dark, or Auto appearance. Auto follows system appearance changes.
Settings persist on this device, separately from project versions.

DRC rules set minimum motor trace width, clearance, via drill, and annular ring
in millimetres. Saving settings applies these values to the current motor
design and uses them for new designs. Opened projects retain their saved rules.
Rule changes update routing, DRC, and export together, and mark a saved design
as edited. Cancel leaves appearance and rules unchanged.

Use **Import KiCad DRC rules** in Settings to upload a `.kicad_dru` file.
Review the imported values and limitations, then save to apply them. The importer
reads minimum trace width, clearance, via drill, annular width, and via diameter
in mm, mil, or inches. Via diameter is converted to annular ring width using the
imported or current minimum drill.

The app uses uniform limits, so it takes the strictest imported minimum across
layers. Only unconditional rules and simple track-only or via-only conditions
are imported. Other conditions, unsupported checks, and maximum or preferred
values are reported but not applied. This does not run KiCad's full DRC engine.
Fields absent from the file keep their current values.

## Project versions

Each `.pmproj` file stores all of its saved design versions, including motor
settings, sensor settings, imported CAD geometry, and mover position.

- Use the title-bar **Versions** or **Version N** button to browse versions,
  open another version, edit a description, or delete a selected version.
- **File > Save** updates the active version. Its creation time stays unchanged;
  its last-edited time advances.
- **File > Save new version…** saves the current design, including unsaved
  edits, as a separate version. You can give it a description before saving.
- **File > Save As…** copies all versions into the chosen file, not just the
  active design.
- Opening a file loads the version with the most recent last-edited time.
  Editing a version's description also updates that time. Viewing a version
  does not change it.
- Deletion requires confirmation. Deleting the active version opens the most
  recently edited remaining version. At least one version must remain.

Version switches ask before discarding unsaved design edits. Description edits
and deletion of an inactive version do not save or discard the working draft.

Older single-design project files load as version 1 and migrate to the new
format on their next save. Builds that only support the older format cannot
open files saved in the new format.

## CAD import and coil assignments

Use **File > Import CAD** to preview a DXF before replacing the design geometry.
Choose the drawing units, trace width, and via sizes. Review any import warnings.

Source DXF layer names determine coil identity, independently of copper planes:

| Source layer | Default assignment |
| --- | --- |
| `L0_A`, `L1_A` | Coil `A`, on the indicated copper layers for legacy 2D files |
| `L0_B`, `L1_B` | Coil `B` |
| `Via_L0_L1_A` | Vias belonging to coil `A` |
| Nonstandard names | Separate coil per source layer name until assigned |

In **Assign source layers to coils**, give all trace and via layers belonging to
one coil the same name. For example, assign `Bottom winding`, `Top winding`, and
`Drilled connections` to `A`. Use different coil names for separate windings.
Names are case-sensitive. Copper planes and via spans in 3D drawings still come
from Z coordinates, not from the coil assignment. Do not put several coils on
one source DXF layer if you need to assign them separately.

Coils have separate preview colours and visibility controls. Assignments and
source-layer names are stored with imported geometry in the project. DXF export
uses the standard layer names with the assigned coil identities.

Enable **Simplify collinear lines on import** to merge touching or overlapping
straight segments within the same coil, copper layer, and active-conductor role.
It is off by default. It does not bridge gaps, merge parallel offset lines, or
change arcs, splines, or vias. The Z tolerance is not a simplification tolerance.
Only numerical roundoff up to 1e-9 mm is allowed when testing collinearity.

After importing a motor coil, use **Simplify lines** below the coil preview or
beside the Measure tool in the expanded preview. This updates actual geometry,
including what is saved and exported, rather than just its display. **Undo
simplify** restores the previous geometry while that preview is open and no
other geometry has replaced it. Save the project to keep the result. Import-time
simplification can be turned off before confirming; after import, reimport the
DXF without simplification to recover its original segmentation.

Supported trace entities include `LINE`, planar `ARC` and `SPLINE`, `LWPOLYLINE`,
and classic 2D/3D `POLYLINE` sequences. A two-point polyline can look like a single
straight line and imports as one trace. Vertical lines or polyline edges encode
via spans. Fitted or mesh polylines, classic bulged vertices, non-default classic
polyline extrusion, and sloped 3D edges are reported as unsupported. Review these
warnings before accepting an import.
