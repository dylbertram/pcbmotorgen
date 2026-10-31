import definitions from "./viewMenu.json";
import type { CoilPreviewViewState } from "./components/design/coilPreviewViewState.svelte";

type View = Pick<CoilPreviewViewState, "viewMode" | "traceMode" | "showTerminals" | "showVias" | "showPcb" | "showPolePitch" | "showBandWidths" | "showPoleRegions" | "showWaveform" | "oneSection" | "zoomWindow">;
export interface ViewCapabilities { active: boolean; polePitch: boolean; bandWidths: boolean; poleRegions: boolean }
interface Definition { id: string; label: string; property?: keyof View; value?: string; capability?: Exclude<keyof ViewCapabilities, "active">; action?: "fitExtents"; submenu?: "Zoom" }
export interface ViewMenuActions { fitExtents: () => void; toggleZoomWindow: () => void }
/** Shared with Rust: groups become native separators or the named submenu. */
export const VIEW_MENU_GROUPS = definitions as Definition[][];
export interface ViewMenuItemState { id: string; checked: boolean; enabled: boolean }
export interface ViewMenuState { owner: string | null; items: ViewMenuItemState[] }
export interface ViewMenuAction { owner: string; id: string }

export function viewMenuItems(view: View | null, capabilities: ViewCapabilities): ViewMenuItemState[] {
  return VIEW_MENU_GROUPS.flat().map((item) => ({
    id: item.id,
    checked: !!view && !!item.property && (item.value === undefined ? !!view[item.property] : view[item.property] === item.value),
    enabled: !!view && capabilities.active && (!item.capability || capabilities[item.capability]),
  }));
}

export function applyViewMenuAction(view: View, id: string, actions?: ViewMenuActions): void {
  const item = VIEW_MENU_GROUPS.flat().find((item) => item.id === id);
  if (!item) return;
  if (item.action === "fitExtents") { actions?.fitExtents(); return; }
  if (item.property === "zoomWindow" && actions) { actions.toggleZoomWindow(); return; }
  if (!item.property) return;
  if (item.property === "viewMode") {
    if (item.value === "top" || item.value === "front" || item.value === "left" || item.value === "iso") view.viewMode = item.value;
  }
  else if (item.property === "traceMode") view.traceMode = item.value === "centerlines" ? "centerlines" : "traces";
  else view[item.property] = !view[item.property];
}
