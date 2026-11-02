/**
 * Tauri invoke wrappers for desktop operations and browser previews.
 *
 * Some preview calls use deterministic mocks when the Tauri runtime is not
 * available. Native-only operations report that they require the desktop app.
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
 * Native errors propagate to callers; they are never replaced by a mock.
 * Solver-backed operations such as move power and housing motion do not
 * fabricate browser results.
 *
 * ## Module layout
 * - `core` — runtime detection
 * - `physics` — preview and simulation calls
 * - `movePower` — native-only move calculation and cancellation
 * - `routing` — routing-pattern plugin catalog
 * - `drc` — generated and imported copper interference checks
 * - `kicad` — board connect / write / diagnostics / preview
 * - `dxf` — DXF import, export and native file dialogs
 * - `project` — project save/load (kata 0cgm; no mock fallback — these are
 *   critical calls)
 * - feature-specific `*Mock` modules — deterministic browser previews (internal)
 * - `sensor` — induction-sensor generation and export
 */

export * from "./core";
export * from "./drc";
export * from "./dxf";
export * from "./kicad";
export * from "./movePower";
export * from "./physics";
export * from "./project";
export * from "./routing";
export * from "./sensor";
