import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isTauriAvailable } from "./core";
import type { ViewMenuAction, ViewMenuState } from "../viewMenu";

export async function publishViewMenu(state: ViewMenuState): Promise<void> {
  if (isTauriAvailable()) await invoke("set_view_menu_state", { state });
}

export async function listenViewMenu(handler: (action: ViewMenuAction) => void): Promise<() => void> {
  if (!isTauriAvailable()) return () => {};
  return listen<ViewMenuAction>("menu:view", (event) => handler(event.payload));
}
