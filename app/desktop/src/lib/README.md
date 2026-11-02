# Desktop library

Feature modules live next to their unit tests:

- `cad/`: imported geometry, phase and terminal mapping, and editing tools.
- `routing/`: generated winding geometry, orientation and routing sources.
- `pcb/`: stackup, copper placement and the preview board envelope.
- `geometry/`, `preview/`, `measure/` and `visualization/`: shared curve math,
  2D previews, measurement tools and 3D rendering, respectively.
- `driver/`, `move/` and `simulation/`: driver selection/calculation, move
  analysis/reporting and simulation job controllers.
- `constraints/` and `drc/`: design input checks and fabrication rule sets.
- `ipc/` and `types/`: native command boundaries and shared data contracts.
- `stores/`: document and workspace state. `menu/` holds native/browser menu
  definitions shared with the Rust shell.
- `components/`: Svelte UI grouped by feature, including shared CAD editing
  controls in `cad/` and measurement controls in `measure/`;
  component-specific helpers live alongside their consumers and `ui/`
  contains shared controls.
- `guide/`, `assets/` and `testFixtures/`: bundled documentation, static assets
  and helpers used only by tests.

Small cross-feature helpers remain at the library root. Native-only physics
must not gain a fabricated browser fallback when moving an IPC boundary.
