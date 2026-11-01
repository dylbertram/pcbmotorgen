export const DESIGN_PANELS = [
  { id: "routing", label: "Routing" },
  { id: "stackup", label: "Stackup" },
  { id: "magnets", label: "Magnets" },
  { id: "drive", label: "Drive & force targets" },
] as const;

export type DesignPanelId = (typeof DESIGN_PANELS)[number]["id"];
export type PreviewPanelId = DesignPanelId | "layers" | "terminals" | "driver" | "fields";

export function isDesignPanel(panel: PreviewPanelId | null): panel is DesignPanelId {
  return DESIGN_PANELS.some(({ id }) => id === panel);
}

export function isLeftPanel(panel: PreviewPanelId | null): boolean {
  return isDesignPanel(panel) || panel === "terminals" || panel === "driver";
}
