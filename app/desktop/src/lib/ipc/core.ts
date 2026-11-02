/**
 * `true` when the page is running inside the Tauri shell, `false` for
 * plain `vite dev` (or any browser without the Tauri IPC bridge).
 *
 * The Tauri v2 runtime injects `window.__TAURI_INTERNALS__`; its mere
 * presence is the canonical "we have a backend" signal. We use this
 * instead of a try/catch around `invoke()` so we can distinguish
 * "no backend available" (return mock) from "backend returned an error"
 * (let the error propagate to the UI).
 */
export function isTauriAvailable(): boolean {
  if (typeof window === "undefined") return false;
  return (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__ !== undefined;
}
