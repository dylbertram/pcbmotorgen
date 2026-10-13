import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

// Exercise the real dialog, store and preview with a deterministic IPC boundary.
// Parsing and coil assignments themselves are covered by Rust DXF fixtures.
test.beforeEach(async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace("export async function bindProjectMenuActions(handlers) {", `export async function bindProjectMenuActions(handlers) {
      window.addEventListener('test-file-action', event => handlers[event.detail]?.());`);
    await route.fulfill({ response, body });
  });
  await page.route(/\/src\/lib\/ipc\/dxf\.ts(?:\?t=\d+)?$/, async route => {
    const response = await route.fetch();
    let body = await response.text();
    body = body.replace(/export async function pickCadDxfPath\(\) \{[\s\S]*?\n\}/, `export async function pickCadDxfPath() { return '/fixture/coil-leads.dxf'; }`);
    body = body.replace(/export async function importCadDxf\([\s\S]*?\n\}/, `export async function importCadDxf(path, units, tolerance, width, count, thickness, assignments = {}) {
      const source = { L0_A: 'A', L0_B: 'B', holes: 'holes' };
      const source_layer_coils = Object.fromEntries(Object.entries(source).map(([name, coil]) => [name, (assignments[name] ?? coil).trim()]));
      return { warnings: [], geometry: { layer_z_mm: [-1.6, 0], trace_width_mm: width, source_layer_coils,
        routing: { format_version: 2, curves: [], splines: [],
          segments: ['A', 'B'].flatMap((coil, row) => [0, 1].map(x => ({
            start: { x, y: row * 2 }, end: { x: x + 1, y: row * 2 },
            layer: 0, net: source_layer_coils['L0_' + coil], is_active: true,
          }))).concat(window.__cadLayered ? [{ start: { x: 0, y: 0 }, end: { x: 2, y: 0 }, layer: 1, net: source_layer_coils.L0_A, is_active: true }] : []),
          vias: [{ position: { x: 2, y: 0 }, from_layer: 0, to_layer: 1, net: source_layer_coils.holes }],
        },
      }};
    }`);
    await route.fulfill({ response, body });
  });
});

async function openTerminalTool(page: Page) {
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByLabel("Coil for terminal selection").selectOption("A");
  await command.getByRole("button", { name: "Select IN", exact: true }).click();
  return { command, tools };
}

test("terminal command advances IN to OUT to review and preserves confirmed labels through simplify", async ({ page }, testInfo) => {
  const { command, tools } = await openTerminalTool(page);
  const input = page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true });
  await expect(command.getByRole("status")).toContainText("Click the IN endpoint");
  const box = (await input.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.up();
  await expect(command.getByRole("status")).toContainText("Click the IN endpoint");
  await input.click();
  await expect(command.getByRole("status")).toContainText("Click the OUT endpoint");
  await input.click();
  await expect(command.getByRole("alert")).toContainText("different from IN");
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Review the highlighted");
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Simplify lines", exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("coil-terminal-review.png") });
  await command.getByRole("button", { name: "Done", exact: true }).click();
  const summary = page.getByRole("region", { name: "Configured coil terminals" });
  await expect(summary).toContainText("IN L0, X 0 mm");
  await expect(summary).toContainText("OUT L0, X 2 mm");
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("OUT L0, X 2 mm");
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(summary).toContainText("IN L0, X 0 mm");
});

test("terminal drafts support Back, Cancel, Escape and switching to Measure", async ({ page }) => {
  const { command, tools } = await openTerminalTool(page);
  const input = () => page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true });
  const output = () => page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true });
  await input().click(); await output().click();
  await command.getByRole("button", { name: "Back", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Click the OUT endpoint");
  await command.getByRole("button", { name: "Back", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Click the IN endpoint");
  await input().click();
  await command.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(command).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await command.getByLabel("Coil for terminal selection").selectOption("A");
  await command.getByRole("button", { name: "Select IN", exact: true }).click();
  await input().click(); await output().click();
  await page.keyboard.press("Escape");
  await expect(command).toHaveCount(0);
  await expect(tools).toBeVisible();
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await tools.getByRole("button", { name: "Toggle measure tool" }).click();
  await expect(command).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
});

test("overlapping endpoints are disambiguated by copper layer and support keyboard selection", async ({ page }) => {
  await page.addInitScript("window.__cadLayered = true;");
  const { command } = await openTerminalTool(page);
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true }).click();
  await command.getByLabel("Copper layer for terminal selection").selectOption("1");
  await expect(page.getByRole("button", { name: /Endpoint coil A, L0/ })).toHaveCount(0);
  const output = page.getByRole("button", { name: "Endpoint coil A, L1, X 2 mm, Y 0 mm", exact: true });
  await output.focus(); await page.keyboard.press("Enter");
  await expect(command.getByRole("status")).toContainText("Review the highlighted");
  await command.getByRole("button", { name: "Done", exact: true }).click();
  const summary = page.getByRole("region", { name: "Configured coil terminals" });
  await expect(summary).toContainText("IN L0, X 0 mm");
  await expect(summary).toContainText("OUT L1, X 2 mm");
});

async function openImport(page: Page) {
  await gotoDesignApp(page);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "importCad" })));
  const dialog = page.getByRole("dialog", { name: "Import CAD", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /Choose DXF/ }).click();
  await expect(dialog.getByLabel("Coil for source layer L0_A")).toHaveValue("A");
  return dialog;
}

test("source-layer assignments preserve coil visibility and import simplification is reversible", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const summary = dialog.getByText(/\d+ line\(s\),/);
  await expect(summary).toContainText("4 line(s)");
  await expect(dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" })).not.toBeChecked();
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
  const preview = dialog.locator('svg[aria-hidden="true"]');
  expect(await preview.locator("path").evaluateAll(paths => new Set(paths.map(p => p.getAttribute("stroke"))).size)).toBe(2);
  await dialog.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
  await expect(preview.locator("path")).toHaveCount(2);
  await dialog.getByRole("checkbox", { name: "Coil B", exact: true }).check();
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).check();
  await expect(summary).toContainText("2 line(s)");
  await page.screenshot({ path: testInfo.outputPath("cad-layer-assignments.png") });
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).uncheck();
  await expect(summary).toContainText("4 line(s)");
  await dialog.getByLabel("Coil for source layer L0_B").fill("");
  await expect(dialog.getByRole("alert").filter({ hasText: "coil name" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toHaveCount(0);
  await dialog.getByLabel("Coil for source layer L0_B").fill("B");
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toBeVisible();
});

test("imported motor preview simplifies saved geometry and supports undo beside Measure", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status")).toContainText("2 line(s) merged");
  await page.screenshot({ path: testInfo.outputPath("cad-simplify-toolbar.png") });
  await tools.getByRole("button", { name: "Undo simplify" }).click();
  await expect(tools.getByRole("status")).toContainText("undone");
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status")).toContainText("2 line(s) merged");
});
