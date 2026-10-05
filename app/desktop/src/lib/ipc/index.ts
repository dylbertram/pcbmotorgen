/**
 * pcbmotorgen — Tauri invoke wrappers with mock fallback.
 *
 * Every call attempts the real Tauri backend command. If the Tauri runtime
 * is not available (frontend-only dev mode, e.g. `vite dev` outside of
 * `tauri dev`), a deterministic mock is returned so the dashboard stays
 * interactive.
 *
 * ## Error handling
 *
 * **Critical IPC calls** (the ones the user can act on, e.g. the
 * "Write to Board" button) **surface real errors** to the UI. We do NOT
 * silently swallow them — the historical `try { invoke() } catch { mock }`
 * pattern is what caused the "0 of 0 written" bug, because a real Tauri
 * failure looked identical to "everything worked but produced 0 items".
 * The mock fallback is only used when the Tauri runtime itself is
 * unavailable (see `isTauriAvailable`).
 *
 * **Physics and preview calls** (force sweep, coil generation, budgets, and
 * B-field sampling) keep the mock fallback because their failure is
 * recoverable — the user just sees stale data, not a broken write. The app
 * schedules simulation calls only while the Simulation tab is active.
 *
 * ## Module layout
 * - `core` — runtime detection, unit helpers, debounce
 * - `physics` — preview and Simulation-tab science calls
 * - `routing` — routing-pattern plugin catalog + DRC checks
 * - `kicad` — board connect / write / diagnostics / preview
 * - `dxf` — DXF export + native file dialog
 * - `project` — project save/load (kata 0cgm; no mock fallback — these are
 *   critical calls)
 * - `mocks` — deterministic offline implementations (internal)
 */

export * from "./core";
export * from "./dxf";
export * from "./kicad";
export * from "./physics";
export * from "./project";
export * from "./routing";
export * from "./sensor";
