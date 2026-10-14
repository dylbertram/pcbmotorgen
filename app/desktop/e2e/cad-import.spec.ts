import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

// Exercise the real dialog, store and preview with a deterministic IPC boundary.
// Parsing and coil assignments themselves are covered by Rust DXF fixtures.
test.beforeEach(async ({ page }) => {
  await page.route(/\/@tauri-apps_plugin-dialog\.js(?:\?.*)?$/, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace(/async function confirm\(message2, options\) \{[\s\S]*?\n\}/, "async function confirm() { return window.__cadConfirmResult ?? false; }");
    await route.fulfill({ response, body });
  });
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
          vias: window.__cadNoVias ? [] : [{ position: { x: 2, y: 0 }, from_layer: 0, to_layer: 1, net: source_layer_coils.holes }],
        },
      }};
    }`);
    body = body.replace(/export async function editableCoilGeometry\([\s\S]*?\n\}/, "export async function editableCoilGeometry() { return (await importCadDxf('', 1, .05, .4, 2, 1.6)).geometry; }");
    await route.fulfill({ response, body });
  });
});

async function openTerminalTool(page: Page, { layered = false } = {}) {
  await page.addInitScript(({ layered }) => { (window as any).__cadNoVias = !layered; (window as any).__cadLayered = layered; }, { layered });
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  return { command, tools };
}

test("terminal defaults need only confirmation, overrides preserve the other end, and labels survive simplify", async ({ page }, testInfo) => {
  const { command, tools } = await openTerminalTool(page);
  await expect(command.getByRole("status")).toContainText("Open ends selected");
  await expect(command).toContainText("IN");
  await expect(command).toContainText("X 2 mm");
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await page.getByRole("button", { name: "Change IN for coil A", exact: true }).click();
  const input = page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true });
  await expect(command.getByRole("status")).toContainText("Choose IN");
  const box = (await input.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.up();
  await expect(command.getByRole("status")).toContainText("Choose IN");
  await input.click();
  await expect(command.getByRole("status")).toContainText("Review IN and OUT");
  await command.getByRole("button", { name: "Change OUT", exact: true }).click();
  await input.click();
  await expect(command.getByRole("alert")).toContainText("must be different");
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Review IN and OUT");
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Simplify lines", exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("coil-terminal-review.png") });
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const summary = page.getByRole("region", { name: "Configured coil terminals" });
  await expect(summary).toContainText("IN L0, X 0 mm");
  await expect(summary).toContainText("OUT L0, X 2 mm");
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("OUT L0, X 2 mm");
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(summary).toContainText("IN L0, X 0 mm");
});

test("terminal drafts support Flip, keeping current points, Cancel, Escape and switching to Measure", async ({ page }) => {
  const { command, tools } = await openTerminalTool(page);
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await expect(page.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await command.getByRole("button", { name: "Change IN", exact: true }).click();
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeEnabled();
  await command.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(command).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(command).toHaveCount(0);
  await expect(tools).toBeVisible();
  await tools.getByRole("button", { name: "Set coil terminals", exact: true }).click();
  await tools.getByRole("button", { name: "Toggle measure tool" }).click();
  await expect(command).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toHaveCount(0);
});

test("overlapping endpoints are disambiguated by copper layer and support keyboard selection", async ({ page }) => {
  const { command } = await openTerminalTool(page, { layered: true });
  await expect(command.getByRole("status")).toContainText("Open ends selected");
  await expect(page.getByRole("img", { name: "Coil A OUT, L1, X 0 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await command.getByRole("button", { name: "Change OUT", exact: true }).click();
  await command.getByLabel("Copper layer for terminal selection").selectOption("1");
  await expect(page.getByRole("button", { name: /Endpoint coil A, L0/ })).toHaveCount(0);
  const output = page.getByRole("button", { name: "Endpoint coil A, L1, X 2 mm, Y 0 mm", exact: true });
  await output.focus(); await page.keyboard.press("Enter");
  await expect(command.getByRole("status")).toContainText("Review IN and OUT");
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const summary = page.getByRole("region", { name: "Configured coil terminals" });
  await expect(summary).toContainText("IN L0, X 0 mm");
  await expect(summary).toContainText("OUT L1, X 2 mm");
});

test("ambiguous linked coils require manual picks instead of unsafe defaults", async ({ page }) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await page.getByRole("toolbar", { name: "Coil preview tools" }).getByRole("button", { name: "Set coil terminals", exact: true }).click();
  const command = page.getByRole("region", { name: "Set coil terminals", exact: true });
  await expect(command).toContainText("No clear pair of open ends");
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 0 mm, Y 0 mm", exact: true }).click();
  await page.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(page.getByRole("region", { name: "Configured coil terminals" })).toContainText("IN L0, X 0 mm");
});

test("apply and next configures multiple coils without reopening, and saved terminals flip in one click", async ({ page }, testInfo) => {
  const { command } = await openTerminalTool(page);
  const modal = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await command.getByRole("button", { name: "Apply & next", exact: true }).click();
  await expect(command.getByLabel("Coil for terminal selection")).toHaveValue("B");
  await expect(command.getByRole("status")).toContainText("Open ends selected");
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  const summary = page.getByRole("region", { name: "Configured coil terminals" });
  await expect(summary).toContainText("Coil A"); await expect(summary).toContainText("Coil B");
  await summary.getByRole("button", { name: "Flip coil A terminals", exact: true }).click();
  await expect(modal.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await summary.getByRole("button", { name: "Edit coil A terminals", exact: true }).click();
  await expect(command.getByRole("status")).toContainText("Saved endpoints selected");
  await expect(page.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm, preview", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("coil-terminal-defaults-and-flip.png") });
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await command.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(modal.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(modal.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
});

test("changing a terminal keeps the inspection zoom and offers keyboard-accessible overrides on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { command } = await openTerminalTool(page);
  const modal = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await modal.getByRole("button", { name: "Zoom in", exact: true }).click();
  await command.getByRole("button", { name: "Change OUT", exact: true }).click();
  await expect(modal.getByRole("button", { name: "Reset zoom", exact: true })).toHaveText("1.5×");
  await command.getByRole("button", { name: "Keep current points", exact: true }).click();
  await command.getByRole("button", { name: "Flip", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(command.getByRole("button", { name: "Apply terminals", exact: true })).toBeEnabled();
  const tips = await command.locator("[title]").evaluateAll((elements) => elements.map((e) => e.getAttribute("title")!));
  expect(tips.every((tip) => tip.length <= 140)).toBe(true);
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

async function expectImportCoil(page: Page, name: string, present: boolean) {
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await expect(panel.getByRole("checkbox", { name: `Coil ${name}`, exact: true })).toHaveCount(present ? 1 : 0);
  await panel.getByRole("button", { name: "Close layers panel" }).click();
}

test("shared editing tools measure and edit CAD drafts, then keep those edits in motor preview", async ({ page }, testInfo) => {
  await page.addInitScript(() => { (window as any).__cadNoVias = true; });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("toolbar", { name: "CAD import tools" });
  const summary = dialog.getByText(/\d+ lines,/);
  const toolNames = await tools.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getAttribute("aria-label")).filter(Boolean));
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("2 lines");
  await tools.getByRole("button", { name: "Undo simplify", exact: true }).click();
  await expect(summary).toContainText("4 lines");
  await tools.getByRole("button", { name: "Toggle measure tool" }).click();
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  for (const x of [0, 2]) {
    const point = await frame.locator(":scope > svg > g").evaluate((group, x) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      const point = new DOMPoint(x, 0).matrixTransform(matrix);
      return { x: point.x, y: point.y };
    }, x);
    await page.mouse.click(point.x, point.y);
  }
  await expect(tools.getByRole("status").filter({ hasText: "click again" })).toContainText("2.00 mm");
  await expect(dialog.getByRole("img", { name: "Measurement 2.00 mm", exact: true })).toBeVisible();
  await tools.getByRole("button", { name: "Set coil terminals" }).click();
  await expect(tools.getByRole("button", { name: "Toggle measure tool" })).toHaveAttribute("aria-pressed", "false");
  const command = dialog.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Change OUT", exact: true }).click();
  const endpoint = dialog.getByRole("button", { name: "Endpoint coil A, L0, X 2 mm, Y 0 mm", exact: true });
  await endpoint.focus();
  await page.keyboard.press("Enter");
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(dialog.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(summary).toContainText("2 lines");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const motor = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const motorTools = motor.getByRole("toolbar", { name: "Coil preview tools" });
  expect(await motorTools.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getAttribute("aria-label")).filter(Boolean))).toEqual(toolNames);
  await expect(motor.getByRole("img", { name: "Coil A IN, L0, X 2 mm, Y 0 mm", exact: true })).toBeVisible();
  await motorTools.getByRole("button", { name: "Toggle measure tool" }).click();
  for (const x of [0, 2]) {
    const point = await motor.locator('[aria-label="Segment selection preview"] svg > g').evaluate((group, x) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      const point = new DOMPoint(x, 0).matrixTransform(matrix);
      return { x: point.x, y: point.y };
    }, x);
    await page.mouse.click(point.x, point.y);
  }
  await expect(motorTools.getByRole("status").filter({ hasText: "click again" })).toContainText("2.00 mm");
  await expect(motor.getByRole("img", { name: "Measurement 2.00 mm", exact: true })).toBeVisible();
  await motorTools.getByRole("button", { name: "Toggle measure tool" }).click();
  await motor.getByRole("button", { name: "Flip coil A terminals" }).click();
  await expect(motor.getByRole("img", { name: "Coil A IN, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await motor.getByRole("button", { name: "Layers", exact: true }).click();
  const layers = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await layers.getByRole("checkbox", { name: "Coil A", exact: true }).uncheck();
  await expect(motor.getByRole("img", { name: /Coil A IN/ })).toHaveCount(0);
  await layers.getByRole("checkbox", { name: "Coil A", exact: true }).check();
  await layers.getByRole("button", { name: "Close layers panel" }).click();
  await motor.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await expect(motor.getByRole("img", { name: "Coil A IN, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("shared-motor-editor.png") });
});

test("CAD terminal editing works on mobile and changing tools cancels unapplied drafts", async ({ page }) => {
  await page.addInitScript(() => { (window as any).__cadNoVias = true; });
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("toolbar", { name: "CAD import tools" });
  await tools.getByRole("button", { name: "Set coil terminals" }).click();
  const command = dialog.getByRole("region", { name: "Set coil terminals", exact: true });
  await command.getByRole("button", { name: "Flip", exact: true }).click();
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await expect(command).toHaveCount(0);
  await tools.getByRole("button", { name: "Set coil terminals" }).click();
  await command.getByRole("button", { name: "Apply terminals", exact: true }).click();
  await expect(dialog.getByRole("img", { name: "Coil A IN, L0, X 0 mm, Y 0 mm", exact: true })).toBeVisible();
  await tools.getByRole("button", { name: "Set coil terminals" }).click();
  await page.keyboard.press("Escape");
  await expect(command).toHaveCount(0);
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate(element => element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("CAD layer popover toggles visibility and display without resizing the viewer", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const trigger = dialog.getByRole("button", { name: "Layers", exact: true });
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  const traces = frame.locator(":scope > svg path");
  const vias = frame.locator(":scope > svg circle");
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const before = await frame.boundingBox();
    const rail = dialog.getByRole("toolbar", { name: "Preview side tools" });
    await expect(rail).toHaveAttribute("aria-orientation", "vertical");
    const railBounds = (await rail.boundingBox())!;
    expect(railBounds.x).toBeCloseTo(before!.x + before!.width, 0);
    expect(railBounds.y).toBeCloseTo(before!.y, 0);
    await expect(panel).toBeHidden();
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(panel).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(await frame.boundingBox()).toEqual(before);
    await expect(panel.getByRole("checkbox", { name: "Show phase waveform" })).toHaveCount(0);
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).uncheck();
    await expect(traces).toHaveCount(0);
    await panel.getByRole("checkbox", { name: "Show layer 0", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
    await expect(traces).toHaveCount(2);
    await panel.getByRole("radio", { name: "Centerlines", exact: true }).check();
    await expect.poll(() => traces.first().evaluate((path) => {
      const matrix = (path as SVGGraphicsElement).getScreenCTM()!;
      return Number(getComputedStyle(path).strokeWidth.replace("px", "")) * Math.abs(matrix.a);
    })).toBeCloseTo(1, 2);
    await panel.getByRole("checkbox", { name: "Show vias", exact: true }).uncheck();
    await expect(vias).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`cad-layers-${viewport.width}.png`) });
    const bounds = (await panel.boundingBox())!;
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(railBounds.x + 4);
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();
    await expect(dialog).toBeVisible();
    await trigger.click();
    await expect(panel.getByRole("checkbox", { name: "Coil B", exact: true })).not.toBeChecked();
    await expect(panel.getByRole("radio", { name: "Centerlines", exact: true })).toBeChecked();
    await panel.getByRole("checkbox", { name: "Coil B", exact: true }).check();
    await panel.getByRole("checkbox", { name: "Show vias", exact: true }).check();
    await panel.getByRole("radio", { name: "Traces", exact: true }).check();
    await panel.getByRole("button", { name: "Close layers panel" }).click();
    await expect(panel).toBeHidden();
    await trigger.click();
    await dialog.getByRole("heading", { name: "Import CAD", exact: true }).click();
    await expect(panel).toBeHidden();
    await trigger.click();
    await trigger.click();
    await expect(panel).toBeHidden();
  }
});

test("CAD import viewer fills its container after resizing without distorting traces", async ({ page }) => {
  const dialog = await openImport(page);
  const frame = dialog.getByRole("img", { name: "CAD import preview", exact: true });
  for (const viewport of [{ width: 1280, height: 800 }, { width: 1600, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect.poll(() => frame.evaluate((element) => {
      const parent = element.parentElement!;
      return Math.abs(element.clientHeight - parent.clientHeight);
    })).toBeLessThanOrEqual(1);
    await expect.poll(() => frame.locator(":scope > svg > g").evaluate((group) => {
      const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
      return Math.abs(Math.abs(matrix.a) - Math.abs(matrix.d));
    })).toBeLessThan(0.01);
    const tools = dialog.getByRole("group", { name: "Segment selection tools" });
    await tools.getByRole("button", { name: "Select", exact: true }).click();
    await clickTrace(page, .5, 0);
    await expect(tools).toContainText("1 selected");
    await page.keyboard.press("Escape");
    expect(await dialog.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
  }
});

test("source-layer assignments preserve coil visibility and import simplification is reversible", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const summary = dialog.getByText(/\d+ lines,/);
  await expect(summary).toContainText("4 lines");
  await expect(dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" })).not.toBeChecked();
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  const preview = dialog.locator('div[role="img"][aria-label="CAD import preview"] > svg');
  expect(await preview.locator("path").evaluateAll(paths => new Set(paths.map(p => p.getAttribute("stroke"))).size)).toBe(2);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await panel.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
  await expect(preview.locator("path")).toHaveCount(2);
  await panel.getByRole("checkbox", { name: "Coil B", exact: true }).check();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).check();
  await expect(summary).toContainText("2 lines");
  await page.screenshot({ path: testInfo.outputPath("cad-layer-assignments.png") });
  await dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" }).uncheck();
  await expect(summary).toContainText("4 lines");
  await dialog.getByLabel("Coil for source layer L0_B").fill("");
  await expect(dialog.getByRole("alert").filter({ hasText: "coil name" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toHaveCount(0);
  await dialog.getByLabel("Coil for source layer L0_B").fill("B");
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toBeVisible();
});

test("imported motor preview simplifies saved geometry and supports undo beside Measure", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expectImportCoil(page, "holes", false);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status").filter({ hasText: "merged" })).toContainText("2 line(s) merged");
  await page.screenshot({ path: testInfo.outputPath("cad-simplify-toolbar.png") });
  await tools.getByRole("button", { name: "Undo simplify" }).click();
  await expect(tools.getByRole("status").filter({ hasText: "undone" })).toBeVisible();
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await expect(tools.getByRole("status").filter({ hasText: "merged" })).toContainText("2 line(s) merged");
});

async function tracePoint(page: Page, x: number, y: number) {
  return await page.getByRole("listbox", { name: "Segment selection preview" }).locator("svg > g").evaluate((group, point) => {
    const matrix = (group as SVGGraphicsElement).getScreenCTM()!;
    const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix);
    return { x: screen.x, y: screen.y };
  }, { x, y });
}

async function clickTrace(page: Page, x: number, y: number, shift = false) {
  const point = await tracePoint(page, x, y);
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.click(point.x, point.y);
  if (shift) await page.keyboard.up("Shift");
}

async function dragBox(page: Page, a: [number, number], b: [number, number]) {
  const start = await tracePoint(page, ...a), end = await tracePoint(page, ...b);
  await page.mouse.move(start.x, start.y); await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 8 }); await page.mouse.up();
}

async function newCoil(page: Page, name: string) {
  await page.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "New coil…", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Change to a new coil", exact: true });
  await dialog.getByLabel("Coil name").fill(name);
  await dialog.getByRole("button", { name: "Move selection", exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function changeLayer(page: Page, layer: number) {
  await page.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await page.getByRole("menuitem", { name: `Layer ${layer}`, exact: true }).click();
}

test("selection context menu changes coil or layer separately and preserves selection on dismissal", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await expect(tools.getByPlaceholder("Keep coil")).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Selection actions" })).toBeDisabled();
  await clickTrace(page, .5, 0);
  const point = await tracePoint(page, .5, 0);
  await page.mouse.click(point.x, point.y, { button: "right" });
  await expect(page.getByRole("menuitem", { name: "Change to coil…", exact: true })).toBeVisible();
  await expect(page.getByRole("menu", { name: "Selection actions", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(tools).toContainText("1 selected");
  await expect(dialog).toBeVisible();
  await page.mouse.click(point.x, point.y, { button: "right" });
  await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "B", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 0/ })).toHaveCount(1);
  await expect(tools).toContainText("1 selected");
  await page.mouse.click(point.x, point.y, { button: "right" });
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await page.getByRole("menuitem", { name: "Layer 2", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  await tools.getByRole("button", { name: "Undo assignment" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 0/ })).toHaveCount(1);
});

test("outside clicks dismiss context menus and submenus while selecting in CAD and motor viewers", async ({ page }) => {
  const cad = await openImport(page);
  for (const viewer of ["cad", "motor"]) {
    if (viewer === "motor") {
      await cad.getByRole("button", { name: "Open with this geometry" }).click();
      await page.getByRole("button", { name: "Expand coil preview" }).click();
    }
    const dialog = viewer === "cad" ? cad : page.getByRole("dialog", { name: "Coil Preview", exact: true });
    const tools = dialog.getByRole("group", { name: "Segment selection tools" });
    await clickTrace(page, .5, 0);
    const frame = dialog.getByRole("img", { name: viewer === "cad" ? "CAD import preview" : "Coil preview — expanded", exact: true });
    const bounds = (await frame.boundingBox())!;
    const menu = page.getByRole("menu", { name: "Selection actions", exact: true });
    const openMenu = async () => {
      await page.mouse.click(bounds.x + bounds.width * .8, bounds.y + bounds.height * .15, { button: "right" });
      await expect(menu).toBeVisible();
    };
    await openMenu();
    await dialog.getByRole("heading", { name: viewer === "cad" ? "Import CAD" : "Coil Preview", exact: true }).click();
    await expect(menu).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect(tools).toContainText("1 selected");
    await openMenu();
    await page.getByRole("menuitem", { name: "Change to coil…", exact: true }).hover();
    const submenu = page.getByRole("menu", { name: "Change to coil", exact: true });
    await expect(submenu).toBeVisible();
    await clickTrace(page, 1.5, 0);
    await expect(menu).toBeHidden();
    await expect(submenu).toBeHidden();
    await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
    await openMenu();
    await dragBox(page, [-.1, -.1], [2.1, .1]);
    await expect(menu).toBeHidden();
    await expect(tools).toContainText("2 selected");
  }
});

test("nested layer destinations support Move to, direct clicks, and independent visibility", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  const phaseB = panel.getByRole("group", { name: "Phase B", exact: true });
  await expect(phaseB.getByRole("button", { name: "Move selection to B, layer 1", exact: true })).toBeDisabled();
  await expect(phaseB.getByRole("button", { name: "Move selection to B, layer 2", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await clickTrace(page, .5, 0);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await phaseB.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click({ button: "right" });
  await page.getByRole("menuitem", { name: "Move to", exact: true }).click();
  await expect(panel).toBeVisible();
  await expect(tools).toContainText("1 selected");
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  await phaseB.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).uncheck();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(0);
  await expect(dialog.getByRole("option", { name: /coil A, layer 0/ })).toHaveCount(1);
  await phaseB.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await expect(phaseB.getByRole("checkbox", { name: "Show B, layer 2", exact: true })).toBeChecked();
  await panel.getByRole("button", { name: "Move selection to Phase A", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil A, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("nested-coil-layers.png") });
});

test("outside clicks dismiss destination and toolbar menus without consuming the next action", async ({ page }) => {
  const dialog = await openImport(page);
  await clickTrace(page, .5, 0);
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "CAD import layers", exact: true });
  await panel.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click({ button: "right" });
  const destinationMenu = page.getByRole("menu", { name: "Move selection", exact: true });
  await expect(destinationMenu).toBeVisible();
  const visibility = panel.getByRole("checkbox", { name: "Show B, layer 1", exact: true });
  await visibility.uncheck();
  await expect(destinationMenu).toBeHidden();
  await expect(visibility).not.toBeChecked();
  await expect(panel).toBeVisible();
  await expect(dialog.getByRole("option", { name: /Segment 1, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await dialog.getByRole("button", { name: "Selection actions", exact: true }).click();
  await page.getByRole("menuitem", { name: "Change to layer…", exact: true }).hover();
  await expect(page.getByRole("menu", { name: "Change to layer", exact: true })).toBeVisible();
  await clickTrace(page, 1.5, 0);
  await expect(page.getByRole("menu", { name: "Selection actions", exact: true })).toBeHidden();
  await expect(page.getByRole("menu", { name: "Change to layer", exact: true })).toBeHidden();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveAttribute("aria-selected", "true");
});

test("nested motor layers move selections on mobile and toggle only their own coil/layer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const motor = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  await clickTrace(page, .5, 0);
  await motor.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "Coil preview layers", exact: true });
  await panel.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await expect(motor.getByRole("option", { name: /Segment 1, coil B, layer 1/ })).toHaveCount(1);
  const canvas = motor.locator("canvas");
  const overlay = motor.getByRole("listbox", { name: "Segment selection preview" }).locator("svg > g");
  const camera = (await overlay.getAttribute("transform"))!;
  const before = Number(await canvas.getAttribute("data-segments"));
  await panel.getByRole("checkbox", { name: "Show B, layer 2", exact: true }).uncheck();
  await expect.poll(async () => Number(await canvas.getAttribute("data-segments"))).toBeLessThan(before);
  await expect(overlay).toHaveAttribute("transform", camera);
  await expect(motor.getByRole("option", { name: /coil A, layer 0/ })).toHaveCount(1);
  await panel.getByRole("button", { name: "Close layers panel" }).click();
  await motor.getByRole("button", { name: "Undo assignment" }).click();
  await expect(motor.getByRole("option", { name: /Segment 1, coil A, layer 0/ })).toHaveCount(1);
});

test("assignment menus are keyboard accessible and cancelling a new coil preserves geometry", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await clickTrace(page, .5, 0);
  for (const cancel of [true, false]) {
    await tools.getByRole("button", { name: "Selection actions" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("menuitem", { name: "Change to coil…", exact: true })).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("menuitem", { name: "A", exact: true })).toBeFocused();
    await page.getByRole("menuitem", { name: "New coil…", exact: true }).focus();
    await expect(page.getByRole("menuitem", { name: "New coil…", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    const nameDialog = page.getByRole("dialog", { name: "Change to a new coil", exact: true });
    await expect(nameDialog.getByRole("button", { name: "Move selection" })).toBeDisabled();
    await nameDialog.getByLabel("Coil name").fill("  C  ");
    await page.keyboard.press(cancel ? "Escape" : "Enter");
    await expect(nameDialog).toBeHidden();
    await expect(tools).toContainText("1 selected");
    await expect(dialog.getByRole("option", { name: new RegExp(`Segment 1, coil ${cancel ? 'A' : 'C'}, layer 0`) })).toHaveCount(1);
  }
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "CAD import layers" }).getByRole("group", { name: "Phase C", exact: true }).getByRole("button", { name: "Move selection to C, layer 2", exact: true })).toBeVisible();
});

test("import selection toggles segments, reassigns coil and layer, and supports undo", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0, true);
  await expect(tools).toContainText("2 selected");
  await clickTrace(page, .5, 0, true);
  await expect(tools).toContainText("1 selected");
  await dialog.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByRole("button", { name: "Move selection to B, layer 2", exact: true }).click();
  await page.getByRole("button", { name: "Close layers panel" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil B, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("cad-segment-selection.png") });
  await tools.getByRole("button", { name: "Undo assignment" }).click();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveCount(1);
});

test("chain assignments persist into the motor preview and selection tools work there too", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(tools).toContainText("2 selected");
  await newCoil(page, "D");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const modalTools = page.getByRole("group", { name: "Segment selection tools" });
  await modalTools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(modalTools).toContainText("2 selected");
  await newCoil(page, "E");
  await changeLayer(page, 2);
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("coil-segment-selection.png") });
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await page.getByRole("group", { name: "Segment selection tools" }).getByRole("button", { name: "Select", exact: true }).click();
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
});

test("default click and drag selection works in CAD and motor viewers without a box tool", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await expect(tools.getByRole("button", { name: "Box", exact: true })).toHaveCount(0);
  await expect(tools.getByRole("button", { name: "Pan", exact: true })).toHaveCount(0);
  await clickTrace(page, .5, 0);
  await expect(tools).toContainText("1 selected");
  await dragBox(page, [.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("0 selected");
  await dragBox(page, [1.1, -.1], [.1, .1]);
  await expect(tools).toContainText("2 selected");
  await tools.getByRole("button", { name: "Chain", exact: true }).click();
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("1 selected");
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const motor = page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const motorTools = motor.getByRole("group", { name: "Segment selection tools" });
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(motorTools).toContainText("1 selected");
  await newCoil(page, "D");
  await expect(motor.getByRole("option", { name: /Segment 1, coil D/ })).toHaveCount(1);
});

test("touch drag selects, two fingers pan, and three-finger pinch zooms without changing selection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 3 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  const start = await tracePoint(page, -.1, -.1);
  const end = await tracePoint(page, 1.1, .1);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ ...start, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ ...end, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(tools).toContainText("1 selected");
  for (const viewer of ["cad", "motor"]) {
  if (viewer === "motor") {
    await dialog.getByRole("button", { name: "Open with this geometry" }).click();
    await page.getByRole("button", { name: "Expand coil preview" }).click();
  }
  const activeDialog = viewer === "cad" ? dialog : page.getByRole("dialog", { name: "Coil Preview", exact: true });
  const activeTools = activeDialog.getByRole("group", { name: "Segment selection tools" });
  const selected = viewer === "cad" ? "1 selected" : "0 selected";
  const frame = activeDialog.getByRole("img", { name: viewer === "cad" ? "CAD import preview" : "Coil preview — expanded", exact: true });
  const group = activeDialog.locator('[aria-label="Segment selection preview"] svg > g');
  const before = await group.evaluate(g => { const m = (g as SVGGraphicsElement).getScreenCTM()!; return { s: m.a, x: m.e, y: m.f }; });
  const bounds = (await frame.boundingBox())!;
  const points = [
    { id: 1, x: bounds.x + bounds.width * .35, y: bounds.y + bounds.height * .4 },
    { id: 2, x: bounds.x + bounds.width * .6, y: bounds.y + bounds.height * .4 },
  ];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points.slice(0, 1) });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points });
  const panned = points.map(p => ({ ...p, x: p.x + 20, y: p.y + 15 }));
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: panned });
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.e)).toBeCloseTo(before.x + 20, 0);
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.f)).toBeCloseTo(before.y + 15, 0);
  await expect(activeDialog.getByRole("button", { name: "Reset zoom", exact: true })).toHaveText("1×");
  await expect(activeTools).toContainText(selected);
  const triple = [...panned, { id: 3, x: bounds.x + bounds.width * .475 + 20, y: bounds.y + bounds.height * .65 + 15 }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: triple });
  const center = { x: triple.reduce((sum, p) => sum + p.x, 0) / 3, y: triple.reduce((sum, p) => sum + p.y, 0) / 3 };
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: triple.map(p => ({ ...p, x: center.x + 2 * (p.x - center.x), y: center.y + 2 * (p.y - center.y) })) });
  await expect.poll(() => group.evaluate(g => (g as SVGGraphicsElement).getScreenCTM()!.a)).toBeCloseTo(before.s * 2, 0);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(activeTools).toContainText(selected);
  await activeDialog.getByRole("button", { name: "Reset zoom", exact: true }).click();
  const tap = await tracePoint(page, .5, 0);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ ...tap, id: 1 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(activeTools).toContainText("1 selected");
  }
  await cdp.detach();
});

test("box selection supports crossing, contained, add and remove without moving the preview", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await expect(tools.getByRole("button", { name: "Box", exact: true })).toHaveCount(0);
  await tools.getByLabel("Box coverage").selectOption({ label: "Crossing" });
  await dragBox(page, [.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("2 selected");
  await tools.getByLabel("Box coverage").selectOption({ label: "Contained" });
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("1 selected");
  await tools.getByLabel("Box selection action").selectOption("add");
  await dragBox(page, [.9, -.1], [2.1, .1]);
  await expect(tools).toContainText("2 selected");
  await tools.getByLabel("Box selection action").selectOption("remove");
  await dragBox(page, [-.1, -.1], [1.1, .1]);
  await expect(tools).toContainText("1 selected");
  const preview = dialog.getByRole("region", { name: "CAD import preview" });
  const before = await preview.boundingBox();
  await dialog.getByLabel("Import settings").evaluate((element) => element.scrollTo(0, element.scrollHeight));
  expect(await preview.boundingBox()).toEqual(before);
  expect(await dialog.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("keyboard selection and short tooltips work at mobile size", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  for (const name of ["Select", "Chain"]) {
    const button = tools.getByRole("button", { name, exact: true });
    await expect(button.locator("svg")).toHaveAttribute("aria-hidden", "true");
    expect((await button.boundingBox())!.width).toBeLessThanOrEqual(36);
  }
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  const preview = page.getByRole("listbox", { name: "Segment selection preview" });
  await preview.focus(); await page.keyboard.press("ArrowRight"); await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowRight"); await page.keyboard.press("Shift+Enter");
  await expect(tools).toContainText("2 selected");
  await page.keyboard.press("Shift+Enter"); await expect(tools).toContainText("1 selected");
  await page.keyboard.press("Escape"); await expect(tools).toContainText("0 selected");
  const titles = await dialog.locator("[title]").evaluateAll((elements) => elements.map((e) => e.getAttribute("title")!));
  expect(titles.every((title) => title.length <= 140)).toBe(true);
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("reimport waits for confirmation before discarding segment assignments", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await clickTrace(page, .5, 0);
  await newCoil(page, "C");
  await dialog.getByLabel("Trace width (mm)", { exact: true }).fill("0.5");
  await expect(dialog.getByRole("button", { name: "Reimport", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expectImportCoil(page, "C", true);
  await page.evaluate(() => { (window as any).__cadConfirmResult = true; });
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expectImportCoil(page, "C", false);
  await expect(tools).toContainText("0 selected");
  await expect(dialog.getByRole("button", { name: "Open with this geometry" })).toBeVisible();
});

test("generated motor geometry becomes editable only after confirmation", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Edit segments", exact: true }).click();
  await expect(tools.getByRole("button", { name: "Edit segments", exact: true })).toBeEnabled();
  await expect(page.getByRole("group", { name: "Segment selection tools" })).toHaveCount(0);
  await page.evaluate(() => { (window as any).__cadConfirmResult = true; });
  await tools.getByRole("button", { name: "Edit segments", exact: true }).click();
  const selection = page.getByRole("group", { name: "Segment selection tools" });
  await expect(selection.getByRole("button", { name: "Select", exact: true })).toHaveAttribute("aria-pressed", "true");
  await clickTrace(page, .5, 0);
  await expect(selection).toContainText("1 selected");
});

test("routing source shows the imported filename in its trigger and dropdown after edits", async ({ page }) => {
  const dialog = await openImport(page);
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  const source = page.getByRole("button", { name: "Routing source", exact: true });
  await expect(source).toContainText("coil-leads.dxf");
  await source.click();
  await expect(page.getByRole("option", { name: "coil-leads.dxf", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const tools = page.getByRole("toolbar", { name: "Coil preview tools" });
  await tools.getByRole("button", { name: "Simplify lines", exact: true }).click();
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await expect(source).toContainText("coil-leads.dxf");
});
