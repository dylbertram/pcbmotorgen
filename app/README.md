# Settings

Open **pcbmotorgen > Settings…** with the menu bar or **Cmd/Ctrl+,**.
Choose Light, Dark, or Auto appearance. Auto follows system appearance changes.
Settings persist on this device, separately from project versions.

DRC rules set minimum motor trace width, clearance, via drill, and annular ring
in millimetres. Saving settings applies these values to the current motor
design and uses them for new designs. Opened projects retain their saved rules.
Rule changes update routing, DRC, and export together, and mark a saved design
as edited. Cancel leaves appearance and rules unchanged.

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
