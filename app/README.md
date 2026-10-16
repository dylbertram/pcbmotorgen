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

Name the limits under **Saved rulesets** to keep them for later. Enter a name and
choose **Save ruleset**; the saved set appears in the list and can be **Load**ed
into the draft or **Delete**d. Saved rulesets persist on this device, separately
from projects, and only affect a design when you save settings.

## Files and projects

Motor coils use `.pmmotor` files. Sensor coils use `.pmsensor` files. These are
separate document types, not alternative extensions for the same design.
Each file contains its own saved versions and imported CAD geometry. Motor
files also retain motor settings and mover position; sensor files retain sensor
settings. Preview and simulation results are regenerated, not stored on disk.

A `.pmproj` file is a workspace manifest. It references coil files by paths
relative to the workspace and remembers the open-file order and active file.
Keep the coil files with the workspace when copying a project to another device.

- **File > New** asks whether to add a motor or sensor coil file, then opens a
  new untitled tab. Existing files and drafts are left alone.
- **File > New Project** starts an empty workspace. Save, discard, and cancel
  choices protect unsaved documents and workspace changes.
- **File > Open** accepts coil files and workspaces. Opening a coil adds a tab;
  opening an already-open file selects its tab. Opening a workspace replaces
  the current workspace only after every referenced file loads successfully.
- **File > Save Project** saves the workspace's file references. Untitled coil
  files must be saved first. It does not save edits in already-named coil files.
- **File > Save All** saves edited and untitled coil files, then the workspace.
- **File > Save Project As** writes a manifest at a new location and adjusts
  relative references. It does not move or copy the referenced coil files.
- Closing a tab asks about unsaved work. Closing a tab never deletes its file.
  Save Project again to retain changes to the open-file list.
- Right-click a file tab to rename or move the file, reveal it in Finder, save it,
  save a new version, or close the tab. Clicking **+** offers new motor or sensor
  coil files and lists other `.pmmotor` and `.pmsensor` files from the same folder
  and subfolders.

## File versions

- Use the file tab's **Versions** or **Version N** tag to browse versions,
  open another version, edit a description, or delete a selected version.
- **File > Save** updates the active version. Its creation time stays unchanged;
  its last-edited time advances.
- **File > Save new version…** saves the current design, including unsaved
  edits, as a separate version. You can give it a description before saving.
- **File > Save As…** copies all versions into the chosen file, not just the
  active design. These actions apply to the active coil file, not the workspace.
- Opening a file loads the version with the most recent last-edited time.
  Editing a version's description also updates that time. Viewing a version
  does not change it.
- Deletion requires confirmation. Deleting the active version opens the most
  recently edited remaining version. At least one version must remain.

Version switches ask before discarding unsaved design edits. Description edits
and deletion of an inactive version do not save or discard the working draft.

## CAD import and coil assignments

Use **File > Import CAD** to preview a DXF before replacing the design geometry.
Choose the drawing units, trace width, and via sizes. Review any import warnings.
The active file determines the coil type. Create another file to import a
different type; import cannot change a motor file into a sensor file.

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

CAD import and the expanded motor preview use the same editing tools. Select
individual segments, chains, or a box to assign coil names and copper layers.
Right-click selected segments and choose **Change to coil…** or **Change to
layer…**. The selection-actions button offers the same commands for keyboard
and touch input, including naming a new coil. In **Layers**, each phase or coil
has nested copper layers. Click a phase to change only the coil, or a nested
layer to change both coil and layer. Right-click a destination and choose
**Move to** for the same action. Visibility checkboxes do not change assignments;
nested checkboxes hide only that coil/layer pair. **Undo assignment** restores
the last move. Changes clear affected coil terminals; check them before export.
Click a segment or drag a selection box without choosing a box tool. Drag
right to select fully contained segments, or left to select crossed segments.
Shift adds to the selection. Two fingers pan; a three-finger pinch zooms.
Mouse users can middle-drag to pan. Trackpad scroll pans and Ctrl-scroll or
browser pinch events zoom, because browsers do not expose trackpad finger counts.
Use Measure for distances, Set coil terminals for IN/OUT endpoints, and the
Layers popover for visibility, vias, and trace or centerline display. CAD edits
remain a draft until **Open with this geometry**. Motor preview edits update
the project geometry. Generated motor geometry requires confirmation before
segment editing, because edits stop following the routing settings.

Use **Simplify lines** in either viewer, or below the motor coil preview.
This updates actual geometry,
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

### Set coil IN and OUT

For imported motor geometry, choose **Set coil terminals** below the coil preview
or in its expanded toolbar. The command panel guides the selection:

1. Choose a coil, then choose **Select IN**.
2. Click the coil's IN endpoint. The tool advances to OUT.
3. Click the OUT endpoint. It must be different from IN.
4. Review the labelled points and coordinates, then choose **Done**.

The view fits the selected coil. The **Pick on copper layer** selector separates
points that overlap in the top-down view, including terminals on different
planes. Only original trace endpoints of the chosen coil and layer are
selectable, including arc ends and evaluated spline ends. Via centres and spline
control points are not independent terminal candidates. Shared trace junctions
are also selectable, so choose the actual ends of the winding rather than an
internal connection. Pan or zoom on the preview background to reach nearby
points. Endpoints also support keyboard focus and Enter or Space.

Use **Back** to revise a selection. **Cancel** or Escape discards the current
draft; closing the expanded preview or switching to Measure also discards it.
The project changes only when you choose **Done**. Repeat the command for each
coil, or use **Edit terminals** in the saved terminal summary. Confirmed points
show IN/OUT labels on both previews and retain their original coordinates and
copper-layer identities. Save the coil file to retain these assignments.
Simplifying lines preserves both assignments and any segment boundary carrying
a terminal. Projects without explicit assignments keep their existing preview
defaults. DXF export remains centerline geometry and does not carry IN/OUT
assignments; these labels do not add pads or route controller connections.
