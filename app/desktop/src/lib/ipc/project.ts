/**
 * Project save/load IPC + native file-dialog helpers (kata 0cgm).
 *
 * The dialogs resolve the target path (interface concern, same convention
 * as `register_routing_plugin`); every persistence concern — serialization,
 * versioning, file I/O, validation — happens in the Rust commands
 * (`save_project` / `load_project`).
 *
 * Like `registerRoutingPlugin`, save/load are CRITICAL calls: they surface
 * real errors to the UI instead of falling back to a mock. The mock
 * fallback pattern is deliberately absent here — a silently-faked save
 * would be indistinguishable from a real one and lose user data.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  confirm,
  open as openDialog,
  save as saveDialog,
} from "@tauri-apps/plugin-dialog";
import type {
  LoadProjectResult,
  ProjectState,
  SaveProjectResult,
} from "../types";
import { isTauriAvailable } from "./core";

const PROJECT_FILE_FILTERS = [
  { name: "pcbmotorgen project (*.pmproj)", extensions: ["pmproj"] },
];

/** Default artifact file name offered by the Save As dialog. */
export const DEFAULT_PROJECT_FILE_NAME = "untitled.pmproj";

/**
 * Open the native file picker restricted to `.pmproj` project files.
 * Resolves with the chosen absolute path, or `null` when cancelled.
 * Throws when the Tauri backend is unavailable (plain browser dev).
 */
export async function pickProjectOpenPath(): Promise<string | null> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — opening projects requires the desktop app",
    );
  }
  return await openDialog({
    multiple: false,
    filters: PROJECT_FILE_FILTERS,
  });
}

/**
 * Open the native save dialog for a `.pmproj` project file.
 * Resolves with the chosen absolute path, or `null` when cancelled.
 * Throws when the Tauri backend is unavailable (plain browser dev).
 */
export async function pickProjectSavePath(
  defaultName: string,
): Promise<string | null> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — saving projects requires the desktop app",
    );
  }
  return await saveDialog({
    defaultPath: defaultName,
    filters: PROJECT_FILE_FILTERS,
  });
}

/**
 * Ask before replacing in-progress work (Open with unsaved changes).
 * Uses the native dialog in the desktop app, `window.confirm` outside it.
 */
export async function confirmDiscardChanges(): Promise<boolean> {
  if (!isTauriAvailable()) {
    return window.confirm(
      "You have unsaved changes. Discard them and open another project?",
    );
  }
  return await confirm(
    "You have unsaved changes. Discard them and open another project?",
    {
      title: "Unsaved changes",
      okLabel: "Discard changes",
      cancelLabel: "Keep editing",
      kind: "warning",
    },
  );
}

/**
 * Save the working state to `path` as a versioned `.pmproj` artifact.
 * The backend serializes and writes atomically; a rejection means the
 * file was not changed.
 */
export async function saveProject(
  path: string,
  project: ProjectState,
): Promise<SaveProjectResult> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — saving projects requires the desktop app",
    );
  }
  return await invoke<SaveProjectResult>("save_project", { path, project });
}

/**
 * Load a `.pmproj` artifact. Resolves with the state to restore plus the
 * backend's load-time design validation. Rejects with a specific message
 * for missing/corrupt/incompatible files — the caller must not touch the
 * in-progress state on rejection.
 */
export async function loadProject(path: string): Promise<LoadProjectResult> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — loading projects requires the desktop app",
    );
  }
  return await invoke<LoadProjectResult>("load_project", { path });
}

/**
 * Mirror the webview-owned recents list (most-recent-first) into the
 * native "Open Recent" File-menu submenu. Outside the Tauri shell there
 * is no native menu — a deliberate no-op (the recents persistence itself
 * still works, see the recents store). Rejections are tolerated by the
 * recents store's port (best-effort menu refresh).
 */
export async function setRecentFiles(paths: string[]): Promise<void> {
  if (!isTauriAvailable()) return;
  await invoke("set_recent_files", { paths });
}

/**
 * Backend disk-existence check (a plain stat on the Rust side — the
 * plugin-fs scope would reject arbitrary user-picked locations). Outside
 * the Tauri shell the check cannot run: resolves `true` (fail-open) so
 * the recents store never prunes on a missing backend.
 */
export async function fileExists(path: string): Promise<boolean> {
  if (!isTauriAvailable()) return true;
  return await invoke<boolean>("file_exists", { path });
}

/**
 * Wire the native File menu to the project flows. The Rust menu bar owns
 * the items and accelerators (`src-tauri/src/menu.rs`) and forwards each
 * click as a Tauri event whose name equals the item id. Handlers run the
 * same `ProjectStore` flows the former header buttons used; the store's
 * `busy` guard serializes overlapping events. Resolves with an unbind
 * function (no-op outside the Tauri shell — plain browser dev has no
 * native menu).
 */
export async function bindProjectMenuActions(handlers: {
  open: () => void;
  save: () => void;
  saveAs: () => void;
  /** The native File > Import CAD menu item was clicked. */
  importCad?: () => void;
  /**
   * An "Open Recent" entry was clicked (kata eap8). The payload is the
   * absolute path exactly as it was displayed in the submenu.
   */
  openRecent?: (path: string) => void;
  /** The "Clear Recent Files" entry was clicked (kata eap8). */
  clearRecent?: () => void;
}): Promise<() => void> {
  if (!isTauriAvailable()) {
    return () => {};
  }
  const unlisteners = await Promise.all([
    listen("menu:open-project", handlers.open),
    listen("menu:save-project", handlers.save),
    listen("menu:save-project-as", handlers.saveAs),
    listen("menu:import-cad", () => handlers.importCad?.()),
    // Open Recent (kata eap8): Rust resolves the entry id to the path that
    // was displayed and forwards it as the event payload. Registered even
    // when the handlers are absent — the recents wiring is optional and
    // the menu emits these events only when its items are clicked.
    listen<string>("menu:open-project-recent", (event) =>
      handlers.openRecent?.(event.payload),
    ),
    listen("menu:clear-recent-files", () => handlers.clearRecent?.()),
  ]);
  return () => {
    for (const unlisten of unlisteners) unlisten();
  };
}
