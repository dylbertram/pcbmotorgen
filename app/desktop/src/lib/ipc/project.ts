/**
 * Project save/load IPC + native file-dialog helpers (kata 0cgm).
 *
 * The dialogs resolve the target path (interface concern, same convention
 * as `register_routing_plugin`); every persistence concern — serialization,
 * versioning, file I/O, validation — happens in the Rust commands
 * (`save_document` / `load_project` and the workspace commands).
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
  DocumentKind,
  WorkspaceLoad,
} from "../types";
import { isTauriAvailable } from "./core";

const PROJECT_FILE_FILTERS = [
  { name: "pcbmotorgen files", extensions: ["pmproj", "pmmotor", "pmsensor"] },
];

/** Default artifact file name offered by the Save As dialog. */
export const DEFAULT_PROJECT_FILE_NAME = "untitled.pmmotor";

export function documentExtension(kind: DocumentKind): string {
  return kind === "motor" ? "pmmotor" : "pmsensor";
}

export async function resolveDocumentPath(path: string): Promise<string> {
  if (!isTauriAvailable()) throw new Error("Opening files requires the desktop app.");
  return await invoke("resolve_document_path", { path });
}

export async function confirmLegacyMigration(): Promise<boolean> {
  if (!isTauriAvailable()) return false;
  return await confirm("This older project contains motor and sensor designs together. Convert it to a new workspace with separate .pmmotor and .pmsensor files? Every saved version is preserved. The original project will not change.", { title: "Convert older project", okLabel: "Choose new workspace", cancelLabel: "Cancel" });
}

export async function loadWorkspace(path: string): Promise<WorkspaceLoad> {
  if (!isTauriAvailable()) throw new Error("Opening workspaces requires the desktop app.");
  return await invoke("load_workspace", { path });
}

export async function saveWorkspace(path: string, files: string[], activeFile: string | null): Promise<void> {
  if (!isTauriAvailable()) throw new Error("Saving workspaces requires the desktop app.");
  await invoke("save_workspace", { path, files, activeFile });
}

export async function migrateWorkspace(source: string, destination: string): Promise<WorkspaceLoad> {
  if (!isTauriAvailable()) throw new Error("Migrating projects requires the desktop app.");
  return await invoke("migrate_workspace", { source, destination });
}

export async function pickWorkspaceSavePath(defaultPath = "untitled.pmproj"): Promise<string | null> {
  if (!isTauriAvailable()) throw new Error("Saving workspaces requires the desktop app.");
  return await saveDialog({ title: "Save project workspace", defaultPath, filters: [{ name: "pcbmotorgen workspace", extensions: ["pmproj"] }] });
}

export async function pickProjectDirectory(defaultPath?: string): Promise<string | null> {
  if (!isTauriAvailable()) throw new Error("Choosing a project folder requires the desktop app");
  return await openDialog({ title: "Choose project location", directory: true, multiple: false, defaultPath });
}

export async function relocateProject(sourcePath: string | null, directory: string, name: string, project: ProjectState, activeVersionId: number | null): Promise<SaveProjectResult> {
  if (!isTauriAvailable()) throw new Error("Renaming or moving projects requires the desktop app");
  return await invoke<SaveProjectResult>("relocate_project", { sourcePath, directory, name, project, activeVersionId });
}

/**
 * Open the native file picker for workspaces and both coil document types.
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
 * Open the native save dialog for the selected coil document type.
 * Resolves with the chosen absolute path, or `null` when cancelled.
 * Throws when the Tauri backend is unavailable (plain browser dev).
 */
export async function pickProjectSavePath(
  defaultName: string,
  kind: DocumentKind = "motor",
): Promise<string | null> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — saving projects requires the desktop app",
    );
  }
  return await saveDialog({
    defaultPath: defaultName,
    filters: [{ name: kind === "motor" ? "Motor coil" : "Sensor coil", extensions: [documentExtension(kind)] }],
  });
}

/**
 * Ask before replacing in-progress work (Open with unsaved changes).
 * Uses the native dialog in the desktop app, `window.confirm` outside it.
 */
export async function confirmDiscardChanges(action = "start another project"): Promise<boolean> {
  const message = `You have unsaved changes. Discard them and ${action}?`;
  if (!isTauriAvailable()) {
    return window.confirm(message);
  }
  return await confirm(
    message,
    {
      title: "Unsaved changes",
      okLabel: "Discard changes",
      cancelLabel: "Keep editing",
      kind: "warning",
    },
  );
}

/**
 * Save the working state to `path` as a typed coil document.
 * The backend serializes and writes atomically; a rejection means the
 * file was not changed.
 */
export async function saveProject(
  path: string,
  project: ProjectState,
  options: { sourcePath: string | null; activeVersionId: number | null; newVersion: boolean; description?: string; kind?: DocumentKind } = { sourcePath: null, activeVersionId: null, newVersion: false },
): Promise<SaveProjectResult> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — saving projects requires the desktop app",
    );
  }
  return await invoke<SaveProjectResult>("save_document", {
    documentType: options.kind ?? "motor",
    path, project, sourcePath: options.sourcePath, activeVersionId: options.activeVersionId,
    newVersion: options.newVersion, description: options.description ?? null,
  });
}

/**
 * Load a `.pmmotor` or `.pmsensor` document. Resolves with the state plus the
 * backend's load-time design validation. Rejects with a specific message
 * for missing/corrupt/incompatible files — the caller must not touch the
 * in-progress state on rejection.
 */
export async function loadProject(path: string, versionId: number | null = null): Promise<LoadProjectResult> {
  if (!isTauriAvailable()) {
    throw new Error(
      "Tauri backend unavailable — loading projects requires the desktop app",
    );
  }
  return await invoke<LoadProjectResult>("load_project", { path, versionId });
}

export async function updateProjectVersion(path: string, versionId: number, activeVersionId: number | null, options: { description?: string; deleteVersion?: boolean }): Promise<LoadProjectResult> {
  if (!isTauriAvailable()) throw new Error("Editing project versions requires the desktop app");
  return await invoke<LoadProjectResult>("update_project_version", {
    path, versionId, activeVersionId, description: options.description ?? null, deleteVersion: options.deleteVersion ?? false,
  });
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
  newFile?: () => void;
  newProject?: () => void;
  saveWorkspace?: () => void;
  saveWorkspaceAs?: () => void;
  saveAll?: () => void;
  closeFile?: () => void;
  exportDxf?: () => void;
  sendKicad?: () => void;
  open: () => void;
  save: () => void;
  saveAs: () => void;
  saveNewVersion?: () => void;
  settings?: () => void;
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
    listen("menu:new-file", () => handlers.newFile?.()),
    listen("menu:new-project", () => handlers.newProject?.()),
    listen("menu:save-workspace", () => handlers.saveWorkspace?.()),
    listen("menu:save-workspace-as", () => handlers.saveWorkspaceAs?.()),
    listen("menu:save-all", () => handlers.saveAll?.()),
    listen("menu:close-file", () => handlers.closeFile?.()),
    listen("menu:export-dxf", () => handlers.exportDxf?.()),
    listen("menu:send-kicad", () => handlers.sendKicad?.()),
    listen("menu:open-project", handlers.open),
    listen("menu:save-project", handlers.save),
    listen("menu:save-project-as", handlers.saveAs),
    listen("menu:save-project-new-version", () => handlers.saveNewVersion?.()),
    listen("menu:settings", () => handlers.settings?.()),
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
