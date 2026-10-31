import definitions from "./viewMenu.json";
import type { CoilPreviewViewState } from "./components/design/coilPreviewViewState.svelte";

type View = Pick<CoilPreviewViewState, "viewMode" | "traceMode" | "showTerminals" | "showVias" | "showPolePitch" | "showBandWidths" | "showPoleRegions" | "showWaveform" | "oneSection">;
export interface ViewCapabilities { active: boolean; polePitch: boolean; bandWidths: boolean; poleRegions: boolean }
interface Definition { id: string; label: string; property: keyof View; value?: string; capability?: Exclude<keyof ViewCapabilities, "active"> }
/** Shared with Rust: group boundaries are native separators, never layer filters. */
export const VIEW_MENU_GROUPS = definitions as Definition[][];
export interface ViewMenuItemState { id: string; checked: boolean; enabled: boolean }
export interface ViewMenuState { owner: string | null; items: ViewMenuItemState[] }
export interface ViewMenuAction { owner: string; id: string }

export function viewMenuItems(view: View | null, capabilities: ViewCapabilities): ViewMenuItemState[] {
  return VIEW_MENU_GROUPS.flat().map((item) => ({
    id: item.id,
    checked: !!view && (item.value === undefined ? !!view[item.property] : view[item.property] === item.value),
    enabled: !!view && capabilities.active && (!item.capability || capabilities[item.capability]),
  }));
}

export function applyViewMenuAction(view: View, id: string): void {
  const item = VIEW_MENU_GROUPS.flat().find((item) => item.id === id);
  if (!item) return;
  if (item.property === "viewMode") view.viewMode = item.value === "iso" ? "iso" : "top";
  else if (item.property === "traceMode") view.traceMode = item.value === "centerlines" ? "centerlines" : "traces";
  else view[item.property] = !view[item.property];
}
