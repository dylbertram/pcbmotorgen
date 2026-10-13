import { expect, test } from "@playwright/test";

test.describe("startup chooser and new-design setup", () => {
  test("new-design routing source opens file loaders and preserves setup on cancel", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "New design" }).click();
    const source = startup.getByLabel("Routing source", { exact: true });
    await expect(source).toBeVisible();
    await expect(startup.getByText("Routing pattern", { exact: true })).toHaveCount(0);
    await startup.getByLabel("Copper layers").selectOption("6");
    const originalSource = await source.inputValue();

    await source.selectOption({ label: "Load new generator from file…" });
    const generator = page.getByRole("dialog", { name: "Load new generator", exact: true });
    await expect(generator).toBeVisible();
    await expect(generator).toHaveCSS("z-index", "120");
    await generator.getByRole("button", { name: "How to write a plugin?" }).click();
    const guide = page.getByRole("dialog", { name: "How to write a routing plugin", exact: true });
    await expect(guide).toBeVisible();
    await expect(guide).toHaveCSS("z-index", "130");
    await page.keyboard.press("Escape");
    await expect(guide).toBeHidden();
    await generator.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(source).toHaveValue(originalSource);

    await source.selectOption({ label: "Load new design from file…" });
    const cad = page.getByRole("dialog", { name: "Import CAD", exact: true });
    await expect(cad.getByLabel("Coil type")).toBeVisible();
    await cad.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(source).toHaveValue(originalSource);
    await expect(startup.getByLabel("Copper layers")).toHaveValue("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(page.locator("#num-layers")).toContainText("6");
  });

  test("a generator loaded from startup becomes the selected routing source", async ({ page }) => {
    await page.route("**/src/lib/ipc/dxf.ts", (route) => route.fulfill({
      contentType: "application/javascript",
      body: `export * from '/src/lib/ipc/dxf.ts?original';
        export async function openFileDialog() { return '/custom.py'; }`,
    }));
    await page.route("**/src/lib/ipc/routing.ts", (route) => route.fulfill({
      contentType: "application/javascript",
      body: `let loaded = false;
        export async function listRoutingPatterns() {
          return [{ id: 'infinity-braid', display_name: 'Infinity Braid' },
            ...(loaded ? [{ id: 'custom', display_name: 'Custom generator', min_layers: 6, max_layers: 6 }] : [])];
        }
        export async function registerRoutingPlugin() { loaded = true; return 'custom'; }
        export async function routingPatternParameters() { return []; }
        export async function loadInstalledPlugins() { return []; }
        export async function checkCoilInterference() { return []; }`,
    }));
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "New design" }).click();
    await startup.getByLabel("Routing source", { exact: true }).selectOption({ label: "Load new generator from file…" });
    const generator = page.getByRole("dialog", { name: "Load new generator", exact: true });
    await generator.getByRole("button", { name: "Browse…" }).click();
    await generator.getByRole("button", { name: "Load generator", exact: true }).click();
    await expect(generator).toBeHidden();
    await expect(startup.getByLabel("Routing source", { exact: true })).toHaveValue("custom");
    await expect(startup.getByLabel("Copper layers")).toHaveValue("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(page.locator("#routing-pattern")).toContainText("Custom generator");
  });

  test("coil type is an import option and cancelling keeps the motor workflow", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    const dialog = page.getByRole("dialog", { name: "Import CAD" });
    await expect(dialog.getByLabel("Coil type")).toHaveValue("motor");
    await dialog.getByLabel("Coil type").selectOption("sensor");
    await expect(dialog.getByLabel("DXF units")).toBeVisible();
    await expect(dialog.getByRole("tab")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await startup.getByRole("button", { name: "Import CAD" }).click();
    await expect(dialog.getByLabel("Coil type")).toHaveValue("motor");
  });

  test("sensor imports open the sensor preview without replacing motor geometry", async ({ page }) => {
    await page.route("**/src/lib/ipc/dxf.ts", (route) => route.fulfill({
      contentType: "application/javascript",
      body: `export async function pickCadDxfPath() { return '/sensor.dxf'; }
        export async function importCadDxf(path, units, tolerance, width) {
          return { warnings: [], geometry: { trace_width_mm: width, layer_z_mm: [-0.8, 0.8],
            routing: { format_version: 1, segments: [{ start: {x: 0, y: 0}, end: {x: 40, y: 2}, layer: 0, net: 'CL1', is_active: true }], curves: [], vias: [] } } };
        }
        export async function openFileDialog() {}
        export async function exportCoilsDxf() {}
        export async function exportCadGeometryDxf() {}`,
    }));
    await page.goto("/");
    await page.getByRole("button", { name: "Import CAD", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Import CAD" });
    await dialog.getByLabel("Coil type").selectOption("sensor");
    await dialog.getByRole("button", { name: "Choose DXF…" }).click();
    await dialog.getByRole("button", { name: "Open with this geometry" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("img", { name: "Imported sensor coil traces" })).toBeVisible();
    await expect(page.locator('section[aria-labelledby="sensor-preview-title"] line')).toHaveCount(1);
    await expect(page.getByRole("tab", { name: /^Simulate/ })).toHaveCount(0);
    await page.getByRole("radio", { name: "Motor coil", exact: true }).check();
    await expect(page.locator("#num-layers")).toContainText("4");
  });

  test("clicking outside Import CAD cancels without applying draft settings", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    const importDialog = page.getByRole("dialog", { name: "Import CAD" });
    const traceWidth = importDialog.getByLabel("Trace width (mm)");
    const originalWidth = await traceWidth.inputValue();
    await traceWidth.fill("0.321");
    await expect(importDialog).toBeVisible();

    await page.mouse.click(2, 2);
    await expect(importDialog).toBeHidden();
    await expect(startup).toBeVisible();

    await startup.getByRole("button", { name: "Import CAD" }).click();
    await expect(traceWidth).toHaveValue(originalWidth);
    await importDialog.getByRole("button", { name: "Cancel" }).click();
    await expect(startup).toBeVisible();
  });

  test("immediately shows recents and keeps Open project available when the list is empty", async ({ page }) => {
    await page.goto("/");
    const dialog = page.getByRole("dialog", { name: "Recent projects" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toBeFocused();
    await expect(dialog).toHaveCSS("outline-style", "none");
    await page.keyboard.press("Tab");
    const openProject = dialog.getByRole("button", { name: "Open project…" });
    await expect(openProject).toBeFocused();
    await expect(openProject).not.toHaveCSS("outline-style", "none");
    await expect(dialog.getByText("No recent projects yet.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Open project…" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "New design" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Import CAD" })).toBeVisible();
  });

  test("sets layer count and generated pattern before entering the app", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog");
    await startup.getByRole("button", { name: "New design" }).click();

    await expect(startup).toHaveAttribute("aria-labelledby", "startup-title");
    await expect(page.locator("#startup-pattern")).toBeVisible();
    await expect(page.locator("#startup-layers")).toHaveValue("4");
    await expect(page.locator("#startup-source")).toHaveCount(0);
    await expect(startup.getByRole("button", { name: "Import CAD", exact: true })).toHaveCount(1);

    await page.locator("#startup-layers").selectOption("6");
    await expect(page.locator("#startup-layers")).toHaveValue("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.locator("#num-layers")).toContainText("6");
  });

  test("Import CAD uses a modal and the Design page has no inline import controls", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    const importDialog = page.getByRole("dialog", { name: "Import CAD" });
    await expect(importDialog).toBeVisible();
    await expect(importDialog.getByLabel("DXF units")).toBeVisible();
    await expect(importDialog.getByLabel("Z tolerance (mm)")).toBeVisible();
    await expect(importDialog.getByRole("button", { name: "About Z tolerance" })).toBeVisible();
    const traceWidth = importDialog.getByLabel("Trace width (mm)");
    await expect(traceWidth).toBeVisible();
    await expect(traceWidth).toHaveAttribute("type", "text");
    await traceWidth.fill("0.127");
    await traceWidth.evaluate((input: HTMLInputElement) => input.setSelectionRange(3, 3));
    await traceWidth.press("Backspace");
    await expect(traceWidth).toHaveValue("0.27");
    await expect(importDialog.getByLabel("Via hole size (mm)")).toBeVisible();
    await expect(importDialog.getByLabel("Annular ring width (mm)")).toBeVisible();
    await expect(importDialog.locator("#cad-retry-layer-count")).toHaveCount(0);
    await expect(importDialog.getByRole("button", { name: "Choose DXF…" })).toBeVisible();

    await importDialog.getByRole("button", { name: "Cancel" }).click();
    await startup.getByRole("button", { name: "New design" }).click();
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.getByRole("button", { name: /Import DXF/i })).toHaveCount(0);
    await expect(page.getByLabel("DXF units")).toHaveCount(0);
  });
});
