import { test, expect } from "@playwright/test";
import { designConstraintsPanel, gotoDesignApp, selectDesignPanel } from "./helpers";

test("constraint readouts share one value color in both themes", async ({ page }) => {
  await gotoDesignApp(page);
  const constraints = designConstraintsPanel(page);
  await constraints.locator("summary", { hasText: "Winding dimensions" }).click();
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
    const colors = await constraints.locator("dd").evaluateAll((elements) =>
      [...new Set(elements.map((el) => getComputedStyle(el).color))],
    );
    expect(colors).toHaveLength(1);
  }
});

test("assembly draws opaque visible faces and keeps its dimension below the board", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const diagram = designConstraintsPanel(page).getByRole("img", { name: "Three-quarter isometric view of the assembly" });
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
    for (const solid of ["board", "mover"]) {
      const faces = diagram.locator(`[data-solid='${solid}'] polygon`);
      await expect(faces).toHaveCount(3);
      expect(await faces.evaluateAll((elements) => elements.every((el) => {
        const style = getComputedStyle(el);
        return style.fill !== "none" && style.fillOpacity === "1" && style.opacity === "1";
      }))).toBe(true);
      await expect(diagram.locator(`[data-solid='${solid}'] :is(path, line)`)).toHaveCount(0);
    }
    const bounds = await diagram.evaluate((svg) => {
      const assembly = svg.querySelector<SVGGraphicsElement>("[data-assembly]")!.getBBox();
      const dimension = svg.querySelector<SVGGraphicsElement>("[data-trace-dimension]")!.getBBox();
      return { bottom: assembly.y + assembly.height, dimensionTop: dimension.y };
    });
    expect(bounds.dimensionTop).toBeGreaterThan(bounds.bottom);
    await diagram.screenshot({ path: testInfo.outputPath(`assembly-${colorScheme}.png`) });
  }
});

test("assembly and dimension stay inside the drawing for tall magnets and both travel limits", async ({ page }) => {
  await gotoDesignApp(page);
  await selectDesignPanel(page, "Magnets");
  const height = page.getByRole("spinbutton", { name: "Z Thickness (mm), magnetisation-axis thickness", exact: true });
  await height.fill("20");
  await height.press("Enter");
  await selectDesignPanel(page, "Constraints");
  const constraints = designConstraintsPanel(page);
  const diagram = constraints.getByRole("img", { name: "Three-quarter isometric view of the assembly" });
  const slider = page.locator("#panel-design").getByRole("slider", { name: "Mover position slider (mm)" });
  for (const key of ["Home", "End"]) {
    await slider.focus();
    await slider.press(key);
    const fits = await diagram.evaluate((svg) => {
      const viewBox = (svg as SVGSVGElement).viewBox.baseVal;
      return ["[data-assembly]", "[data-trace-dimension]"].every((selector) => {
        const box = svg.querySelector<SVGGraphicsElement>(selector)!.getBBox();
        return box.x >= 0 && box.y >= 0 && box.x + box.width <= viewBox.width && box.y + box.height <= viewBox.height;
      });
    });
    expect(fits).toBe(true);
  }
});
