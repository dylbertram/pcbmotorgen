import { listen } from "@tauri-apps/api/event";
import { isTauriAvailable } from "../ipc/core";
import { isSimulationAction, type SimulationAction } from "./simulationMenu";

/** Bind native menu events to workspace and document actions. */
export async function bindProjectMenuActions(handlers: {
  simulate?: (action: SimulationAction) => void;
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
  importCad?: () => void;
  openRecent?: (path: string) => void;
  clearRecent?: () => void;
}): Promise<() => void> {
  if (!isTauriAvailable()) return () => {};
  const unlisteners = await Promise.all([
    listen<unknown>("menu:simulate", (event) => { if (isSimulationAction(event.payload)) handlers.simulate?.(event.payload); }),
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
    listen<string>("menu:open-project-recent", (event) => handlers.openRecent?.(event.payload)),
    listen("menu:clear-recent-files", () => handlers.clearRecent?.()),
  ]);
  return () => {
    for (const unlisten of unlisteners) unlisten();
  };
}
