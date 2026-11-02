import { describe, expect, it } from "vitest";
import { DESIGN_PANELS, isDesignPanel, isLeftPanel } from "./previewPanels";

describe("preview panel placement", () => {
  it("places each design panel on the left", () => {
    for (const { id } of DESIGN_PANELS) {
      expect(isDesignPanel(id)).toBe(true);
      expect(isLeftPanel(id)).toBe(true);
    }
  });

  it("distinguishes other left panels from right panels and no panel", () => {
    for (const id of ["terminals", "driver"] as const) {
      expect(isDesignPanel(id)).toBe(false);
      expect(isLeftPanel(id)).toBe(true);
    }
    for (const id of ["layers", "fields", null] as const) {
      expect(isDesignPanel(id)).toBe(false);
      expect(isLeftPanel(id)).toBe(false);
    }
  });
});
