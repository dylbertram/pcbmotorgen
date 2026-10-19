export const DESIGN_PANELS = [
  { id: "constraints", label: "Constraints" },
  { id: "stackup", label: "Stackup" },
  { id: "routing", label: "Routing" },
  { id: "magnets", label: "Magnets" },
] as const;

export type DesignPanelId = (typeof DESIGN_PANELS)[number]["id"];
export type PreviewPanelId = DesignPanelId | "layers" | "display" | "terminals" | "driver";

export function isDesignPanel(panel: PreviewPanelId | null): panel is DesignPanelId {
  return DESIGN_PANELS.some(({ id }) => id === panel);
}
