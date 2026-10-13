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
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
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

test("source-layer assignments preserve coil visibility and import simplification is reversible", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const summary = dialog.getByText(/\d+ lines,/);
  await expect(summary).toContainText("4 lines");
  await expect(dialog.getByRole("checkbox", { name: "Simplify collinear lines on import" })).not.toBeChecked();
  await dialog.getByLabel("Coil for source layer holes").fill("A");
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
  const preview = dialog.locator('div[role="img"][aria-label="CAD import preview"] > svg');
  expect(await preview.locator("path").evaluateAll(paths => new Set(paths.map(p => p.getAttribute("stroke"))).size)).toBe(2);
  await dialog.getByRole("checkbox", { name: "Coil B", exact: true }).uncheck();
  await expect(preview.locator("path")).toHaveCount(2);
  await dialog.getByRole("checkbox", { name: "Coil B", exact: true }).check();
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
  await expect(dialog.getByRole("checkbox", { name: "Coil holes", exact: true })).toHaveCount(0);
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

test("import selection toggles segments, reassigns coil and layer, and supports undo", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0, true);
  await expect(tools).toContainText("2 selected");
  await clickTrace(page, .5, 0, true);
  await expect(tools).toContainText("1 selected");
  await tools.getByLabel("Assign selected segments to coil").fill("C");
  await tools.getByLabel("Assign selected segments to layer").selectOption("1");
  await tools.getByRole("button", { name: "Assign", exact: true }).click();
  await expect(dialog.getByRole("checkbox", { name: "Coil C", exact: true })).toBeVisible();
  await expect(dialog.getByRole("option", { name: /Segment 2, coil C, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("cad-segment-selection.png") });
  await tools.getByRole("button", { name: "Undo assignment" }).click();
  await expect(dialog.getByRole("checkbox", { name: "Coil C", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("option", { name: /Segment 2, coil A, layer 0/ })).toHaveCount(1);
});

test("chain assignments persist into the motor preview and selection tools work there too", async ({ page }, testInfo) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(tools).toContainText("2 selected");
  await tools.getByLabel("Assign selected segments to coil").fill("D");
  await tools.getByRole("button", { name: "Assign", exact: true }).click();
  await dialog.getByRole("button", { name: "Open with this geometry" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  const modalTools = page.getByRole("group", { name: "Segment selection tools" });
  await modalTools.getByRole("button", { name: "Chain", exact: true }).click();
  await clickTrace(page, .5, 0); await clickTrace(page, 1.5, 0);
  await expect(modalTools).toContainText("2 selected");
  await modalTools.getByLabel("Assign selected segments to coil").fill("E");
  await modalTools.getByLabel("Assign selected segments to layer").selectOption("1");
  await modalTools.getByRole("button", { name: "Assign", exact: true }).click();
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("coil-segment-selection.png") });
  await page.getByRole("button", { name: "Close coil preview" }).click();
  await page.getByRole("button", { name: "Expand coil preview" }).click();
  await page.getByRole("group", { name: "Segment selection tools" }).getByRole("button", { name: "Select", exact: true }).click();
  await expect(page.getByRole("option", { name: /Segment 1, coil E, layer 1/ })).toHaveCount(1);
});

test("box selection supports crossing, contained, add and remove without moving the preview", async ({ page }) => {
  const dialog = await openImport(page);
  const tools = dialog.getByRole("group", { name: "Segment selection tools" });
  await tools.getByRole("button", { name: "Box", exact: true }).click();
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
  await tools.getByLabel("Assign selected segments to coil").fill("C");
  await tools.getByRole("button", { name: "Assign", exact: true }).click();
  await dialog.getByLabel("Trace width (mm)", { exact: true }).fill("0.5");
  await expect(dialog.getByRole("button", { name: "Reimport", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expect(dialog.getByRole("checkbox", { name: "Coil C", exact: true })).toBeVisible();
  await page.evaluate(() => { (window as any).__cadConfirmResult = true; });
  await dialog.getByRole("button", { name: "Reimport", exact: true }).click();
  await expect(dialog.getByRole("checkbox", { name: "Coil C", exact: true })).toHaveCount(0);
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
