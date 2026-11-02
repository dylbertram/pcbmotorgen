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

export function documentExtension(kind: DocumentKind): string {
  return kind === "motor" ? "pmmotor" : "pmsensor";
}

export async function resolveDocumentPath(path: string): Promise<string> {
  if (!isTauriAvailable()) throw new Error("Opening files requires the desktop app.");
  return await invoke("resolve_document_path", { path });
}

export async function listCoilFiles(directory: string): Promise<string[]> {
  if (!isTauriAvailable()) return [];
  return await invoke("list_coil_files", { directory });
}

export async function revealInFinder(path: string): Promise<void> {
  if (!isTauriAvailable()) throw new Error("Revealing files in Finder requires the desktop app.");
  await invoke("reveal_in_finder", { path });
}

export async function loadWorkspace(path: string): Promise<WorkspaceLoad> {
  if (!isTauriAvailable()) throw new Error("Opening workspaces requires the desktop app.");
  return await invoke("load_workspace", { path });
}

export async function saveWorkspace(path: string, files: string[], activeFile: string | null): Promise<void> {
  if (!isTauriAvailable()) throw new Error("Saving workspaces requires the desktop app.");
  await invoke("save_workspace", { path, files, activeFile });
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
