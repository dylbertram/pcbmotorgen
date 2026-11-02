# Desktop library

Feature modules live next to their unit tests:

- `cad/`: imported geometry, phase and terminal mapping, and editing tools.
- `routing/`: generated winding geometry, orientation and routing sources.
- `pcb/`: stackup, copper placement and the preview board envelope.
- `geometry/`, `preview/`, `measure/` and `visualization/`: shared curve and viewport math,
  2D preview geometry, state, gestures and styles, measurement tools and 3D rendering, respectively.
- `driver/`, `move/` and `simulation/`: driver library and calculation, carriage
  mass and move analysis/reporting, and simulation job controllers.
- `sensor/`: sensor state, geometry request lifecycle and imported-CAD preview mapping.
- `constraints/` and `drc/`: design input checks and fabrication rule sets and controller.
- `ipc/` and `types/`: native command boundaries and shared data contracts.
- `stores/`: document sessions, per-view state and workspace orchestration. `menu/` holds native/browser menu
  definitions shared with the Rust shell.
- `components/`: Svelte UI grouped by feature, including the import dialog and
  editing controls in `cad/`, sensor controls in `sensor/`, export panels in
  `export/`, design controls grouped under `design/` and the simulation dock in `simulate/`,
  3D scene and viewer in `scene/`, frame, side rail, layer and zoom controls in `preview/`, measurement controls in `measure/`,
  generator management in `plugins/`, PCB guides in `pcb/`, and design-rule status in `drc/`;
  component-specific helpers live alongside their consumers and `ui/`
  contains shared controls.
- `guide/`, `assets/` and `testFixtures/`: bundled documentation, static assets
  and helpers used only by tests.

Small cross-feature helpers remain at the library root. Native-only physics
must not gain a fabricated browser fallback when moving an IPC boundary.
